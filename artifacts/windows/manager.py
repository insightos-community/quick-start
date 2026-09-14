"""Manage an installed native Windows instance; no network download is needed.

The payload assembler/installer will create the ownership marker and state.
This entry currently provides lifecycle and transactional component configuration.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE/'installer.py').is_file():
    sys.path.insert(0, str(HERE.parent/'runtime'))  # Source checkout only.
import installer as shared
from install_support import web_probe, component_values, read_component_config, validate_components, component_yaml, export_components
import windows_ports as ports


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('Managed path contains a reparse point: '+str(path))
    return path


def replace(path, data):
    plain(path)
    shared.replace_config(path, data)


class Manager:
    def __init__(self, root):
        self.root = plain(Path(root).expanduser())
        if self.root in (Path(self.root.anchor), Path.home().resolve()):
            raise ValueError('A dedicated installation directory is required')
        if not (self.root/'.semantic-install-root').is_file():
            raise ValueError('Directory is not owned by the Semantic installer')
        self.reload()

    def reload(self):
        self.state = shared.load(plain(self.root/'install.json'))
        if self.state.get('platform') != 'windows-amd64':
            raise ValueError('This manager requires a Windows installation')
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', self.state.get('version', '')):
            raise ValueError('Invalid installed version')
        self.release = plain(self.root/'releases'/self.state['version'])
        self.values = validate_components(shared.configured_components(self.root, self.state))

    def records(self):
        path = plain(self.root/'run/services.json')
        return shared.load(path) if path.exists() else {}

    def executable(self, name):
        names = {'server':'semantic-server.exe', 'web':'semantic-web-gateway.exe'}
        return plain(self.release/'bin'/names[name])

    def current(self, name, record):
        expected = self.executable(name)
        if os.path.normcase(record.get('executable', '')) != os.path.normcase(str(expected.resolve())):
            raise RuntimeError('Saved process does not match the installed executable: '+name)
        actual = ports.process_record(record['pid'])
        if actual and actual['created'] == record.get('created'):
            if not ports._matches(actual, record):
                raise RuntimeError('Process executable changed: '+name)
            return actual
        return None

    def status(self):
        records = self.records()
        return {name:bool(name in records and self.current(name, records[name])) for name in ('server', 'web')}

    def assert_robots_stopped(self):
        # Keep unconfirmed/failed state for reconciliation. The UI's runtime
        # release performs the normal Robot hold/stop protocol before management.
        for path in (self.root/'robots').glob('*/*/run/state.json'):
            state = shared.load(plain(path))
            if state.get('status') not in ('stopped', 'released'):
                raise RuntimeError('Release all scenes and Robot instances before management: '+str(path))

    def environment(self):
        env = shared.environment(self.root, self.release)
        env.update(PATH=str(self.release/'python')+os.pathsep+env['PATH'],
                   TMP=str(self.root/'tmp'), TEMP=str(self.root/'tmp'),
                   SEMANTIC_MUJOCO_GL='glfw', MUJOCO_GL='glfw',
                   UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never',
                   UV_PYTHON_PREFERENCE='only-system', PYTHONNOUSERSITE='1', PYTHONUTF8='1')
        return env

    def stop(self, names=('web', 'server')):
        self.assert_robots_stopped()
        records = self.records()
        for name in names:
            if name not in records:
                continue
            if self.current(name, records[name]):
                ports.stop(records[name])
            records.pop(name)
            shared.write_json(self.root/'run/services.json', records)

    def uninstall(self, purge=False):
        self.stop()
        temporary = plain(Path(tempfile.mkdtemp(prefix='semantic-uninstall-')))
        if temporary.is_relative_to(self.root):
            raise ValueError('Uninstall cleanup must run outside the installation directory')
        helper = temporary/'uninstall.ps1'
        shutil.copyfile(HERE/'uninstall.ps1', helper)
        result = temporary/'result.json'
        identity = ports.process_record(os.getpid())
        original = dict(self.state)
        self.state.update(uninstalling=True, uninstall_nonce=secrets.token_hex(32))
        shared.write_json(self.root/'install.json', self.state)
        command = [str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),
                   '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(helper),
                   '-Root', str(self.root), '-Nonce', self.state['uninstall_nonce'],
                   '-ParentPid', str(identity['pid']), '-ParentCreated', identity['created'], '-Result', str(result)]
        if purge:
            command.append('-Purge')
        try:
            with (temporary/'cleanup.log').open('wb') as log:
                child = subprocess.Popen(command, cwd=temporary, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic()+20
            while not (temporary/'result.json.started').exists():
                if child.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Cleanup helper did not start; inspect '+str(temporary/'cleanup.log'))
                time.sleep(0.1)
        except Exception:
            self.state = original
            shared.write_json(self.root/'install.json', self.state)
            raise
        return result

    def start(self, names=('server', 'web')):
        if not self.state.get('ready') or self.state.get('uninstalling'):
            raise RuntimeError('Installation is not complete')
        values = self.values
        web_host = values['web_host']
        web_probe = '127.0.0.1' if web_host == '0.0.0.0' else web_host
        definitions = {
            'server': (['-c', self.root/'configs/semantic-server.yaml'], values['http_port'], '127.0.0.1', '/api/v1/system/healthz'),
            'web': (['--root', self.release/'web', '--listen', f"{web_host}:{values['web_port']}",
                     '--api', f"http://127.0.0.1:{values['http_port']}", '--ws', f"http://127.0.0.1:{values['ws_port']}"],
                    values['web_port'], web_host, '/'),
        }
        records = self.records()
        created = []
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            for name in names:
                if name in records and self.current(name, records[name]):
                    continue
                arguments, port, host, health = definitions[name]
                ports.check_port(port, host)
                if name == 'server':
                    ports.check_port(values['ws_port'])
                with plain(self.root/f'logs/{name}.log').open('a', encoding='utf-8') as log:
                    child = subprocess.Popen([str(self.executable(name)), *map(str, arguments)],
                        cwd=self.root, env=self.environment(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
                record = ports.process_record(child.pid)
                if record is None:
                    child.wait(timeout=5)
                    raise RuntimeError(name+' exited before process identity was recorded')
                records[name] = record
                shared.write_json(self.root/'run/services.json', records)
                created.append(name)
                deadline = time.monotonic()+45
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise RuntimeError(name+' exited; inspect logs/'+name+'.log')
                    try:
                        probe = web_probe if name == 'web' else '127.0.0.1'
                        with client.open(f'http://{probe}:{port}{health}', timeout=1) as reply:
                            if reply.status == 200:
                                break
                    except OSError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(name+' health check timed out')
            if not self.state.get('skills_published', True):
                shared.publish(self.root, self.release, self.state, quiet=True)
                self.state['skills_published'] = True
                shared.write_json(self.root/'install.json', self.state)
        except Exception:
            self.stop(reversed(created))
            raise

    def configure(self, config, no_start=False):
        old = dict(self.values)
        values = validate_components({**old, **read_component_config(config)})
        self.assert_robots_stopped()
        updates = shared.component_updates(self.root, old, values)
        running = self.status()
        old_ports = {old[key] for name, keys in [('server', ('http_port', 'ws_port')), ('web', ('web_port',))]
                     if running[name] for key in keys}
        for key in ('http_port', 'ws_port', 'web_port', 'runtime_port'):
            if values[key] not in old_ports:
                ports.check_port(values[key], values['web_host'] if key == 'web_port' else '127.0.0.1')
        state = {**self.state, **values}
        updates[self.root/'install.json'] = (json.dumps(state,ensure_ascii=False,indent=2)+'\n').encode()
        updates[self.root/'configs/components.yaml'] = component_yaml(values).encode()
        originals = {plain(path): path.read_bytes() if path.exists() else None for path in updates}
        backup = self.root/'configs'/('reconfigure-backup-'+str(time.time_ns()))
        backup.mkdir()
        for path, data in originals.items():
            if data is not None:
                target = backup/path.relative_to(self.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        self.stop()
        try:
            for key in ('http_port', 'ws_port', 'web_port', 'runtime_port'):
                ports.check_port(values[key], values['web_host'] if key == 'web_port' else '127.0.0.1')
            for path, data in updates.items():
                replace(path, data)
            self.reload()
            if not no_start:
                self.start()
        except Exception:
            self.stop()
            for path, data in originals.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    replace(path, data)
            self.reload()
            self.start([name for name in ('server', 'web') if running[name]])
            raise
        return backup


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['open', 'start', 'stop', 'status', 'reconfigure', 'export-config', 'uninstall'])
    parser.add_argument('--dir', type=Path, required=True)
    parser.add_argument('-f', '--config', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--no-start', action='store_true')
    parser.add_argument('--purge', action='store_true', help='Delete this installation including its configuration and data')
    parser.add_argument('--interactive', action='store_true', help='Keep a shortcut console visible on failure')
    parser.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    manager = Manager(args.dir)
    with ports.directory_lock(manager.root):
        manager.reload()
        if args.command in ('start', 'open'):
            manager.start()
            if args.command == 'open':
                os.startfile(f"http://{web_probe(manager.values['web_host'])}:{manager.values['web_port']}")
        elif args.command == 'stop':
            manager.stop()
        elif args.command == 'status':
            print(json.dumps(manager.status()))
        elif args.command == 'uninstall':
            message = 'Permanently delete this instance and all its data' if args.purge else 'Remove programs and preserve configuration, data and logs'
            if not args.yes and input(message+'? [y/N] ').strip().lower() not in ('y','yes'):
                raise RuntimeError('Uninstallation cancelled')
            result = manager.uninstall(args.purge)
            print('Cleanup will finish after this command exits. Result: '+str(result))
            if args.interactive:
                print('Configuration and data will be preserved unless --purge was selected.')
        elif args.command == 'export-config':
            if args.output:
                export_components(args.output, manager.values)
            else:
                print(component_yaml(manager.values), end='')
        else:
            if not args.config:
                parser.error('reconfigure requires -f components.yaml')
            print('Configuration backup: '+str(manager.configure(args.config, args.no_start)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if '--interactive' in sys.argv:
            print(str(exc), file=sys.stderr)
            input('Press Enter to close...')
        raise
