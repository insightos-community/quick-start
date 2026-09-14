# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Small pre-download checks and verified, persistent archive caching."""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import platform
import subprocess
from pathlib import Path
import re
import socket
import tempfile


def macos_listener_conflict(port, host):
    # Darwin permits wildcard and specific-address listeners to coexist with
    # SO_REUSEADDR. Inspect active listeners too, without rejecting TIME_WAIT.
    result = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-Fn'],
                            capture_output=True, text=True, timeout=10)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot inspect listening ports: '+result.stderr.strip())
    for line in result.stdout.splitlines():
        if line.startswith('n'):
            address = line[1:].rsplit(':', 1)[0].strip('[]')
            if host == '0.0.0.0' or address in ('*', '0.0.0.0', '::', host):
                return True
    return False


def installation_arguments(arguments):
    # Forward all resolved ports to immutable release installers.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    defaults = dict(http_port=8034, ws_port=8035, web_port=3000, runtime_port=8036)
    for key in defaults:
        parser.add_argument('--'+key.replace('_', '-'), type=int)
    args, _ = parser.parse_known_args(arguments)
    root = Path(args.dir).expanduser()
    state = json.loads((root/'install.json').read_text()) if (root/'.semantic-install-root').is_file() and (root/'install.json').is_file() else {}
    result = list(arguments)
    for key, default in defaults.items():
        if getattr(args, key) is None:
            result += ['--'+key.replace('_', '-'), str(state.get(key, default))]
    return result


def bootstrap_preflight(arguments, managed=None, default_host='0.0.0.0'):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    parser.add_argument('--no-start', action='store_true')
    parser.add_argument('--web-host')
    parser.add_argument('--lan', action='store_true')
    parser.add_argument('--ability-port-first', type=int, default=18100)
    parser.add_argument('--ability-port-last', type=int, default=18199)
    for name, port in [('http', 8034), ('ws', 8035), ('web', 3000), ('runtime', 8036)]:
        parser.add_argument('--'+name+'-port', type=int, default=port)
    args, _ = parser.parse_known_args(installation_arguments(arguments))
    root = Path(args.dir).expanduser()
    if not root.is_absolute() or root.is_symlink() or root.resolve() in (Path('/'), Path.home().resolve()):
        raise ValueError('--dir must be an absolute instance path, not a symlink or home directory')
    if root.exists() and any(root.iterdir()) and not (root/'.semantic-install-root').is_file():
        raise ValueError('Installation directory is not empty or managed; choose another --dir')
    ports = {name: getattr(args, name+'_port') for name in ('http', 'ws', 'web', 'runtime')}
    if len(set(ports.values())) != 4 or any(not 1024 <= port <= 65535 for port in ports.values()):
        raise ValueError('Ports must be distinct numbers between 1024 and 65535')
    state = json.loads((root/'install.json').read_text()) if (root/'install.json').is_file() else {}
    if state and any(state.get(name+'_port') != port for name, port in ports.items()):
        raise ValueError('Existing instance ports differ; use its original options or a new --dir')
    if not 1024 <= args.ability_port_first <= args.ability_port_last <= 65535 or any(args.ability_port_first <= port <= args.ability_port_last for port in ports.values()):
        raise ValueError('Invalid or overlapping Ability port range')
    host = '0.0.0.0' if args.lan else args.web_host or state.get('web_host', default_host)
    ipaddress.IPv4Address(host)
    owned = managed(root) if managed and state else {}
    records = json.loads((root/'run/services.json').read_text()) if (root/'run/services.json').is_file() else {}
    for name, port in ports.items():
        if name == 'runtime' and state.get('ready'):
            continue  # A completed install does not repeat Runtime setup.
        if name != 'runtime' and args.no_start:
            continue
        service = 'web' if name == 'web' else 'server'
        if name != 'runtime' and records.get(service, {}).get('pid') in owned:
            continue  # Already-running services belonging to this exact instance.
        address = host if name == 'web' else '127.0.0.1'
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                if platform.system() == 'Darwin' and macos_listener_conflict(port, address):
                    raise OSError('Active listener already exists')
                probe.bind((address, port))
                probe.listen(1)  # BSD can defer wildcard-address conflicts until listen.
            except OSError as error:
                raise RuntimeError(f'Port {port} ({name}, {address}) is unavailable; stop its service or use --{name}-port PORT. No archive was downloaded.') from error


def cached_archive(url, expected, directory, download, status=print):
    if not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
        raise ValueError('A valid archive SHA256 is required before downloading')
    directory = Path(directory).expanduser()
    if not directory.is_absolute() or any(p.is_symlink() for p in [directory, *directory.parents]):
        raise ValueError('Cache directory must be absolute and must not contain symlinks')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.stat().st_uid != os.geteuid() or directory.stat().st_mode & 0o022:
        raise ValueError('Cache directory must be owned by you and not writable by other users')
    target = directory/(expected+'.tar.gz')
    descriptor = os.open(directory/(expected+'.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        if os.fstat(lock.fileno()).st_nlink != 1 or os.fstat(lock.fileno()).st_uid != os.geteuid():
            raise ValueError('Invalid cache lock ownership or hard link')
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.stat().st_nlink != 1)):
            raise ValueError('Invalid cached archive path')
        def checksum(path):
            result = hashlib.sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024*1024):
                    result.update(block)
            return result.hexdigest()
        if target.is_file() and checksum(target) == expected:
            status('[OK] Using verified cached archive: '+str(target))
            return target
        if target.exists():
            status('[>] Cached archive checksum differs; downloading a verified replacement')
        descriptor, path = tempfile.mkstemp(prefix='.download-', dir=directory)
        os.close(descriptor)
        staged = Path(path)
        try:
            download(url, staged, 8*1024**3)
            if checksum(staged) != expected:
                raise ValueError('Archive SHA256 mismatch; download was not cached')
            staged.replace(target)
        finally:
            staged.unlink(missing_ok=True)
        status('[OK] Archive cached for retries: '+str(target))
        return target
