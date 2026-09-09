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

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_uninstall', ROOT/'artifacts/runtime/uninstall.py')
uninstaller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uninstaller)


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='semantic-uninstall-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'instance with spaces'
        self.root.mkdir()
        (self.root/'.semantic-install-root').touch()
        (self.root/'install.json').write_text(json.dumps({'version': '0.5.0-dev.test', 'ready': True, 'configured': True}))
        for name in (*uninstaller.UNINSTALL_DIRS, 'configs', 'data', 'logs', 'run', 'content', 'runtimes.d'):
            (self.root/name).mkdir()
            (self.root/name/'sentinel').write_text('preserve or delete by policy')
        (self.root/'releases/v1').mkdir()
        (self.root/'current').symlink_to('releases/v1')
        (self.root/'run/services.json').write_text('{}')

    def bootstrap(self, *args, pipe=False):
        if pipe:
            return subprocess.run(['bash', '-s', '--', '--uninstall', '--dir', str(self.root), *args],
                input=(ROOT/'artifacts/install.sh').read_text(), text=True, capture_output=True)
        return subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), '--uninstall', '--dir', str(self.root), *args],
                              text=True, capture_output=True)

    def test_embedded_uninstaller_matches_source(self):
        script = (ROOT/'artifacts/install.sh').read_text()
        embedded = script.split('# BEGIN EMBEDDED UNINSTALLER\n')[1].split('# END EMBEDDED UNINSTALLER')[0]
        self.assertEqual(embedded.strip(), (ROOT/'artifacts/runtime/uninstall.py').read_text().strip())

    def test_default_removes_only_programs_and_preserves_data(self):
        result = self.bootstrap('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in uninstaller.UNINSTALL_DIRS:
            self.assertFalse((self.root/name).exists(), name)
        for name in ('configs', 'data', 'logs', 'content', 'runtimes.d'):
            self.assertEqual((self.root/name/'sentinel').read_text(), 'preserve or delete by policy')
        self.assertFalse((self.root/'current').is_symlink())
        self.assertFalse(json.loads((self.root/'install.json').read_text())['ready'])
        self.assertEqual((self.root/'install.json').stat().st_mode & 0o777, 0o600)

    def test_pipe_purge_is_offline_and_keeps_audit_log_outside_root(self):
        result = self.bootstrap('--yes', '--purge', pipe=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.root.exists())
        logfile = Path(result.stdout.split('卸载日志: ', 1)[1].splitlines()[0])
        self.assertTrue(logfile.is_file())
        self.assertEqual(logfile.stat().st_mode & 0o777, 0o600)
        self.assertIn('purge complete', logfile.read_text())
        logfile.unlink()  # Only this test's generated audit log.

    def test_default_uninstall_is_repeatable_then_can_purge(self):
        for _ in range(2):
            result = self.bootstrap('--yes')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.bootstrap('--yes', '--purge').returncode, 0)

    def test_dry_run_does_not_change_instance(self):
        before = (self.root/'install.json').read_bytes()
        result = self.bootstrap('--dry-run', '--purge')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root/'releases/sentinel').exists())
        self.assertEqual((self.root/'install.json').read_bytes(), before)
        self.assertFalse((self.root/'run/install.lock').exists())

    def test_unknown_arguments_fail_without_deleting(self):
        self.assertNotEqual(self.bootstrap('--yes', '--force').returncode, 0)
        self.assertTrue((self.root/'data/sentinel').exists())

    def test_noninteractive_requires_explicit_confirmation(self):
        # New session has no controlling tty, matching an unattended pipe.
        result = subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), '--uninstall', '--dir', str(self.root)],
                                start_new_session=True, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--yes', result.stderr)
        self.assertTrue((self.root/'releases/sentinel').exists())

    def test_foreign_directory_and_invalid_state_rejected(self):
        (self.root/'.semantic-install-root').unlink()
        self.assertNotEqual(self.bootstrap('--yes', '--purge').returncode, 0)
        self.assertTrue((self.root/'data/sentinel').exists())
        (self.root/'.semantic-install-root').touch()
        (self.root/'install.json').write_text('{}')
        self.assertNotEqual(self.bootstrap('--yes', '--purge').returncode, 0)

    def test_broad_relative_and_symlink_roots_rejected(self):
        alias = Path(self.tmp.name)/'alias'
        alias.symlink_to(self.root)
        for target in ('/', '/tmp', str(Path.home()), str(ROOT), '.', str(alias)):
            with self.subTest(target=target), self.assertRaises(ValueError):
                uninstaller.uninstall_root(target)

    def test_symlinked_management_directory_rejected(self):
        outside = Path(self.tmp.name)/'outside'
        outside.mkdir()
        (self.root/'run').rename(self.root/'old-run')
        (self.root/'run').symlink_to(outside)
        self.assertNotEqual(self.bootstrap('--yes', '--purge').returncode, 0)
        self.assertTrue(outside.exists())

    def test_internal_symlinks_never_delete_external_targets(self):
        outside = Path(self.tmp.name)/'outside'
        outside.mkdir()
        (outside/'keep').write_text('external')
        (self.root/'releases/external-link').symlink_to(outside)
        self.assertEqual(self.bootstrap('--yes', '--purge').returncode, 0)
        self.assertEqual((outside/'keep').read_text(), 'external')

    def test_concurrent_install_lock_blocks_deletion(self):
        with (self.root/'run/install.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertNotEqual(self.bootstrap('--yes', '--purge').returncode, 0)
        self.assertTrue((self.root/'data/sentinel').exists())

    def child(self, command):
        proc = subprocess.Popen(command, start_new_session=True, cwd=self.tmp.name)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
        self.addCleanup(cleanup)
        return proc

    def test_active_robot_blocks_before_stopping_services_or_deleting(self):
        proc = self.child([sys.executable, '-c', 'import time; time.sleep(30)', str(self.root/'data/robot')])
        result = self.bootstrap('--yes', '--purge')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('活动进程', result.stderr)
        self.assertIsNone(proc.poll())
        self.assertTrue((self.root/'data/sentinel').exists())

    def shell_in(self, directory):
        proc = subprocess.Popen(['/bin/bash', '--noprofile', '--norc', '-c', "printf 'ready\\n'; read -r -t 60 unused"],
                                cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
            proc.stdin.close()
            proc.stdout.close()
        self.addCleanup(cleanup)
        self.assertEqual(proc.stdout.readline(), b'ready\n')
        return proc

    def test_shell_in_deleted_directory_does_not_block_or_get_killed(self):
        directory = self.root/'logs/old-terminal'
        directory.mkdir()
        proc = self.shell_in(directory)
        directory.rmdir()
        self.assertEqual(Path(f'/proc/{proc.pid}/cwd').stat().st_nlink, 0)
        # Also reproduce a new live directory at the old path after reinstallation.
        directory.mkdir()
        result = self.bootstrap('--yes', '--purge')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.root.exists())
        self.assertIsNone(proc.poll(), 'the unrelated terminal must remain alive')

    def test_live_shell_cwd_explains_cd_instead_of_kill_even_with_deleted_suffix(self):
        directory = self.root/'logs/live (deleted)'
        directory.mkdir()
        proc = self.shell_in(directory)
        result = self.bootstrap('--yes', '--purge')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(proc.pid), result.stderr)
        self.assertIn('bash', result.stderr)
        self.assertIn('工作目录', result.stderr)
        self.assertIn('cd ~', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIsNone(proc.poll())
        self.assertTrue(directory.is_dir())

    def test_deleted_cwd_does_not_hide_a_live_instance_executable(self):
        binary = self.root/'releases/v1/busy-worker'
        shutil.copy2('/bin/sleep', binary)
        directory = self.root/'logs/removed'
        directory.mkdir()
        proc = subprocess.Popen([str(binary), '60'], cwd=directory, start_new_session=True)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
        self.addCleanup(cleanup)
        directory.rmdir()
        result = self.bootstrap('--yes', '--purge')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('可执行文件', result.stderr)
        self.assertIsNone(proc.poll())
        self.assertTrue(binary.is_file())

    def test_control_status_is_explicit_and_uninstall_has_cli_entry(self):
        command = [sys.executable, '-B', str(ROOT/'artifacts/runtime/installer.py'), 'control', '--root', str(self.root)]
        result = subprocess.run([*command, 'status'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Server', result.stdout)
        self.assertIn('Web', result.stdout)
        self.assertIn('已停止', result.stdout)
        self.assertIn('0 个进程', result.stdout)
        result = subprocess.run([*command, 'uninstall', '--dry-run'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root/'releases').exists())
        result = subprocess.run([*command, 'uninstall', '--yes'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root/'releases').exists())
        self.assertTrue((self.root/'data/sentinel').exists())

    def test_verified_server_is_stopped(self):
        binary = self.root/'releases/v1/bin/semantic-server'
        binary.parent.mkdir()
        shutil.copy2('/bin/sleep', binary)
        proc = self.child([str(binary), '30'])
        (self.root/'run/services.json').write_text(json.dumps({'server': {
            'pid': proc.pid, 'start_ticks': uninstaller.uninstall_identity(proc.pid)}}))
        result = self.bootstrap('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(proc.poll())

    def test_forged_live_pid_is_not_killed(self):
        proc = self.child(['/bin/sleep', '30'])
        (self.root/'run/services.json').write_text(json.dumps({'server': {
            'pid': proc.pid, 'start_ticks': uninstaller.uninstall_identity(proc.pid)}}))
        self.assertNotEqual(self.bootstrap('--yes', '--purge').returncode, 0)
        self.assertIsNone(proc.poll())

    def test_stale_pid_is_not_killed(self):
        proc = self.child(['/bin/sleep', '30'])
        (self.root/'run/services.json').write_text(json.dumps({'server': {'pid': proc.pid, 'start_ticks': 'stale'}}))
        result = self.bootstrap('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(proc.poll())

    def test_timeout_does_not_delete_or_force_kill(self):
        with patch.object(uninstaller, 'uninstall_managed', return_value={12345: 'identity'}), \
             patch.object(uninstaller, 'uninstall_busy'), \
             patch.object(uninstaller, 'uninstall_identity', return_value='identity'), \
             patch.object(uninstaller.os, 'kill') as kill, \
             patch.object(uninstaller.time, 'monotonic', side_effect=[0, 21]):
            with self.assertRaisesRegex(RuntimeError, '不强制'):
                uninstaller.uninstall_entry(['--dir', str(self.root), '--yes', '--purge'])
        kill.assert_called_once_with(12345, uninstaller.signal.SIGTERM)
        self.assertTrue((self.root/'releases/sentinel').exists())

    def test_mount_point_is_rejected(self):
        original = Path.read_text
        mount = str(self.root/'data').replace(' ', r'\040')
        def read(path, *args, **kwargs):
            if path == Path('/proc/self/mountinfo'):
                return f'1 2 0:1 / {mount} rw - tmpfs tmpfs rw\n'
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read), self.assertRaisesRegex(ValueError, '挂载点'):
            uninstaller.uninstall_root(str(self.root))

    def test_purge_without_uninstall_is_rejected(self):
        result = subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), '--purge', '--dir', str(self.root)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('必须与 --uninstall', result.stderr)

    def test_positional_uninstall_is_supported(self):
        result = subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), 'uninstall', '--dir', str(self.root), '--yes'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
