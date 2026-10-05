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
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import semantic_installer as installer

# 旧版式 (2026-09-21 之前): 阶段 8 是两个「日常再开」服务, LIBERO 在阶段 9。
LEGACY_STATUSES = {
    "1.0": "ok", "5.4": "ok", "6.4": "ok",
    "8.1": "ok", "8.2": "ok",
}


class StatusMigrationTests(unittest.TestCase):
    """旧版步骤状态必须迁到现编号, 且迁移幂等、留备份。"""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.status_file = self.root / "installer-status.json"
        p = patch.object(installer, "STATUS_FILE", self.status_file)
        p.start()
        self.addCleanup(p.stop)

    def write(self, data):
        self.status_file.write_text(json.dumps(data), encoding="utf-8")

    def read(self):
        return json.loads(self.status_file.read_text(encoding="utf-8"))

    def test_old_layout_services_move_from_8_to_9(self):
        """旧 8.1/8.2 是日常再开服务, 迁移后应记在 9.1/9.2, 不再冒充 LIBERO 的前置检查。"""
        self.write(LEGACY_STATUSES)
        statuses, backup = installer.load_statuses()
        self.assertEqual(statuses["9.1"], "ok")
        self.assertEqual(statuses["9.2"], "ok")
        self.assertNotIn("8.1", statuses)
        self.assertNotIn("8.2", statuses)
        self.assertIsNotNone(backup)

    def test_untouched_stages_are_preserved(self):
        self.write(LEGACY_STATUSES)
        statuses, _ = installer.load_statuses()
        for sid in ("1.0", "5.4", "6.4"):
            self.assertEqual(statuses[sid], "ok")

    def test_old_layout_libero_steps_move_from_9_to_8(self):
        """反过来也要对: 旧 9.x 是 LIBERO, 迁移后应记在 8.x。"""
        self.write({"9.1": "ok", "9.10": "ok", "9.12": "skip"})
        statuses, _ = installer.load_statuses()
        self.assertEqual(statuses["8.1"], "ok")
        self.assertEqual(statuses["8.10"], "ok")
        self.assertEqual(statuses["8.12"], "skip")
        self.assertNotIn("9.1", statuses)

    def test_swap_does_not_overwrite_itself(self):
        """相邻两个键互换时不能互相覆盖 (8.1 与 9.1 同时存在)。"""
        self.write({"8.1": "ok", "9.1": "skip", "8.2": "warn", "9.2": "done"})
        statuses, _ = installer.load_statuses()
        self.assertEqual(statuses["9.1"], "ok")
        self.assertEqual(statuses["8.1"], "skip")
        self.assertEqual(statuses["9.2"], "warn")
        self.assertEqual(statuses["8.2"], "done")

    def test_migration_is_idempotent(self):
        """迁移写回的标记让第二次读取不再动数据。"""
        self.write(LEGACY_STATUSES)
        first, backup = installer.load_statuses()
        self.assertIsNotNone(backup)
        raw_after_first = self.read()
        second, backup_again = installer.load_statuses()
        self.assertIsNone(backup_again)
        self.assertEqual(first, second)
        self.assertEqual(raw_after_first, self.read())

    def test_migration_keeps_a_backup_of_the_original(self):
        self.write(LEGACY_STATUSES)
        installer.load_statuses()
        backup = self.status_file.with_name(self.status_file.name + installer.STATUS_BACKUP_SUFFIX)
        self.assertTrue(backup.exists())
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), LEGACY_STATUSES)

    def test_current_layout_is_left_alone(self):
        """已是现版式的文件不迁移、不留备份。"""
        self.write({installer.STATUS_LAYOUT_KEY: installer.STATUS_LAYOUT, "8.1": "ok", "9.1": "ok"})
        statuses, backup = installer.load_statuses()
        self.assertIsNone(backup)
        self.assertEqual(statuses["8.1"], "ok")
        self.assertEqual(statuses["9.1"], "ok")

    def test_new_steps_do_not_get_remapped_on_next_start(self):
        """全新工作区跑完 LIBERO 后再启动, 8.x 必须保持 8.x。

        这是迁移最容易写错的地方: 不带标记的空状态写回 8.x 后, 下一次读取会把它
        当成旧编号再搬一次, 步骤就会在 8/9 之间来回跳。
        """
        self.assertFalse(self.status_file.exists())
        statuses, backup = installer.load_statuses()
        self.assertIsNone(backup)
        self.assertEqual(statuses[installer.STATUS_LAYOUT_KEY], installer.STATUS_LAYOUT)
        statuses["8.11"] = "ok"
        installer.save_json(self.status_file, statuses)
        next_start, backup_again = installer.load_statuses()
        self.assertIsNone(backup_again)
        self.assertEqual(next_start["8.11"], "ok")

    def test_missing_and_corrupt_files_are_handled(self):
        statuses, backup = installer.load_statuses()
        self.assertIsNone(backup)
        self.assertEqual(statuses[installer.STATUS_LAYOUT_KEY], installer.STATUS_LAYOUT)
        self.status_file.write_text("{not json", encoding="utf-8")
        statuses, backup = installer.load_statuses()
        self.assertIsNone(backup)
        self.assertEqual(statuses[installer.STATUS_LAYOUT_KEY], installer.STATUS_LAYOUT)

    def test_unwritable_status_file_does_not_break_startup(self):
        """备份/写盘失败时只是不迁移, 不能把安装器带崩。"""
        self.write(LEGACY_STATUSES)
        with patch.object(installer, "save_json", side_effect=OSError("read-only")):
            statuses, backup = installer.load_statuses()
        self.assertIsNone(backup)
        self.assertEqual(statuses["9.1"], "ok")

    def test_sid_remap_only_touches_stage_eight_and_nine(self):
        self.assertEqual(installer.remap_status_sid("8.1"), "9.1")
        self.assertEqual(installer.remap_status_sid("9.12"), "8.12")
        self.assertEqual(installer.remap_status_sid("7.1"), "7.1")
        self.assertEqual(installer.remap_status_sid("1.1b"), "1.1b")
        self.assertEqual(installer.remap_status_sid("unknown"), "unknown")


class StatusLayoutContractTests(unittest.TestCase):
    """现版式与文档/步骤定义保持一致, 防止再次错位。"""

    def test_stage_eight_is_the_extension_stage(self):
        stages = dict(installer.STAGES)
        self.assertIn("扩展", stages[8])
        self.assertEqual(stages[9], "日常再开")

    def test_every_declared_step_belongs_to_a_declared_stage(self):
        stages = {num for num, _title in installer.STAGES}
        for step in installer.build_steps():
            self.assertIn(step["stage"], stages,
                          f"{step['sid']} 的阶段 {step['stage']} 不在 STAGES 里")

    def test_stage_prerequisites_only_reference_declared_stages(self):
        stages = {num for num, _title in installer.STAGES}
        for stage, needs in installer.STAGE_PREREQ.items():
            self.assertIn(stage, stages)
            for need in needs:
                self.assertIn(need, stages)

    def test_status_keys_align_with_declared_steps(self):
        """状态文件里的键必须都是已声明的步骤号 (标记键除外)。"""
        known = {s["sid"] for s in installer.build_steps()}
        legacy = {installer.STATUS_LAYOUT_KEY}
        for sid in LEGACY_STATUSES:
            for mapped in (sid, installer.remap_status_sid(sid)):
                self.assertTrue(mapped in known or mapped in legacy,
                                f"{sid} -> {mapped} 不是已声明的步骤")

    def test_legacy_service_keys_map_onto_the_current_service_steps(self):
        """LEGACY 的 8.1/8.2 必须正是现在两个日常再开服务的步骤号。"""
        title = {s["sid"]: s["title"] for s in installer.build_steps()}
        self.assertIn("日常再开", title[installer.remap_status_sid("8.1")])
        self.assertIn("日常再开", title[installer.remap_status_sid("8.2")])

    def test_remap_is_its_own_inverse(self):
        for sid in ("8.1", "8.12", "9.1", "9.10"):
            self.assertEqual(installer.remap_status_sid(installer.remap_status_sid(sid)), sid)


if __name__ == "__main__":
    unittest.main()
