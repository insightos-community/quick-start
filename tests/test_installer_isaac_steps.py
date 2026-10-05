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

"""阶段 8 的 isaac 线「项目启用」: 激活 Project 并把 BEHAVIOR 场景加进 project-scenes。

与 LIBERO 的 8.12 同构。LIBERO 早已把这一步自动化, isaac 线此前只做到"装好",
加场景要人手动在 Web 点——这里锁住新的 8.27 行为, 免得回退。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import semantic_installer as installer


def make_app(**overrides):
    settings = dict(installer.DEFAULT_SETTINGS)
    settings["SEMANTIC"] = "/tmp/ws/semantic"
    settings.update(overrides)
    return SimpleNamespace(settings=settings, log=Mock(), vars={})


class IsaacBindProjectTests(unittest.TestCase):
    def test_scene_ids_default_and_split(self):
        app = make_app(ISAAC_SCENES="")
        self.assertEqual(installer._isaac_project_scene_ids(app),
                         ["behavior-turning_on_radio-0"])
        app = make_app(ISAAC_SCENES="behavior-turning_on_radio-0, behavior-other-1")
        self.assertEqual(installer._isaac_project_scene_ids(app),
                         ["behavior-turning_on_radio-0", "behavior-other-1"])

    def test_skipped_without_the_isaac_extension(self):
        state, reason = installer._step_isaac_bind_project(make_app(EXTENSION="none"))[:2]
        self.assertEqual(state, "skip")
        self.assertIn("isaac", reason)

    def test_activates_and_adds_the_configured_scenes(self):
        app = make_app(EXTENSION="isaac", ISAAC_PROJECT_ID="proj-1")
        captured = {}

        def fake(app_, project, scene_ids, runtime_preference=None):
            captured["project"] = project
            captured["scene_ids"] = scene_ids
            captured["pref"] = runtime_preference
            return ("ok", None)

        with patch.object(installer, "_ensure_project_scenes", side_effect=fake):
            state, _ = installer._step_isaac_bind_project(app)[:2]
        self.assertEqual(state, "ok")
        self.assertEqual(captured["project"], "proj-1")
        self.assertEqual(captured["scene_ids"], ["behavior-turning_on_radio-0"])
        self.assertEqual(captured["pref"],
                         (installer.ISAAC_RUNTIME_PROFILE, installer.ISAAC_RUNTIME_ID_DEFAULT))

    def test_falls_back_to_the_default_development_project(self):
        app = make_app(EXTENSION="isaac")
        with patch.object(installer, "fetch_project_id", return_value=("proj-9", "默认项目")), \
                patch.object(installer, "_ensure_project_scenes", return_value=("ok", None)):
            installer._step_isaac_bind_project(app)
        self.assertEqual(app.vars.get("ISAAC_PROJECT_ID"), "proj-9")

    def test_fails_when_no_project_can_be_resolved(self):
        app = make_app(EXTENSION="isaac")
        with patch.object(installer, "fetch_project_id", return_value=(None, "未登录")):
            state, reason = installer._step_isaac_bind_project(app)[:2]
        self.assertEqual(state, "fail")
        self.assertIn("Project", reason)


class IsaacPolicyGpuTests(unittest.TestCase):
    def test_picks_the_gpu_with_the_most_free_memory(self):
        app = make_app(EXTENSION="isaac")
        with patch.object(installer, "_isaac_probe",
                          return_value=(True, "0, 1000\n1, 24000\n2, 12000")):
            self.assertEqual(installer.isaac_policy_gpu(app), "1")

    def test_falls_back_to_gpu_zero_without_nvidia_smi(self):
        app = make_app(EXTENSION="isaac")
        with patch.object(installer, "_isaac_probe", return_value=(False, "nvidia-smi not found")):
            self.assertEqual(installer.isaac_policy_gpu(app), "0")


class IsaacStageWiringTests(unittest.TestCase):
    def test_bind_project_is_an_automated_step_before_the_manual_checklist(self):
        steps = {s["sid"]: s for s in installer.build_steps()}
        self.assertEqual(steps["8.27"]["title"], "激活 Project 并加入 BEHAVIOR 场景")
        self.assertEqual(steps["8.27"]["kind"], "python")
        self.assertEqual(steps["8.28"]["kind"], "manual")
        self.assertEqual(installer.EXTENSIONS["isaac"]["steps"], 15)

    def test_manual_checklist_no_longer_asks_users_to_add_the_scene(self):
        self.assertNotIn("添加兼容场景", installer.MANUAL_ISAAC)
        self.assertIn("已由步骤 8.27 自动完成", installer.MANUAL_ISAAC)


if __name__ == "__main__":
    unittest.main()
