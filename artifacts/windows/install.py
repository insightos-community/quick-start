"""Install the verified native Windows payload using only bundled components."""
import argparse
import csv
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import secrets
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from manager import Manager, plain, ports, shared
from install_support import component_values, read_component_config, validate_components, component_yaml, export_components


def private_directory(root):
    identity = subprocess.check_output(['whoami.exe', '/user', '/fo', 'csv', '/nh']).decode(errors='replace')
    row = next(csv.reader(identity.splitlines()))
    sid = row[1]
    if not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise RuntimeError('Cannot determine the current Windows user identity')
    subprocess.run(['icacls.exe', str(root), '/inheritance:r', '/grant:r', '*'+sid+':(OI)(CI)F',
                    '/grant:r', '*S-1-5-18:(OI)(CI)F'], check=True, stdout=subprocess.DEVNULL)


def verify(payload):
    plain(payload)
    records = shared.load(payload/'files.json')
    for name in records:
        path = PureWindowsPath(name)
        if path.anchor or '\\' in name or ':' in name or '..' in path.parts:
            raise ValueError('Invalid Windows payload member: '+name)
        plain(payload/name)
    manifest = shared.verify_payload(payload)
    if manifest.get('platform') != 'windows-amd64':
        raise ValueError('Payload does not target Windows x64')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', manifest.get('version', '')):
        raise ValueError('Invalid release version')
    for field in ('bundle_name', 'runtime_pack'):
        path = PureWindowsPath(manifest[field])
        if path.anchor or '..' in path.parts or ':' in str(path):
            raise ValueError('Invalid manifest path: '+field)
    return manifest, records


def install(args):
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('This payload requires native Windows x64')
    if sys.getwindowsversion().build < 18362:
        raise ValueError('This payload requires Windows 10 version 1903 or newer')
    payload = plain(args.payload.resolve())
    root = plain(args.dir.expanduser().absolute())
    if root in (Path(root.anchor), Path.home().resolve(), payload) or root in payload.parents or payload in root.parents:
        raise ValueError('Choose a dedicated installation directory outside the extracted payload')
    if any(ord(char) < 32 for char in str(root)):
        raise ValueError('Invalid installation directory')
    manifest, records = verify(payload)
    old = shared.load(root/'install.json') if (root/'install.json').exists() else {}
    values = component_values(old)
    if args.config:
        values.update(read_component_config(args.config))
    values = validate_components(values)
    if old and (old.get('version') != manifest['version'] or old.get('platform') != 'windows-amd64'
                or old.get('payload_sha256') != shared.digest(payload/'files.json')):
        raise ValueError('Existing installation differs; use a new directory')
    if old and values != component_values(old):
        raise ValueError('Use the installed reconfigure command to change component ports')
    owned_ports = set()
    if old:
        manager = Manager(root)
        status = manager.status()
        for name, keys in [('server', ('http_port','ws_port')), ('web', ('web_port',))]:
            if status[name]:
                owned_ports.update(old[key] for key in keys)
    for key in ('http_port', 'ws_port', 'web_port', 'runtime_port'):
        if (key == 'runtime_port' and old.get('ready')) or values[key] in owned_ports:
            continue
        ports.check_port(values[key], values['web_host'] if key == 'web_port' else '127.0.0.1')
    if not args.yes and input(f'Install Semantic {manifest["version"]} into {root}? [y/N] ').strip().lower() not in ('y', 'yes'):
        raise RuntimeError('Installation cancelled')
    root.mkdir(parents=True, exist_ok=True)
    with ports.directory_lock(root):
        current = shared.load(root/'install.json') if (root/'install.json').exists() else {}
        if current != old:
            raise RuntimeError('Installation changed while waiting; rerun the local installer')
        if not old and any(path.name != '.semantic-management.lock' for path in root.iterdir()):
            raise ValueError('Installation directory is not empty')
        if not old:
            private_directory(root)
        for name in ('configs', 'run', 'logs', 'tmp', 'releases', 'bin'):
            (root/name).mkdir(exist_ok=True)
        (root/'.semantic-install-root').touch()
        state = old or dict(values, version=manifest['version'], platform='windows-amd64', ready=False,
                            configured=False, skills_published=False, payload_sha256=shared.digest(payload/'files.json'))
        shared.write_json(root/'install.json', state)
        release = plain(root/'releases'/manifest['version'])
        release.mkdir(parents=True, exist_ok=True)
        # Resume an interrupted copy from the already verified local payload.
        # A completed installation must retain its original executable bytes.
        for name, checksum in {**records, 'files.json': shared.digest(payload/'files.json')}.items():
            path = plain(release/name)
            if not path.is_file() or shared.digest(path) != checksum:
                if state['ready']:
                    raise RuntimeError('Installed payload is incomplete or modified: '+name)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = plain(path.with_name(path.name+'.install-copy'))
                shutil.copyfile(payload/name, temporary)
                temporary.replace(path)
        manager = Manager(root)
        env = manager.environment()
        log = root/'logs/install.log'
        if not state['ready']:
            bundle = release/'robot-bundles'/manifest['bundle_name']
            python = release/'python/python.exe'
            uv = release/'bin/uv.exe'
            venv = bundle/'python/venv'
            shared.run([uv, 'venv', '--allow-existing', '--python', python, venv], log, env)
            shared.run([uv, 'pip', 'install', '--python', venv/'Scripts/python.exe', '--no-index', '--no-deps',
                        *sorted((bundle/'wheels').glob('*.whl'))], log, env)
            shared.run([uv, 'pip', 'check', '--python', venv/'Scripts/python.exe'], log, env)
            shared.run([venv/'Scripts/python.exe', '-I', '-c',
                        'import ability_py,pinocchio,ruckig,mujoco,numpy; assert numpy.__version__=="2.3.5"'], log, env)
            shared.run([bundle/'bin/AbilityFramework.exe', '--version'], log, env)
            cli = release/'bin/semantic.exe'
            config = root/'configs/semantic-server.yaml'
            if not state.get('configured'):
                shared.run([cli, 'init', '-c', config], log, env)
                cfg = shared.load(release/'defaults/server.json')
                cfg['server'].update(http_addr=f"127.0.0.1:{values['http_port']}", ws_addr=f"127.0.0.1:{values['ws_port']}")
                cfg['store']['sqlite_path'] = str(root/'data/semantic.db')
                cfg['agents'].update(profiles_dir=str(root/'configs/agents'), teams_dir=str(root/'configs/agents/teams'))
                cfg['skills']['dir'] = str(root/'configs/skills')
                cfg['simulation'].update(runtimes_dir=str(root/'runtimes.d'), catalog_dir=str(root/'content/scene-catalogs'))
                cfg['robot_runtime'].update(enabled=True, bundles_dir=str(release/'robot-bundles'), data_root=str(root),
                    server_http_url=f"http://127.0.0.1:{values['http_port']}", server_websocket_url=f"ws://127.0.0.1:{values['ws_port']}/ws/pilot",
                    ability_port_first=values['ability_port_first'], ability_port_last=values['ability_port_last'])
                shared.write_json(config, cfg)
                state['configured'] = True
                shared.write_json(root/'install.json', state)
            if not (root/'configs/secrets.json').exists():
                shared.write_json(root/'configs/secrets.json', {'SEMANTIC_ADMIN_PASSWORD':secrets.token_urlsafe(24)})
            env = manager.environment()
            pack = release/manifest['runtime_pack']
            shared.run([cli, 'runtime', 'install', '--pack', pack, '--sha256', shared.digest(pack),
                        '--installation-id', 'local-native-mujoco', '--asset-root', release/'assets/mujoco',
                        '--endpoint', f"http://127.0.0.1:{values['runtime_port']}", '--replace', '-c', config], log, env)
            state['ready'] = True
            shared.write_json(root/'install.json', state)
        (root/'configs/components.yaml').write_text(component_yaml(values),encoding='utf-8')
        script = ('@echo off\r\n"%~dp0..\\releases\\'+state['version']+'\\python\\python.exe" -I -B '
                  '"%~dp0..\\releases\\'+state['version']+'\\manager.py" --dir "%~dp0.." %*\r\n')
        (root/'bin/semanticctl.cmd').write_text(script,encoding='utf-8',newline='')
        manager.reload()
        if not args.no_start:
            manager.start()
        print(f"Semantic installed: {root}\nWeb: http://127.0.0.1:{values['web_port']}\nAccount: admin\nCredentials: {root/'configs/secrets.json'}")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, default=HERE)
    parser.add_argument('--dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Semantic')
    parser.add_argument('-f', '--config', type=Path)
    parser.add_argument('--export-config', type=Path)
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args()
    if args.export_config:
        export_components(args.export_config, component_values())
        return
    install(args)


if __name__ == '__main__':
    main()
