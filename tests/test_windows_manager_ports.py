"""Native Windows manager contracts against real OS objects and Framework."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/windows'))
if os.name == 'nt':
    import windows_ports as ports


@unittest.skipUnless(os.name == 'nt', 'requires native Windows')
class WindowsManagerContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/"中文 user's instance"
        self.root.mkdir()

    def test_exclusive_lock_survives_contention_and_releases_after_crash(self):
        script = ('import sys,time; from pathlib import Path; '
                  f'sys.path.insert(0, {str(ROOT / "artifacts/windows")!r}); '
                  'import windows_ports as p; '
                  'ctx=p.directory_lock(Path(sys.argv[1])); ctx.__enter__(); '
                  'print("locked",flush=True); time.sleep(60)')
        with ports.directory_lock(self.root):
            result = subprocess.run([sys.executable, '-c', script, str(self.root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('WinError 32', result.stderr)
            with self.assertRaises(PermissionError):
                (self.root/'.semantic-management.lock').unlink()
        child = subprocess.Popen([sys.executable, '-c', script, str(self.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'locked')
            with self.assertRaises(OSError):
                with ports.directory_lock(self.root):
                    self.fail('concurrent lock acquired')
        finally:
            child.terminate()  # Deliberately crash this test-owned lock holder.
            child.wait(timeout=10)
            child.stdout.close()
        with ports.directory_lock(self.root):
            self.assertTrue((self.root/'.semantic-management.lock').is_file())

    def test_active_reusable_listener_is_rejected_without_stopping_it(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('0.0.0.0', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with self.assertRaises(RuntimeError):
                ports.check_port(port)
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                accepted, _ = listener.accept()
                accepted.close()
        ports.check_port(port)

    def test_process_without_endpoint_is_preserved(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        try:
            record = ports.process_record(child.pid)
            with self.assertRaisesRegex(RuntimeError, 'endpoint unavailable'):
                ports.stop(record, timeout=0.1)
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=10)

    def test_real_server_restarts_and_stops_from_python_manager(self):
        import yaml
        binaries = Path(os.environ['SEMANTIC_NATIVE_BIN'])
        config = self.root/'configs/semantic-server.yaml'
        subprocess.run([binaries/'semantic.exe', 'init', '-c', config], check=True, timeout=30)
        values = yaml.safe_load(config.read_text(encoding='utf-8'))
        # Hold both sockets while allocating so HTTP and WS cannot select the same port.
        with socket.socket() as http, socket.socket() as ws:
            http.bind(('127.0.0.1', 0)); ws.bind(('127.0.0.1', 0))
            address = f'127.0.0.1:{http.getsockname()[1]}'
            values['server']['http_addr'] = address
            values['server']['ws_addr'] = f'127.0.0.1:{ws.getsockname()[1]}'
        config.write_text(yaml.safe_dump(values), encoding='utf-8')
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for cycle in range(2):
            with (self.root/f'server-{cycle}.log').open('w', encoding='utf-8') as log:
                child = subprocess.Popen([binaries/'semantic-server.exe', '-c', config], cwd=self.root,
                                         stdout=log, stderr=subprocess.STDOUT)
                try:
                    record = ports.process_record(child.pid)
                    for attempt in range(150):
                        self.assertIsNone(child.poll(), 'Server exited before health check')
                        try:
                            with client.open('http://'+address+'/api/v1/system/healthz', timeout=1) as reply:
                                if reply.status == 200:
                                    break
                        except OSError:
                            pass
                        time.sleep(0.2)
                    else:
                        self.fail('Server health timeout')
                    for stale in (dict(record, created='0000000000000000'),
                                  dict(record, executable=str(self.root/'unrelated.exe'))):
                        with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                            ports.stop(stale)
                        self.assertIsNone(child.poll())
                    ports.stop(record)
                    self.assertEqual(child.wait(timeout=10), 0)
                    self.assertIsNone(ports.process_record(child.pid))
                finally:
                    if child.poll() is None:
                        child.terminate()  # Empty test instance only; never a Robot stop policy.
                        child.wait(timeout=10)
            database = Path(values['store']['sqlite_path'])
            if not database.is_absolute():
                database = self.root/database
            renamed = database.with_suffix('.stopped')
            database.rename(renamed)
            renamed.rename(database)

    def test_native_gateway_serves_assets_and_stops_without_console_signal(self):
        binaries = Path(os.environ['SEMANTIC_NATIVE_BIN'])
        web = self.root/'web'; web.mkdir()
        (web/'index.html').write_text('Semantic SPA', encoding='utf-8')
        (web/'app.js').write_text('window.semantic = true;', encoding='utf-8')
        (web/'.private').write_text('must not be served', encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        address = f'127.0.0.1:{port}'
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for cycle in range(2):
            child = subprocess.Popen([binaries/'semantic-web-gateway.exe', '--root', web, '--listen', address])
            try:
                record = ports.process_record(child.pid)
                for attempt in range(100):
                    self.assertIsNone(child.poll())
                    try:
                        with client.open('http://'+address+'/workspace', timeout=1) as reply:
                            self.assertEqual(reply.read(), b'Semantic SPA')
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail('Gateway did not become ready')
                with client.open('http://'+address+'/app.js', timeout=1) as reply:
                    self.assertEqual(reply.read(), b'window.semantic = true;')
                for path in ('/.private', '/app.js:stream', '/nested%5C.private'):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        client.open('http://'+address+path, timeout=1)
                    self.assertEqual(error.exception.code, 404)
                ports.stop(record)
                self.assertEqual(child.wait(timeout=10), 0)
                ports.check_port(port)
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
