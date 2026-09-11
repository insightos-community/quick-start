#!/usr/bin/env bash
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

# Semantic bootstrap. Download, verify and extract before executing release code.
# OSS base: https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic
# Private objects require a short-lived ticket from oss_client.py; never embed AccessKeys here.
set -euo pipefail
main() {
  command -v python3 >/dev/null || { echo '请先通过系统包管理器安装 Python 3.10+，然后重新运行安装器。' >&2; return 1; }
  python3 - "$@" <<'PY'
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tarfile, tempfile, urllib.parse, urllib.request
if sys.version_info < (3, 10):
    raise SystemExit('需要 Python 3.10+')
# BEGIN EMBEDDED UNINSTALLER
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

"""Offline uninstaller; mirrored into install.sh so old releases need no download."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
import traceback

UNINSTALL_DIRS = ('releases', 'python', 'runtime-envs', 'runtime-packs', 'bin')


def uninstall_root(value):
    raw = Path(value).expanduser()
    root = raw.resolve()
    forbidden = {Path('/'), Path.home().resolve(), *Path.cwd().resolve().parents, Path.cwd().resolve()}
    forbidden.update(map(Path, ('/tmp', '/var', '/usr', '/opt', '/home', '/srv', '/mnt', '/media')))
    if not raw.is_absolute() or raw != root or root in forbidden or any(ord(c) < 32 for c in str(root)):
        raise ValueError('拒绝卸载：必须是明确的绝对实例路径，不能是符号链接、主目录或工作区及其父目录')
    if not root.is_dir() or root.stat().st_uid != os.geteuid():
        raise ValueError('实例目录不存在或不属于当前用户；请使用安装时的用户卸载')
    for name in ('.semantic-install-root', 'install.json'):
        path = root/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('目录不是可识别的 Semantic 托管实例：缺少 '+name)
        if path.stat().st_nlink != 1 or path.stat().st_uid != os.geteuid():
            raise ValueError('实例管理文件的所有者或硬链接状态异常：'+name)
    state = json.loads((root/'install.json').read_text())
    if not isinstance(state, dict) or not isinstance(state.get('version'), str) or not state['version']:
        raise ValueError('安装状态无效，拒绝卸载')
    # Do not cross bind mounts or filesystem mounts, including same-device bind mounts.
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        mount = line.split()[4]
        for escaped, char in ((r'\040', ' '), (r'\011', '\t'), (r'\012', '\n'), (r'\134', '\\')):
            mount = mount.replace(escaped, char)
        if Path(mount) == root or root in Path(mount).parents:
            raise ValueError('实例目录内存在挂载点，先由管理员卸载挂载：'+mount)
    for name in (*UNINSTALL_DIRS, 'run', 'logs'):
        path = root/name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('实例管理目录异常：'+name)
    for name in ('run/services.json', 'run/install.lock'):
        path = root/name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('实例管理文件异常：'+name)
    current = root/'current'
    if current.is_symlink():
        if root/'releases' not in current.resolve().parents:
            raise ValueError('current 指向实例外部或非法位置')
    elif current.exists():
        raise ValueError('current 不是安装器符号链接')
    return root, state


def uninstall_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def uninstall_managed(root):
    path = root/'run/services.json'
    records = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(records, dict):
        raise ValueError('services.json 无效')
    owned = {}
    for name, record in records.items():
        if name not in ('server', 'web') or not isinstance(record, dict):
            raise ValueError('存在未知托管进程，拒绝自动停止')
        pid, ticks = record.get('pid'), record.get('start_ticks')
        if not isinstance(pid, int) or pid <= 1 or not isinstance(ticks, str) or not ticks:
            raise ValueError('托管进程身份记录不完整')
        if uninstall_identity(pid) != ticks:
            continue  # Stale PID records are never signalled.
        executable = Path(f'/proc/{pid}/exe').resolve(strict=True)
        expected = 'semantic-server' if name == 'server' else 'semantic-web-gateway'
        if executable.name != expected or root/'releases' not in executable.parents:
            raise ValueError('托管 PID 与实例程序不匹配，拒绝停止')
        owned[pid] = ticks
    return owned


def uninstall_processes(root, allowed=()):
    # Ignore this CLI and its invoking shell/terminal, not arbitrary processes.
    ignored = set()
    pid = os.getpid()
    while pid > 1 and pid not in ignored:
        ignored.add(pid)
        try:
            pid = int(Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[1])
        except (FileNotFoundError, ProcessLookupError):
            break
    busy = []
    prefix = str(root)+'/'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid() or int(proc.name) in allowed:
            continue
        pid = int(proc.name)
        try:
            args = (proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            reasons = []
            if pid not in ignored and any(arg == str(root) or arg.startswith(prefix) or ('='+prefix) in arg for arg in args):
                reasons.append('命令参数引用实例')
            if proc.stat().st_uid == os.geteuid():
                for name in ('exe', 'cwd'):
                    try:
                        target = os.readlink(proc/name)
                        # Linux retains an unlinked directory as a shell's cwd.
                        # Its textual path ends in " (deleted)", but it no longer
                        # references the live installation tree. Check the inode,
                        # not that suffix: a real directory may have that name.
                        if name == 'cwd' and (proc/name).stat().st_nlink == 0:
                            continue
                        if target == str(root) or target.startswith(prefix):
                            reasons.append(('工作目录: ' if name == 'cwd' else '可执行文件: ') + target)
                    except (FileNotFoundError, PermissionError):
                        # Protected system services may expose cmdline but not exe/cwd.
                        # Their readable command arguments are still checked above.
                        pass
            if reasons and uninstall_identity(pid) is not None:
                command = (proc/'comm').read_text().strip()
                busy.append({'pid': pid, 'command': ''.join(c for c in command if c.isprintable()),
                             'reasons': reasons})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            # Same-user processes must be inspectable; do not silently assume safety.
            if proc.exists() and proc.stat().st_uid == os.geteuid():
                raise RuntimeError(f'无法检查同用户进程 {pid}，拒绝卸载')
    return sorted(busy, key=lambda item: item['pid'])


def uninstall_busy(root, allowed):
    busy = uninstall_processes(root, allowed)
    if busy:
        details = '; '.join(f"PID {item['pid']} ({item['command']}): " + ', '.join(item['reasons']) for item in busy)
        raise RuntimeError('实例仍有活动进程，未删除文件；'+details+
                           '。若为终端工作目录，请在对应终端执行 cd ~ 或退出该终端；服务请使用其关闭入口。不自动杀死无关进程。')


def uninstall_confirm(root, purge, yes):
    if yes:
        return
    try:
        with open('/dev/tty', 'w', encoding='utf-8') as output, open('/dev/tty', 'r', encoding='utf-8') as source:
            output.write(f'确认卸载 {root}'+(' 并永久删除全部配置、数据和日志？' if purge else '（保留配置、数据和日志）？')+' [y/N] ')
            output.flush()
            answer = source.readline().strip().lower()
    except OSError:
        raise RuntimeError('非交互环境请显式提供 --yes；先使用 --dry-run 查看计划')
    if answer not in ('y', 'yes'):
        raise RuntimeError('用户取消卸载')


def uninstall_shortcuts(root, state, note, dry_run=False):
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    home = Path.home().resolve()
    for name, checksum in state.get('desktop_shortcuts', {}).items():
        path = Path(name)
        if (not path.is_absolute() or home not in path.parents or path.name != f'semantic-{identity}.desktop'
                or any(p.is_symlink() for p in [path, *path.parents]) or not path.is_file()):
            continue
        if path.stat().st_uid != os.geteuid() or path.stat().st_nlink != 1 or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            note('preserved modified shortcut '+str(path))
            continue
        note(('would remove ' if dry_run else 'removed ') + str(path))
        if not dry_run:
            path.unlink()


def uninstall_entry(argv):
    parser = argparse.ArgumentParser(description='Semantic 离线安全卸载；不下载制品，不卸载系统共享依赖')
    parser.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    parser.add_argument('--purge', action='store_true', help='永久删除该实例全部配置、数据库、日志及其他文件')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='只检查和显示计划，不停止进程或删除文件')
    a = parser.parse_args(argv)
    fd, logfile = tempfile.mkstemp(prefix='semantic-uninstall-', suffix='.log')
    os.close(fd)  # 0600; outside the instance so purge cannot erase failure evidence.
    print('卸载日志:', logfile, flush=True)
    def note(message):
        with open(logfile, 'a') as f:
            f.write(message+'\n')
    try:
        root, state = uninstall_root(a.dir)
        note(f'root={root}; purge={a.purge}; dry_run={a.dry_run}')
        owned = uninstall_managed(root)
        uninstall_busy(root, owned)
        targets = [root] if a.purge else [root/name for name in (*UNINSTALL_DIRS, 'current')
                                          if (root/name).exists() or (root/name).is_symlink()]
        print('将停止已核验的 Server/Web PID:', ', '.join(map(str, owned)) or '无')
        for path in targets:
            print('将删除:', path)
        if not a.purge:
            print('保留: 配置、数据库、日志、场景/Robot 数据及其他非程序目录；同版本重装可恢复运行环境。')
        if a.dry_run:
            uninstall_shortcuts(root, state, note, dry_run=True)
            note('dry-run complete; no processes stopped or files deleted')
            return
        uninstall_confirm(root, a.purge, a.yes)
        (root/'run').mkdir(exist_ok=True, mode=0o700)
        lockfd = os.open(root/'run/install.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lockfd, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            uninstall_root(str(root))  # Validate again after confirmation and locking.
            owned = uninstall_managed(root)
            uninstall_busy(root, owned)
            for pid, ticks in owned.items():
                if uninstall_identity(pid) == ticks:
                    os.kill(pid, signal.SIGTERM)  # Never signal arbitrary process groups/Robots.
                    note(f'SIGTERM owned PID {pid}')
            deadline = time.monotonic()+20
            while any(uninstall_identity(pid) == ticks for pid, ticks in owned.items()):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Server/Web 未在 20 秒内停止；未删除数据，不强制杀进程')
                time.sleep(.1)
            uninstall_busy(root, {})
            uninstall_shortcuts(root, state, note)
            if a.purge:
                shutil.rmtree(root)
                note('purge complete; entire managed instance removed')
            else:
                # Persist a non-runnable state before removing binaries; failed deletion is retryable.
                state.update(ready=False, uninstalled_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
                for path, value in ((root/'install.json', state), (root/'run/services.json', {})):
                    descriptor, temporary = tempfile.mkstemp(prefix='.uninstall-state-', dir=path.parent)
                    with os.fdopen(descriptor, 'w') as f:
                        json.dump(value, f, indent=2)
                    os.replace(temporary, path)
                for path in targets:
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                    note('removed '+str(path))
                note('uninstall complete; user data preserved')
        print('卸载完成。'+('整个实例已永久删除，无法由本脚本恢复。' if a.purge else '程序已删除，配置、数据和日志已保留。'))
        print('未卸载系统软件包；仅清理本实例创建且未被修改的桌面入口。日志:', logfile)
    except Exception:
        with open(logfile, 'a') as f:
            traceback.print_exc(file=f)
        raise
# END EMBEDDED UNINSTALLER
arguments = sys.argv[1:]
if arguments and arguments[0] == 'uninstall':
    arguments = ['--uninstall', *arguments[1:]]
if '--uninstall' in arguments:
    arguments.remove('--uninstall')
    try:
        uninstall_entry(arguments)
    except Exception as error:
        print(f'卸载失败: {error}', file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0)
if '--purge' in arguments or '--dry-run' in arguments:
    raise SystemExit('--purge/--dry-run 必须与 --uninstall 一起使用')
p = argparse.ArgumentParser(description='Semantic verified bootstrap', add_help=False)
p.add_argument('--base-url', default=os.environ.get('SEMANTIC_DOWNLOAD_BASE', 'https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic'))
p.add_argument('--version', default='stable')
p.add_argument('--package', type=pathlib.Path)
p.add_argument('--ticket', type=pathlib.Path, help='Private OSS download ticket; no long-lived credentials required')
p.add_argument('--sha256')
p.add_argument('--allow-http', action='store_true', help='Only for local/private test mirrors')
p.add_argument('--configure-existing', action='store_true', help='Only update installed instance management, LAN access and shortcuts; preserve app version/data')
p.add_argument('-h', '--help', action='store_true')
a, rest = p.parse_known_args()
if a.help:
    print('Semantic: --base-url HTTPS_URL [--version VERSION] | --package FILE [--sha256 HASH]')
    print('安装选项: --dir ABS_PATH --yes --no-start --install-system-deps')
    print('网络: 新安装 Web 默认 0.0.0.0:3000（含本机与局域网）；API/WS 保持本机')
    print('自定义: --web-host IPv4 --web-port PORT；仅本机用 --web-host 127.0.0.1')
    print('桌面入口: 自动检测；--desktop-shortcut 强制创建 / --no-desktop-shortcut 跳过')
    print('已有实例: --configure-existing --dir ABS_PATH --lan（只更新管理工具，不升级业务产物）')
    print('离线卸载: --uninstall --dir ABS_PATH [--purge] [--yes] [--dry-run]')
    print('私有 OSS: --ticket /绝对路径/download.json（由 oss_client.py 生成的限时下载票据）')
    print('端口: --http-port 8080 --ws-port 8081 --web-port 3000 --runtime-port 8090')
    print('默认 OSS: https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic；私有制品请使用 --ticket。')
    raise SystemExit(0)
def status(message):
    color = sys.stderr.isatty() and os.environ.get('TERM', '') not in ('', 'dumb') and 'NO_COLOR' not in os.environ
    for row in message.splitlines():
        marker, _, label = row.partition(' ')
        role = '\033[32m' if marker == '[OK]' else '\033[36m'
        print('  '+(role if color else '')+marker+('\033[0m' if color else '')+'  '+label, file=sys.stderr, flush=True)

def byte_progress(size, total, final=False):
    # stdout may be piped into bash; progress belongs on stderr, never in scripts.
    tty = sys.stderr.isatty() and os.environ.get('TERM') != 'dumb'
    if not tty and not final:
        return
    try:
        width = max(10, os.get_terminal_size(sys.stderr.fileno()).columns - 1)
    except (OSError, ValueError):
        width = 79
    count = min(20, max(3, width//5))
    if total:
        fraction = min(1, size/total)
        bar = '#' * int(count*fraction) + '-' * (count-int(count*fraction))
        message = f'[{bar}] {fraction:5.1%} {size/1024**2:.1f}/{total/1024**2:.1f} MiB'
    else:
        message = f'Download {size/1024**2:.1f} MiB'
    print(('\r\033[2K' if tty else '') + '    '+message[:max(1,width-4)], file=sys.stderr, end='\n' if final or not tty else '', flush=True)
if a.package and a.ticket:
    raise SystemExit('--package 和 --ticket 不能同时使用')
if not a.package and not a.base_url and not a.ticket:
    raise SystemExit('请用 --base-url 指定发布站点，或 --package 指定本地发布包。')
def download(url, target, limit):
    status('[>] 下载发布包' if limit > 1024*1024 else '[>] 读取版本清单')
    scheme = urllib.parse.urlsplit(url).scheme
    if scheme != 'https' and not (a.allow_http and scheme == 'http'):
        raise ValueError('下载必须使用 HTTPS；本地测试可显式 --allow-http')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urllib.parse.urlsplit(newurl).scheme != 'https' and not a.allow_http:
                raise ValueError('拒绝 HTTPS 降级重定向')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    try:
        response = urllib.request.build_opener(Redirect()).open(url, timeout=60)
    except Exception as error:
        raise RuntimeError('下载失败（HTTP '+str(getattr(error, 'code', 'unknown'))+
            '）；私有 OSS 请使用有效 --ticket，过期后重新生成。') from None
    with response, target.open('wb') as f:
        size = 0
        total = int(response.headers.get('Content-Length', '0'))
        last = 0
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > limit: raise ValueError('下载超过大小限制')
            f.write(block)
            if limit > 1024*1024 and time.monotonic() - last >= .2:
                byte_progress(size, total)
                last = time.monotonic()
        if total and total != size:
            raise ValueError('下载长度与服务器声明不一致')
        if limit > 1024*1024:
            byte_progress(size, total, final=True)
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024 * 1024): h.update(block)
    return h.hexdigest()
with tempfile.TemporaryDirectory(prefix='semantic-download-') as temporary:
    work = pathlib.Path(temporary)
    if a.package:
        archive = a.package.expanduser().resolve(strict=True)
        sidecar = pathlib.Path(str(archive) + '.sha256')
        expected = a.sha256 or (sidecar.read_text().split()[0] if sidecar.exists() else '')
    else:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', a.version): raise ValueError('非法版本')
        if a.ticket:
            import datetime
            m = json.loads(a.ticket.read_text())
            if datetime.datetime.fromisoformat(m['expires_at']) <= datetime.datetime.now(datetime.timezone.utc):
                raise ValueError('OSS 下载票据已过期，请用 oss_client.py ticket 重新生成')
            if a.version != 'stable' and a.version != m['version']:
                raise ValueError('下载票据版本与 --version 不一致')
        else:
            suffix = 'channels/stable.json' if a.version == 'stable' else f'releases/{a.version}/linux-x86_64/manifest.json'
            download(a.base_url.rstrip('/') + '/' + suffix, work/'manifest.json', 1024*1024)
            m = json.loads((work/'manifest.json').read_text())
        if m.get('platform') != 'linux-x86_64': raise ValueError('不支持的制品平台')
        path = pathlib.PurePosixPath(m['archive'])
        if path.is_absolute() or '..' in path.parts or not re.fullmatch(r'[A-Za-z0-9/_.-]+', str(path)):
            raise ValueError('非法制品下载路径')
        archive = work/'release.tar.gz'
        expected = a.sha256 or m['sha256']
        url = a.base_url.rstrip('/') + '/' + str(path)
        if a.ticket:
            url = m['archive_url']
            actual = urllib.parse.urlsplit(url)
            expected_url = urllib.parse.urlsplit(m['base_url'].rstrip('/')+'/'+str(path))
            if (actual.scheme, actual.netloc, actual.path) != (expected_url.scheme, expected_url.netloc, expected_url.path) or actual.username or actual.fragment:
                raise ValueError('签名下载 URL 与票据中的 Bucket/制品路径不一致')
        download(url, archive, 8*1024**3)
    if not re.fullmatch(r'[0-9a-f]{64}', expected): raise ValueError('缺少有效 SHA256，请传 --sha256 或保留 .sha256 文件')
    status('[>] 校验 SHA-256')
    if digest(archive) != expected: raise ValueError('制品 SHA256 不匹配，停止安装')
    status('[OK] SHA-256 校验通过\n[>] 安全解包')
    payload = work/'payload'
    payload.mkdir()
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 100000 or sum(x.size for x in members) > 12*1024**3:
            raise ValueError('解包超过大小限制')
        seen = set()
        for item in members:
            path = pathlib.PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or str(path) in seen or not (item.isfile() or item.isdir()):
                raise ValueError('不安全的归档路径/链接: ' + item.name)
            seen.add(str(path))
        for item in members:
            target = payload/item.name
            if item.isdir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(item) as source, target.open('wb') as dest: shutil.copyfileobj(source, dest)
            target.chmod(0o755 if item.mode & 0o111 else 0o644)
    status('[OK] 解包完成；开始'+('配置已有实例' if a.configure_existing else '安装'))
    # The child already reports its error; preserve the exit status without a second traceback.
    result = subprocess.run([sys.executable, '-B', str(payload/'installer.py'), 'configure' if a.configure_existing else 'install', '--payload', str(payload), *rest])
    raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
PY
}
main "$@"
