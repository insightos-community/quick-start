# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import ast
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]


class PlatformBootstrapTests(unittest.TestCase):
    def selection(self, script, args, env=None):
        source = (ROOT / script).read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0]
        start = source.index('p = argparse.ArgumentParser(')
        end = source.index('def status(message):')
        prefix = 'import argparse, os, pathlib, re\n'
        namespace = {'arguments': args}
        with unittest.mock.patch.dict(os.environ, env or {}, clear=True):
            with unittest.mock.patch('sys.argv', ['bootstrap', *args]):
                exec(compile(ast.parse(prefix + source[start:end]), script, 'exec'), namespace)
        return namespace

    def test_tags_select_the_platform_and_release_source_in_both_languages(self):
        for script in ['install.sh', 'install-en.sh']:
            with self.subTest(script=script):
                ns = self.selection(script, ['--tag', 'musl-v0.1.0-2'])
                self.assertTrue(ns['a'].musl)
                self.assertTrue(ns['use_github'])
                self.assertIn('--musl', ns['rest'])
                ns = self.selection(script, ['--tag', 'v0.1.0'])
                self.assertFalse(ns['a'].musl)
                self.assertTrue(ns['use_github'])
                ns = self.selection(script, ['--source', 'oss'])
                self.assertFalse(ns['use_github'])
                self.assertIn('aliyuncs.com', ns['a'].base_url)
                with self.assertRaises(SystemExit):
                    self.selection(script, ['--tag', 'macos-v0.1.0-rc.2'])
                with self.assertRaises(SystemExit):
                    self.selection(script, ['--tag', 'v0.1.0', '--musl'])
                with self.assertRaises(SystemExit):
                    self.selection(script, ['--tag', 'v0.1.0', '--version', 'stable'])
                with self.assertRaises(SystemExit):
                    self.selection(script, ['--source', 'github', '--base-url', 'https://example.test'])
                with self.assertRaises(SystemExit):
                    self.selection(script, ['--tag', '$(touch bad)'])
        self.assertFalse(self.selection('install.sh', [])['use_github'])
        self.assertTrue(self.selection('install-en.sh', [])['use_github'])

    def test_macos_offline_route_needs_no_host_python_and_checks_archive_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / 'tools'; tools.mkdir()
            for name, body in [('uname', 'if [ "$1" = -s ]; then echo Darwin; else echo arm64; fi'),
                               ('python3', 'echo UNEXPECTED_HOST_PYTHON >&2; exit 99'),
                               ('curl', 'echo UNEXPECTED_NETWORK >&2; exit 98')]:
                path = tools / name; path.write_text('#!/bin/sh\n' + body + '\n'); path.chmod(0o755)
            archive = root / 'package.tar.gz'
            content = b'#!/bin/bash\nprintf "%s\\n" "$@"\n'
            with tarfile.open(archive, 'w:gz') as tar:
                member = tarfile.TarInfo('install.command'); member.mode = 0o755; member.size = len(content)
                tar.addfile(member, io.BytesIO(content))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            env = {**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH']}
            for script in ['install.sh', 'install-en.sh']:
                command = ['bash', str(ROOT / script), '--tag', 'macos-v0.1.0-rc.2', '--source', 'github', '--package', str(archive), '--sha256', digest, '--dir', str(root / 'instance with spaces'), '--no-start', '--yes']
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(str(root / 'instance with spaces'), result.stdout)
                bad = command.copy(); bad[bad.index('--sha256') + 1] = '0' * 64
                result = subprocess.run(bad, env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('SHA256 mismatch', result.stderr)
                result = subprocess.run(['bash', str(ROOT / script), '--musl'], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('musl requires Linux', result.stderr)
                result = subprocess.run(['bash', str(ROOT / script), '--source', 'oss'], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('not published', result.stderr)
