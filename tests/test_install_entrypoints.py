# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Exercise the standalone scripts outside the source checkout, without network."""
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallEntrypointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='semantic-entrypoints-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        for name in ('install.sh', 'install-en.sh'):
            shutil.copyfile(ROOT/name, self.work/name)
        # Capture the actual first download request. Never reach an external host
        # or execute an installer payload while checking source selection.
        (self.work/'sitecustomize.py').write_text(
            'import urllib.request\n'
            'def capture(request, *args, **kwargs):\n'
            '    print("DOWNLOAD=" + (request if isinstance(request, str) else request.full_url))\n'
            '    raise SystemExit(73)\n'
            'urllib.request.urlopen = capture\n'
            'urllib.request.OpenerDirector.open = lambda self, request, *args, **kwargs: capture(request)\n')

    def run_script(self, name, *args, pipe=False, **environment):
        env = dict(os.environ, PYTHONPATH=str(self.work))
        env.pop('SEMANTIC_DOWNLOAD_BASE', None)
        env.update(environment)
        command = ['bash', '-s', '--'] if pipe else ['bash', str(self.work/name)]
        return subprocess.run(command + list(args), cwd=self.work, env=env,
                              input=(self.work/name).read_text() if pipe else '',
                              text=True, capture_output=True, timeout=15)

    def test_default_download_sources_work_without_checkout(self):
        for name, expected in [
            ('install.sh', 'https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/channels/stable.json'),
            ('install-en.sh', 'https://github.com/insightos-community/quick-start/releases/download/v0.1.0/SHA256SUMS'),
        ]:
            with self.subTest(name=name):
                result = self.run_script(name, pipe=True)
                self.assertEqual(result.returncode, 73, result.stderr)
                self.assertIn('DOWNLOAD='+expected, result.stdout)

    def test_version_and_source_overrides_are_forwarded(self):
        cases = [
            ('install.sh', ['--version', '0.5.0-example'], {},
             'https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/releases/0.5.0-example/linux-x86_64/manifest.json'),
            ('install.sh', [], {'SEMANTIC_DOWNLOAD_BASE': 'https://mirror.example/semantic'},
             'https://mirror.example/semantic/channels/stable.json'),
            ('install.sh', ['--base-url', 'https://explicit.example/semantic'],
             {'SEMANTIC_DOWNLOAD_BASE': 'https://mirror.example/semantic'},
             'https://explicit.example/semantic/channels/stable.json'),
            ('install-en.sh', ['--version', 'v0.2.0'],
             {'SEMANTIC_DOWNLOAD_BASE': 'https://mirror.example/semantic'},
             'https://github.com/insightos-community/quick-start/releases/download/v0.2.0/SHA256SUMS'),
            ('install-en.sh', ['--base-url', 'https://explicit.example/semantic'], {},
             'https://explicit.example/semantic/channels/stable.json'),
        ]
        for name, args, env, expected in cases:
            with self.subTest(name=name, args=args, env=env):
                result = self.run_script(name, *args, pipe=True, **env)
                self.assertEqual(result.returncode, 73, result.stderr)
                self.assertIn('DOWNLOAD='+expected, result.stdout)

    def test_local_package_checksums_and_archive_boundaries(self):
        archive = self.work/'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            output.addfile(tarfile.TarInfo('../escape'), io.BytesIO(b''))
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        for name in ('install.sh', 'install-en.sh'):
            for digest, message in [('0'*64, 'SHA256'), (checksum, '归档' if name == 'install.sh' else 'archive')]:
                with self.subTest(name=name, digest=digest):
                    result = self.run_script(name, '--package', str(archive), '--sha256', digest,
                                             '--dir', str(self.work/'instance'), '--yes', pipe=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotEqual(result.returncode, 73)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn('DOWNLOAD=', result.stdout)
                    self.assertFalse((self.work/'escape').exists())
                    self.assertFalse((self.work/'instance').exists())


if __name__ == '__main__':
    unittest.main()
