# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at https://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# See the License for the specific language governing permissions and limitations.

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'artifacts/install-en.sh'
spec = importlib.util.spec_from_file_location('english_generator', ROOT/'artifacts/build_english_installer.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class EnglishInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='semantic-english-test-')
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def bootstrap(self, *args, pipe=False):
        command = ['bash', '-s', '--'] if pipe else ['bash', str(SCRIPT)]
        return subprocess.run(command+list(args), input=SCRIPT.read_text() if pipe else '',
                              capture_output=True, text=True, start_new_session=True, timeout=15)

    def assertEnglish(self, text):
        self.assertNotRegex(text, '[\u4e00-\u9fff]')

    def test_generated_script_is_current(self):
        self.assertEqual(SCRIPT.read_text(), generator.render())
        subprocess.run(['bash', '-n', str(SCRIPT)], check=True)

    def test_untranslated_strings_fail_generation(self):
        with self.assertRaisesRegex(ValueError, 'Missing English translation'):
            generator.translate("print('未翻译的新消息')\n")

    def test_only_string_nodes_are_translated(self):
        class NormalizeStrings(ast.NodeTransformer):
            def visit_Constant(self, node):
                if isinstance(node.value, str):
                    return ast.copy_location(ast.Constant(value='STRING'), node)
                return node
        for name in ('installer.py', 'install_support.py', 'uninstall.py'):
            original = (ROOT/'artifacts/runtime'/name).read_text()
            before = NormalizeStrings().visit(ast.parse(original))
            after = NormalizeStrings().visit(ast.parse(generator.translate(original)))
            self.assertEqual(ast.dump(before), ast.dump(after), name)

    def test_help_and_uninstall_help_are_english_and_pipe_safe(self):
        for args in [('--help',), ('--uninstall', '--help')]:
            result = self.bootstrap(*args, pipe=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEnglish(result.stdout+result.stderr)
            self.assertIn('--dir', result.stdout)

    def test_uninstall_invalid_root_is_safe_and_english(self):
        result = self.bootstrap('--uninstall', '--dir', '/', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Uninstall refused', result.stderr)
        self.assertEnglish(result.stdout+result.stderr)

    def test_bad_checksum_is_rejected_before_extraction(self):
        archive = self.work/'bad.tar.gz'
        archive.write_bytes(b'not an archive')
        result = self.bootstrap('--package', str(archive), '--sha256', '0'*64, '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA256 mismatch', result.stderr)
        self.assertEnglish(result.stdout+result.stderr)

    def test_unsafe_archive_is_rejected(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)]:
            archive = self.work/'unsafe.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                if kind == tarfile.SYMTYPE:
                    entry.linkname = '/etc/passwd'
                tar.addfile(entry, io.BytesIO(b''))
            result = self.bootstrap('--package', str(archive), '--sha256', hashlib.sha256(archive.read_bytes()).hexdigest(), '--yes')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Unsafe archive path/link', result.stderr)
            self.assertFalse((self.work/'escape').exists())

    def test_existing_payload_uses_english_manager_without_repacking(self):
        payload = self.work/'payload'
        payload.mkdir()
        (payload/'release.json').write_text(json.dumps({'version': '0.5.0-dev.test', 'minimum_glibc': '2.17'}))
        (payload/'installer.py').write_text('raise SystemExit("LEGACY_MANAGER_MUST_NOT_RUN")\n')
        (payload/'files.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.iterdir()}))
        archive = self.work/'release.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for path in payload.iterdir():
                tar.add(path, arcname=path.name)
        result = self.bootstrap('--package', str(archive), '--sha256', hashlib.sha256(archive.read_bytes()).hexdigest(), '--dir', 'relative-path', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--dir must be an absolute path', result.stderr)
        self.assertNotIn('LEGACY_MANAGER_MUST_NOT_RUN', result.stderr)
        self.assertEnglish(result.stdout+result.stderr)
        self.assertNotIn('english-manager', (payload/'files.json').read_text())

    def test_offline_uninstall_dry_run_and_default_preservation(self):
        root = self.work/'instance'
        root.mkdir()
        (root/'.semantic-install-root').touch()
        (root/'install.json').write_text(json.dumps({'version': '0.5.0-dev.test', 'ready': True}))
        for name in ('releases', 'python', 'runtime-envs', 'runtime-packs', 'bin', 'data', 'configs', 'logs', 'run'):
            (root/name).mkdir()
        (root/'data/keep').write_text('user data')
        (root/'run/services.json').write_text('{}')
        result = self.bootstrap('--uninstall', '--dir', str(root), '--dry-run', pipe=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEnglish(result.stdout+result.stderr)
        self.assertTrue((root/'bin').exists())
        result = self.bootstrap('--uninstall', '--dir', str(root), '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEnglish(result.stdout+result.stderr)
        self.assertFalse((root/'bin').exists())
        self.assertEqual((root/'data/keep').read_text(), 'user data')

    def test_english_manager_persists_and_assets_remain_unchanged(self):
        modules = generator.manager_sources()
        manager = self.work/'english-manager'
        manager.mkdir()
        for name, content in modules.items():
            (manager/name).write_text(content)
        payload = self.work/'payload'
        (payload/'assets').mkdir(parents=True)
        for name in ('ios.png', 'banner.json'):
            (payload/'assets'/name).write_bytes(b'asset sentinel')
        root = self.work/'instance'
        root.mkdir()
        code = 'from pathlib import Path; import installer; installer.install_manager(Path('+repr(str(root))+'), Path('+repr(str(payload))+'))'
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=manager, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, content in modules.items():
            self.assertEqual((root/'bin/semantic-manager'/name).read_text(), content)
        self.assertEqual((root/'bin/semantic-manager/assets/ios.png').read_bytes(), b'asset sentinel')
        result = subprocess.run([str(root/'bin/semanticctl'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEnglish(result.stdout+result.stderr)
        self.assertIn('uninstall', result.stdout)

    def test_english_forms_fit_narrow_terminals_and_preserve_user_text(self):
        path = self.work/'support.py'
        path.write_text(generator.manager_sources()['install_support.py'])
        spec = importlib.util.spec_from_file_location('english_support_test', path)
        support = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(support)
        for size in (24, 40, 80):
            stream = io.StringIO()
            with patch.object(support, 'columns', return_value=size):
                console = support.Console(stream)
                rows = console.form('Installation settings', [('Directory', '/tmp/我的目录'), ('01 Running', 'System dependencies')])
                console.write(rows)
            self.assertTrue(all(support.width(line) <= size for line in stream.getvalue().splitlines()))
            self.assertIn('我的目录', stream.getvalue())
        stream = io.StringIO()
        with patch('builtins.open', side_effect=OSError), patch.object(support, 'lan_addresses', return_value=[]):
            support.welcome(self.work, {'version': 'test', 'web_host': '127.0.0.1', 'web_port': 3000}, False,
                            desktop_message=support.desktop_shortcuts(self.work, {}, mode='never'), stream=stream)
        self.assertEnglish(stream.getvalue())
        self.assertIn('Skipped', stream.getvalue())
        self.assertNotIn('Not created', stream.getvalue())


if __name__ == '__main__':
    unittest.main()
