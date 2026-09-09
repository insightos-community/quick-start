# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("wheel_fetch", Path(__file__).resolve().parents[1] / "scripts/fetch_runtime_wheels.py")
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


class WheelFetchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = b"pinned third party payload"
        self.entry = {"path": "wheels/blinker-1.9.0-py3-none-any.whl",
                      "sha256": hashlib.sha256(self.data).hexdigest(), "size": len(self.data)}
        self.dest = self.root / self.entry["path"]
        self.dest.parent.mkdir()
        self.import_patch = patch.object(fetcher, "install_cached_wheel", side_effect=
            lambda repo, entry, candidate: (repo / entry["path"]).write_bytes(candidate.read_bytes()))
        self.import_patch.start()
        self.addCleanup(self.import_patch.stop)

    def run_fetch(self, mode="auto"):
        with patch.object(fetcher, "inventory", return_value=("revision", [self.entry])), \
             patch.object(fetcher, "git", return_value="revision"):
            fetcher.fetch(self.root, mode)

    def test_valid_cache_does_not_contact_network(self):
        self.dest.write_bytes(self.data)
        with patch.object(fetcher, "download_wheel") as download, patch.object(fetcher.subprocess, "run") as run:
            self.run_fetch()
        download.assert_not_called()
        run.assert_not_called()

    def test_offline_missing_does_not_contact_network(self):
        with patch.object(fetcher.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "Offline cache"):
                self.run_fetch("offline")
        run.assert_not_called()

    def test_modified_file_is_preserved(self):
        self.dest.write_bytes(b"user modified data")
        with self.assertRaisesRegex(ValueError, "preserved"):
            self.run_fetch()
        self.assertEqual(self.dest.read_bytes(), b"user modified data")

    def test_pointer_can_be_replaced_by_verified_download(self):
        self.dest.write_bytes(fetcher.POINTER)
        def download(entry, destination, index):
            destination.write_bytes(self.data)
            return True
        with patch.object(fetcher, "download_wheel", side_effect=download), patch.object(fetcher.subprocess, "run") as run:
            self.run_fetch()
        run.assert_not_called()

    def test_failed_index_falls_back_to_exact_lfs_paths(self):
        def lfs(cmd, **kwargs):
            self.assertEqual(cmd[-4:], ["-I", self.entry["path"], "-X", ""])
            self.dest.write_bytes(self.data)
        with patch.object(fetcher, "download_wheel", return_value=False), \
             patch.object(fetcher.subprocess, "run", side_effect=lfs):
            self.run_fetch()

    def test_lfs_mode_does_not_call_pip(self):
        with patch.object(fetcher, "download_wheel") as download, \
             patch.object(fetcher.subprocess, "run", side_effect=lambda *a, **kw: self.dest.write_bytes(self.data)):
            self.run_fetch("lfs")
        download.assert_not_called()

    def test_final_hash_mismatch_fails(self):
        with patch.object(fetcher, "download_wheel", return_value=False), \
             patch.object(fetcher.subprocess, "run"):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.run_fetch()

    def test_special_and_source_built_packages(self):
        for name in ("cmeel_tinyxml2_9-9.0.0-0-py3-none-manylinux_2_28_x86_64.whl",
                     "cmeel_urdfdom-4.0.0-2-py3-none-manylinux_2_28_x86_64.whl"):
            self.assertIsNone(fetcher.wheel_spec(name))
        for name in ("AbilityFramework", "wheels/ability_py-0.4.0-py3-none-any.whl", "ability_scaffold-1.2.0-py3-none-any.whl"):
            self.assertTrue(fetcher.source_built(name))

    def test_pip_is_download_only_hash_locked_and_credential_safe(self):
        def pip(cmd, **kwargs):
            self.assertIn("download", cmd)
            self.assertNotIn("install", cmd)
            self.assertIn("--require-hashes", cmd)
            self.assertIn("--no-deps", cmd)
            self.assertIn("--only-binary=:all:", cmd)
            self.assertNotIn("secret", " ".join(cmd))
            self.assertEqual(kwargs["env"]["PIP_INDEX_URL"], "https://user:secret@example.test/simple")
            self.assertNotIn("PIP_EXTRA_INDEX_URL", kwargs["env"])
            lock = Path(cmd[cmd.index("-r") + 1])
            self.assertIn(self.entry["sha256"], lock.read_text())
            (lock.parent / self.dest.name).write_bytes(self.data)
            return subprocess.CompletedProcess(cmd, 0, "")
        with patch.object(fetcher.subprocess, "run", side_effect=pip):
            self.assertTrue(fetcher.download_wheel(self.entry, self.dest, "https://user:secret@example.test/simple"))
        self.assertEqual(self.dest.read_bytes(), self.data)

    def test_download_hash_mismatch_never_replaces_pointer(self):
        self.dest.write_bytes(fetcher.POINTER)
        def pip(cmd, **kwargs):
            (Path(cmd[-1]) / self.dest.name).write_bytes(b"wrong bytes")
            return subprocess.CompletedProcess(cmd, 0, "")
        with patch.object(fetcher.subprocess, "run", side_effect=pip):
            self.assertFalse(fetcher.download_wheel(self.entry, self.dest, ""))
        self.assertEqual(self.dest.read_bytes(), fetcher.POINTER)

    def test_download_timeout_falls_back(self):
        with patch.object(fetcher.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 90)):
            self.assertFalse(fetcher.download_wheel(self.entry, self.dest, ""))

    def test_symlink_escape_rejected(self):
        self.dest.symlink_to("/tmp/outside-wheel")
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.run_fetch()

    def test_revision_change_rejected(self):
        self.dest.write_bytes(self.data)
        with patch.object(fetcher, "inventory", return_value=("revision", [self.entry])), \
             patch.object(fetcher, "git", return_value="other"):
            with self.assertRaisesRegex(ValueError, "revision changed"):
                fetcher.fetch(self.root)

    def test_index_circuit_breaker(self):
        entries = [{**self.entry, "path": f"wheels/pkg{i}-1.0-py3-none-any.whl"} for i in range(5)]
        def lfs(*args, **kwargs):
            for e in entries:
                (self.root / e["path"]).write_bytes(self.data)
        with patch.object(fetcher, "inventory", return_value=("revision", entries)), \
             patch.object(fetcher, "git", return_value="revision"), \
             patch.object(fetcher, "download_wheel", return_value=False) as download, \
             patch.object(fetcher.subprocess, "run", side_effect=lfs):
            fetcher.fetch(self.root)
        self.assertEqual(download.call_count, 3)

    def test_real_mixed_download_preserves_git_index_and_worktree(self):
        self.import_patch.stop()
        self.data *= 4096  # Exceed the clean filter's initial sniff buffer.
        def git(repo, *args):
            return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
        source = self.root / "source"
        source.mkdir()
        git(source, "init", "-q", "-b", "main")
        git(source, "lfs", "install", "--local")
        (source / ".gitattributes").write_text("*.whl filter=lfs diff=lfs merge=lfs -text\n")
        normal = "blinker-1.9.0-py3-none-any.whl"
        special = "cmeel_tinyxml2_9-9.0.0-0-py3-none-manylinux_2_28_x86_64.whl"
        for name in (normal, special):
            (source / name).write_bytes(self.data)
        (source / "README.md").write_text("original\n")
        git(source, "add", ".")
        git(source, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "test")
        clone = self.root / "clone"
        subprocess.run(["git", "clone", "-q", str(source), str(clone)], check=True,
                       env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
        (clone / "README.md").write_text("staged user change\n")
        git(clone, "add", "README.md")
        (clone / "README.md").write_text("unstaged user change\n")
        index_before = git(clone, "ls-files", "--stage")
        def download(entry, dest, index):
            dest.write_bytes(self.data)
            return True
        with patch.object(fetcher, "download_wheel", side_effect=download):
            fetcher.fetch(clone)
        self.assertEqual(git(clone, "ls-files", "--stage"), index_before)
        self.assertEqual(git(clone, "status", "--porcelain"), "MM README.md")


if __name__ == "__main__":
    unittest.main()
