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
from pathlib import Path
from unittest.mock import patch

import semantic_installer as installer


class InstallerPresentationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for key, value in (("SCRIPT_DIR", self.root), ("STATUS_FILE", self.root / "status.json")):
            p = patch.object(installer, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.app = installer.App(dict(installer.DEFAULT_SETTINGS))
        self.plan = [{"repo": "one", "url": "https://example.test/one.git", "ref": "v1", "status": "pending"},
                     {"repo": "two", "url": "https://example.test/two.git", "ref": "v2", "status": "pending"}]
        p = patch.object(installer, "_repo_plan", return_value=("manifest.json", self.plan))
        p.start()
        self.addCleanup(p.stop)

    def run_step(self, commands):
        step = dict(self.app.bysid["2.1"], pre=None, note=None, cmds=commands, cwd=str(self.root))
        self.app._begin(step, False)
        deadline = time.monotonic() + 5
        while self.app.cur and time.monotonic() < deadline:
            self.app.pump()
            time.sleep(0.005)
        self.assertIsNone(self.app.cur)
        return Path(self.app.log_paths["2.1"])

    def test_failed_process_keeps_diagnostics_in_file_not_command_stream(self):
        self.app.queue = [("2.2", False)]
        path = self.run_step([installer._repo_event("one", "running") +
                              "\nprintf 'fatal: unavailable repository\\n' >&2\nexit 7"])
        self.assertEqual(self.app.status("2.1"), "fail")
        self.assertFalse(self.app.queue)
        self.assertEqual(self.plan[0]["status"], "fail")
        self.assertEqual(self.plan[1]["status"], "pending")
        form = self.app.form_for(self.app.bysid["2.1"])
        self.assertIn("unavailable repository", form["error"])
        log = path.read_text()
        self.assertIn("exit 7", log)
        self.assertIn("[out] fatal: unavailable repository", log)
        self.assertIn("最终结果: fail", log)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(any(kind in ("cmd", "out") for kind, _, _ in self.app.logbuf))

    def test_successful_rows_and_logs_survive_screen_clear(self):
        path = self.run_step(["\n".join(installer._repo_event(name, state)
                                       for name in ("one", "two") for state in ("running", "ok"))])
        self.assertEqual(self.app.status("2.1"), "ok")
        self.assertTrue(all(row["status"] == "ok" for row in self.plan))
        self.app.logbuf.clear()
        self.assertIn("最终结果: ok", path.read_text())

    def test_secrets_are_redacted_before_persisting(self):
        self.app.vars["SUDO_PW"] = "private-password"
        self.app._start_step_log("test")
        self.app.log("out", "private-password https://oauth2:secret@example.test/repo glpat-secretvalue")
        content = Path(self.app.step_log_path).read_text()
        self.assertNotIn("private-password", content)
        self.assertNotIn("oauth2:secret", content)
        self.assertNotIn("glpat-secretvalue", content)
        self.assertIn("[REDACTED]", content)

    def test_python_exception_is_logged_and_stops_step(self):
        def fail(app):
            raise RuntimeError("diagnostic failure")
        step = dict(self.app.bysid["1.6"], fn=fail)
        self.app._begin(step, False)
        self.assertEqual(self.app.status("1.6"), "fail")
        self.assertIn("Traceback", Path(self.app.log_paths["1.6"]).read_text())

    def test_configuration_form_does_not_contain_admin_password(self):
        form = self.app.form_for(self.app.bysid["3.1"])
        self.assertIn(("管理员密码", "已配置"), form["fields"])
        self.assertNotIn(self.app.settings["SEMANTIC_ADMIN_PASSWORD"], repr(form))

    def test_build_colors_are_removed_from_screen_and_log_file(self):
        self.app._start_step_log("5.1")
        self.app.log("out", "\x1b[0m\x1b[38;2;255;255;0m  => \x1b[0m"
                     "download https://example.test/v0.18.7.tar.gz .. "
                     "\x1b[38;2;0;255;0;1mok\x1b[0m ✓ 构建成功")
        expected = "  => download https://example.test/v0.18.7.tar.gz .. ok ✓ 构建成功"
        self.assertEqual(self.app.logbuf[-1][1], expected)
        content = Path(self.app.step_log_path).read_text()
        self.assertIn(expected, content)
        self.assertNotIn("\x1b", content)

    def test_terminal_controls_preserve_hyperlink_label_and_unicode(self):
        text = ("\x1b]0;terminal title\x07\x1b[?25l\x1b[2K"
                "\x1b]8;;https://example.test\x1b\\下载链接\x1b]8;;\x1b\\"
                "\x1b[?25h\r\n\t✓ 完成\x07\x08")
        self.assertEqual(installer.plain_log_text(text), "下载链接\n\t✓ 完成")

    def test_colored_failure_summary_is_plain_text(self):
        path = self.run_step(["printf '\\033[31merror: 构建失败\\033[0m\\n' >&2\nexit 1"])
        form = self.app.form_for(self.app.bysid["2.1"])
        self.assertEqual(form["error"], "error: 构建失败")
        self.assertIn("[out] error: 构建失败", path.read_text())
        self.assertNotIn("\x1b", path.read_text())


if __name__ == "__main__":
    unittest.main()
