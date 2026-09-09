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

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import semantic_installer as installer


POINTER = b"version https://git-lfs.github.com/spec/v1\n"


class RuntimeAssetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.vendor = self.root / "semantic-ability/ability-runtime"
        self.bundle = self.vendor / "base-bundles/r1pro-mujoco-test"
        self.wheels = self.bundle / "wheels"
        self.wheels.mkdir(parents=True)
        (self.bundle / "bundle.yaml").write_text("version: test\n")
        self.wheel = self.wheels / "numpy-test.whl"
        self.wheel.write_bytes(b"third party wheel")
        self.app = SimpleNamespace(settings={"SEMANTIC": str(self.root), "BUNDLE_VER": "test"}, log=Mock())
        self.names = ["AbilityFramework", "ability_py-test.whl", "ability_scaffold-test.whl",
                      "base-bundles/r1pro-mujoco-test/wheels/ability_py-test.whl",
                      str(self.wheel.relative_to(self.vendor))]

    def check(self):
        with patch.object(installer, "_run_quick", return_value=(0, "\n".join(self.names))):
            return installer._check_runtime_assets(self.app)

    def test_source_artifacts_can_be_absent_before_build(self):
        self.assertIsNone(self.check())
        self.assertIn("1 个 LFS 文件", self.app.log.call_args.args[1])

    def test_missing_third_party_or_pointer_fails(self):
        self.wheel.unlink()
        self.assertEqual(self.check()[0], "fail")
        self.wheel.write_bytes(POINTER)
        result = self.check()
        self.assertEqual(result[0], "fail")
        self.assertIn("numpy-test.whl", result[1])

    def test_bundle_configuration_remains_required(self):
        (self.bundle / "bundle.yaml").unlink()
        self.assertEqual(self.check()[0], "fail")

    def test_git_lfs_listing_failure_is_reported(self):
        with patch.object(installer, "_run_quick", return_value=(1, "not a repository")):
            self.assertEqual(installer._check_runtime_assets(self.app)[0], "fail")

    def test_checkout_and_pull_with_real_local_lfs_remote(self):
        if subprocess.run(["git", "lfs", "version"], capture_output=True).returncode:
            self.skipTest("git-lfs unavailable")
        # A local remote ensures no production repository or network is touched.
        source = self.root / "source"
        remote = self.root / "remote.git"
        workspace = self.root / "checkout"
        vendor = workspace / "semantic-ability/ability-runtime"

        def git(*args, env=None):
            result = subprocess.run(["git", *map(str, args)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        git("init", "--bare", remote)
        git("init", "-b", "main", source)
        git("-C", source, "lfs", "install", "--local")
        (source / ".gitattributes").write_text(
            "AbilityFramework filter=lfs diff=lfs merge=lfs -text\n*.whl filter=lfs diff=lfs merge=lfs -text\n")
        names = self.names + ["base-bundles/r1pro-mujoco-test/wheels/ability_scaffold-test.whl"]
        for version in ("v1", "v2"):
            for name in names:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((version + " binary payload " + name).encode())
            (source / "base-bundles/r1pro-mujoco-test/bundle.yaml").write_text("version: test\n")
            git("-C", source, "add", ".")
            git("-C", source, "-c", "user.name=Test", "-c", "user.email=test@example.test",
                "commit", "-m", version)
            git("-C", source, "tag", version)
        git("-C", remote, "symbolic-ref", "HEAD", "refs/heads/main")
        git("-C", source, "remote", "add", "origin", remote)
        git("-C", source, "push", "origin", "main", "--tags")
        vendor.parent.mkdir(parents=True)
        git("clone", remote, vendor, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
        app = SimpleNamespace(settings={"SEMANTIC": str(workspace), "BUNDLE_VER": "test"}, log=Mock())
        with patch.object(installer, "REPOS", [("semantic-ability/ability-runtime", "unused", None)]), \
                patch.object(installer, "find_repo_manifest", return_value=(
                    "manifest", {"semantic-ability/ability-runtime": {"ref": "v1"}})):
            script = installer._branch_script(app)[0]
        subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
        for name in names:
            self.assertTrue((vendor / name).read_bytes().startswith(POINTER), name)
        step = next(s for s in installer.build_steps() if s["sid"] == "2.3")
        subprocess.run(["bash", "-c", step["cmds"](app)[1]],
                       capture_output=True, text=True, check=True)
        for name in names:
            if installer._source_built_asset(name):
                self.assertTrue((vendor / name).read_bytes().startswith(POINTER), name)
            else:
                self.assertTrue((vendor / name).read_bytes().startswith(b"v1 binary payload"), name)
        # Only the third-party object was transferred, not just left un-checked-out.
        objects = [p for p in (vendor / ".git/lfs/objects").rglob("*") if p.is_file()]
        self.assertEqual(len(objects), 1)
        self.assertIsNone(step["post"](app, 0))


if __name__ == "__main__":
    unittest.main()
