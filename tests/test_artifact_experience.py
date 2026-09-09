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

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/runtime'))
import install_support as support
import installer
import uninstall


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.root = self.home/'instance with spaces'
        self.root.mkdir()
        self.state = dict(version='0.5.0-dev.test', web_port=3010, web_host='0.0.0.0')
        (self.root/'configs').mkdir()
        (self.root/'configs/secrets.json').write_text(json.dumps({'SEMANTIC_ADMIN_PASSWORD': 'secret-MUST-NOT-BE-LOGGED'}))

    def test_ipv4_validation_and_probe(self):
        for address in ('0.0.0.0', '127.0.0.1', '192.168.1.20'):
            self.assertEqual(support.web_host(address), address)
        for address in ('localhost', '::1', '192.168.1.2:3000', '255.255.255.255', '224.0.0.1', '1.2.3.4\n'):
            with self.assertRaises(ValueError):
                support.web_host(address)
        self.assertEqual(support.web_probe('0.0.0.0'), '127.0.0.1')
        self.assertEqual(support.web_probe('192.168.1.2'), '192.168.1.2')

    def test_lan_urls_never_advertise_wildcard(self):
        with patch.object(support, 'lan_addresses', return_value=['192.168.1.10']):
            self.assertEqual(support.urls(self.state), ['http://127.0.0.1:3010', 'http://192.168.1.10:3010'])

    def test_wildcard_port_check_detects_interface_listener(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.2', 0))
            sock.listen()
            with self.assertRaisesRegex(RuntimeError, '已占用'):
                installer.check_port(sock.getsockname()[1], '0.0.0.0')

    def test_configure_web_port_rejects_collision_before_stopping_services(self):
        state = dict(self.state, ready=True, http_port=8080, ws_port=8081, runtime_port=8090)
        server = self.root/'releases'/state['version']/'bin/semantic-server'
        server.parent.mkdir(parents=True)
        server.touch()
        for port in (8080, 80, 65536, 3011):
            args = SimpleNamespace(dir=str(self.root), payload=self.home, web_host='0.0.0.0', web_port=port)
            with self.subTest(port=port), patch.object(uninstall, 'uninstall_root', return_value=(self.root, state)), \
                 patch.object(installer, 'verify_payload'), patch.object(installer, 'stop_owned') as stop, \
                 patch.object(installer, 'check_port', side_effect=RuntimeError('已占用')):
                with self.assertRaisesRegex((ValueError, RuntimeError), 'Web 端口|已占用'):
                    installer.configure_existing(args)
                stop.assert_not_called()

    def test_cell_wrapping_and_control_filter(self):
        for size in (10, 19, 39, 79):
            for line in support.lines('欢迎使用 Semantic '+('中文/abc' * 20)+'\npassword-value\x00', size):
                self.assertLessEqual(support.width(line), size)
                self.assertNotIn('\x00', line)

    def test_plain_progress_has_no_escape_and_reports_failure(self):
        output = io.StringIO()
        progress = support.Progress(['one', 'two'], output)
        progress.next('one')
        progress.next('two')
        progress.finish(RuntimeError('failed'))
        self.assertNotIn('\x1b', output.getvalue())
        self.assertIn('50%', output.getvalue())
        self.assertIn('[FAIL]', output.getvalue())
        self.assertNotIn('100%', output.getvalue())

    def test_banner_is_valid_and_each_variant_fits(self):
        data = json.loads((ROOT/'artifacts/assets/banner.json').read_text())
        for size, rows in data.items():
            self.assertTrue(rows)
            self.assertTrue(all(len(row) <= int(size) for row in rows))
            self.assertTrue(all(set(row) <= set(' #*') for row in rows))

    def test_password_never_goes_to_redirected_output(self):
        output = io.StringIO()
        with patch('builtins.open', side_effect=OSError('no tty')), patch.object(support, 'lan_addresses', return_value=[]):
            support.welcome(self.root, self.state, False, stream=output)
        self.assertNotIn('secret-MUST', output.getvalue())
        self.assertIn('尚未启动', output.getvalue())
        self.assertIn('SEMANTIC_HOME', output.getvalue())

    def test_password_goes_only_to_controlling_terminal_not_tee_log(self):
        import runpy
        import shlex
        helper = runpy.run_path(str(ROOT/'tests/test_artifact_terminal.py'))['TerminalConfirmationTests']()
        output = self.home/'captured.log'
        code = ('import sys; from pathlib import Path; sys.path.insert(0, '+repr(str(ROOT/'artifacts/runtime'))+'); '
                'from install_support import welcome; welcome(Path('+repr(str(self.root))+'), '+repr(self.state)+', False)')
        command = 'stty cols 40 rows 24; '+shlex.join([sys.executable, '-B', '-c', code])+' > '+shlex.quote(str(output))
        rc, tty_output = helper.terminal(['bash', '-c', command], b'')
        self.assertEqual(rc, 0, tty_output)
        self.assertIn('secret-MUST-NOT-BE-LOGGED', tty_output.replace('\r', '').replace('\n', ''))
        self.assertNotIn('secret-MUST', output.read_text())

    def desktop(self, state=None, mode='always'):
        state = state if state is not None else self.state
        with patch.object(Path, 'home', return_value=self.home), \
             patch.dict(os.environ, {'XDG_DATA_HOME': str(self.home/'.local/share')}, clear=True), \
             patch.object(support.shutil, 'which', side_effect=lambda n: '/usr/bin/'+n if n in ('xdg-user-dir', 'xdg-open') else None), \
             patch.object(support.subprocess, 'check_output', return_value=str(self.home/'桌面')+'\n'):
            return support.desktop_shortcuts(self.root, state, mode)

    def test_desktop_icon_url_and_format_with_localized_directory(self):
        self.desktop()
        records = self.state['desktop_shortcuts']
        self.assertEqual(len(records), 2)
        for name, digest in records.items():
            path = Path(name)
            self.assertIn('Exec=xdg-open http://127.0.0.1:3010', path.read_text())
            self.assertIn('Icon='+str(self.root/'bin/semantic-manager/assets/ios.png'), path.read_text())
            self.assertNotIn('secret-MUST', path.read_text())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            if shutil.which('desktop-file-validate'):
                result = subprocess.run(['desktop-file-validate', str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_modified_or_symlinked_shortcut_is_preserved(self):
        self.desktop()
        paths = list(map(Path, self.state['desktop_shortcuts']))
        paths[0].write_text('user edit')
        target = self.home/'outside'
        target.write_text('outside')
        paths[1].unlink()
        paths[1].symlink_to(target)
        self.desktop()
        self.assertEqual(paths[0].read_text(), 'user edit')
        self.assertTrue(paths[1].is_symlink())
        self.assertEqual(target.read_text(), 'outside')

    def test_headless_auto_skips_desktop(self):
        self.assertIn('未检测到桌面', self.desktop(mode='auto'))
        self.assertNotIn('desktop_shortcuts', self.state)

    def test_uninstall_removes_only_unmodified_owned_shortcuts(self):
        self.desktop()
        paths = list(map(Path, self.state['desktop_shortcuts']))
        paths[0].write_text('user edit')
        with patch.object(Path, 'home', return_value=self.home):
            uninstall.uninstall_shortcuts(self.root, self.state, lambda _: None, dry_run=True)
            self.assertTrue(paths[1].exists())
            uninstall.uninstall_shortcuts(self.root, self.state, lambda _: None)
        self.assertEqual(paths[0].read_text(), 'user edit')
        self.assertFalse(paths[1].exists())

    def test_manager_update_preserves_business_release(self):
        payload = self.home/'payload'
        payload.mkdir()
        for name in ('installer.py', 'install_support.py', 'uninstall.py'):
            shutil.copyfile(ROOT/'artifacts/runtime'/name, payload/name)
        shutil.copytree(ROOT/'artifacts/assets', payload/'assets')
        original = self.root/'original-release'
        original.write_bytes(b'not changed')
        installer.install_manager(self.root, payload)
        self.assertEqual(original.read_bytes(), b'not changed')
        self.assertIn('semantic-manager/installer.py', (self.root/'bin/semanticctl').read_text())
        self.assertEqual((self.root/'bin/semantic-manager/assets/ios.png').read_bytes(), (ROOT/'artifacts/assets/ios.png').read_bytes())

    def test_standalone_installer_does_not_add_unlisted_bytecode(self):
        payload = self.home/'payload'
        payload.mkdir()
        for name in ('installer.py', 'install_support.py', 'uninstall.py'):
            shutil.copyfile(ROOT/'artifacts/runtime'/name, payload/name)
        (payload/'release.json').write_text(json.dumps(dict(version='0.5.0-dev.test', minimum_glibc='2.28')))
        records = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.iterdir()}
        (payload/'files.json').write_text(json.dumps(records))
        result = subprocess.run([sys.executable, str(payload/'installer.py'), 'install', '--payload', str(payload),
                                 '--dir', str(self.home/'new-instance'), '--yes', '--web-port', '1'], capture_output=True, text=True)
        self.assertIn('端口必须', result.stderr)
        self.assertNotIn('未列入', result.stderr)
        self.assertFalse((payload/'__pycache__').exists())

    def test_success_refreshes_to_welcome_only_and_preserves_scrollback(self):
        class Screen(io.StringIO):
            def isatty(self): return True
        output = Screen()
        with patch.dict(os.environ, {'TERM': 'xterm-256color'}, clear=True), \
             patch.object(support, 'columns', return_value=79), patch.object(support, 'height', return_value=24), \
             patch.object(support, 'lan_addresses', return_value=[]), patch('builtins.open', side_effect=OSError('no tty')):
            progress = support.Progress(['测试安装任务'], output)
            progress.next('测试安装任务')
            progress.finish()
            support.welcome(self.root, self.state, True, stream=output)
        screen = output.getvalue().rsplit('\033[2J\033[H', 1)[-1]
        self.assertIn('欢迎使用', screen)
        self.assertNotIn('测试安装任务', screen)
        self.assertNotIn('\033[3J', output.getvalue())
        self.assertIn('\033[1;36m', screen)
        self.assertIn('\033[1;32m', screen)

    def test_failed_dashboard_remains_visible(self):
        class Screen(io.StringIO):
            def isatty(self): return True
        output = Screen()
        with patch.dict(os.environ, {'TERM': 'xterm'}), patch.object(support, 'height', return_value=24):
            progress = support.Progress(['系统依赖', '启动服务'], output)
            progress.next('系统依赖')
            progress.finish(RuntimeError('failed'))
        screen = output.getvalue().rsplit('\033[2J\033[H', 1)[-1]
        self.assertIn('失败', screen)
        self.assertIn('系统依赖', screen)
        self.assertNotIn('欢迎使用', screen)

    def test_forms_align_cjk_and_wrap_without_horizontal_overflow(self):
        for size in (19, 31, 39, 63, 79):
            output = io.StringIO()
            with patch.object(support, 'columns', return_value=size):
                console = support.Console(output)
                rendered = console.form('环境设置', [('当前会话', '中文路径/'*20), ('目录', '/some/very/long/path'*8)])
            self.assertTrue(all(support.width(row) <= size for row in rendered), (size, rendered))
            if size >= 39:
                # CJK labels and continuation values occupy the same number of cells.
                self.assertTrue(rendered[2].startswith(' '*12))

    def test_no_color_and_dumb_terminal_fallback(self):
        class Screen(io.StringIO):
            def isatty(self): return True
        for environment in ({'TERM': 'dumb'}, {'TERM': 'xterm', 'NO_COLOR': '1'}):
            output = Screen()
            with patch.dict(os.environ, environment, clear=True), patch('builtins.open', side_effect=OSError('no tty')), \
                 patch.object(support, 'lan_addresses', return_value=[]):
                support.welcome(self.root, self.state, True, stream=output)
            self.assertNotRegex(output.getvalue(), r'\x1b\[[0-9;]*m')
            if environment['TERM'] == 'dumb':
                self.assertNotIn('\x1b', output.getvalue())

    def test_text_only_welcome_fits_standard_terminal_even_with_banner_asset(self):
        class Screen(io.StringIO):
            def isatty(self): return True
        output = Screen()
        with patch.dict(os.environ, {'TERM': 'xterm'}), patch.object(support, 'columns', return_value=79), \
             patch.object(support, 'height', return_value=24), patch.object(support, 'lan_addresses', return_value=['192.168.1.20']), \
             patch.object(support, '__file__', str(ROOT/'artifacts/install_support.py')), patch('builtins.open', side_effect=OSError('no tty')):
            support.welcome(self.root, self.state, True, '快捷入口: test', stream=output)
        plain = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output.getvalue())
        self.assertLessEqual(len(plain.splitlines()), 24)
        self.assertTrue(all(support.width(row) <= 79 for row in plain.splitlines()))
        self.assertNotIn('#', plain)
        self.assertNotIn('*', plain)
        self.assertTrue(plain.startswith('  SEMANTIC\n'))


if __name__ == '__main__':
    unittest.main()
