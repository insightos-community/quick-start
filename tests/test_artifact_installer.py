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

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import socket
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_installer', ROOT/'artifacts/runtime/installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ArtifactInstallerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def payload(self):
        (self.root/'release.json').write_text('{"version":"0.5.0-dev.1"}')
        (self.root/'file').write_bytes(b'payload')
        records = {p.name: installer.digest(p) for p in self.root.iterdir()}
        (self.root/'files.json').write_text(json.dumps(records))

    def test_payload_hashes_and_extra_files(self):
        self.payload()
        self.assertEqual(installer.verify_payload(self.root)['version'], '0.5.0-dev.1')
        (self.root/'extra').write_text('unlisted')
        with self.assertRaisesRegex(ValueError, '未列入'):
            installer.verify_payload(self.root)

    def test_corrupted_payload_is_rejected(self):
        self.payload()
        (self.root/'file').write_text('corrupted')
        with self.assertRaisesRegex(ValueError, '校验失败'):
            installer.verify_payload(self.root)

    def test_manifest_traversal_is_rejected(self):
        (self.root/'files.json').write_text(json.dumps({'../escape': '0'*64}))
        with self.assertRaisesRegex(ValueError, '非法'):
            installer.verify_payload(self.root)

    def test_symlink_is_rejected(self):
        self.payload()
        (self.root/'file').unlink()
        (self.root/'file').symlink_to(self.root/'release.json')
        with self.assertRaisesRegex(ValueError, '符号链接'):
            installer.verify_payload(self.root)

    def test_secret_file_permissions(self):
        installer.write_json(self.root/'secrets.json', {'password': 'example'})
        self.assertEqual((self.root/'secrets.json').stat().st_mode & 0o777, 0o600)

    def test_pid_reuse_or_unknown_identity_is_not_owned(self):
        with patch.object(installer, 'process_identity', return_value='new'):
            self.assertFalse(installer.alive({'pid': 1, 'start_ticks': 'old'}))
        with patch.object(installer, 'process_identity', return_value=None):
            self.assertFalse(installer.alive({'pid': 1, 'start_ticks': None}))

    def test_port_probe_rejects_listener_but_allows_time_wait(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen()
            with self.assertRaisesRegex(RuntimeError, '已占用'):
                installer.check_port(port)
            with socket.create_connection(('127.0.0.1', port)) as client:
                connection, _ = listener.accept()
                connection.close()  # Server actively closes, leaving TIME_WAIT.
                self.assertEqual(client.recv(1), b'')
        installer.check_port(port)

    def bootstrap(self, archive, checksum):
        return subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), '--package', str(archive),
                               '--sha256', checksum, '--yes'], capture_output=True, text=True)

    def test_bootstrap_rejects_bad_checksum(self):
        archive = self.root/'bad.tar.gz'
        archive.write_bytes(b'invalid archive')
        result = self.bootstrap(archive, '0'*64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA256 不匹配', result.stderr)

    def test_bootstrap_rejects_archive_traversal_and_links(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('symlink', tarfile.SYMTYPE)]:
            with self.subTest(kind=kind):
                archive = self.root/'unsafe.tar.gz'
                with tarfile.open(archive, 'w:gz') as tar:
                    info = tarfile.TarInfo(name)
                    info.type = kind
                    if kind == tarfile.SYMTYPE:
                        info.linkname = '/etc/passwd'
                    tar.addfile(info, io.BytesIO(b''))
                result = self.bootstrap(archive, installer.digest(archive))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('不安全的归档', result.stderr)

    def test_bootstrap_pipe_reads_options_not_stdin_prompts(self):
        result = subprocess.run(['bash', '-s', '--', '--help'], input=(ROOT/'artifacts/install.sh').read_text(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--base-url', result.stdout)

    def test_package_manager_distro_mapping(self):
        for distro, expected in [('ubuntu', 'apt-get'), ('debian', 'apt-get'),
                                 ('fedora', 'dnf'), ('rocky', 'dnf'), ('almalinux', 'dnf'),
                                 ('arch', 'pacman'), ('manjaro', 'pacman'),
                                 ('opensuse-leap', 'zypper'), ('opensuse-tumbleweed', 'zypper')]:
            with self.subTest(distro=distro), patch.object(installer.shutil, 'which', side_effect=lambda x: '/bin/'+x):
                self.assertEqual(installer.package_manager({'ID': distro}), expected)

    def test_package_manager_derivative_and_yum_fallback(self):
        with patch.object(installer.shutil, 'which', side_effect=lambda x: '/bin/yum' if x == 'yum' else None):
            self.assertEqual(installer.package_manager({'ID': 'custom', 'ID_LIKE': 'rhel fedora'}), 'yum')
        with patch.object(installer.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '不支持'):
                installer.package_manager({'ID': 'ubuntu'})
        with self.assertRaisesRegex(RuntimeError, '不支持'):
            installer.package_manager({'ID': 'alpine'})

    def test_dependency_commands_never_upgrade_system_or_disable_signatures(self):
        for manager in installer.SYSTEM_PACKAGES:
            commands = installer.dependency_commands(manager)
            self.assertTrue(commands)
            self.assertTrue(all(command[0] == manager for command in commands))
            args = [a for command in commands for a in command]
            for forbidden in ('upgrade', 'dist-upgrade', '-Sy', '-Syu', '--nogpgcheck', '--allow-unauthenticated'):
                self.assertNotIn(forbidden, args)
            self.assertNotIn('libyaml-cpp0.8', args)
            self.assertNotIn('libssl3t64', args)

    def test_dependency_install_uses_log_and_sudo(self):
        log = self.root/'install.log'
        with patch.object(installer, 'package_manager', return_value='dnf'), \
             patch.object(installer.os, 'geteuid', return_value=1000), \
             patch.object(installer.shutil, 'which', return_value='/usr/bin/sudo'), \
             patch.object(installer, 'run') as run:
            installer.install_dependencies(log)
        self.assertEqual(run.call_args.args[0][:5], ['sudo', '-n', 'dnf', 'install', '-y'])
        self.assertEqual(run.call_args.args[1], log)

    def test_dependency_install_without_privilege_fails_before_command(self):
        with patch.object(installer, 'package_manager', return_value='dnf'), \
             patch.object(installer.os, 'geteuid', return_value=1000), \
             patch.object(installer.shutil, 'which', return_value=None), \
             patch.object(installer, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'root 或 sudo'):
                installer.install_dependencies(self.root/'log')
            run.assert_not_called()

    def test_sudo_authorization_root_or_cached_does_not_prompt(self):
        for uid in (0, 1000):
            with self.subTest(uid=uid), patch.object(installer.os, 'geteuid', return_value=uid), \
                 patch.object(installer.shutil, 'which', return_value='/usr/bin/sudo'), \
                 patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run, \
                 patch('builtins.open', side_effect=AssertionError('must not open tty')):
                installer.authorize_dependencies(self.root/'log')
                if uid:
                    self.assertEqual(run.call_args.args[0], ['sudo', '-n', '-v'])
                    self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
                else:
                    run.assert_not_called()

    def test_sudo_authorization_missing_sudo_or_tty_fails(self):
        for available in (False, True):
            with self.subTest(available=available), patch.object(installer.os, 'geteuid', return_value=1000), \
                 patch.object(installer.shutil, 'which', return_value='/bin/sudo' if available else None), \
                 patch.object(installer.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run, \
                 patch('builtins.open', side_effect=OSError('no tty')):
                with self.assertRaisesRegex(RuntimeError, '--yes 不会代替 sudo 授权' if available else 'root 或 sudo'):
                    installer.authorize_dependencies(self.root/'log')
                self.assertEqual(run.call_count, int(available))
        self.assertIn('失败', (self.root/'log').read_text())

    def test_sudo_authorization_timeout_is_bounded(self):
        with patch.object(installer.os, 'geteuid', return_value=1000), \
             patch.object(installer.shutil, 'which', return_value='/bin/sudo'), \
             patch.object(installer.subprocess, 'run', side_effect=subprocess.TimeoutExpired('sudo', 15)):
            with self.assertRaisesRegex(RuntimeError, '权限检查超时'):
                installer.authorize_dependencies(self.root/'log')
        self.assertIn('超时', (self.root/'log').read_text())

    def test_authorization_precedes_dashboard_and_dependency_commands(self):
        args = SimpleNamespace(payload=self.root/'payload', dir=str(self.root/'install'),
            http_port=18080, ws_port=18081, web_port=13000, runtime_port=18090,
            web_host=None, desktop='never', yes=True, install_system_deps=True)
        with patch.object(installer, 'verify_payload', return_value={'version': '0.5.0-dev.9'}), \
             patch.object(installer, 'check_platform'), patch.object(installer, 'settings_form'), \
             patch.object(installer, 'package_manager', return_value='apt-get'), \
             patch.object(installer, 'authorize_dependencies', side_effect=RuntimeError('auth stopped')) as auth, \
             patch.object(installer, 'Progress') as progress, \
             patch.object(installer, 'install_dependencies') as dependencies, \
             patch.object(installer, 'INSTALL_LOG', None):
            with self.assertRaisesRegex(RuntimeError, 'auth stopped'):
                installer.install(args)
            self.assertTrue(auth.call_args.args[0].is_file())
            progress.assert_not_called()
            dependencies.assert_not_called()

    def test_new_install_defaults_to_all_interfaces_and_honors_explicit_host(self):
        for requested, expected in [(None, '0.0.0.0'), ('127.0.0.1', '127.0.0.1'), ('192.168.1.10', '192.168.1.10')]:
            args = SimpleNamespace(payload=self.root/'payload', dir=str(self.root/'install'),
                http_port=18080, ws_port=18081, web_port=13000, runtime_port=18090,
                web_host=requested, desktop='never', yes=False)
            with self.subTest(requested=requested), \
                 patch.object(installer, 'verify_payload', return_value={'version': '0.5.0-dev.10'}), \
                 patch.object(installer, 'check_platform'), patch.object(installer, 'settings_form') as form, \
                 patch.object(installer, 'confirm', side_effect=RuntimeError('cancel')):
                with self.assertRaisesRegex(RuntimeError, 'cancel'):
                    installer.install(args)
                self.assertIn(('Web', f'{expected}:13000', 'command'), form.call_args.args[1])

    def test_reinstall_preserves_existing_loopback_in_preview(self):
        root = self.root/'install'
        root.mkdir()
        (root/'.semantic-install-root').touch()
        installer.write_json(root/'install.json', {'version': '0.5.0-dev.9', 'web_host': '127.0.0.1'})
        args = SimpleNamespace(payload=self.root/'payload', dir=str(root),
            http_port=18080, ws_port=18081, web_port=13000, runtime_port=18090,
            web_host=None, desktop='never', yes=False)
        with patch.object(installer, 'verify_payload', return_value={'version': '0.5.0-dev.9'}), \
             patch.object(installer, 'check_platform'), patch.object(installer, 'settings_form') as form, \
             patch.object(installer, 'confirm', side_effect=RuntimeError('cancel')):
            with self.assertRaisesRegex(RuntimeError, 'cancel'):
                installer.install(args)
            self.assertIn(('Web', '127.0.0.1:13000', 'command'), form.call_args.args[1])

    def test_command_logs_start_before_execution_and_never_reads_stdin(self):
        log = self.root/'command.log'
        def execute(command, **kwargs):
            self.assertIn('START sudo', log.read_text())
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            return SimpleNamespace(returncode=1)
        with patch.object(installer.subprocess, 'run', side_effect=execute):
            with self.assertRaisesRegex(RuntimeError, 'sudo 不会等待密码'):
                installer.run(['sudo', '-n', 'apt-get', 'update'], log)
        self.assertIn('END sudo rc=1 elapsed=', log.read_text())

    def test_platform_uses_release_baseline_not_build_host(self):
        with patch.object(installer.platform, 'system', return_value='Linux'), \
             patch.object(installer.platform, 'machine', return_value='x86_64'), \
             patch.object(installer.platform, 'libc_ver', return_value=('glibc', '2.31')):
            installer.check_platform({'minimum_glibc': '2.28'})
            with self.assertRaisesRegex(RuntimeError, '2.39'):
                installer.check_platform({'minimum_glibc': '2.39'})
            with self.assertRaisesRegex(ValueError, '无效'):
                installer.check_platform({'minimum_glibc': 'oops'})

    def test_platform_rejects_musl_old_glibc_and_wrong_arch(self):
        for machine, libc in [('aarch64', ('glibc', '2.39')), ('x86_64', ('musl', '1.2')),
                              ('x86_64', ('glibc', '2.17'))]:
            with self.subTest(machine=machine, libc=libc), \
                 patch.object(installer.platform, 'system', return_value='Linux'), \
                 patch.object(installer.platform, 'machine', return_value=machine), \
                 patch.object(installer.platform, 'libc_ver', return_value=libc):
                with self.assertRaises(RuntimeError):
                    installer.check_platform({'minimum_glibc': '2.28'})


if __name__ == '__main__':
    unittest.main()
