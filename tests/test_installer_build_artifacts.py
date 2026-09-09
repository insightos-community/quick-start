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

import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import semantic_installer as installer


POINTER = b"version https://git-lfs.github.com/spec/v1\n"
WHEELS = {
    "ability_py": "ability_py-0.4.0-py3-none-any.whl",
    "ability_scaffold": "ability_scaffold-1.2.0-py3-none-any.whl",
}


class BuildArtifactTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for key, value in (("SCRIPT_DIR", self.root), ("STATUS_FILE", self.root / "status.json")):
            p = patch.object(installer, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.app = installer.App({**installer.DEFAULT_SETTINGS, "SEMANTIC": str(self.root)})
        self.vendor = self.root / "semantic-ability/ability-runtime"
        self.cache = self.vendor / f"base-bundles/r1pro-mujoco-{self.app.settings['BUNDLE_VER']}/wheels"
        self.cache.mkdir(parents=True)
        self.repos = {
            "ability_py": self.root / "ability-framework/ability-py-sdk",
            "ability_scaffold": self.root / "ability-framework/ability-scaffold",
        }
        for key, repo in self.repos.items():
            (repo / ".git").mkdir(parents=True)
            (repo / "dist").mkdir()
            self.make_wheel(repo / "dist" / WHEELS[key])
            (self.vendor / WHEELS[key]).write_bytes(POINTER)
        (self.cache / WHEELS["ability_py"]).write_bytes(POINTER)

    def make_wheel(self, path):
        name, version = path.name.split("-")[:2]
        with zipfile.ZipFile(path, "w") as wheel:
            wheel.writestr(f"{name}/__init__.py", "")
            for entry, text in (("METADATA", f"Name: {name}\nVersion: {version}\n"),
                                ("WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n"),
                                ("RECORD", "")):
                wheel.writestr(f"{name}-{version}.dist-info/{entry}", text)

    def install(self):
        return installer._install_ability_wheels(self.app, self.repos, self.vendor, self.cache)

    def run_dynamic_step(self, sid, info):
        step = dict(self.app.bysid[sid], fn=lambda app: ("shell", info), note=None)
        self.app._begin(step, False)
        deadline = time.monotonic() + 5
        while self.app.cur and time.monotonic() < deadline:
            self.app.pump()
            time.sleep(0.005)
        self.assertIsNone(self.app.cur)
        return Path(self.app.log_paths[sid]).read_text()

    def test_dynamic_wheel_step_installs_then_verifies_outputs(self):
        _, info = installer._step_build_ability_py(self.app)
        info["cmds"] = ["true"]  # Source build fixtures already exist; no downloads.
        log = self.run_dynamic_step("5.2", info)
        self.assertEqual(self.app.status("5.2"), "ok")
        for key, name in WHEELS.items():
            self.assertEqual((self.vendor / name).read_bytes(),
                             (self.repos[key] / "dist" / name).read_bytes())
            self.assertEqual((self.vendor / (name + ".lfs-orig")).read_bytes(), POINTER)
        installer._check_built_wheel(self.cache / WHEELS["ability_py"])
        self.assertLess(log.index("已安装"), log.index("校验通过"))
        self.assertLess(log.index("校验通过"), log.index("完成 ("))

    def test_post_failure_stops_queue_and_never_reports_completion(self):
        (self.repos["ability_scaffold"] / "dist" / WHEELS["ability_scaffold"]).write_bytes(POINTER)
        _, info = installer._step_build_ability_py(self.app)
        info["cmds"] = ["true"]
        self.app.queue = [("5.4", False)]
        log = self.run_dynamic_step("5.2", info)
        self.assertEqual(self.app.status("5.2"), "fail")
        self.assertFalse(self.app.queue)
        self.assertIn("源码 Wheel 缺失或无效", log)
        self.assertNotIn("完成 (", log)
        self.assertEqual((self.vendor / WHEELS["ability_py"]).read_bytes(), POINTER)

    def test_dynamic_verification_failure_stops_queue(self):
        post = Mock()
        self.app.queue = [("5.4", False)]
        self.run_dynamic_step("5.2", {"cmds": ["true"], "cwd": str(self.root),
                                     "post": post, "verify": ["false"]})
        post.assert_called_once_with(self.app, 0)
        self.assertEqual(self.app.status("5.2"), "fail")
        self.assertFalse(self.app.queue)

    def test_failed_build_does_not_run_post(self):
        post = Mock()
        self.run_dynamic_step("5.2", {"cmds": ["false"], "cwd": str(self.root), "post": post})
        post.assert_not_called()
        self.assertEqual(self.app.status("5.2"), "fail")

    def test_wrong_version_is_not_renamed_or_installed(self):
        wheel = self.repos["ability_py"] / "dist" / WHEELS["ability_py"]
        wheel.rename(wheel.with_name("ability_py-9.0.0-py3-none-any.whl"))
        self.assertEqual(self.install()[0], "fail")
        self.assertEqual((self.vendor / WHEELS["ability_py"]).read_bytes(), POINTER)

    def test_zip_without_wheel_metadata_fails(self):
        wheel = self.repos["ability_py"] / "dist" / WHEELS["ability_py"]
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("readme.txt", "not a wheel")
        self.assertEqual(self.install()[0], "fail")

    def test_missing_destination_fails(self):
        self.assertEqual(installer._install_ability_wheels(
            self.app, self.repos, self.vendor, self.root / "missing")[0], "fail")

    def test_copy_failure_is_propagated(self):
        with patch.object(installer.shutil, "copy2", side_effect=OSError("disk full")):
            result = self.install()
        self.assertEqual(result[0], "fail")
        self.assertIn("disk full", result[1])

    def test_destination_is_validated_after_copy(self):
        with patch.object(installer.shutil, "copy2", return_value=None):
            self.assertEqual(self.install()[0], "fail")

    def test_dynamic_binary_step_installs_source_output(self):
        repo = self.root / "ability-framework/abilityframework"
        (repo / ".git").mkdir(parents=True)
        (repo / "build").mkdir()
        binary = repo / "build/AbilityFramework"
        binary.write_text("#!/bin/sh\necho AbilityFramework-test\n")
        binary.chmod(0o755)
        (self.vendor / "AbilityFramework").write_bytes(POINTER)
        _, info = installer._step_build_af(self.app)
        info["cmds"] = ["true"]
        self.run_dynamic_step("5.1", info)
        self.assertEqual(self.app.status("5.1"), "ok")
        self.assertEqual((self.vendor / "AbilityFramework").read_bytes(), binary.read_bytes())

    def test_missing_or_unusable_binary_fails(self):
        repo = self.root / "binary-repo"
        self.assertEqual(installer._install_af(self.app, repo, self.vendor)[0], "fail")
        (repo / "build").mkdir(parents=True)
        binary = repo / "build/AbilityFramework"
        binary.write_bytes(POINTER)
        binary.chmod(0o755)
        self.assertEqual(installer._install_af(self.app, repo, self.vendor)[0], "fail")


if __name__ == "__main__":
    unittest.main()
