# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import repo_versions as rv
import semantic_installer as installer


def git(*args):
    return subprocess.run(
        ["git", *map(str, args)], check=True, capture_output=True, text=True
    ).stdout.strip()


class ManifestRemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.workspace = self.root / "workspace"
        self.seed = self.root / "seed"
        git("init", "--bare", self.remote)
        git("init", "-b", "main", self.seed)
        git("-C", self.seed, "-c", "user.name=Test", "-c", "user.email=test@example.test",
            "commit", "--allow-empty", "-m", "initial")
        git("-C", self.seed, "-c", "user.name=Test", "-c", "user.email=test@example.test",
            "tag", "-a", "v1.0", "-m", "release")
        git("-C", self.seed, "tag", "main")
        git("-C", self.seed, "push", self.remote, "refs/heads/main", "--tags")
        git("-C", self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.local = "custom/nested-repo"
        self.entry = {"url": str(self.remote), "ref": "v1.0", "commit": "", "note": "keep"}
        self.data = {"version": 1, "repos": {self.local: dict(self.entry)}}
        self.config = self.root / "manifest.json"
        rv.save_manifest(self.config, self.data)

    def tui(self):
        tui = rv.TUI(str(self.config), str(self.workspace))
        self.addCleanup(tui.close)
        return tui

    def clone(self):
        path = self.workspace / self.local
        path.parent.mkdir(parents=True)
        git("clone", self.remote, path)
        return path

    def test_queries_uncloned_manifest_url_and_keeps_same_name_tag(self):
        refs, error = rv.remote_refs(self.workspace / self.local, self.entry)
        self.assertEqual(error, "")
        self.assertEqual(refs, [("branch", "main"), ("tag", "main"), ("tag", "v1.0")])
        self.assertFalse(self.workspace.exists())

    def test_empty_remote_is_distinct_from_failure(self):
        empty = self.root / "empty.git"
        git("init", "--bare", empty)
        self.assertEqual(rv.remote_refs(self.workspace, {"url": str(empty)}), ([], ""))
        refs, error = rv.remote_refs(self.workspace, {"url": str(self.root / "absent.git")})
        self.assertEqual(refs, [])
        self.assertIn("fatal", error)
        self.assertIn("未配置 url", rv.remote_refs(self.workspace)[1])

    def test_old_manifest_and_worktree_origin_fallback(self):
        path = self.clone()
        refs, error = rv.remote_refs(path)
        self.assertEqual(error, "")
        self.assertIn(("branch", "main"), refs)
        worktree = self.root / "worktree"
        git("-C", path, "worktree", "add", "--detach", worktree, "HEAD")
        self.assertTrue((worktree / ".git").is_file())
        self.assertEqual(rv.remote_url(worktree), str(self.remote))
        self.assertNotEqual(rv.current_ref(worktree)[0], "missing")

    def test_url_overrides_local_origin(self):
        path = self.clone()
        git("-C", path, "remote", "set-url", "origin", str(self.root / "absent.git"))
        self.assertEqual(rv.remote_refs(path, self.entry)[1], "")
        self.assertTrue(rv.remote_refs(path)[1])

    def test_discovery_uses_custom_manifest_without_checkout(self):
        tui = self.tui()
        tui.refresh_states()
        self.assertEqual(tui.repo_names, [self.local])
        self.assertNotEqual(tui.remotes[self.local], "-")
        self.assertEqual(tui.states[self.local][0], "missing")
        tui.discover_remotes()
        for future in tui.pending.values():
            future.result(timeout=5)
        tui.poll_remotes()
        self.assertFalse(tui.pending)
        self.assertEqual(tui.discovered[self.local][1], "")
        self.assertTrue(any("1 个分支 / 2 个 Tag" in msg for _, msg in tui.logs))

    def test_edit_clear_pick_adopt_save_and_freeze_preserve_url(self):
        tui = self.tui()
        for value in ("main", ""):
            with patch.object(tui, "input_dlg", return_value=value):
                tui.do_edit(None, self.local)
            self.assertEqual(tui.data["repos"][self.local]["url"], self.entry["url"])
            self.assertEqual(tui.data["repos"][self.local]["ref"], value)
        with patch.object(tui, "picker", return_value="v1.0"):
            tui.do_pick(None, self.local)
        self.clone()
        self.assertEqual(rv.adopt_all(str(self.workspace), tui.data), 1)
        rv.save_manifest(self.config, tui.data)
        saved = rv.load_manifest(self.config)
        self.assertEqual(saved["repos"][self.local]["url"], self.entry["url"])
        self.assertEqual(saved["repos"][self.local]["note"], "keep")
        snapshot, count = rv.freeze_release(str(self.workspace), saved, "test", self.root / "releases")
        self.assertEqual(count, 1)
        self.assertEqual(rv.load_manifest(snapshot)["repos"][self.local]["url"], self.entry["url"])

    def test_sync_reports_missing_clone_and_rejects_wrong_origin(self):
        tui = self.tui()
        with patch.object(rv, "checkout") as checkout:
            tui.do_sync(self.local)
            self.assertIn("本地未克隆", tui.logs[-1][1])
            path = self.clone()
            git("-C", path, "remote", "set-url", "origin", str(self.root / "other.git"))
            tui.do_sync(self.local)
            self.assertIn("清单 url 与本地 origin 不同", tui.logs[-1][1])
            checkout.assert_not_called()

    def test_installer_clone_uses_manifest_url_and_quotes_shell(self):
        url = "ssh://git@example.test/group/repo$(false)'name.git"
        app = SimpleNamespace(settings={"SEMANTIC": str(self.workspace),
                                       "GITLAB": "https://example.test/group"}, log=lambda *args: None)
        with patch.object(installer, "find_repo_manifest", return_value=(
            str(self.config), {"semantic-framework": {"url": url}}
        )):
            script = installer._clone_script(app)[0]
        import shlex
        clone_line = next(line for line in script.splitlines()
                          if line.startswith("clone_if ") and "semantic-framework" in line)
        self.assertEqual(shlex.split(clone_line), ["clone_if", str(self.workspace / "semantic-framework"), url])
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_invalid_manifest_is_not_silently_replaced(self):
        for data in ({"repos": {"../escape": {}}}, {"repos": {"repo": {"url": []}}}, {"repos": []}):
            with patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(data))):
                with self.assertRaises(ValueError):
                    rv.load_manifest(self.config)

    def test_failed_fetch_does_not_checkout_stale_ref(self):
        with patch.object(rv, "run", return_value=(1, "authentication failed")) as run:
            self.assertEqual(rv.checkout("repo", "main"), (False, "authentication failed"))
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
