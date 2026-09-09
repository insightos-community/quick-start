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

"""Dependency-free terminal presentation, networking and desktop integration."""
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text)


def lines(text, columns):
    """Wrap by terminal cells, including CJK; strip terminal control characters."""
    for paragraph in str(text).split('\n'):
        row = ''
        for char in paragraph:
            if unicodedata.category(char).startswith('C'):
                continue
            if row and width(row + char) > max(1, columns):
                yield row
                row = ''
            row += char
        yield row


def columns(stream):
    try:
        return max(10, os.get_terminal_size(stream.fileno()).columns - 1)
    except (OSError, ValueError, AttributeError):
        return 79


def colored(stream):
    return terminal(stream) and 'NO_COLOR' not in os.environ


def terminal(stream):
    return stream.isatty() and os.environ.get('TERM', '') not in ('dumb', '')


def height(stream):
    try:
        return max(6, os.get_terminal_size(stream.fileno()).lines)
    except (OSError, ValueError, AttributeError):
        return 24


class Console:
    """Small cell-aware forms. ANSI is added after wrapping, never measured as text."""
    palette = {'title': '1;36', 'label': '2', 'value': '39', 'ok': '1;32',
               'warn': '33', 'error': '1;31', 'command': '36', 'secret': '1;33', 'border': '2'}

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout

    @property
    def size(self):
        return min(82, columns(self.stream))

    def paint(self, text, role='value'):
        if colored(self.stream):
            return '\033['+self.palette[role]+'m'+text+'\033[0m'
        return text

    def rule(self, title=''):
        inner = self.size - 4
        label = next(lines(' '+title+' ' if title else '', inner))
        return '  '+self.paint(label, 'title')+self.paint('─' * max(0, inner-width(label)), 'border')

    def row(self, label, value, role='value'):
        available = self.size - 4
        # Stacked labels keep very narrow terminals readable.
        if available < 28:
            result = ['  '+self.paint(row, 'label') for row in lines(label, available)]
            result += ['    '+self.paint(row, role) for row in lines(str(value), max(1, available-2))]
            return result
        label_size = 8
        result = []
        label = next(lines(str(label), label_size))
        prefix = label+' '*(label_size-width(label))+'  '
        for index, row in enumerate(lines(str(value), available-label_size-2)):
            result.append('  '+self.paint(prefix if index == 0 else ' '*(label_size+2), 'label')+self.paint(row, role))
        return result

    def form(self, title, rows):
        result = [self.rule(title)]
        for row in rows:
            result.extend(self.row(*row))
        return result

    def write(self, rows, clear=False):
        if clear and terminal(self.stream):
            # Clear the viewport only; never erase shell scrollback (CSI 3J).
            self.stream.write('\033[2J\033[H')
        self.stream.write('\n'.join(rows)+'\n')
        self.stream.flush()


def settings_form(title, rows, stream=None):
    console = Console(stream)
    console.write(console.form(title, rows))


class Progress:
    def __init__(self, tasks, stream=None):
        self.tasks, self.stream = tasks, stream or sys.stderr
        self.done = 0
        self.active = ''
        self.started = time.monotonic()
        self.event = threading.Event()
        self.current = None
        self.animated = terminal(self.stream)
        self.console = Console(self.stream)
        self.states = ['等待'] * len(tasks)
        self.durations = [''] * len(tasks)
        self.index = -1
        self.log_path = ''
        self.detail = ''
        self.error = False
        if not self.animated:
            self.console.write(self.console.form('安装任务', [(str(i), task) for i, task in enumerate(tasks, 1)]))

    def next(self, task):
        self.finish()
        self.current = self.stage(task)
        self.current.__enter__()

    def finish(self, error=None):
        if self.current:
            current, self.current = self.current, None
            current.__exit__(type(error) if error else None, error, error.__traceback__ if error else None)

    def say(self, text):
        for row in lines(text, columns(self.stream)):
            print(row, file=self.stream, flush=True)

    def frame(self):
        while not self.event.wait(.4):
            self.render()

    def render(self):
        rows = []
        count = len(self.tasks)
        for i, task in enumerate(self.tasks):
            active = i == self.index and self.states[i] == '运行'
            elapsed = f'{time.monotonic()-self.started:.0f}s' if active else self.durations[i]
            role = 'command' if active else 'ok' if self.states[i] == '完成' else 'error' if self.states[i] == '失败' else 'label'
            rows.append((f'{i+1:02d} {self.states[i]}', task + ('  '+elapsed if elapsed else ''), role))
        bar_size = min(20, max(3, self.console.size//4))
        done = bar_size*self.done//count
        bar = '['+'#'*done+'-'*(bar_size-done)+f'] {self.done}/{count}  {self.done*100//count}%'
        output = self.console.form('SEMANTIC / 安装', [('进度', bar, 'ok' if self.done == count else 'command')])
        output += self.console.form('任务', rows)
        if self.detail:
            output += self.console.row('当前命令', self.detail, 'command')
        if self.log_path:
            output += self.console.row('日志', self.log_path, 'label')
        # Resize-safe compact view when the whole checklist does not fit vertically.
        if len(output) >= height(self.stream)-1:
            current = rows[max(0, self.index)]
            output = self.console.form('SEMANTIC', [('进度', f'{self.done}/{count} 完成'), current])
            if self.detail:
                output += self.console.row('当前命令', self.detail, 'command')
            if self.log_path:
                output += self.console.row('日志', self.log_path, 'label')
        self.console.write(output[:max(1, height(self.stream)-1)], clear=True)

    @contextmanager
    def stage(self, task):
        self.active, self.started = task, time.monotonic()
        self.index += 1
        self.states[self.index] = '运行'
        if self.animated:
            self.render()
        else:
            self.console.write(self.console.row(f'{self.index+1:02d} 运行', task, 'command'))
        self.event.clear()
        thread = threading.Thread(target=self.frame, daemon=True) if self.animated else None
        if thread:
            thread.start()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            self.event.set()
            if thread:
                thread.join()
            if not failed:
                self.done += 1
            self.states[self.index] = '失败' if failed else '完成'
            self.durations[self.index] = f'{time.monotonic()-self.started:.1f}s'
            self.error = failed
            if self.animated:
                self.render()
            else:
                self.console.write(self.console.row('[FAIL]' if failed else '[OK]',
                    f'{task} · {self.durations[self.index]} · {self.done*100//len(self.tasks)}%', 'error' if failed else 'ok'))


def web_host(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError('--web-host 必须为 IPv4 地址；--lan 表示 0.0.0.0') from None
    if address.is_multicast or int(address) == 0xffffffff:
        raise ValueError('不能监听组播或广播地址')
    return str(address)


def web_probe(host):
    return '127.0.0.1' if host == '0.0.0.0' else host


def lan_addresses():
    addresses = set()
    if shutil.which('ip'):
        try:
            reply = subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'scope', 'global'], timeout=3, stderr=subprocess.DEVNULL)
            for interface in json.loads(reply):
                for item in interface.get('addr_info', []):
                    addresses.add(item.get('local', ''))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if not addresses:
        try:
            addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
    return sorted(a for a in addresses if a and not ipaddress.IPv4Address(a).is_loopback)


def urls(state):
    host, port = state.get('web_host', '127.0.0.1'), state['web_port']
    if host != '0.0.0.0':
        return [f'http://{host}:{port}']
    return [f'http://127.0.0.1:{port}', *[f'http://{a}:{port}' for a in lan_addresses()]]


def desktop_escape(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def desktop_shortcuts(root, state, mode='auto'):
    if mode == 'never':
        return '已跳过桌面入口'
    home = Path.home().resolve()
    desktop = None
    if shutil.which('xdg-user-dir'):
        try:
            candidate = Path(subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True, timeout=3).strip())
            if candidate.is_absolute() and candidate != home:
                desktop = candidate
        except (OSError, subprocess.SubprocessError):
            pass
    graphical = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY') or (desktop and desktop.is_dir()))
    if mode == 'auto' and not graphical:
        return '未检测到桌面，已跳过快捷方式（可用 --desktop-shortcut 显式创建）'
    if not shutil.which('xdg-open'):
        return '未找到 xdg-open，跳过快捷方式；安装 xdg-utils 后重试'
    if desktop is None and mode == 'always':
        desktop = home/'Desktop'
    data = Path(os.environ.get('XDG_DATA_HOME', str(home/'.local/share')))
    targets = [data/'applications']
    if desktop:
        targets.append(desktop)
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    filename = f'semantic-{identity}.desktop'
    url = f"http://{web_probe(state.get('web_host', '127.0.0.1'))}:{state['web_port']}"
    icon = root/'bin/semantic-manager/assets/ios.png'
    text = ('[Desktop Entry]\nType=Application\nVersion=1.0\nName=Semantic\n'
            'Comment=Open Semantic Web\nExec=xdg-open '+url+'\nTryExec=xdg-open\n'
            'Icon='+desktop_escape(icon)+'\nTerminal=false\nCategories=Development;\n'
            'StartupNotify=false\nX-Semantic-Root='+desktop_escape(root)+'\n')
    records = state.setdefault('desktop_shortcuts', {})
    created = []
    for directory in targets:
        # Never write through links, outside the user's home, or over foreign files.
        if not directory.is_absolute() or home not in directory.parents or any(p.is_symlink() for p in [directory, *directory.parents]):
            continue
        path = directory/filename
        if path.is_symlink() or (path.exists() and (path.stat().st_uid != os.geteuid() or path.stat().st_nlink != 1 or
                hashlib.sha256(path.read_bytes()).hexdigest() != records.get(str(path)))):
            continue
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        path.chmod(0o755 if directory == desktop else 0o644)
        records[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        created.append(str(path))
        if directory == desktop and shutil.which('gio') and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            try:
                subprocess.run(['gio', 'set', str(path), 'metadata::trusted', 'true'], timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
    return ('快捷入口: ' + ', '.join(created) + '\n桌面如提示不受信任，请右键选择“允许启动”。') if created else '未创建桌面入口：目标路径不安全或文件已被修改'


def welcome(root, state, started, desktop_message='', stream=None, clear=True):
    import shlex
    console = Console(stream)
    stream = console.stream
    compact = terminal(stream) and height(stream) < 30
    secret = None
    tty = None
    try:
        tty = open('/dev/tty', 'w', encoding='utf-8')
        if tty.isatty():
            secret = json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD']
    except OSError:
        pass
    try:
        # Only an actual TTY receives the inline secret. Redirected output remains public.
        inline_secret = secret is not None and stream.isatty()
        title = ['SEMANTIC', '欢迎使用 · 从语义到行动', state['version'],
                 '服务已启动' if started else '尚未启动服务']
        output = []
        # Keep the original orca PNG for desktop shortcuts, not terminal ASCII art.
        for i, text in enumerate(title):
            role = 'title' if i < 2 else 'label' if i == 2 else 'ok' if started else 'warn'
            output.extend('  '+console.paint(row, role) for row in lines(text, console.size-4))
        access = []
        addresses = urls(state)
        for index, url in enumerate(addresses):
            access.append(('访问' if len(addresses) == 1 else '本机' if index == 0 else '局域网', url, 'command'))
        access += [('账号', 'admin'),
                   ('密码', secret if inline_secret else '仅终端显示；见 configs/secrets.json', 'secret' if inline_secret else 'label')]
        output += console.form('访问', access)
        output += console.form('管理', [('启动', 'semanticctl start', 'command'), ('停止', 'semanticctl stop', 'command')])
        output += console.form('环境', [
            ('当前会话', 'export SEMANTIC_HOME='+shlex.quote(str(root)), 'command'),
            ('', 'export PATH="$SEMANTIC_HOME/bin:$PATH"', 'command'),
            ('持久化', '将上面两行加入 ~/.bashrc 或 ~/.zshrc', 'label')])
        notes = [('日志', 'semanticctl logs', 'command')]
        if desktop_message.startswith('快捷入口:') or (not desktop_message and state.get('desktop_shortcuts')):
            notes.append(('桌面', '已创建 · 首次可能需右键“允许启动”', 'ok'))
        elif desktop_message:
            notes.append(('桌面', '已跳过' if '跳过' in desktop_message else '未创建；检查 xdg-open / 目录权限', 'label'))
        if state.get('web_host', '127.0.0.1') != '127.0.0.1':
            notes.append(('网络', f"TCP {state['web_port']} 仅可信内网 · 公网需 HTTPS", 'warn'))
        if not compact:
            notes += [('密码文件', str(root/'configs/secrets.json'), 'label'),
                      ('提示', '先停止场景 / Robot 再停服务；不配置开机自启', 'label')]
        output += console.form('提示', notes)
        # Success clears the live task page, not scrollback. Failure never calls welcome.
        console.write(output, clear=clear)
        if secret is not None and not inline_secret and tty and tty.isatty():
            private_console = Console(tty)
            private_console.write(private_console.form('登录凭据 · 仅终端', [('密码', secret, 'secret')]))
    finally:
        if tty:
            tty.close()
