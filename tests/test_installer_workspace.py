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
from unittest.mock import Mock, patch

import semantic_installer as installer


class InstallerWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "quick-start"
        self.repo.mkdir()
        for name, value in (
            ("SCRIPT_DIR", self.repo),
            ("SETTINGS_FILE", self.root / "settings.json"),
            ("STATUS_FILE", self.root / "status.json"),
            ("ENV_SH", self.root / "env.sh"),
        ):
            p = patch.object(installer, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.app = installer.App(dict(installer.DEFAULT_SETTINGS))
        self.old_workspace = self.app.settings["SEMANTIC"]
        self.app.workspace_prompt = Mock(return_value=str(self.repo))
        self.app.confirm = Mock(return_value=True)

    def test_default_is_script_repository_and_persists_for_later_steps(self):
        self.assertTrue(self.app.prepare_clone_workspace())
        self.app.workspace_prompt.assert_called_once_with(str(self.repo), "")
        self.app.confirm.assert_called_once()
        self.assertEqual(self.app.settings["SEMANTIC"], str(self.repo))
        self.assertEqual(self.app.env["SEMANTIC"], str(self.repo))
        saved = json.loads(installer.SETTINGS_FILE.read_text())
        self.assertEqual(saved["SEMANTIC"], str(self.repo))
        self.assertIn(str(self.repo), installer.ENV_SH.read_text())
        self.assertEqual(self.app.bysid["3.2"]["cwd"](self.app), str(self.repo / "semantic-framework"))

    def test_missing_absolute_path_requires_creation_confirmation(self):
        chosen = self.root / "工作区 with spaces" / "semantic"
        self.app.workspace_prompt.return_value = str(chosen)
        self.assertTrue(self.app.prepare_clone_workspace())
        self.assertTrue(chosen.is_dir())
        self.assertEqual(self.app.confirm.call_count, 2)
        self.assertEqual(self.app.confirm.call_args_list[1].args[0], "目录不存在")
        self.assertEqual(self.app.env["SEMANTIC"], str(chosen))

    def test_cancel_or_decline_stops_queue_before_clone_command_generation(self):
        for mode in ("cancel", "decline_directory", "decline_create"):
            with self.subTest(mode=mode):
                target = self.root / mode
                self.app.workspace_prompt = Mock(return_value=None if mode == "cancel" else str(target))
                self.app.confirm = Mock(side_effect=[True, False] if mode == "decline_create" else [False])
                self.app.queue = [("2.2", False), ("3.2", False)]
                with patch.object(installer, "_clone_script") as clone, \
                        patch.object(installer.subprocess, "Popen") as popen:
                    self.app._begin(self.app.bysid["2.1"], False)
                    clone.assert_not_called()
                    popen.assert_not_called()
                self.assertEqual(self.app.status("2.1"), "fail")
                self.assertEqual(self.app.queue, [])
                self.assertIsNone(self.app.cur)
                self.assertFalse(target.exists())
                self.assertEqual(self.app.settings["SEMANTIC"], self.old_workspace)
                self.assertFalse(installer.SETTINGS_FILE.exists())

    def test_invalid_inputs_reprompt_without_creating_or_saving(self):
        existing_file = self.root / "file"
        existing_file.touch()
        values = ["relative/path", "", str(existing_file), str(self.root / 'bad"path'),
                  str(self.root / "$(touch sentinel)"), None]
        self.app.workspace_prompt.side_effect = values
        self.assertFalse(self.app.prepare_clone_workspace())
        self.assertEqual(self.app.workspace_prompt.call_count, len(values))
        self.app.confirm.assert_not_called()
        self.assertTrue(all(call.args[1] for call in self.app.workspace_prompt.call_args_list[1:]))
        self.assertFalse(installer.SETTINGS_FILE.exists())

    def test_creation_error_stops_without_changing_workspace(self):
        self.app.workspace_prompt.return_value = str(self.root / "denied")
        with patch.object(installer.os, "makedirs", side_effect=PermissionError("denied")):
            self.assertFalse(self.app.prepare_clone_workspace())
        self.assertEqual(self.app.settings["SEMANTIC"], self.old_workspace)
        self.assertFalse(installer.SETTINGS_FILE.exists())

    def test_save_error_stops_before_clone(self):
        with patch.object(installer, "save_json", side_effect=OSError("disk full")):
            self.assertFalse(self.app.prepare_clone_workspace())
        self.assertEqual(self.app.settings["SEMANTIC"], self.old_workspace)
        self.assertIsNone(self.app.clone_workspace)

    def test_retries_reuse_confirmation_but_setting_changes_prompt_again(self):
        self.assertTrue(self.app.prepare_clone_workspace())
        self.assertTrue(self.app.prepare_clone_workspace())
        self.app.workspace_prompt.assert_called_once()
        self.app.settings["SEMANTIC"] = str(self.root / "changed")
        self.assertTrue(self.app.prepare_clone_workspace())
        self.assertEqual(self.app.workspace_prompt.call_count, 2)

    def test_shell_only_starts_after_workspace_confirmation(self):
        with patch.object(self.app, "_run_shell") as run:
            self.app._begin(self.app.bysid["2.1"], False)
        run.assert_called_once()
        step = run.call_args.args[0]
        self.assertEqual(step["cwd"](self.app), str(self.repo))
        self.assertEqual(self.app.clone_workspace, str(self.repo))

    def test_headless_preserves_configured_workspace_without_prompt(self):
        self.app.headless = True
        with patch.object(self.app, "log"):
            self.assertTrue(self.app.prepare_clone_workspace())
        self.app.workspace_prompt.assert_not_called()
        self.app.confirm.assert_not_called()
        self.assertEqual(self.app.settings["SEMANTIC"], self.old_workspace)
        self.assertFalse(installer.SETTINGS_FILE.exists())


if __name__ == "__main__":
    unittest.main()
