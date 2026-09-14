# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bootstrap_support', ROOT/'artifacts/bootstrap_support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class RetryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # macOS temporary roots may use /var -> /private/var; cache tests
        # need a canonical private directory, like the production cache under HOME.
        self.root = Path(temporary.name).resolve()

    def test_verified_cache_survives_failure_and_repairs_corruption(self):
        content = b'verified release content'
        digest = hashlib.sha256(content).hexdigest()
        download = Mock(side_effect=lambda url, path, limit: path.write_bytes(content))
        path = support.cached_archive('https://example.test/a', digest, self.root/'cache', download, lambda _: None)
        # The application installation failing does not own or remove this cache.
        self.assertTrue(path.is_file())
        self.assertEqual(support.cached_archive('https://example.test/b', digest, self.root/'cache', download, lambda _: None), path)
        self.assertEqual(download.call_count, 1)
        path.write_bytes(b'corrupt')
        self.assertEqual(support.cached_archive('https://example.test/a', digest, self.root/'cache', download, lambda _: None).read_bytes(), content)
        self.assertEqual(download.call_count, 2)

    def test_failed_download_never_becomes_a_cached_archive(self):
        digest = '0'*64
        def fail(url, path, limit):
            path.write_bytes(b'partial')
            raise OSError('network interrupted')
        with self.assertRaises(OSError):
            support.cached_archive('https://example.test/a', digest, self.root/'cache', fail)
        self.assertFalse((self.root/'cache'/f'{digest}.tar.gz').exists())
        self.assertFalse(list((self.root/'cache').glob('.download-*')))
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            support.cached_archive('https://example.test/a', digest, self.root/'cache', lambda u, p, l: p.write_bytes(b'bad'))
        self.assertFalse((self.root/'cache'/f'{digest}.tar.gz').exists())

    def test_cache_symlink_cannot_modify_an_outside_file(self):
        content = b'keep'; digest = hashlib.sha256(content).hexdigest()
        cache = self.root/'cache'; cache.mkdir(mode=0o700)
        outside = self.root/'outside'; outside.write_bytes(content)
        (cache/f'{digest}.tar.gz').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'Invalid cached archive'):
            support.cached_archive('https://example.test/a', digest, cache, Mock())
        self.assertEqual(outside.read_bytes(), content)

    def test_preflight_rejects_busy_runtime_even_with_no_start(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, f'Port {port}.*runtime'):
                support.bootstrap_preflight(['--dir', str(self.root/'instance'), '--no-start', '--runtime-port', str(port)])
        support.bootstrap_preflight(['--dir', str(self.root/'instance'), '--no-start', '--runtime-port', str(port)])

    def test_preflight_preserves_owned_running_instance(self):
        root = self.root/'instance'; (root/'run').mkdir(parents=True)
        (root/'.semantic-install-root').touch()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            (root/'install.json').write_text(json.dumps(dict(http_port=8080, ws_port=8081, web_port=port, runtime_port=8090, ready=True)))
            (root/'run/services.json').write_text(json.dumps({'web': {'pid': 123}, 'server': {'pid': 124}}))
            support.bootstrap_preflight(['--dir', str(root), '--web-port', str(port)], lambda _: {123:'identity',124:'identity'})
            with self.assertRaises(RuntimeError):
                support.bootstrap_preflight(['--dir', str(root), '--web-port', str(port)], lambda _: {})

    def fake_macos(self, busy=False):
        tools = self.root/'tools'; tools.mkdir()
        def tool(name, text):
            path = tools/name; path.write_text(text); path.chmod(0o755)
        tool('uname', '#!/bin/sh\nif [ "$1" = -s ]; then echo Darwin; else echo arm64; fi\n')
        tool('lsof', '#!/bin/sh\nprintf "p123\\nn127.0.0.1:8036\\n"\n' if busy else '#!/bin/sh\nexit 1\n')
        return tools, tool, {**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH']}

    def test_macos_busy_port_stops_before_network(self):
        _, tool, env = self.fake_macos(busy=True)
        tool('curl', '#!/bin/sh\necho UNEXPECTED_DOWNLOAD >&2\nexit 98\n')
        result = subprocess.run(['bash', str(ROOT/'install-en.sh'), '--dir', str(self.root/'instance'), '--no-start'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Port 8036', result.stderr)
        self.assertNotIn('UNEXPECTED_DOWNLOAD', result.stderr)

    def test_macos_failed_install_reuses_verified_archive(self):
        _, tool, env = self.fake_macos()
        archive = self.root/'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            data = b'#!/bin/bash\nexit 23\n'
            entry = tarfile.TarInfo('install.command'); entry.size = len(data); entry.mode = 0o755
            tar.addfile(entry, io.BytesIO(data))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        count = self.root/'downloads'
        curl = f'''#!{sys.executable}
import pathlib,sys
args=sys.argv[1:]; url=next(a for a in args if a.startswith('https://')); out=pathlib.Path(args[args.index('-o')+1])
if url.endswith('SHA256SUMS'):
 out.write_text({(digest+'  semantic-0.1.0-rc.5-macos-arm64.tar.gz'+chr(10))!r})
else:
 out.write_bytes(pathlib.Path({str(archive)!r}).read_bytes())
 with pathlib.Path({str(count)!r}).open('a') as log:log.write('download\\n')
'''
        tool('curl', curl)
        command = ['bash', str(ROOT/'artifacts/macos/bootstrap.sh'), '--dir', str(self.root/'instance'), '--cache-dir', str(self.root/'cache'), '--no-start']
        for _ in range(2):
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(count.read_text().splitlines(), ['download'])
        self.assertIn('Using verified cached archive', result.stderr)
        cached = self.root/'cache'/f'{digest}.tar.gz'
        cached.write_bytes(b'damaged')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual(len(count.read_text().splitlines()), 2)
        self.assertEqual(cached.read_bytes(), archive.read_bytes())

    def test_macos_incomplete_install_uninstalls_from_bundled_python_offline(self):
        _, tool, env = self.fake_macos()
        tool('curl', '#!/bin/sh\necho UNEXPECTED_DOWNLOAD >&2\nexit 98\n')
        root = self.root/'instance'; release = root/'releases/test'; python = release/'python/bin/python3.13'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n'); python.chmod(0o755)
        shutil.copyfile(ROOT/'artifacts/runtime/uninstall.py', release/'uninstall.py')
        (root/'.semantic-install-root').touch()
        (root/'install.json').write_text(json.dumps({'version':'test','ready':False}))
        (root/'run').mkdir()
        result = subprocess.run(['bash', str(ROOT/'artifacts/macos/bootstrap.sh'), '--uninstall', '--dir', str(root), '--yes'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('UNEXPECTED_DOWNLOAD', result.stderr)
        self.assertFalse((root/'releases').exists())
        self.assertTrue((root/'install.json').exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux bootstrap integration')
    def test_linux_bootstrap_retries_cached_archive_after_child_failure(self):
        archive = self.root/'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            data = b'raise SystemExit(23)\n'
            entry = tarfile.TarInfo('installer.py'); entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
        content = archive.read_bytes(); digest = hashlib.sha256(content).hexdigest()
        manifest = json.dumps(dict(platform='linux-x86_64', archive='release.tar.gz', sha256=digest)).encode()
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                body = content if self.path == '/release.tar.gz' else manifest
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        command = ['bash', str(ROOT/'install.sh'), '--base-url', f'http://127.0.0.1:{server.server_port}',
                   '--allow-http', '--dir', str(self.root/'instance'), '--cache-dir', str(self.root/'cache'),
                   '--no-start', '--runtime-port', str(port), '--yes']
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual(requests.count('/release.tar.gz'), 1)
        self.assertIn('Using verified cached archive', result.stderr)
        with socket.socket() as busy:
            busy.bind(('127.0.0.1', 0)); busy.listen()
            command[command.index('--runtime-port')+1] = str(busy.getsockname()[1])
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No archive was downloaded', result.stderr)
        self.assertEqual(requests.count('/release.tar.gz'), 1)

    def test_macos_incomplete_install_checks_ports_before_downloading(self):
        _, tool, env = self.fake_macos()
        tool('curl', '#!/bin/sh\necho UNEXPECTED_DOWNLOAD >&2\nexit 98\n')
        root = self.root/'instance'; release = root/'releases/test'; python = release/'python/bin/python3.13'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' "$@"\n'); python.chmod(0o755)
        shutil.copyfile(ROOT/'artifacts/runtime/uninstall.py', release/'uninstall.py')
        (root/'.semantic-install-root').touch()
        with socket.socket() as busy:
            busy.bind(('127.0.0.1', 0)); busy.listen(); port = busy.getsockname()[1]
            (root/'install.json').write_text(json.dumps(dict(version='test', ready=False,
                http_port=8080, ws_port=8081, web_port=3000, runtime_port=port)))
            result = subprocess.run(['bash', str(ROOT/'artifacts/macos/bootstrap.sh'), '--dir', str(root),
                                     '--no-start', '--runtime-port', str(port)], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f'Port {port}', result.stderr)
        self.assertNotIn('UNEXPECTED_DOWNLOAD', result.stderr)
