#!/usr/bin/env python3
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

"""Install verified prebuilt Semantic artifacts; no source checkout or target builds."""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import tempfile
import traceback
import urllib.error
import urllib.request

sys.dont_write_bytecode = True  # Imports must not mutate the hash-verified payload.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_support import Progress, desktop_shortcuts, welcome, web_host, web_probe, urls, settings_form

INSTALL_LOG = None
PROGRESS = None


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text())


def verify_payload(payload):
    records = load(payload/'files.json')
    if not isinstance(records, dict) or not records:
        raise ValueError('文件校验清单为空')
    for name, checksum in records.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ValueError('非法校验路径')
        target = payload/path
        if any(p.is_symlink() for p in [target, *target.parents] if p != payload.parent):
            raise ValueError('发布包不能包含符号链接')
        if not target.is_file() or digest(target) != checksum:
            raise ValueError('文件校验失败: ' + name)
    actual = {p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
    if actual != set(records) | {'files.json'}:
        raise ValueError('发布包存在未列入校验的文件')
    return load(payload/'release.json')


def confirm(message, yes=False):
    if yes:
        return
    try:
        # Text update mode (r+) requires seeking; terminals are not seekable.
        # stdin may be a pipe/heredoc, so use the controlling terminal directly.
        with open('/dev/tty', 'w', encoding='utf-8') as output, open('/dev/tty', 'r', encoding='utf-8') as source:
            output.write(message + ' [y/N] ')
            output.flush()
            answer = source.readline().strip().lower()
    except OSError as error:
        raise RuntimeError('无法访问交互终端 /dev/tty；自动安装请显式提供 --yes') from error
    if answer not in ('y', 'yes'):
        raise RuntimeError('用户取消')


def run(command, log, env=None):
    # Never echo environment variables or API credentials.
    with Path(log).open('a') as f:
        started = time.monotonic()
        name = Path(str(command[0])).name
        f.write(f'[{time.strftime("%H:%M:%S")}] START {name}\n')
        f.flush()  # Visible even if a command produces no output or waits on a lock.
        try:
            result = subprocess.run(list(map(str, command)), stdin=subprocess.DEVNULL,
                                    stdout=f, stderr=subprocess.STDOUT, env=env)
        except BaseException as error:
            f.write(f'ERROR {name}: {type(error).__name__}\n')
            raise
        f.write(f'[{time.strftime("%H:%M:%S")}] END {name} rc={result.returncode} elapsed={time.monotonic()-started:.1f}s\n')
    if result.returncode:
        hint = '；sudo 不会等待密码，授权过期时先执行 sudo -v 后重试' if name == 'sudo' else ''
        raise RuntimeError(f'{name} 执行失败 ({result.returncode})，日志: {log}{hint}')


def musl_runtime_mode(root, release):
    state = load(root/'install.json') if (root/'install.json').exists() else {}
    default = 'bundled' if (release/'python/bin/python3.13.musl-template').exists() else 'system'
    return state.get('musl_runtime', default)


def musl_python(root, release):
    name = 'python3.13-bundled' if musl_runtime_mode(root, release) == 'bundled' else 'python3.13'
    return release/'python/bin'/name


def relocated_musl_python(template, loader):
    """Fill the reserved ELF interpreter slot without needing a host patchelf."""
    import struct
    data = bytearray(template.read_bytes())
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 62:
        raise ValueError('Invalid x86_64 musl Python template')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    slots = []
    for index in range(count):
        entry = offset + index*size
        if size < 56 or entry + size > len(data):
            raise ValueError('Invalid ELF program headers')
        if struct.unpack_from('<I', data, entry)[0] == 3:
            start = struct.unpack_from('<Q', data, entry+8)[0]
            length = struct.unpack_from('<Q', data, entry+32)[0]
            slots.append((start, length))
    if len(slots) != 1:
        raise ValueError('Missing unique musl interpreter slot')
    start, length = slots[0]
    if start + length > len(data) or not data[start:start+length].startswith(b'/__SEMANTIC_BUNDLED_MUSL__/'):
        raise ValueError('Unexpected musl interpreter template')
    path = os.fsencode(loader)
    if not loader.is_absolute() or b'\0' in path or len(path) >= length:
        raise ValueError('Installation path exceeds the bundled musl interpreter capacity')
    data[start:start+length] = path + bytes(length-len(path))
    return bytes(data)


def prepare_musl_runtime(root, release):
    template = release/'python/bin/python3.13.musl-template'
    if not template.exists():
        return  # Releases predating the bundled loader keep the original behavior.
    python = musl_python(root, release)
    if musl_runtime_mode(root, release) == 'bundled':
        loader = release/'musl/lib/ld-musl-x86_64.so.1'
        expected = relocated_musl_python(template, loader)
        if python.exists():
            if python.is_symlink() or python.read_bytes() != expected:
                raise RuntimeError('Prepared musl Python was modified; use a new installation directory')
        else:
            import tempfile
            with tempfile.NamedTemporaryFile(dir=python.parent, prefix='.musl-python-', delete=False) as target:
                target.write(expected)
                temporary = Path(target.name)
            temporary.chmod(0o755)
            temporary.replace(python)
    launchers = root/'python-launchers'/release.name/'bin'
    launchers.mkdir(parents=True, exist_ok=True)
    for name in ('python', 'python3', 'python3.13'):
        alias = launchers/name
        if alias.is_symlink():
            if alias.readlink() != python:
                raise RuntimeError('Existing Python launcher selects a different musl runtime')
        elif alias.exists():
            raise RuntimeError('Unexpected file at the managed Python launcher path')
        else:
            alias.symlink_to(python)


def environment(root, release):
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    env.update(PATH=str(release/'bin') + os.pathsep + env.get('PATH', ''),
               UV_PYTHON_INSTALL_DIR=str(root/'python'), UV_NO_CONFIG='1',
               TMPDIR=str(root/'tmp'), PYTHONUNBUFFERED='1',
               SEMANTIC_MUJOCO_GL='cgl' if platform.system() == 'Darwin' else 'egl',
               MUJOCO_GL='cgl' if platform.system() == 'Darwin' else 'egl')
    if platform.system() == 'Darwin':
        env.update(PATH=str(release/'python/bin') + os.pathsep + env['PATH'],
                   UV_PYTHON_DOWNLOADS='never', UV_PYTHON_PREFERENCE='only-system',
                   UV_OFFLINE='1', PYTHONNOUSERSITE='1')
    if (release/'musl').is_dir():
        env.update(PATH=str(release/'python/bin') + os.pathsep + env['PATH'],
                   UV_PYTHON_DOWNLOADS='never', UV_PYTHON_PREFERENCE='only-system',
                   LD_LIBRARY_PATH=str(release/'musl/lib'),
                   PYTHONPATH=str(release/'musl/lib/python3.13/site-packages'),
                   PYOPENGL_PLATFORM='egl')
        if (release/'python/bin/python3.13.musl-template').exists():
            env['PATH'] = str(root/'python-launchers'/release.name/'bin') + os.pathsep + env['PATH']
            # The prepared interpreter's RPATH scopes musl libraries to Python.
            # In particular, host tar/zstd and shells must not load these libraries.
            env.pop('LD_LIBRARY_PATH', None)
            env.pop('LD_PRELOAD', None)
        for key in ('LIBGL_ALWAYS_SOFTWARE', 'GALLIUM_DRIVER', 'MESA_LOADER_DRIVER_OVERRIDE',
                    'LIBGL_DRIVERS_PATH', '__EGL_VENDOR_LIBRARY_FILENAMES',
                    '__EGL_VENDOR_LIBRARY_DIRS', 'DRI_PRIME', 'EGL_PLATFORM', 'MUJOCO_EGL_DEVICE_ID'):
            env.pop(key, None)
        report = root/'configs/musl-render.json'
        if report.exists():
            selected = load(report)
            env['MUJOCO_EGL_DEVICE_ID'] = str(selected['device'])
            if selected['selected'] == 'software':
                env.update(LIBGL_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='llvmpipe')
    if (root/'configs/secrets.json').exists():
        env.update(load(root/'configs/secrets.json'))
    return env


def probe_musl(root, release, backend='auto'):
    if not (release/'musl').is_dir():
        return
    manifest = load(release/'release.json')
    python = release/'robot-bundles'/manifest['bundle_name']/'python/venv/bin/python'
    run([python, release/'musl/share/insightos-mesa/launch.py', '--profile', backend,
         '--mesa-prefix', release/'musl', '--check', '--report', root/'configs/musl-render.json'],
        root/'logs/musl-render.log', environment(root, release))


def system_musl_available():
    loader = Path('/lib/ld-musl-x86_64.so.1')
    return loader.is_file() and os.access(loader, os.X_OK)


def check_port(port, host='127.0.0.1'):
    with socket.socket() as s:
        # Match the server's reuse behavior: TIME_WAIT is not an active listener.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError as e:
            raise RuntimeError(f'端口 {port} 已占用；请显式选择其他端口，不会停止已有服务') from e


def process_identity(pid):
    if platform.system() == 'Darwin':
        from uninstall import uninstall_identity
        return uninstall_identity(pid)
    try:
        text = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
        return None if text[0] == 'Z' else text[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def alive(record):
    return bool(record.get('start_ticks')) and process_identity(record['pid']) == record['start_ticks']


def services(root):
    path = root/'run/services.json'
    return load(path) if path.exists() else {}


def show_status(root):
    from uninstall import uninstall_managed, uninstall_processes
    records = services(root)
    owned = uninstall_managed(root)
    rows = [(name.title(), '运行中' if record.get('pid') in owned else '已停止',
             'ok' if record.get('pid') in owned else 'label')
            for name in ('server', 'web') for record in [records.get(name, {})]]
    busy = uninstall_processes(root, owned)
    rows.append(('其他占用', str(len(busy))+' 个进程', 'warn' if busy else 'label'))
    for item in busy:
        rows.append((f"PID {item['pid']}", item['command']+' · '+', '.join(item['reasons']), 'warn'))
    if busy:
        rows.append(('终端占用', '在对应终端 cd ~ 或退出；不会自动关闭终端', 'label'))
    settings_form('实例状态', rows)


def stop_owned(root, names=None):
    records = services(root)
    for name, item in list(records.items()):
        if names is not None and name not in names:
            continue
        if alive(item):
            os.killpg(item['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 20
            while alive(item) and time.monotonic() < deadline:
                time.sleep(0.1)
            if alive(item):
                raise RuntimeError(f'{name} 未在超时内退出，保留记录，不强制杀死进程')
        records.pop(name, None)
    write_json(root/'run/services.json', records)


def request(url, token=None, data=None, content_type='application/json'):
    headers = {'Content-Type': content_type}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def publish(root, release, state, quiet=False):
    base = f"http://127.0.0.1:{state['http_port']}/api/v1"
    password = load(root/'configs/secrets.json')['SEMANTIC_ADMIN_PASSWORD']
    token = request(base+'/auth/login', data=json.dumps({'username': 'admin', 'password': password}).encode())['token']
    for skill in load(release/'release.json')['robot_skills']:
        reply = request(base+'/robot-skills', token, (release/skill['path']).read_bytes(), 'application/zip')
        actual = reply.get('skill', reply)
        if (actual.get('name'), actual.get('version')) != (skill['name'], skill['version']):
            raise RuntimeError('发布后技能版本与清单不匹配')
    if not quiet:
        print('Robot Skill 已发布，版本与 Bundle 一致。')


def start(root, quiet=False):
    state = load(root/'install.json')
    if not state.get('ready'):
        raise RuntimeError('安装尚未完成，请先重跑安装')
    release = root/'releases'/state['version']
    prepare_musl_runtime(root, release)
    probe_musl(root, release, state.get('render_backend', 'auto'))
    env = environment(root, release)
    records = services(root)
    host = web_host(state.get('web_host', '127.0.0.1'))
    definitions = {
        'server': ([release/'bin/semantic-server', '-c', root/'configs/semantic-server.yaml'], state['http_port'], '/api/v1/system/healthz'),
        'web': ([release/'bin/semantic-web-gateway', '--root', release/'web', '--listen', f"{host}:{state['web_port']}",
                 '--api', f"http://127.0.0.1:{state['http_port']}", '--ws', f"http://127.0.0.1:{state['ws_port']}"], state['web_port'], '/'),
    }
    created = []
    try:
        for name, (command, port, health) in definitions.items():
            if name in records and alive(records[name]):
                continue
            check_port(port, host if name == 'web' else '127.0.0.1')
            if name == 'server':
                check_port(state['ws_port'])
            with (root/f'logs/{name}.log').open('a') as log:
                child = subprocess.Popen(list(map(str, command)), cwd=root, env=env, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            records[name] = {'pid': child.pid, 'start_ticks': process_identity(child.pid)}
            write_json(root/'run/services.json', records)
            created.append(name)
            deadline = time.monotonic() + 45
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f'{name} 提前退出，检查 logs/{name}.log')
                try:
                    probe = web_probe(host) if name == 'web' else '127.0.0.1'
                    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://{probe}:{port}{health}', timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(f'{name} 健康检查超时')
                time.sleep(0.2)
        publish(root, release, state, quiet=quiet)
    except Exception:
        stop_owned(root, created)
        raise
    if not quiet:
        settings_form('服务已启动', [('Web', '\n'.join(urls(state)), 'command'), ('账号', 'admin'),
                       ('密码', 'semanticctl welcome 查看', 'label')])


# Native application binaries are static. These libraries serve Python Wheels and EGL.
SYSTEM_PACKAGES = {
    'apk': ['ca-certificates', 'tar', 'zstd'],
    'apt-get': ['ca-certificates', 'zstd', 'libstdc++6', 'libgcc-s1', 'libgomp1',
                'libegl1', 'libgl1', 'libgl1-mesa-dri'],
    'dnf': ['ca-certificates', 'zstd', 'libstdc++', 'libgcc', 'libgomp',
            'mesa-libEGL', 'mesa-libGL', 'mesa-dri-drivers'],
    'yum': ['ca-certificates', 'zstd', 'libstdc++', 'libgcc', 'libgomp',
            'mesa-libEGL', 'mesa-libGL', 'mesa-dri-drivers'],
    'pacman': ['ca-certificates', 'zstd', 'gcc-libs', 'libglvnd', 'mesa'],
    'zypper': ['ca-certificates', 'zstd', 'libstdc++6', 'libgcc_s1', 'libgomp1',
               'libEGL1', 'libGL1', 'Mesa-dri'],
}
SYSTEM_LIBRARIES = ('libstdc++.so.6', 'libgcc_s.so.1', 'libgomp.so.1', 'libEGL.so.1', 'libGL.so.1')


def package_manager(info=None):
    info = platform.freedesktop_os_release() if info is None else info
    distro = info.get('ID', '')
    families = [distro, *info.get('ID_LIKE', '').split()]
    for family in families:
        candidates = {
            'alpine': ('apk',),
            'debian': ('apt-get',), 'ubuntu': ('apt-get',),
            'fedora': ('dnf', 'yum'), 'rhel': ('dnf', 'yum'), 'centos': ('dnf', 'yum'),
            'rocky': ('dnf', 'yum'), 'almalinux': ('dnf', 'yum'),
            'arch': ('pacman',), 'manjaro': ('pacman',),
            'suse': ('zypper',), 'opensuse': ('zypper',),
            'opensuse-leap': ('zypper',), 'opensuse-tumbleweed': ('zypper',),
        }.get(family, ())
        for name in candidates:
            if shutil.which(name):
                return name
    raise RuntimeError(f'不支持自动安装系统依赖的发行版: {distro or "unknown"}；请由管理员手动安装依赖')


def dependency_commands(manager, musl=False):
    packages = ['ca-certificates', 'tar', 'zstd'] if musl else SYSTEM_PACKAGES[manager]
    if manager == 'apk':
        return [['apk', 'add', '--no-cache', *packages]]
    if manager == 'apt-get':
        return [['apt-get', 'update'], ['apt-get', 'install', '-y', '--no-install-recommends', *packages]]
    if manager in ('dnf', 'yum'):
        return [[manager, 'install', '-y', *packages]]
    if manager == 'pacman':
        # Never -Sy (partial upgrade), or -Syu (unrequested whole-system upgrade).
        # The administrator must keep Arch synchronized before invoking this installer.
        return [['pacman', '-S', '--needed', '--noconfirm', *packages]]
    return [['zypper', '--non-interactive', 'install', '--no-recommends', *packages]]


def authorize_dependencies(log):
    """Complete sudo authentication before any animated screen is started."""
    def note(message):
        with Path(log).open('a') as output:
            output.write(f'[{time.strftime("%H:%M:%S")}] sudo 授权: {message}\n')
    note('检查权限')
    if os.geteuid() == 0:
        note('root，无需 sudo')
        return
    if not shutil.which('sudo'):
        note('失败：未安装 sudo')
        raise RuntimeError('安装系统依赖需要 root 或 sudo；也可由管理员预装依赖')
    try:
        cached = subprocess.run(['sudo', '-n', '-v'], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except subprocess.TimeoutExpired:
        note('失败：非交互授权检查超时')
        raise RuntimeError('sudo 权限检查超时；请在终端手动执行 sudo -v 排查') from None
    if cached.returncode == 0:
        note('已有有效授权或无需密码')
        return
    note('等待交互授权（密码不经安装器读取或记录）')
    try:
        with open('/dev/tty', 'r', encoding='utf-8') as source, open('/dev/tty', 'w', encoding='utf-8') as output:
            if not source.isatty() or not output.isatty():
                raise OSError('not a terminal')
            settings_form('sudo 授权', [('用途', '安装系统依赖'), ('密码', '输入当前 Linux 用户密码；输入不回显', 'warn'),
                ('说明', '授权完成后显示进度；密码不写日志', 'label')], stream=output)
            result = subprocess.run(['sudo', '-v', '-p', '[Semantic sudo] %u 的密码: '],
                                    stdin=source, stdout=output, stderr=output, timeout=180)
    except OSError:
        note('失败：无可用交互终端')
        raise RuntimeError('sudo 需要授权但没有交互终端；请在同一终端先运行 sudo -v，或由管理员预装依赖后不传 --install-system-deps。--yes 不会代替 sudo 授权') from None
    except subprocess.TimeoutExpired:
        note('失败：交互授权超时')
        raise RuntimeError('sudo 授权超过 180 秒；请重新运行安装器或先执行 sudo -v') from None
    if result.returncode:
        note(f'失败：rc={result.returncode}')
        raise RuntimeError('sudo 授权失败或已取消；未启动依赖安装')
    note('授权成功')


def install_dependencies(log, musl=False):
    manager = package_manager()
    sudo = [] if os.geteuid() == 0 else ['sudo', '-n']
    if sudo and not shutil.which('sudo'):
        raise RuntimeError('安装系统依赖需要 root 或 sudo；也可由管理员预装依赖')
    if not PROGRESS:
        print(f'系统依赖安装器: {manager}；详情写入 {log}', flush=True)
    if manager == 'pacman':
        with Path(log).open('a') as output:
            output.write('Arch 请先由管理员完成系统更新；本脚本不刷新数据库或执行全系统升级。\n')
    for command in dependency_commands(manager, musl):
        with Path(log).open('a') as output:
            output.write(f'[{time.strftime("%H:%M:%S")}] 执行依赖命令: {shlex.join([*sudo, *command])}\n')
        if PROGRESS:
            PROGRESS.detail = shlex.join(command)
        run([*sudo, *command], log)
    if PROGRESS:
        PROGRESS.detail = ''


def check_platform(manifest, musl=False, musl_runtime=None):
    if manifest.get('platform') == 'macos-arm64':
        if musl or platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise RuntimeError('This package requires native Apple Silicon macOS (without --musl)')
        minimum = tuple(map(int, manifest['minimum_macos'].split('.')))
        if tuple(map(int, platform.mac_ver()[0].split('.'))) < minimum:
            raise RuntimeError('This package requires macOS ' + manifest['minimum_macos'] + ' or newer')
        return
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('本制品仅支持 Linux x86_64')
    variant = manifest.get('libc') == 'musl'
    if variant != musl:
        raise RuntimeError('The musl package requires --musl; --musl cannot install a glibc package')
    if variant:
        mode = musl_runtime or ('bundled' if manifest.get('musl_runtime') else 'system')
        if manifest.get('platform') != 'linux-musl-x86_64':
            raise RuntimeError('Invalid musl package platform')
        if mode == 'bundled' and not manifest.get('musl_runtime'):
            raise RuntimeError('This release does not include musl; choose a newer release or --musl-runtime system')
        if mode == 'system' and not system_musl_available():
            raise RuntimeError('--musl-runtime system requires a musl host loader at /lib/ld-musl-x86_64.so.1; use --musl-runtime bundled otherwise')
        if mode not in ('bundled', 'system'):
            raise ValueError('Invalid musl runtime selection')
        return
    minimum = manifest.get('minimum_glibc', '2.39')
    if not re.fullmatch(r'[0-9]+\.[0-9]+', minimum):
        raise ValueError('制品 minimum_glibc 无效')
    libc = platform.libc_ver()
    if libc[0] != 'glibc' or not libc[1] or tuple(map(int, libc[1].split('.'))) < tuple(map(int, minimum.split('.'))):
        raise RuntimeError(f'本制品 Python/动态依赖需要 glibc >= {minimum}；musl/Alpine 请显式使用 --musl')


def install(a):
    global INSTALL_LOG, PROGRESS
    payload = a.payload.resolve()
    manifest = verify_payload(payload)
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', manifest['version']):
        raise ValueError('非法发布版本')
    if getattr(a, 'musl_runtime', None) and not getattr(a, 'musl', False):
        raise ValueError('--musl-runtime requires --musl')
    if not getattr(a, 'musl', False) and getattr(a, 'render_backend', None) not in (None, 'auto'):
        raise ValueError('--render-backend requires --musl')
    raw = Path(a.dir).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise ValueError('--dir 必须是绝对路径且不能是符号链接')
    root = raw.resolve()
    if manifest.get('libc') == 'musl' and ':' in str(root):
        raise ValueError('The musl install path must not contain a colon (library search separator)')
    if payload in root.parents:
        raise ValueError('The installation directory must be outside the extracted package')
    if root in (Path('/'), Path.home(), payload) or any(ord(c) < 32 for c in str(root)):
        raise ValueError('拒绝使用根目录、用户主目录或含控制字符的目录作为安装目录')
    if root.exists() and any(root.iterdir()) and not (root/'.semantic-install-root').is_file():
        raise ValueError('目标目录非空且不是本安装器管理的目录；请选择新目录')
    ports = [a.http_port, a.ws_port, a.web_port, a.runtime_port]
    if len(set(ports)) != len(ports) or any(p < 1024 or p > 65535 for p in ports):
        raise ValueError('端口必须是不同的 1024～65535 数字')
    old = load(root/'install.json') if (root/'install.json').exists() else {}
    runtime_mode = getattr(a, 'musl_runtime', None) or old.get('musl_runtime') or ('bundled' if manifest.get('musl_runtime') else 'system')
    check_platform(manifest, getattr(a, 'musl', False), runtime_mode)
    if old.get('musl_runtime') and old['musl_runtime'] != runtime_mode:
        raise ValueError('Changing musl runtime requires a new --dir')
    host = web_host(a.web_host or (old.get('web_host', '127.0.0.1') if old else '0.0.0.0'))
    if a.web_host and old:
        if host != old.get('web_host', '127.0.0.1'):
            raise ValueError('已有实例请使用 --configure-existing --lan/--web-host 修改监听地址')
    settings_form('安装配置', [('版本', manifest['version']), ('目录', str(root)),
        ('Web', f'{host}:{a.web_port}', 'command'), ('桌面', {'auto': '自动检测', 'always': '创建入口', 'never': '跳过'}[a.desktop]),
        ('网络', 'Web 所有 IPv4 网卡；仅向可信内网放行' if host == '0.0.0.0' else 'Web 按指定地址监听', 'warn'),
        ('后端', 'API/WS 仅本机；防火墙不自动修改', 'label'),
        ('自定义', '--web-host IPv4 / --web-port PORT', 'command')])
    confirm('  确认安装并创建所需目录？', a.yes)
    tasks = ['系统依赖', '部署与校验产物', 'Robot Python 环境', '配置 Server', 'MuJoCo Runtime 自检', '管理命令与桌面入口', '启动服务与健康检查']
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root/'.semantic-install-root').touch(mode=0o600)
    for directory in ('logs', 'run', 'tmp', 'configs', 'releases', 'bin'):
        (root/directory).mkdir(exist_ok=True, mode=0o700)
    with (root/'run/install.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log = root/'logs'/f'install-{time.strftime("%Y%m%d-%H%M%S")}.log'
        log.touch(mode=0o600)
        INSTALL_LOG = log
        if a.install_system_deps and platform.system() != 'Darwin':
            package_manager()  # Reject unsupported systems before prompting for privilege.
            authorize_dependencies(log)
        progress = PROGRESS = Progress(tasks)
        progress.log_path = str(log)
        progress.next(tasks[0])
        if a.install_system_deps and platform.system() != 'Darwin':
            install_dependencies(log, musl=manifest.get('libc') == 'musl')
        missing = []
        if platform.system() != 'Darwin' and not shutil.which('zstd'):
            missing.append('zstd')
        if manifest.get('libc') == 'musl':
            tar = shutil.which('tar')
            if not tar or '--zstd' not in subprocess.run([tar, '--help'], capture_output=True, text=True).stdout:
                missing.append('GNU tar (--zstd)')
        for library in (() if manifest.get('libc') == 'musl' or platform.system() == 'Darwin' else SYSTEM_LIBRARIES):
            try:
                ctypes.CDLL(library)
            except OSError:
                missing.append(library)
        if missing:
            raise RuntimeError('缺少系统依赖: '+', '.join(missing)+'；重跑加 --install-system-deps 或由管理员安装')
        progress.next(tasks[1])
        state_path = root/'install.json'
        signature = digest(payload/'files.json')
        state = load(state_path) if state_path.exists() else {}
        if state and (state.get('version') != manifest['version'] or state.get('payload_sha256') != signature):
            raise RuntimeError('不覆盖已有不同版本；请用新的 --dir 并迁移数据。此版本不做自动数据库升级。')
        if state and [state[k] for k in ('http_port', 'ws_port', 'web_port', 'runtime_port')] != ports:
            raise RuntimeError('已有安装的端口不可通过重装隐式变更')
        state = state or dict(version=manifest['version'], payload_sha256=signature, ready=False,
                              http_port=a.http_port, ws_port=a.ws_port, web_port=a.web_port, runtime_port=a.runtime_port)
        state.setdefault('web_host', host)
        if manifest.get('libc') == 'musl':
            state['render_backend'] = a.render_backend or state.get('render_backend', 'auto')
            state['musl_runtime'] = runtime_mode
        write_json(state_path, state)
        release = root/'releases'/manifest['version']
        if not release.exists():
            shutil.copytree(payload, release)
        else:
            # Preserve newly created venvs; verify every original immutable payload file.
            for name, checksum in load(payload/'files.json').items():
                if not (release/name).is_file() or digest(release/name) != checksum:
                    raise RuntimeError('已有安装制品不完整或被修改: '+name)
        prepare_musl_runtime(root, release)
        env = environment(root, release)
        progress.next(tasks[2])
        if not state['ready']:
            bundle = release/'robot-bundles'/manifest['bundle_name']
            venv = bundle/'python/venv'
            uv = release/'bin/uv'
            run([uv, 'venv', '--allow-existing', '--python',
                 musl_python(root, release) if manifest.get('libc') == 'musl' else
                 release/'python/bin/python3.13' if platform.system() == 'Darwin' else manifest['robot_python'], venv], log, env)
            run([uv, 'pip', 'install', '--python', venv/'bin/python', '--no-index', '--no-deps',
                 *sorted((bundle/'wheels').glob('*.whl'))], log, env)
            if manifest.get('libc') == 'musl':
                # Robot workers intentionally clear PYTHONPATH. Register the verified
                # prefix in this managed venv, so that isolation still works.
                site = venv/'lib/python3.13/site-packages'
                (site/'semantic-musl.pth').write_text(str(release/'musl/lib/python3.13/site-packages')+'\n')
            run([venv/'bin/python', '-c', 'import ability_py, pinocchio, ruckig, websockets'], log, {**env, 'PYTHONPATH': ''})
            run([bundle/'bin/AbilityFramework', '--version'], log, env)
            probe_musl(root, release, state.get('render_backend', 'auto'))
            env = environment(root, release)
            progress.next(tasks[3])
            cli = release/'bin/semantic'
            config = root/'configs/semantic-server.yaml'
            run([cli, 'init', '-c', config], log, env)
            if not (root/'configs/secrets.json').exists():
                write_json(root/'configs/secrets.json', {'SEMANTIC_ADMIN_PASSWORD': secrets.token_urlsafe(24)})
            # Only initialize our pristine configuration once; preserve subsequent user changes.
            if not state.get('configured'):
                cfg = load(release/'defaults/server.json')
                cfg['server'].update(http_addr=f'127.0.0.1:{a.http_port}', ws_addr=f'127.0.0.1:{a.ws_port}')
                cfg['store']['sqlite_path'] = str(root/'data/semantic.db')
                cfg['agents'].update(profiles_dir=str(root/'configs/agents'), teams_dir=str(root/'configs/agents/teams'))
                cfg['skills']['dir'] = str(root/'configs/skills')
                cfg['simulation'].update(runtimes_dir=str(root/'runtimes.d'), catalog_dir=str(root/'content/scene-catalogs'))
                cfg['robot_runtime'].update(enabled=True, bundles_dir=str(release/'robot-bundles'), data_root=str(root),
                    server_http_url=f'http://127.0.0.1:{a.http_port}', server_websocket_url=f'ws://127.0.0.1:{a.ws_port}/ws/pilot')
                write_json(config, cfg)  # JSON is valid YAML; no target-side YAML dependency.
                state['configured'] = True
                write_json(state_path, state)
            progress.next(tasks[4])
            pack = release/manifest['runtime_pack']
            run([cli, 'runtime', 'install', '--pack', pack, '--sha256', digest(pack),
                 '--installation-id', 'local-native-mujoco', '--asset-root', release/'assets/mujoco',
                 '--endpoint', f'http://127.0.0.1:{a.runtime_port}', '--replace', '-c', config], log, env)
            state['ready'] = True
            write_json(state_path, state)
        else:
            progress.next(tasks[3]+'（已有配置）')
            progress.next(tasks[4]+'（已通过，跳过）')
        progress.next(tasks[5])
        current = root/'current'
        if current.exists() and not current.is_symlink():
            raise RuntimeError('current 不是安装器符号链接')
        if current.is_symlink():
            current.unlink()
        current.symlink_to(Path('releases')/manifest['version'])
        install_manager(root, payload)
        desktop_message = desktop_shortcuts(root, state, a.desktop)
        write_json(state_path, state)
        progress.next(tasks[6]+('（按要求跳过）' if a.no_start else ''))
        if not a.no_start:
            start(root, quiet=True)
        progress.finish()
        welcome(root, state, not a.no_start, desktop_message)


def install_manager(root, payload):
    """Update only management files; immutable app releases and data stay untouched."""
    manager = root/'bin/semantic-manager'
    for directory in (root/'bin', manager, manager/'assets'):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError('管理目录异常: '+str(directory))
        directory.mkdir(exist_ok=True, mode=0o700)
    for name in ('installer.py', 'install_support.py', 'uninstall.py', 'assets/ios.png', 'assets/banner.json'):
        target = manager/name
        if target.is_symlink() or (target.exists() and target.stat().st_nlink != 1):
            raise ValueError('管理文件链接异常: '+str(target))
        shutil.copyfile(payload/name, target)
        target.chmod(0o600)
    launcher = root/'bin/semanticctl'
    if launcher.is_symlink() or (launcher.exists() and launcher.stat().st_nlink != 1):
        raise ValueError('管理入口链接异常')
    python_command = shlex.quote(str(root/'current/python/bin/python3.13')) if platform.system() == 'Darwin' else 'python3'
    launcher.write_text('#!/bin/sh\nexec '+python_command+' -B '+shlex.quote(str(manager/'installer.py'))+
                        ' control --root '+shlex.quote(str(root))+' "$@"\n')
    launcher.chmod(0o755)


def configure_existing(a):
    global INSTALL_LOG, PROGRESS
    from uninstall import uninstall_root
    root, state = uninstall_root(a.dir)
    verify_payload(a.payload)
    if not state.get('ready') or not (root/'releases'/state['version']/'bin/semantic-server').is_file():
        raise ValueError('只支持已完成安装的实例；不升级或修复业务产物')
    host = web_host(a.web_host or state.get('web_host', '127.0.0.1'))
    port = a.web_port if a.web_port is not None else state['web_port']
    if not 1024 <= port <= 65535 or port in [state[k] for k in ('http_port', 'ws_port', 'runtime_port')]:
        raise ValueError('Web 端口必须为 1024～65535 且不能与 API/WS/Runtime 重复')
    if port != state['web_port']:
        check_port(port, host)  # Reject conflicts before stopping the existing Web service.
    settings_form('更新管理工具', [('业务版本', state['version']+'（保留）'), ('目录', str(root)),
        ('Web', f"{host}:{port}", 'command'), ('操作', '保留数据；必要时重启 Web', 'warn')])
    confirm('  确认更新管理工具？', a.yes)
    tasks = ['校验并备份配置', '更新管理工具与访问入口', '应用 Web 监听配置']
    progress = PROGRESS = Progress(tasks)
    progress.next(tasks[0])
    with (root/'run/install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        INSTALL_LOG = root/'logs'/f'configure-{time.time_ns()}.log'
        INSTALL_LOG.touch(mode=0o600)
        progress.log_path = str(INSTALL_LOG)
        write_json(root/'configs'/f'install-state-backup-{time.time_ns()}.json', state)
        progress.next(tasks[1])
        install_manager(root, a.payload)
        progress.next(tasks[2])
        if host != state.get('web_host', '127.0.0.1') or port != state['web_port']:
            stop_owned(root, ['web'])
        state['web_host'] = host
        state['web_port'] = port
        message = desktop_shortcuts(root, state, a.desktop)
        write_json(root/'install.json', state)
        if not a.no_start:
            start(root, quiet=True)
        progress.finish()
        welcome(root, state, not a.no_start, message)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('install')
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    p.add_argument('--yes', action='store_true')
    p.add_argument('--no-start', action='store_true')
    p.add_argument('--install-system-deps', action='store_true')
    p.add_argument('--musl', action='store_true', help='Use the optional musl release')
    p.add_argument('--musl-runtime', choices=['bundled', 'system'], help='Use bundled musl (default for new releases) or the host musl')
    p.add_argument('--render-backend', choices=['auto', 'mesa-gpu', 'software'])
    def presentation_options(p):
        network = p.add_mutually_exclusive_group()
        network.add_argument('--lan', dest='web_host', action='store_const', const='0.0.0.0', help='Web 监听所有 IPv4 网卡，仅对可信局域网开放防火墙')
        network.add_argument('--web-host', type=web_host, help='Web 监听 IPv4；新安装默认 0.0.0.0，已有实例保留原设置；127.0.0.1 限制为仅本机')
        desktop = p.add_mutually_exclusive_group()
        desktop.add_argument('--desktop-shortcut', dest='desktop', action='store_const', const='always')
        desktop.add_argument('--no-desktop-shortcut', dest='desktop', action='store_const', const='never')
        p.set_defaults(desktop='auto')
    presentation_options(p)
    for name, default in (('http', 8080), ('ws', 8081), ('web', 3000), ('runtime', 8090)):
        p.add_argument(f'--{name}-port', type=int, default=default)
    p = commands.add_parser('configure')
    p.add_argument('--web-port', type=int, help='修改已有实例 Web 端口；默认保留')
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    p.add_argument('--yes', action='store_true')
    p.add_argument('--no-start', action='store_true')
    presentation_options(p)
    p = commands.add_parser('control')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('action', choices=['start', 'stop', 'status', 'doctor', 'logs', 'welcome', 'uninstall'])
    p.add_argument('--yes', action='store_true', help='uninstall: 跳过确认')
    p.add_argument('--purge', action='store_true', help='uninstall: 删除全部实例数据')
    p.add_argument('--dry-run', action='store_true', help='uninstall: 只显示计划')
    a = parser.parse_args()
    if a.command == 'control' and a.action != 'uninstall' and (a.yes or a.purge or a.dry_run):
        parser.error('--yes/--purge/--dry-run 仅用于 uninstall')
    if a.command == 'install':
        install(a)
    elif a.command == 'configure':
        configure_existing(a)
    elif a.action == 'welcome':
        welcome(a.root, load(a.root/'install.json'), all(alive(r) for r in services(a.root).values()) and len(services(a.root)) == 2)
    elif a.action == 'start':
        start(a.root)
    elif a.action == 'stop':
        # Only these services; do not force-kill any Robot instance or unrelated user process.
        stop_owned(a.root)
        print('已停止本安装器托管的 Server/Web。')
        show_status(a.root)
    elif a.action == 'status':
        show_status(a.root)
    elif a.action == 'uninstall':
        from uninstall import uninstall_entry
        uninstall_entry(['--dir', str(a.root), *(['--yes'] if a.yes else []),
                         *(['--purge'] if a.purge else []), *(['--dry-run'] if a.dry_run else [])])
    elif a.action == 'logs':
        print(a.root/'logs')
    elif a.action == 'doctor':
        release = a.root/'current'
        env = environment(a.root, release.resolve())
        subprocess.run([str(release/'bin/semantic'), 'doctor', '-c', str(a.root/'configs/semantic-server.yaml')], env=env, check=True)


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] in ('install', 'configure'):
            descriptor, filename = tempfile.mkstemp(prefix='semantic-management-', suffix='.log')
            os.close(descriptor)
            INSTALL_LOG = Path(filename)
        main()
    except Exception as error:
        if PROGRESS:
            PROGRESS.finish(error)
        if INSTALL_LOG:
            with INSTALL_LOG.open('a') as f:
                traceback.print_exc(file=f)
        print(f'安装/管理失败: {error}', file=sys.stderr)
        if INSTALL_LOG:
            print('日志: '+str(INSTALL_LOG), file=sys.stderr)
        sys.exit(1)
