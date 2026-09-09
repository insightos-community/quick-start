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

"""Regression tests with a real controlling PTY and piped stdin, not mocked open()."""
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import struct
import sys
import tempfile
import termios
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TerminalConfirmationTests(unittest.TestCase):
    def command(self, module, call):
        code = f"import runpy; m = runpy.run_path({str(ROOT/'artifacts/runtime'/module)!r}); {call}; print('CONFIRMED')"
        # A shell pipeline preserves /dev/tty but replaces the Python child's stdin.
        import shlex
        return ['bash', '-c', 'printf ignored | '+shlex.join([sys.executable, '-c', code])]

    def terminal(self, command, answer, timeout=10):
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            os.execvp(command[0], command)
        output = b''
        sent = False
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if not select.select([fd], [], [], .1)[0]:
                    continue
                try:
                    data = os.read(fd, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not data:
                    break
                output += data
                if b'[y/N]' in output and not sent:
                    os.write(fd, answer)
                    sent = True
            else:
                self.fail('PTY timeout: '+output.decode(errors='replace'))
            _, status = os.waitpid(pid, 0)
            pid = None
            return os.waitstatus_to_exitcode(status), output.decode(errors='replace')
        finally:
            os.close(fd)
            if pid is not None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)

    def test_install_and_uninstall_confirm_with_piped_stdin(self):
        for module, call in [('installer.py', "m['confirm']('安装测试')"),
                             ('uninstall.py', "m['uninstall_confirm']('/tmp/example', False, False)")]:
            for answer, accepted in [(b'y\n', True), (b'yes\n', True), (b'n\n', False), (b'\n', False), (b'\x04', False)]:
                with self.subTest(module=module, answer=answer):
                    rc, output = self.terminal(self.command(module, call), answer)
                    self.assertEqual(rc == 0, accepted, output)
                    self.assertIn('[y/N]', output)
                    self.assertNotIn('seekable', output)
                    if not accepted:
                        self.assertIn('用户取消', output)

    def test_no_controlling_terminal_requires_yes(self):
        for module, call in [('installer.py', "m['confirm']('test')"),
                             ('uninstall.py', "m['uninstall_confirm']('/tmp/example', False, False)")]:
            result = subprocess.run(self.command(module, call), start_new_session=True, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--yes', result.stderr)

    def test_yes_needs_no_terminal(self):
        for module, call in [('installer.py', "m['confirm']('test', True)"),
                             ('uninstall.py', "m['uninstall_confirm']('/tmp/example', False, True)")]:
            result = subprocess.run(self.command(module, call), start_new_session=True, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_sudo_authorization_with_piped_stdin_before_dashboard(self):
        import shutil
        for accepted in (True, False):
            with self.subTest(accepted=accepted), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fake = root/'sudo'
                shutil.copyfile(ROOT/'tests/fixtures/fake_sudo.py', fake)
                fake.chmod(0o755)
                log = root/'install.log'
                call = (f"import os; os.environ['PATH'] = {directory!r} + os.pathsep + os.environ['PATH']; "
                        f"os.environ['SEMANTIC_TEST_AUTH_MARKER'] = {str(root/'authorized')!r}; "
                        "os.environ['TERM'] = 'xterm-256color'; os.geteuid = lambda: 1000; "
                        f"m['authorize_dependencies']({str(log)!r}); "
                        "print('DASHBOARD_START', flush=True); "
                        "p = m['Progress'](['系统依赖']); "
                        "m['install_dependencies'].__globals__.update(PROGRESS=p, package_manager=lambda: 'apt-get'); "
                        "p.next('系统依赖'); "
                        f"m['install_dependencies']({str(log)!r}); p.finish()")
                answer = b'fake-secret-for-pty\n' if accepted else b'incorrect\n'
                rc, output = self.terminal(self.command('installer.py', call), answer)
                self.assertEqual(rc == 0, accepted, output)
                self.assertIn('sudo 授权', output)
                self.assertNotIn('fake-secret-for-pty', output)
                self.assertNotIn('fake-secret-for-pty', log.read_text())
                if accepted:
                    self.assertLess(output.index('TEST PASSWORD'), output.index('DASHBOARD_START'))
                    self.assertIn('sudo -n apt-get update', log.read_text())
                    self.assertIn('FAKE_DEPENDENCY_OK', log.read_text())
                else:
                    self.assertNotIn('\r\nDASHBOARD_START\r\n', output)
                    self.assertIn('未启动依赖安装', output)


if __name__ == '__main__':
    unittest.main()
