"""Native Windows manager contracts against real OS objects and Framework."""
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/windows'))
sys.path.insert(0, str(ROOT/'artifacts/runtime'))
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

    def test_offline_uninstall_preserves_data_and_explicit_purge_removes_instance(self):
        from install_support import component_values
        for purge in (False, True):
            root = self.root/('purge' if purge else 'preserve')
            for name in ('releases/0.1.0-test.1/bin', 'configs', 'data', 'run'):
                (root/name).mkdir(parents=True, exist_ok=True)
            (root/'.semantic-install-root').touch()
            (root/'releases/0.1.0-test.1/bin/program.exe').write_bytes(b'test-owned payload')
            (root/'data/user.txt').write_text('keep my data', encoding='utf-8')
            (root/'configs/user.yaml').write_text('keep: true', encoding='utf-8')
            # Cleanup must stay bounded for populated Skill environments and use
            # native long paths even when the host's Python can create them.
            tree = root/'releases/0.1.0-test.1/many-files'
            tree.mkdir()
            for index in range(1500):
                (tree/f'module-{index}.py').write_bytes(b'# installed dependency\n')
            deep = tree/('long-directory-'*10)/('nested-module-'*10)/'owned.py'
            self.assertGreater(len(str(deep)), 260)
            native_deep = Path('\\\\?\\'+str(deep))
            native_deep.parent.mkdir(parents=True)
            native_deep.write_bytes(b'# long path\n')

            (root/'install.json').write_text(json.dumps(dict(component_values(), version='0.1.0-test.1',
                platform='windows-amd64', ready=True)), encoding='utf-8')
            (root/'bin').mkdir(exist_ok=True)
            (root/'releases/0.1.0-test.1/assets').mkdir()
            (root/'releases/0.1.0-test.1/python').mkdir()
            shutil.copyfile(sys.executable, root/'releases/0.1.0-test.1/python/python.exe')
            shutil.copyfile(ROOT/'artifacts/assets/ios.png', root/'releases/0.1.0-test.1/assets/ios.png')
            entries = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'artifacts/windows/desktop.ps1'),
                '-Root', str(root), '-Version', '0.1.0-test.1']).decode('utf-8-sig'))
            state = json.loads((root/'install.json').read_text(encoding='utf-8'))
            (root/'install.json').write_text(json.dumps(dict(state, **entries)), encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT/'artifacts/windows/manager.py'),
                       '--dir', str(root), 'uninstall', '--yes']
            if purge:
                command.append('--purge')
            def cleanup():
                result = subprocess.run(command, check=True, capture_output=True, timeout=30)
                report = Path(result.stdout.decode('utf-8').strip().split('Result: ',1)[1])
                deadline = time.monotonic()+30
                while not report.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(report.exists(), (report.parent/'cleanup.log').read_text(errors='replace'))
                result = json.loads(report.read_text(encoding='utf-8'))
                if result.get('success'):
                    self.assertTrue(all(not Path(p).exists() for p in entries['native_shortcuts']))
                    import winreg
                    with self.assertRaises(FileNotFoundError):
                        winreg.OpenKey(winreg.HKEY_CURRENT_USER, entries['uninstall_registry'].removeprefix('HKCU:\\'))
                return result
            if not purge:
                outside = self.root/'outside'
                outside.mkdir()
                (outside/'user.txt').write_text('external data',encoding='utf-8')
                junction = root/'releases/0.1.0-test.1/bin/external'
                subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(junction),str(outside)],
                               check=True,capture_output=True)
                try:
                    rejected = cleanup()
                    self.assertFalse(rejected['success'], rejected)
                    self.assertIn('Reparse point', rejected['error'])
                    self.assertEqual((outside/'user.txt').read_text(), 'external data')
                    self.assertTrue((root/'releases/0.1.0-test.1/bin/program.exe').is_file())
                finally:
                    os.rmdir(junction)
            evidence = cleanup()
            self.assertTrue(evidence['success'], evidence)
            if purge:
                self.assertFalse(root.exists())
            else:
                self.assertFalse((root/'releases').exists())
                self.assertEqual((root/'data/user.txt').read_text(), 'keep my data')
                self.assertEqual((root/'configs/user.yaml').read_text(), 'keep: true')
                self.assertFalse(json.loads((root/'install.json').read_text())['ready'])

    def test_cleanup_waits_for_parent_handle_and_preserves_reused_pid(self):
        powershell = str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
        for matched in (True, False):
            root = self.root/('matching-parent' if matched else 'reused-parent')
            root.mkdir()
            (root/'.semantic-install-root').touch()
            (root/'install.json').write_text(json.dumps(dict(platform='windows-amd64',
                ready=True, uninstalling=True, uninstall_nonce='parent-handle-test')))
            result = root.with_suffix('.result.json')
            log = root.with_suffix('.log')
            parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            helper = None
            try:
                identity = ports.process_record(parent.pid)
                with log.open('wb') as stream:
                    helper = subprocess.Popen([powershell, '-NoProfile', '-NonInteractive',
                        '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'artifacts/windows/uninstall.ps1'),
                        '-Root', str(root), '-Nonce', 'parent-handle-test', '-ParentPid', str(parent.pid),
                        '-ParentCreated', identity['created'] if matched else '0000000000000000',
                        '-Result', str(result), '-Purge'], stdout=stream, stderr=subprocess.STDOUT)
                if matched:
                    deadline = time.monotonic()+20
                    while 'Waiting for installer PID' not in log.read_text(errors='replace'):
                        self.assertIsNone(helper.poll(), log.read_text(errors='replace'))
                        self.assertLess(time.monotonic(), deadline, log.read_text(errors='replace'))
                        time.sleep(0.05)
                    self.assertTrue(root.exists())
                    self.assertFalse(result.exists(), 'Cleanup ran before the owned parent exited')
                    parent.terminate()  # This test owns the inert sleeper.
                    parent.wait(timeout=10)
                helper.wait(timeout=30)
                self.assertEqual(helper.returncode, 0, log.read_text(errors='replace'))
                self.assertTrue(json.loads(result.read_text(encoding='utf-8'))['success'])
                self.assertFalse(root.exists())
                if not matched:
                    self.assertIsNone(parent.poll(), 'Cleanup touched a reused PID')
            finally:
                if parent.poll() is None:
                    parent.terminate()
                parent.wait(timeout=10)
                if helper is not None and helper.poll() is None:
                    helper.wait(timeout=30)

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

    def test_manager_reconfigures_real_services_and_rolls_back_failed_restart(self):
        import manager as managed
        import yaml
        from unittest.mock import patch
        from install_support import component_values, export_components

        def free_values():
            listeners = [socket.socket() for _ in range(4)]
            try:
                for listener in listeners:
                    listener.bind(('127.0.0.1', 0))
                values = component_values()
                values.update(zip(('http_port','ws_port','web_port','runtime_port'),
                                  (listener.getsockname()[1] for listener in listeners)))
                values['web_host'] = '127.0.0.1'
                return values
            finally:
                for listener in listeners:
                    listener.close()

        values = free_values()
        binaries = Path(os.environ['SEMANTIC_NATIVE_BIN'])
        release = self.root/'releases/0.1.0-test.1'
        for name in ('bin', 'web'):
            (release/name).mkdir(parents=True)
        for name in ('semantic-server.exe', 'semantic-web-gateway.exe'):
            shutil.copyfile(binaries/name, release/'bin'/name)
        (release/'web/index.html').write_text('Semantic manager test', encoding='utf-8')
        for name in ('run', 'logs', 'tmp', 'runtimes.d', 'robots/test/robot'):
            (self.root/name).mkdir(parents=True, exist_ok=True)
        (self.root/'.semantic-install-root').touch()
        config = self.root/'configs/semantic-server.yaml'
        subprocess.run([binaries/'semantic.exe', 'init', '-c', config], check=True)
        cfg = yaml.safe_load(config.read_text(encoding='utf-8'))
        cfg['server'].update(http_addr=f"127.0.0.1:{values['http_port']}", ws_addr=f"127.0.0.1:{values['ws_port']}")
        cfg['robot_runtime']['enabled'] = False  # No Robot/physical scene in this manager fixture.
        config.write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
        runtime = self.root/'runtimes.d/local-native-mujoco.yaml'
        template = binaries.parents[1]/'configs/runtimes.d/native-mujoco.yaml'
        runtime_cfg = yaml.safe_load(template.read_text(encoding='utf-8'))
        runtime_cfg.update(endpoint=f"http://127.0.0.1:{values['runtime_port']}", enabled=False)
        runtime.write_text(yaml.safe_dump(runtime_cfg),encoding='utf-8')
        instance = self.root/'robots/test/robot/instance.yaml'
        instance.write_text(f"server: http://127.0.0.1:{values['http_port']}\nws: ws://127.0.0.1:{values['ws_port']}/ws/pilot\n",encoding='utf-8')
        state = dict(values, version='0.1.0-test.1', ready=True, platform='windows-amd64')
        (self.root/'install.json').write_text(json.dumps(state),encoding='utf-8')
        export_components(self.root/'configs/components.yaml', values)
        service = managed.Manager(self.root)
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def healthy(expected):
            self.assertEqual(service.status(), {'server':True,'web':True})
            # This checks real gateway-to-Server discovery after the HTTP port moves.
            with client.open(f"http://127.0.0.1:{expected['web_port']}/api/v1/system/healthz", timeout=3) as response:
                self.assertEqual(response.status, 200)

        try:
            service.start()
            healthy(values)
            before = (self.root/'install.json').read_bytes()
            records = service.records()
            with socket.socket() as busy:
                busy.bind(('127.0.0.1',0)); busy.listen(1)
                blocked = self.root/'blocked.yaml'
                export_components(blocked, dict(values,web_port=busy.getsockname()[1]))
                with self.assertRaises(RuntimeError):
                    service.configure(blocked)
                self.assertEqual((self.root/'install.json').read_bytes(), before)
                self.assertEqual(service.records(), records)
                healthy(values)
            changed = free_values()
            new_config = self.root/'changed.yaml'
            export_components(new_config, changed)
            service.configure(new_config)
            healthy(changed)
            self.assertIn(f"http://127.0.0.1:{changed['runtime_port']}", runtime.read_text())
            self.assertIn(f"http://127.0.0.1:{changed['http_port']}", instance.read_text())
            self.assertIn(f"ws://127.0.0.1:{changed['ws_port']}/ws/pilot", instance.read_text())
            cfg = json.loads(config.read_text(encoding='utf-8'))
            self.assertEqual(cfg['robot_runtime']['server_http_url'], f"http://127.0.0.1:{changed['http_port']}")
            attempts = 0
            original_start = service.start

            def fail_once(names=('server','web')):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError('injected restart failure')
                return original_start(names)

            previous = self.root/'previous.yaml'
            export_components(previous, values)
            with patch.object(service, 'start', side_effect=fail_once):
                with self.assertRaisesRegex(RuntimeError, 'injected restart failure'):
                    service.configure(previous)
            self.assertEqual(service.values, changed)
            healthy(changed)
        except Exception:
            for log in (self.root/'logs').glob('*.log'):
                print(log.name+':\n'+log.read_text(encoding='utf-8', errors='replace')[-16000:])
            raise
        finally:
            service.stop()
            self.assertEqual(service.status(), {'server':False,'web':False})


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    unittest.main(verbosity=2)
