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

"""阶段 2 的 isaac 线接入: 只在 EXTENSION=isaac 时克隆 isaac-runtime, 并按仓切行为分支。

LIBERO 的做法是「一个功能线分支 + 单分支例外」; isaac 线的分支名各仓不统一, 所以用
内置逐仓表 ISAAC_LINE_BRANCHES, ISAAC_LINE_BRANCH 非空时统一覆盖。这里锁住这份约定。
"""

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import semantic_installer as installer


def make_app(**overrides):
    settings = dict(installer.DEFAULT_SETTINGS)
    settings["SEMANTIC"] = "/tmp/ws/semantic"
    settings.update(overrides)
    return SimpleNamespace(settings=settings, log=Mock())


class ExtensionCloneGateTests(unittest.TestCase):
    def test_isaac_runtime_is_not_cloned_without_the_isaac_extension(self):
        for extension in ("none", "libero"):
            script = installer._clone_script(make_app(EXTENSION=extension))[0]
            self.assertNotRegex(script, r'clone_if .*isaac-runtime')
            self.assertIn("仅 EXTENSION=isaac 时克隆", script)
            subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_isaac_runtime_is_cloned_with_the_isaac_extension(self):
        script = installer._clone_script(make_app(EXTENSION="isaac"))[0]
        line = next(line for line in script.splitlines()
                    if line.startswith("clone_if ") and "isaac-runtime" in line)
        self.assertIn("issac-runtime.git", line)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)


class BranchLineTests(unittest.TestCase):
    def script(self, **overrides):
        with patch.object(installer, "find_repo_manifest", return_value=(None, None)):
            return installer._branch_script(make_app(**overrides))[0]

    def test_without_the_isaac_extension_the_isaac_repo_is_not_switched(self):
        script = self.script(EXTENSION="none")
        self.assertNotIn("/semantic-simulation/isaac-runtime", script)
        self.assertIn("未启用 EXTENSION=isaac, 不切分支", script)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_the_isaac_extension_switches_the_line_repos(self):
        script = self.script(EXTENSION="isaac")
        self.assertIn('"/tmp/ws/semantic/semantic-framework" "feature/behavior-test"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-robotsdk/robot-sdk" "feature/behavior-test"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-skill/robot-skill" "feature/behavior-test"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-robot-deployment" "feature/behavior-test"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-simulation/isaac-runtime" "feature/behavior-test"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-web" "feature/behavior-isaac"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-ability/r1pro-ability" "feature/behavior-isaac"', script)
        self.assertIn('"/tmp/ws/semantic/semantic-ability/ability-runtime" "develop"', script)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_isaac_line_branch_overrides_every_line_repo(self):
        script = self.script(EXTENSION="isaac", ISAAC_LINE_BRANCH="develop")
        for repo in installer.ISAAC_REPOS:
            self.assertIn(f'"/tmp/ws/semantic/{repo}" "develop"', script)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_the_isaac_line_keeps_its_own_defaults(self):
        self.assertEqual(installer.DEFAULT_SETTINGS["ISAAC_LINE_BRANCH"], "")
        for repo in installer.ISAAC_REPOS:
            self.assertIn(repo, installer.ISAAC_LINE_BRANCHES)


if __name__ == "__main__":
    unittest.main()
