#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

"""
Semantic 安装器 (TUI)
由《新版Semantic安装步骤》PDF 转化: 分阶段执行 Ubuntu 从 0 到 1 的完整安装流程。

布局:
    顶部: 标题 / 状态
    左侧: 阶段与步骤树 (状态: · pending  ▶ running  ✓ ok  ✗ fail  ! warn  - skip  M 手动)
    中间: 实时日志输出
    底部: 快捷键

环境变量: e 键打开设置 (路径 / 版本 / 镜像 / 渲染 / 服务地址 / 各仓库分支),
保存到 installer-settings.json, 并生成 semantic-env.sh 供终端 source。

仅依赖 Python3 标准库 (curses)。无头模式: --list / --run-all / --stage N
"""

import argparse
import glob
import curses
import json
import locale
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import traceback
import unicodedata
import zipfile
from collections import deque
from pathlib import Path
from queue import Empty, Queue

from terminal_compat import prepare_terminal

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = SCRIPT_DIR / "installer-settings.json"
STATUS_FILE = SCRIPT_DIR / "installer-status.json"
ENV_SH = SCRIPT_DIR / "semantic-env.sh"
LOG_DIRNAME = ".tui-logs"
LOG_LIMIT = 4000
CMD_MARK = "\u00a7"  # § 标记脚本回显的命令行
REPO_EVENT_MARK = "@@semantic-repo:"
# 子进程的颜色、光标和超链接控制序列不能直接交给 curses 渲染。
ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1b\]|\x9d)[^\x07\x1b\x9c\r\n]*(?:\x07|\x1b\\|\x9c|(?=\r?\n|$))"
    r"|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]"
    r"|\x1b[ -/]*[0-~]"
)


def plain_log_text(text):
    """保留 Unicode 正文，去除日志中的终端控制码（不模拟终端）。"""
    text = ANSI_ESCAPE_RE.sub("", str(text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)


DONE_STATES = {"ok", "skip", "warn", "done"}
STAGE_PREREQ = {6: [1, 2, 3, 4, 5], 7: [1, 2, 3, 4, 5, 6], 8: [1, 2, 3, 4, 5]}

STAGES = [
    (1, "系统依赖"),
    (2, "拉代码与资产"),
    (3, "构建 Server"),
    (4, "登记 MuJoCo Runtime"),
    (5, "Robot 执行栈"),
    (6, "启动 Server/Web/Skills"),
    (7, "Studio 手动联调"),
    (8, "日常再开"),
]


# 设置


DEFAULT_SETTINGS = {
    "SEMANTIC": "$HOME/workspace/semantic",
    "GITLAB": "https://github.com/insightos-community",
    "GITLAB_USER": "oauth2",
    "GITLAB_OAUTH_CLIENT_ID": "",
    "GITLAB_OAUTH_CLIENT_SECRET": "",
    "OAUTH_CALLBACK_PORT": "8377",
    "PAT_PAGE_PATH": "",
    "APPS_PAGE_PATH": "",
    "GO_VERSION": "1.23.8",
    "BUNDLE_VER": "0.5.0-dev",
    "UV_DEFAULT_INDEX": "https://mirrors.aliyun.com/pypi/simple",
    "RUNTIME_WHEEL_SOURCE": "auto",
    "SEMANTIC_ADMIN_PASSWORD": "test-admin-pass",
    "SEMANTIC_MUJOCO_GL": "egl",
    "APT_MIRROR": "https://mirrors.aliyun.com/ubuntu",
    "GO_DL_MIRROR": "https://mirrors.aliyun.com/golang",
    "GO_PROXY": "https://goproxy.cn,direct",
    "NODE_MIRROR": "https://cdn.npmmirror.com/binaries/node",
    "NODE_VERSION": "22.14.0",
    "NPM_REGISTRY": "https://registry.npmmirror.com",
    "GITHUB_PROXY": "",
    "SUDO_AUTH": "tui",
    "REPO_VERSIONS_FILE": "",
    "SERVER_HTTP": "http://127.0.0.1:8080",
    "SERVER_WS": "ws://127.0.0.1:8081/ws/pilot",
    "WEB_URL": "http://127.0.0.1:3000",
    "ABILITY_PORT_FIRST": "18100",
    "ABILITY_PORT_LAST": "18199",
    "BR_SEMANTIC_FRAMEWORK": "feature/robot-ability-binding",
    "BR_SEMANTIC_WEB": "feature/v050-device-workbench",
    "BR_SEMANTIC_DOCS": "feature/v050-robot-runtime-docs",
    "BR_R1PRO_ABILITY": "feature/r1pro-seven-abilities",
    "BR_ROBOT_SDK": "feature/v040-robot-sdk-core",
    "BR_ROBOT_SKILL": "feature/robot-skill-skeleton",
    "BR_MUJOCO_RUNTIME": "feature/v060-r1pro-tote-gripper-runtime",
    "BR_MUJOCO_ASSET": "feature/v060-r1pro-tote-gripper-assets",
    "BR_SEMANTIC_DEPLOYMENT": "feature/v050-r1pro-runtime-bundle",
    "BR_ABILITY_FRAMEWORK": "v2.1.0",
    "BR_ABILITY_PY_SDK": "v0.4.0",
    "BR_ABILITY_SCAFFOLD": "v1.2.0",
}

SETTINGS_GROUPS = [
    ("路径与远程", ["SEMANTIC", "GITLAB"]),
    ("GitLab 凭证", ["GITLAB_USER", "GITLAB_OAUTH_CLIENT_ID",
                 "GITLAB_OAUTH_CLIENT_SECRET", "OAUTH_CALLBACK_PORT",
                 "PAT_PAGE_PATH", "APPS_PAGE_PATH"]),
    ("版本", ["GO_VERSION", "BUNDLE_VER"]),
    ("镜像与密钥", ["UV_DEFAULT_INDEX", "RUNTIME_WHEEL_SOURCE", "SEMANTIC_ADMIN_PASSWORD"]),
    ("国内镜像 (置空即直连)", ["APT_MIRROR", "GO_DL_MIRROR", "GO_PROXY", "NODE_MIRROR",
                          "NODE_VERSION", "NPM_REGISTRY", "GITHUB_PROXY"]),
    ("sudo 鉴权", ["SUDO_AUTH"]),
    ("版本清单", ["REPO_VERSIONS_FILE"]),
    ("渲染后端", ["SEMANTIC_MUJOCO_GL"]),
    ("服务地址与端口", ["SERVER_HTTP", "SERVER_WS", "WEB_URL", "ABILITY_PORT_FIRST", "ABILITY_PORT_LAST"]),
    ("仓库分支", [
        "BR_SEMANTIC_FRAMEWORK", "BR_SEMANTIC_WEB", "BR_SEMANTIC_DOCS",
        "BR_R1PRO_ABILITY", "BR_ROBOT_SDK", "BR_ROBOT_SKILL",
        "BR_MUJOCO_RUNTIME", "BR_MUJOCO_ASSET", "BR_SEMANTIC_DEPLOYMENT",
    ]),
]

SETTINGS_DESC = {
    "SEMANTIC": "工作根目录 (所有仓库的父目录)",
    "GITLAB": "GitLab 组地址(含组路径, 克隆用); OAuth/PAT 页面会自动改用实例根地址",
    "GITLAB_USER": "HTTPS 凭证用户名; PAT 方式一般填 oauth2 也可",
    "GITLAB_OAUTH_CLIENT_ID": "OAuth 应用 ID (g 键 OAuth 登录用); 在 GitLab 个人设置 Applications 创建",
    "GITLAB_OAUTH_CLIENT_SECRET": "OAuth 应用 Secret; Redirect URI 填 http://127.0.0.1:回调端口/callback",
    "OAUTH_CALLBACK_PORT": "OAuth 本地回调端口 (默认 8377, 需与应用里 Redirect URI 一致)",
    "PAT_PAGE_PATH": "PAT 页面路径 (留空自动探测; 404 时可填 /-/user_settings/personal_access_tokens)",
    "APPS_PAGE_PATH": "应用页面路径 (留空自动探测; 404 时可填 /-/user_settings/applications)",
    "GO_VERSION": "官方 Go 版本, go.mod 要求 >= 1.23",
    "BUNDLE_VER": "r1pro-mujoco Bundle 版本目录名后缀",
    "UV_DEFAULT_INDEX": "uv 的 PyPI 镜像; 备用: https://pypi.tuna.tsinghua.edu.cn/simple",
    "RUNTIME_WHEEL_SOURCE": "auto = 缓存/包源优先, LFS 兜底; lfs = 只从 LFS 获取; offline = 仅校验缓存",
    "SEMANTIC_ADMIN_PASSWORD": "写入 framework .env 的管理员密码 (不要提交 Git)",
    "SEMANTIC_MUJOCO_GL": "egl (默认) 或 osmesa (EGL 起不来时, 需另装 libosmesa6)",
    "APT_MIRROR": "apt 软件源基址, 步骤 1.0 自动切换; 例 https://mirrors.aliyun.com/ubuntu",
    "GO_DL_MIRROR": "Go 官方包下载镜像; 例 https://mirrors.aliyun.com/golang 或 https://golang.google.cn/dl",
    "GO_PROXY": "go env -w GOPROXY; 例 https://goproxy.cn,direct (备用 https://goproxy.io,direct)",
    "NODE_MIRROR": "Node 二进制镜像 (npmmirror); 置空则改走 NodeSource apt 源",
    "NODE_VERSION": "镜像方式安装的 Node 版本; 置空 = 自动解析 latest-v22.x",
    "NPM_REGISTRY": "npm registry, 写入 ~/.npmrc; 例 https://registry.npmmirror.com",
    "GITHUB_PROXY": "GitHub 代理前缀, 加速 uv 及 Python 解释器下载; 例 https://mirror.ghproxy.com",
    "SUDO_AUTH": "tui = TUI 内弹密码框经 sudo -S 鉴权(推荐); terminal = 临时切到真实终端输密码",
    "REPO_VERSIONS_FILE": "子仓库版本清单 repo-versions.json 路径 (repo_versions.py 维护; 留空按 $SEMANTIC/安装器目录/quick-start 顺序查找), 2.2 优先读它",
    "SERVER_HTTP": "Server HTTP 地址 (登录/发布 Skill 用)",
    "SERVER_WS": "Server WebSocket 地址 (Pilot 用, 须含 /ws/pilot; Web 前端自动取其根地址)",
    "WEB_URL": "Web 开发服务器地址",
    "ABILITY_PORT_FIRST": "robot_runtime.ability_port_first",
    "ABILITY_PORT_LAST": "robot_runtime.ability_port_last",
}

# 本地目录, GitLab 仓库路径, 分支设置键 (None = 只有 main, 不切)
REPOS = [
    ("semantic-framework", "Semantic-Framework", "BR_SEMANTIC_FRAMEWORK"),
    ("semantic-web", "semantic-web", "BR_SEMANTIC_WEB"),
    ("semantic-docs", "semantic-docs", "BR_SEMANTIC_DOCS"),
    ("semantic-ability/r1pro-ability", "r1pro-ability", "BR_R1PRO_ABILITY"),
    ("semantic-robotsdk/robot-sdk", "robot-sdk", "BR_ROBOT_SDK"),
    ("semantic-skill/robot-skill", "robot-skill", "BR_ROBOT_SKILL"),
    ("semantic-simulation/mujoco-runtime", "mujoco-runtime", "BR_MUJOCO_RUNTIME"),
    ("semantic-scene/mujoco-asset", "mujoco-asset", "BR_MUJOCO_ASSET"),
    ("semantic-robot-deployment", "semantic-deployment", "BR_SEMANTIC_DEPLOYMENT"),
    ("semantic-ability/ability-runtime", "ability-runtime", None),
    ("ability-framework/abilityframework", "AbilityFramework", "BR_ABILITY_FRAMEWORK"),
    ("ability-framework/ability-py-sdk", "Ability-SDK-Python", "BR_ABILITY_PY_SDK"),
    ("ability-framework/ability-scaffold", "ability-scaffold", "BR_ABILITY_SCAFFOLD"),
]


def sx(s):
    """展开 ~ 与 $VAR"""
    return os.path.expandvars(os.path.expanduser(s)) if isinstance(s, str) else s


def gitlab_root(url):
    """从组地址提取 GitLab 实例根 (scheme://host[:port]);
    OAuth/PAT/profile 页面必须挂在根地址下, 挂在组路径下会 404"""
    m = re.match(r"^(https?://[^/]+)", (url or "").strip())
    return m.group(1) if m else (url or "").strip().rstrip("/")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def write_env_sh(settings):
    lines = [
        "# 由 semantic_installer.py 生成, 可 source 到任意终端",
        f'export SEMANTIC="{settings["SEMANTIC"]}"',
        f'export UV_DEFAULT_INDEX="{settings["UV_DEFAULT_INDEX"]}"',
        f'export SEMANTIC_MUJOCO_GL="{settings["SEMANTIC_MUJOCO_GL"]}"',
        f'export SERVER_HTTP="{settings["SERVER_HTTP"]}"',
        f'export SERVER_WS="{settings["SERVER_WS"]}"',
        'export PATH="/usr/local/go/bin:$HOME/go/bin:$HOME/.local/bin:$PATH"',
    ]
    if settings.get("GO_PROXY", "").strip():
        lines.append(f'export GOPROXY="{settings["GO_PROXY"]}"')
    if settings.get("NPM_REGISTRY", "").strip():
        lines.append(f'# npm registry 已在步骤 1.6 写入 ~/.npmrc: {settings["NPM_REGISTRY"]}')
    gp = settings.get("GITHUB_PROXY", "").strip()
    if gp:
        lines.append(
            "export UV_PYTHON_INSTALL_MIRROR=\"" + gp.rstrip("/") +
            "/https://github.com/astral-sh/python-build-standalone/releases/latest/download\"")
    lines += [
        "# Python 3.13 路径: PYTHON313=$(uv python find 3.13)",
        "",
    ]
    ENV_SH.write_text("\n".join(lines), encoding="utf-8")



# 显示宽度工具 (CJK 占 2 列)


_WIDE_CACHE = {}


def is_wide(ch):
    r = _WIDE_CACHE.get(ch)
    if r is None:
        r = unicodedata.east_asian_width(ch) in ("W", "F")
        _WIDE_CACHE[ch] = r
    return r


def dwidth(s):
    return sum(2 if is_wide(c) else 1 for c in s)


def trunc(s, width):
    if dwidth(s) <= width:
        return s
    out, cw = "", 0
    for ch in s:
        c = 2 if is_wide(ch) else 1
        if cw + c > width - 1:
            break
        out += ch
        cw += c
    return out + "…"


def wrap_cells(s, width):
    """按显示单元格折行 (中文无空格也可断)"""
    if width <= 0:
        return [s]
    lines, cur, cw = [], "", 0
    for ch in s:
        c = 2 if is_wide(ch) else 1
        if ch == "\t":
            ch, c = " ", 1
        if cw + c > width:
            lines.append(cur)
            cur, cw = ch, c
        else:
            cur += ch
            cw += c
    if cur or not lines:
        lines.append(cur)
    return lines


def norm_key(ch):
    """get_wch 对普通字符返回 str, 特殊键返回 int; 统一转 int 方便比较"""
    if isinstance(ch, str) and len(ch) == 1:
        return ord(ch)
    return ch


# keypad 拼方向键依赖 ESCDELAY。wget 的 timeout 一旦短于 ESCDELAY, ncurses
# 会在 ESC 后超时, 把 ↑↓ 拆成 ESC / [ / A, 表现为“卡住”或误触发 A(连续执行)。
# 长按自动重复也要求一次排空缓冲区, 不能每读一键就全量重绘。
INPUT_POLL_MS = 80
ESC_GATHER_MS = 25


def _csi_is_final(ch):
    return ch == 126 or 65 <= ch <= 90 or 97 <= ch <= 122


def _map_csi(params, final):
    letter = chr(final) if 32 <= final < 127 else ""
    simple = {
        "A": curses.KEY_UP, "B": curses.KEY_DOWN,
        "C": curses.KEY_RIGHT, "D": curses.KEY_LEFT,
        "H": curses.KEY_HOME, "F": curses.KEY_END,
    }
    if letter in simple:
        return simple[letter]
    raw = "".join(chr(c) for c in params if 48 <= c <= 57 or c == 59)
    num = raw.split(";")[0] if raw else ""
    if letter == "~":
        return {
            "5": curses.KEY_PPAGE, "6": curses.KEY_NPAGE,
            "1": curses.KEY_HOME, "4": curses.KEY_END,
            "7": curses.KEY_HOME, "8": curses.KEY_END,
        }.get(num)
    return None


def _incomplete_esc(raw):
    if not raw or raw[0] != 27:
        return False
    if len(raw) == 1:
        return True
    if raw[1] == 91:
        return not any(_csi_is_final(c) for c in raw[2:])
    if raw[1] == 79:
        return len(raw) < 3
    return False


def parse_curses_raw(raw):
    """解析 get_wch 字节流。已完整的 CSI/SS3 变成 KEY_*; 不完整的 ESC 前缀原样留下。"""
    keys = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != 27:
            keys.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            break
        nxt = raw[i + 1]
        if nxt == 91:
            j = i + 2
            while j < n and not _csi_is_final(raw[j]):
                j += 1
            if j >= n:
                break
            mapped = _map_csi(raw[i + 2:j], raw[j])
            if mapped is not None:
                keys.append(mapped)
            i = j + 1
            continue
        if nxt == 79:
            if i + 2 >= n:
                break
            mapped = _map_csi([], raw[i + 2])
            if mapped is not None:
                keys.append(mapped)
            i += 3
            continue
        keys.append(27)
        i += 1
    return keys, raw[i:]


class CursesInput:
    """带 CSI 回退解析的按键读取, 避免方向键被 timeout 拆开。"""

    def __init__(self):
        self.raw = []
        self.keys = deque()
        self.poll_ms = INPUT_POLL_MS

    def configure(self, win):
        try:
            curses.set_escdelay(ESC_GATHER_MS)
        except Exception:
            pass
        try:
            win.keypad(True)
        except curses.error:
            pass
        try:
            win.nodelay(False)
        except curses.error:
            pass
        win.timeout(self.poll_ms)

    def restore(self, win):
        self.poll_ms = INPUT_POLL_MS
        self.configure(win)

    def block(self, win):
        self.poll_ms = -1
        self.configure(win)

    def _wget(self, win):
        try:
            ch = win.get_wch()
        except curses.error:
            return None
        if ch in (None, -1):
            return None
        return norm_key(ch)

    def _parse(self):
        keys, rest = parse_curses_raw(self.raw)
        self.raw = rest
        self.keys.extend(keys)

    def _gather_esc(self, win):
        win.timeout(ESC_GATHER_MS)
        while _incomplete_esc(self.raw):
            extra = self._wget(win)
            if extra is None:
                if self.raw == [27]:
                    self.keys.append(self.raw.pop(0))
                else:
                    self.raw = []
                break
            self.raw.append(extra)
            self._parse()
            win.timeout(0)

    def read_key(self, win, wait=True):
        if self.keys:
            return self.keys.popleft()
        win.timeout(self.poll_ms if wait else 0)
        ch = self._wget(win)
        if ch is None:
            if _incomplete_esc(self.raw):
                if wait:
                    self._gather_esc(win)
                elif self.raw == [27]:
                    self.keys.append(self.raw.pop(0))
                else:
                    self.raw = []
            return self.keys.popleft() if self.keys else None
        self.raw.append(ch)
        self._parse()
        if _incomplete_esc(self.raw):
            self._gather_esc(win)
        return self.keys.popleft() if self.keys else None

    def read_nav_burst(self, win):
        first = self.read_key(win, wait=True)
        if first is None:
            return []
        nav = {
            curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE,
            curses.KEY_HOME, curses.KEY_END, curses.KEY_LEFT, curses.KEY_RIGHT,
            ord("j"), ord("k"),
        }
        if first not in nav:
            return [first]
        out = [first]
        try:
            while len(out) < 64:
                k = self.read_key(win, wait=False)
                if k is None:
                    break
                if k not in nav:
                    self.keys.appendleft(k)
                    break
                out.append(k)
        finally:
            self.configure(win)
        return out


def url_host_port(url):
    m = re.match(r"^(?:http|ws)s?://([^/:]+)(?::(\d+))?", url or "")
    if not m:
        return None, None
    host = m.group(1)
    port = int(m.group(2)) if m.group(2) else (443 if "s://" in url else 80)
    return host, port


def _port_open(host, port, timeout=0.3):
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_alive(pid):
    """真正在跑才算活着。僵尸已被回收资源，不能挡启动。"""
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("State:"):
                return not line.split()[1].startswith("Z")
    except OSError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _iter_user_procs():
    """当前用户的进程 (pid, exe, cmd, cwd)。跳过安装器自身。"""
    proc = Path("/proc")
    if not proc.is_dir():
        return
    uid = os.getuid()
    skip = {os.getpid(), os.getppid(), 1}
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) in skip:
            continue
        try:
            owner = None
            state = None
            for line in (entry / "status").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Uid:"):
                    owner = int(line.split()[1])
                elif line.startswith("State:"):
                    state = line.split()[1]
            if owner != uid or (state is not None and state.startswith("Z")):
                continue
            exe = str((entry / "exe").resolve(strict=True))
            cmd = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="replace")
                .strip()
            )
            try:
                cwd = str((entry / "cwd").resolve(strict=True))
            except OSError:
                cwd = ""
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
            continue
        yield int(entry.name), exe, cmd, cwd


def _signal_tree(pid, sig):
    try:
        pgid = os.getpgid(pid)
        mine = os.getpgid(0)
    except OSError:
        return
    try:
        if pgid not in (0, 1, mine):
            os.killpg(pgid, sig)
        else:
            os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            return


def _stop_pids(app, pids, label, timeout=12):
    pids = sorted({int(p) for p in pids if _pid_alive(p)})
    if not pids:
        return True
    app.log("note", f"发现旧{label}: pid={pids}，先停止再继续")
    for pid in pids:
        _signal_tree(pid, signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = [p for p in pids if _pid_alive(p)]
        if not pids:
            app.log("ok", f"旧{label}已退出")
            return True
        time.sleep(0.2)
    leftover = [p for p in pids if _pid_alive(p)]
    for pid in leftover:
        _signal_tree(pid, signal.SIGKILL)
    time.sleep(0.3)
    leftover = [p for p in leftover if _pid_alive(p)]
    if leftover:
        app.log("err", f"旧{label}仍未退出: pid={leftover}")
        return False
    app.log("ok", f"旧{label}已强制退出")
    return True


def _workspace_server_pids(framework_root):
    root = os.path.realpath(framework_root)
    binary = os.path.join(root, ".output/bin/semantic-server")
    config = os.path.join(root, ".output/configs/semantic-server.yaml")
    found = []
    for pid, exe, cmd, _cwd in _iter_user_procs():
        if exe == binary or binary in cmd or (config in cmd and "semantic-server" in cmd):
            found.append(pid)
    return found


def _workspace_web_pids(web_root):
    root = os.path.realpath(web_root)
    prefix = root + os.sep
    found = []
    for pid, exe, cmd, cwd in _iter_user_procs():
        in_web = cwd == root or cwd.startswith(prefix)
        looks_dev = ("vite" in cmd) or ("npm run dev" in cmd) or exe.endswith("/node")
        if in_web and looks_dev:
            found.append(pid)
        elif root in cmd and (("vite" in cmd) or ("npm run dev" in cmd)):
            found.append(pid)
    return found


def _bundle_user_pids(bundle_root):
    root = os.path.realpath(bundle_root) + os.sep
    if not os.path.isdir(os.path.dirname(root.rstrip(os.sep))):
        return []
    found = []
    for pid, exe, cmd, _cwd in _iter_user_procs():
        if exe.startswith(root) or root in cmd:
            found.append(pid)
    return found


def _wait_port_free(app, host, port, timeout=8):
    if not host or not port:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_open(host, port):
            return True
        time.sleep(0.2)
    app.log("err", f"{host}:{port} 仍被占用")
    return False


def now():
    return time.strftime("%H:%M:%S")



# 系统补丁函数 (python 步骤 / 钩子使用)


def ensure_bashrc_paths(app):
    """幂等追加 go / uv 的 PATH 到 ~/.bashrc, 并更新本进程 env"""
    notes = []
    bashrc = Path.home() / ".bashrc"
    try:
        text = bashrc.read_text(encoding="utf-8", errors="replace") if bashrc.exists() else ""
    except Exception:
        text = ""
    add = []
    if "/usr/local/go/bin" not in text:
        add.append('export PATH="/usr/local/go/bin:$HOME/go/bin:$PATH"')
        notes.append("~/.bashrc: 追加 Go PATH")
    if "$HOME/.local/bin" not in text:
        add.append('export PATH="$HOME/.local/bin:$PATH"')
        notes.append("~/.bashrc: 追加 uv PATH (~/.local/bin)")
    if add:
        try:
            with open(bashrc, "a", encoding="utf-8") as f:
                f.write("\n# added by semantic_installer\n" + "\n".join(add) + "\n")
        except Exception as e:
            notes.append(f"~/.bashrc 写入失败: {e}")
    for p in ("/usr/local/go/bin", os.path.expanduser("~/go/bin"), os.path.expanduser("~/.local/bin")):
        if p not in app.env.get("PATH", ""):
            app.env["PATH"] = p + os.pathsep + app.env.get("PATH", "")
    return notes


def ensure_env_file(app, dirpath, values):
    """cp -n .env.example .env, 并确保键值存在 (存在则覆盖该行)"""
    p = Path(dirpath) / ".env"
    if not p.exists():
        ex = Path(dirpath) / ".env.example"
        if ex.exists():
            shutil.copy(ex, p)
            app.log("info", f"已复制 {Path(dirpath).name}/.env.example -> .env")
        else:
            p.write_text("", encoding="utf-8")
            app.log("warn", f"{dirpath} 无 .env.example, 新建空 .env")
    lines = p.read_text(encoding="utf-8").splitlines()
    out, seen = [], set()
    for ln in lines:
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", ln)
        if m and m.group(1) in values:
            k = m.group(1)
            out.append(f"{k}={values[k]}")
            seen.add(k)
        else:
            out.append(ln)
    for k, v in values.items():
        if k not in seen:
            out.append(f"{k}={v}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    for k, v in values.items():
        app.log("ok", f"{Path(dirpath).name}/.env: {k} 已设置")


def patch_server_yaml(app, path):
    """把 robot_runtime 块改为受管 Robot 配置 (只改 .output 这份)"""
    s = app.settings
    fw = sx(s["SEMANTIC"]) + "/semantic-framework"
    desired = {
        "enabled": "true",
        "bundles_dir": fw + "/.output/robot-bundles",
        "data_root": fw + "/.output",
        "server_http_url": s["SERVER_HTTP"],
        "server_websocket_url": s["SERVER_WS"],
        "ability_port_first": s["ABILITY_PORT_FIRST"],
        "ability_port_last": s["ABILITY_PORT_LAST"],
    }
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if re.match(r"^robot_runtime\s*:", ln):
            start = i
        elif start is not None and ln.strip() and not ln[0].isspace():
            end = i
            break
    if start is None:
        block = ["robot_runtime:"] + [f"    {k}: {v}" for k, v in desired.items()]
        newlines = lines + [""] + block
        app.log("warn", "semantic-server.yaml 未找到 robot_runtime 块, 已在文件末尾追加")
    else:
        if end is None:
            end = len(lines)
        indent = "    "
        for j in range(start + 1, end):
            if lines[j].strip():
                indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                break
        body, found = [], set()
        for j in range(start + 1, end):
            ln = lines[j]
            m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", ln)
            if m and m.group(2) in desired:
                k = m.group(2)
                body.append(f"{m.group(1)}{k}: {desired[k]}")
                found.add(k)
            else:
                body.append(ln)
        for k, v in desired.items():
            if k not in found:
                body.append(f"{indent}{k}: {v}")
        newlines = lines[: start + 1] + body + lines[end:]
    try:
        shutil.copy(path, str(path) + ".bak")
    except Exception:
        pass
    p.write_text("\n".join(newlines) + "\n", encoding="utf-8")
    for k, v in desired.items():
        app.log("ok", f"robot_runtime.{k} = {v}")
    app.log("info", "已备份为 semantic-server.yaml.bak; bundles_dir 指向活动 Catalog (.output/robot-bundles)")


def ensure_leader_allowlist(app, path):
    """确保 leader role.yaml 的 skills.allowlist 含 depalletizing-workflow-planning"""
    name = "depalletizing-workflow-planning"
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if name in text:
        app.log("ok", f"leader allowlist 已包含 {name}")
        return
    lines = text.splitlines()
    skills_idx = None
    for i, ln in enumerate(lines):
        if re.match(r"^skills\s*:", ln):
            skills_idx = i
    if skills_idx is None:
        lines += ["", "skills:", "  allowlist:", f"    - {name}"]
        app.log("warn", "role.yaml 无 skills 块, 已在末尾追加 allowlist")
    else:
        base = re.match(r"^(\s*)", lines[skills_idx]).group(1)
        allow_idx, item_indent = None, None
        for j in range(skills_idx + 1, len(lines)):
            ln = lines[j]
            if ln.strip() and not ln.startswith((" ", "\t")):
                break
            m = re.match(r"^(\s+)allowlist\s*:", ln)
            if m:
                allow_idx = j
                item_indent = m.group(1) + "  "
        if allow_idx is None:
            allow_idx = skills_idx
            lines.insert(allow_idx + 1, f"{base}  allowlist:")
            item_indent = base + "      "
            insert_at = allow_idx + 2
        else:
            insert_at = allow_idx + 1
            k = allow_idx + 1
            while k < len(lines) and (not lines[k].strip() or lines[k].startswith(item_indent)):
                if lines[k].strip():
                    insert_at = k + 1
                k += 1
        lines.insert(insert_at, f"{item_indent}- {name}")
        app.log("warn", f"role.yaml 已补 {name} 进 skills.allowlist")
    try:
        shutil.copy(path, str(path) + ".bak")
    except Exception:
        pass
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")



# GitLab 凭证助手


CLIP_CMDS = (["wl-paste"], ["xclip", "-o", "-selection", "clipboard"],
             ["xsel", "--clipboard", "--output"])
PAT_RE = re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b")


def read_clipboard():
    for c in CLIP_CMDS:
        if shutil.which(c[0]):
            try:
                r = subprocess.run(c, capture_output=True, text=True, timeout=2)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass
    return None


def clip_available():
    return any(shutil.which(c[0]) for c in CLIP_CMDS)


def _pat_from_clipboard(baseline):
    """剪贴板内容相对 baseline 变化且含 glpat- Token 时返回它"""
    txt = read_clipboard()
    if not txt or txt == baseline:
        return None
    m = PAT_RE.search(txt)
    return m.group(0) if m else None


def open_browser(app, url):
    """尽量打开浏览器; 失败时把 URL 打进日志供手动复制"""
    import threading
    for cmd in ("xdg-open", "sensible-browser", "x-www-browser", "wslview"):
        if shutil.which(cmd):
            try:
                subprocess.Popen([cmd, url], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                app.log("ok", f"已调用浏览器打开: {url}")
                return True
            except Exception:
                pass
    app.log("warn", f"未找到浏览器命令, 请手动打开: {url}")
    return False


def _oauth_callback_server(app, port, state):
    """启动本地 OAuth 回调服务; 返回 (server, result_queue)"""
    import secrets
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import urllib.parse as _up
    from queue import Queue

    result = Queue()
    state = state or secrets.token_hex(8)

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = _up.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            q = _up.parse_qs(parsed.query)
            code = q.get("code", [""])[0]
            st = q.get("state", [""])[0]
            err = q.get("error_description", q.get("error", [""]))[0]
            if code and st == state:
                result.put(("code", code))
                msg = "<h3>semantic-installer</h3><p>登录成功, 请回到终端继续。</p>"
            else:
                result.put(("error", err or "回调缺少 code 或 state 不匹配"))
                msg = "<h3>semantic-installer</h3><p>登录失败, 请回终端查看日志。</p>"
            body = msg.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, result, state


def _oauth_token(app, gitlab, cid, sec, code, redirect):
    """用授权码换 access_token"""
    import urllib.request
    import urllib.parse
    import ssl
    import json as _json
    data = urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec, "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect,
    }).encode()
    url = gitlab.rstrip("/") + "/oauth/token"
    last = None
    for ctx in (None, ssl._create_unverified_context()):
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                tok = _json.loads(r.read().decode()).get("access_token")
            if tok:
                app.log("ok", "OAuth 令牌获取成功")
                return tok
            app.log("err", "OAuth 响应中没有 access_token")
            return None
        except Exception as e:
            last = e
    app.log("err", f"OAuth 令牌交换失败: {last}")
    return None


def _git_store_credential(app, gitlab, user, token):
    """凭证写入 git credential store (仅作用于该 GitLab 实例), 并验证"""
    base = gitlab_root(gitlab)
    try:
        subprocess.run(["git", "config", "--global", f"credential.{base}.helper", "store"],
                       check=True, capture_output=True)
    except Exception as e:
        app.log("warn", f"git config 失败(仍尝试存凭证): {e}")
    payload = f"url={base}\nusername={user}\npassword={token}\n"
    r = subprocess.run(["git", "credential", "approve"], input=payload,
                       capture_output=True, text=True)
    if r.returncode != 0:
        app.log("err", f"凭证写入失败: {(r.stderr or '').strip()}")
        return False
    credfile = Path.home() / ".git-credentials"
    try:
        os.chmod(credfile, 0o600)
    except Exception:
        pass
    app.log("ok", f"凭证已存入 {credfile} (0600), 后续 clone/pull 免密")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        v = subprocess.run(["git", "ls-remote", base + "/semantic-framework.git", "HEAD"],
                           capture_output=True, text=True, env=env, timeout=60)
        if v.returncode == 0:
            app.log("ok", "验证通过: git ls-remote 成功")
        else:
            # 认证失败时 git 会自动 reject 已存凭证, 需重新写回, 避免静默丢失
            subprocess.run(["git", "credential", "approve"], input=payload,
                           capture_output=True, text=True)
            app.log("warn", "验证未通过, 凭证已重新写回 (Token 可能无效或网络不通): "
                    + (v.stderr or v.stdout).strip()[:200])
    except Exception as e:
        app.log("warn", f"验证异常: {e}")
    return True


def _clear_git_credential(app, gitlab):
    base = gitlab_root(gitlab)
    host = re.sub(r"^\w+://", "", base)
    variants = [host, host.replace(":", "%3a"), host.replace(":", "%3A")]
    credfile = Path.home() / ".git-credentials"
    before = credfile.read_text().splitlines() if credfile.exists() else []
    subprocess.run(["git", "credential", "reject"],
                   input=f"url={base}\n", capture_output=True, text=True)
    if credfile.exists():
        lines = credfile.read_text().splitlines()
        keep = [l for l in lines if not any(v in l for v in variants)]
        if len(keep) != len(lines):
            credfile.write_text("\n".join(keep) + ("\n" if keep else ""))
    else:
        keep = []
    removed = max(0, len(before) - len(keep))
    if removed:
        app.log("ok", f"已从 {credfile} 清除 {removed} 条 {host} 凭证")
    else:
        app.log("note", f"没有找到 {host} 的已存凭证")
    return removed



# 版本探测 (skip_check 用)


def _run_quick(cmds, env=None, timeout=15):
    try:
        r = subprocess.run(cmds, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception:
        return 127, ""


def go_version_ok(app):
    rc, out = _run_quick(["go", "version"], env=app.env)
    m = re.search(r"go(\d+)\.(\d+)", out)
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (1, 23)), out


def node_version_ok(app):
    rc, out = _run_quick(["node", "-v"], env=app.env)
    m = re.search(r"v(\d+)\.(\d+)", out)
    if not m:
        return False, out
    v = (int(m.group(1)), int(m.group(2)))
    return ((20, 19) <= v < (21, 0)) or v >= (22, 12), out


def uv_ok(app):
    rc, out = _run_quick(["uv", "--version"], env=app.env)
    return rc == 0, out


def python313_ok(app):
    rc, out = _run_quick(["uv", "python", "find", "3.13"], env=app.env)
    return rc == 0, out


PAT_PAGE_PATHS = ["/-/profile/personal_access_tokens",
                 "/-/user_settings/personal_access_tokens"]
APPS_PAGE_PATHS = ["/-/profile/applications", "/-/user_settings/applications"]


def _http_status(url, timeout=8):
    """匿名探测路由是否存在: 30x(跳登录)/2xx 算存在, 404 算不存在, 网络失败返回 None"""
    import urllib.request
    import urllib.error
    import ssl

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    for ctx in (None, ssl._create_unverified_context()):
        try:
            opener = urllib.request.build_opener(
                NoRedirect, urllib.request.HTTPSHandler(context=ctx) if ctx
                else urllib.request.HTTPSHandler())
            req = urllib.request.Request(url, method="GET",
                                         headers={"User-Agent": "semantic-installer/1.0"})
            with opener.open(req, timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            continue
    return None


def pick_page_path(app, root, paths, setting_key=None):
    """返回可用的页面路径; 设置里固定了就直接用, 否则匿名探测"""
    if setting_key:
        fixed = app.settings.get(setting_key, "").strip()
        if fixed:
            return fixed
    for p in paths:
        code = _http_status(root + p)
        if code is None:
            app.log("note", f"探测 {p} 失败(网络), 使用默认路径")
            return paths[0]
        if code != 404:
            return p
        app.log("note", f"{p} 返回 404, 尝试备选路径")
    return paths[-1]



# 步骤定义


def build_steps():
    steps = []

    def S(sid, title, kind="shell", **kw):
        d = {
            "sid": sid, "stage": int(sid.split(".")[0]), "title": title, "kind": kind,
            "sudo": False, "confirm": None, "cmds": [], "cwd": None, "env": None,
            "pre": None, "post": None, "verify": [], "verify_required": True,
            "skip_check": None, "retry": None, "note": None,
            "manual_text": None, "service": None,
        }
        d.update(kw)
        steps.append(d)
        return d

    # ---------------- 阶段 1 ----------------
    S("1.0", "配置 apt 国内源", sudo=True,
      cmds=lambda app: _apt_mirror_script(app),
      skip_check=lambda app: None if app.settings.get("APT_MIRROR", "").strip()
      else "APT_MIRROR 未配置, 保持系统源",
      note="将 archive/security.ubuntu.com 替换为 APT_MIRROR, 每个源文件保留 .bak-orig 备份")

    S("1.1", "基础工具 (curl/git/git-lfs/编译工具链)", sudo=True,
      cmds=["sudo apt update",
            "sudo apt install -y curl ca-certificates git git-lfs make xz-utils "
            "build-essential ninja-build cmake pkg-config",
            "git lfs install"],
      note="更新软件包索引并安装 curl、Git、Git LFS、make、解压工具与 C/C++ 编译工具链; "
           "build-essential 提供 gcc/g++, ninja-build/cmake 供 5.1 xmake 编译 AbilityFramework 使用")

    S("1.2", "安装 Go >= 1.23 (镜像下载)", sudo=True,
      confirm="将执行 sudo rm -rf /usr/local/go 并解压 Go, 确认继续?",
      cmds=lambda app: _go_install_cmds(app),
      post=lambda app, rc: ensure_bashrc_paths(app) and None,
      skip_check=lambda app: (lambda ok, out: f"已满足: {out}" if ok else None)(*go_version_ok(app)),
      verify=["go version"])

    S("1.3", "Node.js 22 (国内镜像二进制)", sudo=True,
      cmds=lambda app: _node_install_script(app),
      env=lambda app: {"PATH": _path_with_tools(app)},
      skip_check=lambda app: (lambda ok, out: f"已满足: {out}" if ok else None)(*node_version_ok(app)),
      verify=["node -v", "npm -v"],
      note="从 NODE_MIRROR (npmmirror) 下载官方二进制解压到 /usr/local; 置空 NODE_MIRROR 则改走 NodeSource apt")

    S("1.4", "uv 与 Python 3.13 (多策略 + 镜像)",
      cmds=lambda app: _uv_install_script(app),
      env=lambda app: {"PATH": _path_with_tools(app),
                       "UV_DEFAULT_INDEX": app.settings["UV_DEFAULT_INDEX"]},
      post=lambda app, rc: ensure_bashrc_paths(app) and None,
      skip_check=lambda app: (lambda a, b: (lambda c, d: f"已满足: uv + {d}" if a and c else None)(*python313_ok(app)))(*uv_ok(app)),
      note="回退链: astral.sh -> GitHub 代理(GITHUB_PROXY) -> pip 国内源; 解释器下载走 UV_PYTHON_INSTALL_MIRROR")

    S("1.5", "仿真渲染库 (EGL/Mesa)", sudo=True,
      cmds=lambda app: [
          "sudo apt install -y libgl1 libglib2.0-0 libgomp1 libegl1 libegl-mesa0 libgles2"
          + (" libosmesa6" if app.settings["SEMANTIC_MUJOCO_GL"] == "osmesa" else ""),
      ],
      note="无头机器也要 Mesa EGL; 若 EGL 起不来: 装 libosmesa6 并在设置里把 SEMANTIC_MUJOCO_GL 改为 osmesa")

    S("1.6", "镜像与工具源配置 (GOPROXY/npm)", kind="python", fn=_step_mirror_config,
      note="go env -w GOPROXY 与 npm registry 写入 ~/.npmrc; 直连模式可把对应项置空")

    S("1.7", "版本自检",
      cmds=["go version", "node -v", "npm -v", "uv --version",
            "uv python find 3.13", "git lfs version", "make --version"],
      env=lambda app: {"PATH": _path_with_tools(app)},
      post=_check_versions_post)

    # ---------------- 阶段 2 ----------------
    S("2.1", "克隆全部子仓库",
      pre=lambda app: app.prepare_clone_workspace(),
      cmds=lambda app: _clone_script(app), cwd=lambda app: sx(app.settings["SEMANTIC"]),
      note="按拉取清单准备子仓库。")

    S("2.2", "切换到版本清单指定的分支/Tag",
      cmds=lambda app: _branch_script(app),
      note="优先读取 repo-versions.json 版本清单 (用 repo_versions.py 维护, 支持 branch/tag/commit); "
           "清单缺失时回退到设置里的分支")

    S("2.3", "准备场景资产与 Wheel",
      cmds=lambda app: _asset_pull_script(app),
      env=lambda app: {"UV_DEFAULT_INDEX": app.settings.get("UV_DEFAULT_INDEX", "")},
      post=lambda app, rc: _check_runtime_assets(app),
      note="拉取清单: 场景资产、运行时 bundle 配置与第三方 Wheel。")

    S("2.4", "目录与资产核对",
      cmds=lambda app: _verify2_script(app),
      note="检查场景/部署目录和第三方资产; AbilityFramework、ability_py、ability_scaffold 在阶段 5 源码构建后校验")

    # ---------------- 阶段 3 ----------------
    S("3.1", "准备 .env (管理员密码)", kind="python", fn=_step_prepare_env,
      note="模型 Key 不必写 .env, 后面在 Studio 系统设置里加; .env 不要提交 Git")

    S("3.2", "make build",
      cmds=["make build"], cwd=lambda app: sx(app.settings["SEMANTIC"]) + "/semantic-framework",
      env=lambda app: _fw_build_env(app))

    S("3.3", "make init",
      cmds=["make init"], cwd=lambda app: sx(app.settings["SEMANTIC"]) + "/semantic-framework",
      env=lambda app: _fw_build_env(app))

    S("3.4", "产物核对",
      cmds=lambda app: [
          f'test -f "{sx(app.settings["SEMANTIC"])}/semantic-framework/.output/bin/semantic-server"',
          f'test -f "{sx(app.settings["SEMANTIC"])}/semantic-framework/.output/bin/semantic"',
          f'test -f "{sx(app.settings["SEMANTIC"])}/semantic-framework/.output/bin/semantic-pilot"',
          f'test -f "{sx(app.settings["SEMANTIC"])}/semantic-framework/.output/configs/semantic-server.yaml"',
      ],
      note="运行配置只改 .output 这份; robot_runtime.enabled 在 5.4 打开")

    # ---------------- 阶段 4 ----------------
    S("4.1", "uv sync (MuJoCo Runtime venv)",
      cmds=["uv sync --frozen --extra dev"],
      cwd=lambda app: sx(app.settings["SEMANTIC"]) + "/semantic-simulation/mujoco-runtime",
      env=lambda app: {"PATH": _path_with_tools(app), "UV_DEFAULT_INDEX": app.settings["UV_DEFAULT_INDEX"],
                       **_mirror_env_extra(app)},
      verify=lambda app: [
          f'test -x "{sx(app.settings["SEMANTIC"])}/semantic-simulation/mujoco-runtime/.venv/bin/plugin-mujoco"',
      ])

    S("4.2", "登记 Native MuJoCo Runtime",
      cmds=lambda app: [
          " ".join([
              shlex.quote(sx(app.settings["SEMANTIC"]) + "/semantic-framework/.output/bin/semantic"),
              "runtime", "install",
              "--dev-source", shlex.quote(sx(app.settings["SEMANTIC"]) + "/semantic-simulation/mujoco-runtime"),
              "--profile", "native-mujoco",
              "--asset-root", shlex.quote(sx(app.settings["SEMANTIC"]) + "/semantic-scene/mujoco-asset"),
              "--scene-catalog", shlex.quote(sx(app.settings["SEMANTIC"]) + "/semantic-framework/configs/scenes.d"),
              "-c", shlex.quote(sx(app.settings["SEMANTIC"]) + "/semantic-framework/.output/configs/semantic-server.yaml"),
          ])
      ],
      env=lambda app: {"PATH": _path_with_tools(app)},
      retry=lambda app, out: ("--replace",) if ("已存在" in out or "exists" in out.lower()) else None,
      note="若提示已存在会自动加 --replace 重试; 之后 make run 直接读 runtimes.d 配置, 不必再 export SEMANTIC_MUJOCO_WORKDIR / ASSET_ROOT")

    # ---------------- 阶段 5 ----------------
    S("5.1", "编译 AbilityFramework (源码, 替代 LFS 二进制)", kind="python", fn=_step_build_af,
      note="ability-framework/abilityframework 源码 xmake 编译; 产物覆盖 ability-runtime/AbilityFramework "
           "(原 LFS 二进制备份为 .lfs-orig); 版本由版本清单/BR_ABILITY_FRAMEWORK 决定")

    S("5.2", "构建 ability_py / ability_scaffold Wheel (源码, 替代 LFS Wheel)", kind="python", fn=_step_build_ability_py,
      note="ability-py-sdk 与 ability-scaffold 源码 uv build; ability_py 放 ability-runtime 根目录与 Wheel 缓存 "
           "(refresh 按文件名 ability_py-0.4.0-*.whl 查找), ability_scaffold 放根目录 "
           "(refresh 按文件名 ability_scaffold-1.2.0-*.whl 自装 venv); 安装时清掉旧 .venv 以生效")

    S("5.3", "Wheel 缓存检查 (无需下载)", kind="python", fn=_step_wheelcache,
      note="第三方 Wheel 已随 ability-runtime 仓库提供, 不要 pip download, 不要拷进 .output/robot-bundles; "
           "ability_py / ability_scaffold 已改为源码构建(5.2), scaffold venv 由 refresh 按需自装")

    S("5.4", "构建并激活 Robot Bundle", kind="python", fn=_step_build_bundle,
      note="先给 Python 3.13 补 setuptools/wheel (uv 解释器不带, 否则 --no-build-isolation 打包报 "
           "Cannot import setuptools.build_meta); 脚本自己找 $SEMANTIC 下的 SDK/Ability/Skill/Deployment 与 Wheel 缓存; "
           "重跑时先停本工作区 Server 和占用旧 Bundle 的实例, 再 --activate --stop-users")

    S("5.5", "启用受管 Robot (改 .output 配置)", kind="python", fn=_step_enable_robot,
      note="只改 .output/configs/semantic-server.yaml; bundles_dir 指活动 Catalog, 不是 base-bundles")

    # ---------------- 阶段 6 ----------------
    S("6.1", "启动 Server (make run)", kind="service",
      service=lambda app: _server_service(app),
      note="端口: HTTP 8080 / WS 8081 / MuJoCo Runtime 随后一般 8090 / Ability 18100-18199; "
           "TMPDIR 已指向 .output/tmp (AF 打包在 /tmp 跨设备 rename 会 EXDEV); "
           "已有本工作区 Server 会先停再拉")

    S("6.2", "Web 依赖与 .env", kind="python", fn=_step_web_env,
      note=".env 保持 VITE_SERVER_HTTP / VITE_SERVER_WS / VITE_STUDIO_FIXTURES=false")

    S("6.3", "启动 Web (npm run dev)", kind="service",
      service=lambda app: {
          "name": "web",
          "start": "npm run dev",
          "cwd": sx(app.settings["SEMANTIC"]) + "/semantic-web",
          "env": {"PATH": _path_with_tools(app)},
          "health": app.settings["WEB_URL"],
          "timeout": 240,
      },
      note=lambda app: (f"启动后浏览器打开 {app.settings['WEB_URL']}; 登录: 用户名 admin / "
                        f"密码 SEMANTIC_ADMIN_PASSWORD (当前设置值已写入 .env); "
                        f"已有本工作区 Web 会先停再拉"))

    S("6.4", "发布三个 Robot Skill", kind="python", fn=_step_publish_skills,
      note="只在 Bundle 刷新后做一次; Server 必须已在跑; 发布清单: semantic-navigation / grasp-object / place-object，版本以本次构建产物为准")

    # ---------------- 阶段 7 ----------------
    S("7.1", "Studio 场景联调 (手动)", kind="manual", manual_text=MANUAL_STUDIO)

    # ---------------- 阶段 8 ----------------
    S("8.1", "日常再开: Server", kind="service",
      service=lambda app: _server_service(app),
      note="先停本工作区已在跑的 semantic-server, 再 make run")
    S("8.2", "日常再开: Web", kind="service",
      service=lambda app: {
          "name": "web",
          "start": "npm run dev",
          "cwd": sx(app.settings["SEMANTIC"]) + "/semantic-web",
          "env": {"PATH": _path_with_tools(app)},
          "health": app.settings["WEB_URL"],
          "timeout": 240,
      },
      note="先停本工作区已在跑的 npm/vite, 再 npm run dev")

    return steps


MANUAL_STUDIO = """[Studio 手动联调清单] (对应文档第 7 节)
1. 系统设置里加 DeepSeek (text + tool_call), 设为全局默认; Token 只放设置里
2. 新建或打开 Project; 左侧 Agent Skills 勾选
   depalletizing-workflow-planning / depalletizing-robot-task
3. 资源页面手动增加仿真 Runtime Profile, 选 Native MuJoCo
4. 添加场景 R1 Pro 拆码垛 (depalletizing-r1pro)
5. 第一次用 layout001, 点启动 Layout
6. 查看设备中是否存在 r1_pro_tote_gripper-1 这个 Robot
7. 启动后切换回对话页面, 输入框左边 + 选「规划模式」(不要「协作」)
8. 发送指令 (首行触发词 + 完整任务描述):
   PLAN-V050-MUJOCO-LAYER-DEEPSEEK
   请在当前Project的layout001中完成一层周转箱拆垛, 并直接生成可审阅的Plan Proposal。
   (完整八条指令原文见《新版Semantic安装步骤》第 7 节)
完成标准: 四个箱体分别稳定进入对应目标列第一层、双工具为空、Robot 恢复 travel 姿态。"""


def _path_with_tools(app):
    p = app.env.get("PATH", os.environ.get("PATH", ""))
    for d in ("/usr/local/go/bin", os.path.expanduser("~/go/bin"), os.path.expanduser("~/.local/bin")):
        if d not in p:
            p = d + os.pathsep + p
    return p


def _fw_build_env(app):
    """framework make build/init 的环境: 附加 GOPROXY"""
    e = {"SEMANTIC": sx(app.settings["SEMANTIC"]), "PATH": _path_with_tools(app)}
    if app.settings.get("GO_PROXY", "").strip():
        e["GOPROXY"] = app.settings["GO_PROXY"]
    return e


def _mirror_env_extra(app):
    """GitHub 代理相关附加环境 (加速 uv 下载 Python 解释器)"""
    e = {}
    gp = app.settings.get("GITHUB_PROXY", "").strip()
    if gp:
        e["UV_PYTHON_INSTALL_MIRROR"] = (
            gp.rstrip("/") +
            "/https://github.com/astral-sh/python-build-standalone/releases/latest/download")
    return e


def _go_install_cmds(app):
    base = app.settings.get("GO_DL_MIRROR", "").strip().rstrip("/") or "https://go.dev/dl"
    return [
        f'curl -fsSL "{base}/go{app.settings["GO_VERSION"]}.linux-amd64.tar.gz" -o /tmp/go.tgz',
        "sudo rm -rf /usr/local/go",
        "sudo tar -C /usr/local -xzf /tmp/go.tgz",
    ]


def _apt_mirror_script(app):
    m = app.settings.get("APT_MIRROR", "").strip().rstrip("/")
    return ["\n".join([
        "set -o pipefail",
        'files="/etc/apt/sources.list"',
        "for f in /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do",
        '  if [ -f "$f" ]; then files="$files $f"; fi',
        "done",
        "changed=0",
        "for f in $files; do",
        '  [ -f "$f" ] || continue',
        '  if grep -qE "(archive|security)\\.ubuntu\\.com" "$f"; then',
        '    [ -f "$f.bak-orig" ] || sudo cp "$f" "$f.bak-orig"',
        f'    sudo sed -i -E "s|https?://(cn\\.)?archive\\.ubuntu\\.com/ubuntu|{m}|g; s|https?://security\\.ubuntu\\.com/ubuntu|{m}|g" "$f"',
        '    echo "[apt源] 已切换: $f (备份: $f.bak-orig)"; changed=1',
        "  fi",
        "done",
        'if [ "$changed" -eq 0 ]; then echo "[apt源] 未发现官方源地址, 无需修改"; fi',
    ])]


def _node_install_script(app):
    m = app.settings.get("NODE_MIRROR", "").strip().rstrip("/")
    if not m:
        return ["curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/nodesource-setup.sh",
                "sudo -E bash /tmp/nodesource-setup.sh",
                "sudo apt install -y nodejs"]
    v = app.settings.get("NODE_VERSION", "").strip()
    return ["\n".join([
        "set -o pipefail",
        f"M={shlex.quote(m)}",
        f"V={shlex.quote(v)}",
        'if [ -n "$V" ]; then',
        '  tag="v$V"; fbase="node-$tag-linux-x64"',
        '  set -- "$M/$tag/$fbase.tar.xz" "$M/$tag/$fbase.tar.gz"',
        "else",
        '  shas=$(curl -fsSL --connect-timeout 15 "$M/latest-v22.x/SHASUMS256.txt") || { echo "[node] 无法获取 latest-v22.x 清单"; exit 1; }',
        '  fbase=$(echo "$shas" | grep -oE \'node-v22\\.[0-9]+\\.[0-9]+-linux-x64\\.tar\\.xz\' | head -1 || true)'
        '  [ -n "$fbase" ] || { echo "[node] 清单里未找到 linux-x64 包"; exit 1; }',
        '  set -- "$M/latest-v22.x/$fbase"',
        "fi",
        'got=""',
        'for u in "$@"; do',
        '  echo "[node] 尝试下载: $u"',
        '  if curl -fL --connect-timeout 20 "$u" -o /tmp/node.tar; then got="$u"; break; fi',
        "done",
        '[ -n "$got" ] || { echo "[node] 下载失败, 请检查 NODE_MIRROR / NODE_VERSION"; exit 1; }',
        'case "$got" in',
        '  *.xz) sudo tar -C /usr/local --strip-components=1 -xJf /tmp/node.tar ;;',
        '  *)    sudo tar -C /usr/local --strip-components=1 -xzf /tmp/node.tar ;;',
        "esac",
        'hash -r 2>/dev/null || true',
        "node -v && npm -v",
    ])]


def _uv_install_script(app):
    s = app.settings
    gp = s.get("GITHUB_PROXY", "").strip().rstrip("/")
    uvpy = _mirror_env_extra(app).get("UV_PYTHON_INSTALL_MIRROR", "")
    return ["\n".join([
        "set -o pipefail",
        f'UV_INDEX={shlex.quote(s["UV_DEFAULT_INDEX"])}',
        f"GP={shlex.quote(gp)}",
        f"UVPYM={shlex.quote(uvpy)}",
        'UV="$HOME/.local/bin/uv"',
        'if [ -n "$UVPYM" ]; then export UV_PYTHON_INSTALL_MIRROR="$UVPYM"; echo "[uv] Python 解释器镜像: $UVPYM"; fi',
        'if [ -x "$UV" ]; then',
        '  echo "[uv] 已存在: $UV"',
        "else",
        '  ok=0',
        '  echo "[uv] 策略1: astral.sh 官方脚本"',
        '  if curl -LsSf --connect-timeout 15 https://astral.sh/uv/install.sh | sh; then ok=1; else echo "[uv] 策略1 失败"; fi',
        '  if [ -x "$UV" ]; then ok=1; fi',
        '  if [ "$ok" -eq 0 ] && [ -n "$GP" ]; then',
        '    echo "[uv] 策略2: GitHub 代理下载二进制"',
        '    if curl -fL --connect-timeout 20 "$GP/https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz" -o /tmp/uv.tgz && mkdir -p "$HOME/.local/bin" && tar -xzf /tmp/uv.tgz -C "$HOME/.local/bin" --strip-components=1; then ok=1; else echo "[uv] 策略2 失败"; fi',
        "  fi",
        '  if [ "$ok" -eq 0 ]; then',
        '    echo "[uv] 策略3: pip 走国内 PyPI 源"',
        '    if ! python3 -m pip --version >/dev/null 2>&1; then',
        '      if sudo -n true 2>/dev/null; then sudo apt install -y python3-pip; else echo "[uv] pip 缺失且 sudo 需密码, 跳过 apt 安装"; fi',
        "    fi",
        '    if python3 -m pip --version >/dev/null 2>&1; then',
        '      python3 -m pip install --user --break-system-packages --upgrade uv --index-url "$UV_INDEX" || python3 -m pip install --user --upgrade uv --index-url "$UV_INDEX" || echo "[uv] 策略3 失败"',
        "    fi",
        "  fi",
        '  [ -x "$UV" ] || { echo "[uv] 三种策略均失败: 可在设置里配置 GITHUB_PROXY (GitHub 代理) 后重试"; exit 1; }',
        "fi",
        'export UV_DEFAULT_INDEX="$UV_INDEX"',
        'echo "[uv] $( \'$UV\' --version )"',
        '"$UV" python install 3.13',
        '"$UV" python find 3.13',
    ])]


def _check_versions_post(app, rc):
    msgs = []
    ok, out = go_version_ok(app)
    if not ok:
        msgs.append("Go 不满足 >= 1.23")
    ok, out = node_version_ok(app)
    if not ok:
        msgs.append("Node 不满足 ^20.19 或 >= 22.12")
    ok, _ = uv_ok(app)
    ok2, _ = python313_ok(app)
    if not (ok and ok2):
        msgs.append("uv 或 Python 3.13 缺失")
    if msgs:
        app.log("warn", "自检: " + "; ".join(msgs))
        return ("warn", "; ".join(msgs))
    app.log("ok", "自检通过: Go / Node / uv / Python3.13 / git-lfs / make")
    return None



# 原组(upstream)完整路径: quick-start 自身来自原组时, 子仓按此克隆;
# 自身来自 staging(或镜像副本无 git)时, 全部走 fork
UPSTREAM_REPOS = {
    "semantic-framework": "/example/semantic/semantic-framework",
    "semantic-web": "/example/semantic/semantic-web",
    "semantic-docs": "/example/semantic/semantic-docs",
    "semantic-ability/r1pro-ability": "/example/semantic/semantic-ability/r1pro-ability",
    "semantic-robotsdk/robot-sdk": "/example/semantic/semantic-robotsdk/robot-sdk",
    "semantic-skill/robot-skill": "/example/semantic/semantic-skill/robot-skill",
    "semantic-simulation/mujoco-runtime": "/example/semantic/semantic-simulation/mujoco-runtime",
    "semantic-scene/mujoco-asset": "/example/semantic/semantic-scene/mujoco-asset",
    "semantic-robot-deployment": "/example/semantic/semantic-deployment",
    "semantic-ability/ability-runtime": "/example/semantic/semantic-ability/ability-runtime",
    "ability-framework/abilityframework": "/example/ability/abilityframework",
    "ability-framework/ability-py-sdk": "/example/ability/ability-py-sdk",
    "ability-framework/ability-scaffold": "/example/ability/ability-scaffold",
}


def self_org_mode():
    """探测 quick-start 自身来源: 脚本所在目录是 git 仓则取 origin 的组名;
    组为 staging -> 'fork'; 其他(原组)-> 'upstream'; 非 git(镜像副本)-> 'fork'"""
    d = SCRIPT_DIR
    while d != d.parent:
        if (d / ".git").exists():
            rc, out = _run_quick(["git", "-C", str(d), "remote", "get-url", "origin"])
            if rc == 0 and out:
                url = out.splitlines()[0].rstrip("/")
                for pfx in ("https://", "http://", "ssh://git@"):
                    if url.startswith(pfx):
                        url = url[len(pfx):]
                        break
                url = url.removesuffix(".git")
                parts = url.split("/")
                group = parts[-2] if len(parts) >= 2 else ""
                return "upstream" if group != "staging" else "fork"
            return "fork"
        d = d.parent
    return "fork"


def _repo_event(local, status):
    return "printf '%s\\n' " + shlex.quote(REPO_EVENT_MARK + json.dumps([local, status]))


def _repo_plan(app):
    s = app.settings
    gl = s["GITLAB"]
    root = gitlab_root(gl)
    mpath, manifest = find_repo_manifest(app)
    mode = self_org_mode()
    rows = []
    for local, repo, brkey in REPOS:
        if repo.startswith("/"):
            url = f"{root}{repo}.git"
            if mode == "upstream" and local in UPSTREAM_REPOS:
                url = f"{root}{UPSTREAM_REPOS[local]}.git"
        else:
            url = f"{gl}/{repo}.git"
        entry = manifest.get(local, {}) if manifest else {}
        if isinstance(entry, dict) and isinstance(entry.get("url"), str) and entry["url"].strip():
            url = sx(entry["url"].strip())
        ref = entry.get("ref", "") if isinstance(entry, dict) else ""
        rows.append({"repo": local, "url": url, "ref": ref or (s.get(brkey, "") if brkey else ""),
                     "status": "pending"})
    return mpath, rows


def _clone_script(app):
    base = sx(app.settings["SEMANTIC"])
    _mpath, rows = _repo_plan(app)
    lines = ["set -eo pipefail",
             f'mkdir -p "{base}"',
             'clone_if() { d="$1"; u="$2"; if [ -d "$d/.git" ]; then echo "[跳过] $d 已存在"; '
             'else echo "[克隆] $d"; GIT_LFS_SKIP_SMUDGE=1 git clone "$u" "$d"; fi; }']
    for row in rows:
        local, url = row["repo"], row["url"]
        lines.append(_repo_event(local, "running"))
        lines.append("mkdir -p " + shlex.quote(os.path.dirname(os.path.join(base, local))))
        lines.append(f'clone_if {shlex.quote(os.path.join(base, local))} {shlex.quote(url)}')
        lines.append(_repo_event(local, "ok"))
    return ["\n".join(lines)]


def find_repo_manifest(app):
    """按优先级查找子仓库版本清单 (repo_versions.py 维护):
    设置 REPO_VERSIONS_FILE > $SEMANTIC/ > 安装器目录 > ../quick-start/"""
    cands = []
    p = app.settings.get("REPO_VERSIONS_FILE", "").strip()
    if p:
        cands.append(sx(p))
    cands.append(os.path.join(sx(app.settings["SEMANTIC"]), "repo-versions.json"))
    cands.append(str(SCRIPT_DIR / "repo-versions.json"))
    cands.append(str(SCRIPT_DIR.parent / "quick-start" / "repo-versions.json"))
    for c in cands:
        if c and os.path.isfile(c):
            try:
                d = json.load(open(c, encoding="utf-8"))
                repos = d.get("repos")
                if isinstance(repos, dict) and repos:
                    return c, repos
            except Exception:
                pass
    return None, None


def _branch_script(app):
    s = app.settings
    base = sx(s["SEMANTIC"])
    mpath, manifest = find_repo_manifest(app)
    if mpath:
        app.log("note", f"2.2 使用版本清单 {mpath} (repo_versions.py 维护, 覆盖设置里的分支)")
    lines = [
        "set -eo pipefail",
        "export GIT_LFS_SKIP_SMUDGE=1",
        "sw() { dir=\"$1\"; ref=\"$2\"; echo \"[版本] $dir -> $ref\"; "
        "git -C \"$dir\" fetch origin --tags --prune 2>&1 | tail -1; "
        "if ! git -C \"$dir\" checkout -q \"$ref\" 2>/dev/null; then "
        "git -C \"$dir\" switch -C \"$ref\" --track \"origin/$ref\"; fi; }",
    ]
    for local, repo, brkey in REPOS:
        m = manifest.get(local) if manifest else None
        ref = m.get("ref", "").strip() if isinstance(m, dict) else ""
        if not ref and brkey:
            ref = s[brkey]
        if ref:
            lines.append(_repo_event(local, "running"))
            lines.append(f'sw "{os.path.join(base, local)}" "{ref}"')
            lines.append(_repo_event(local, "ok"))
        else:
            lines.append(_repo_event(local, "skip"))
    return ["\n".join(lines)]


def _asset_pull_script(app):
    base = sx(app.settings["SEMANTIC"])
    source = app.settings.get("RUNTIME_WHEEL_SOURCE", "auto")
    if source not in ("auto", "lfs", "offline"):
        raise ValueError("RUNTIME_WHEEL_SOURCE 必须为 auto、lfs 或 offline")
    fetch = " ".join(shlex.quote(str(arg)) for arg in (
        sys.executable, SCRIPT_DIR / "scripts/fetch_runtime_wheels.py",
        "--repo", os.path.join(base, "semantic-ability/ability-runtime"), "--source", source))
    commands = []
    for local, action in (
        ("semantic-scene/mujoco-asset", 'git lfs pull -I "" -X ""'),
        ("semantic-ability/ability-runtime", fetch),
    ):
        commands.append("\n".join(["set -e", _repo_event(local, "running"),
                                   "cd " + shlex.quote(os.path.join(base, local)), action,
                                   _repo_event(local, "ok")]))
    return commands


def _server_service(app):
    """Server 服务的统一定义; TMPDIR 重定向到与 .output 同文件系统,
    避免 AbilityFramework /api/package 在 /tmp (tmpfs) 暂存后 rename 到 $HOME 报 EXDEV"""
    s = app.settings
    fw = sx(s["SEMANTIC"]) + "/semantic-framework"
    return {
        "name": "server",
        "start": "make run",
        "cwd": fw,
        "env": {"SEMANTIC": sx(s["SEMANTIC"]), "PATH": _path_with_tools(app),
                "TMPDIR": os.path.join(fw, ".output/tmp")},
        "health": s["SERVER_HTTP"],
        "timeout": 240,
    }


def _source_built_asset(path):
    """Source-built artifacts are excluded at any depth, including bundle caches."""
    return re.fullmatch(r"AbilityFramework|ability_(?:py|scaffold)-.*\.whl", Path(path).name) is not None


def _check_runtime_assets(app):
    """Check only downloaded third-party assets; source outputs are checked in stage 5."""
    vendor = Path(_vendor_root(app))
    bundle = vendor / "base-bundles" / f"r1pro-mujoco-{app.settings['BUNDLE_VER']}"
    if not (bundle / "bundle.yaml").is_file() or not (bundle / "wheels").is_dir():
        return ("fail", f"第三方资产缺失: {bundle}/bundle.yaml 或 wheels/")
    rc, out = _run_quick(["git", "-C", str(vendor), "-c", "core.quotePath=false",
                          "lfs", "ls-files", "--name-only"], timeout=60)
    if rc != 0:
        return ("fail", f"无法列出 ability-runtime LFS 资产: {out}")
    checked = 0
    missing = []
    for name in out.splitlines():
        if not name or _source_built_asset(name):
            continue
        try:
            with (vendor / name).open("rb") as f:
                content = f.read(128)
            if not content or content.startswith(b"version https://git-lfs.github.com/spec/v1"):
                missing.append(name)
            else:
                checked += 1
        except OSError:
            missing.append(name)
    if missing:
        return ("fail", "第三方 LFS 资产未下载或不可读: " + ", ".join(missing[:5]))
    app.log("ok", f"ability-runtime 第三方资产齐全 ({checked} 个 LFS 文件); "
                  "AbilityFramework / ability_py / ability_scaffold 留待阶段 5 源码构建")
    return None


def _verify2_script(app):
    base = sx(app.settings["SEMANTIC"])
    ar = os.path.join(base, "semantic-ability/ability-runtime")
    cmds = [
        f'python3 {shlex.quote(os.path.join(base, "semantic-scene/mujoco-asset/check_external_models.py"))}',
        f'ls "{os.path.join(base, "semantic-skill/robot-skill/semantic_robot_skills/skills")}"',
        f'test -d "{os.path.join(ar, "base-bundles/r1pro-mujoco-" + app.settings["BUNDLE_VER"] + "/wheels")}"',
        f'ls "{os.path.join(base, "semantic-robot-deployment/type-packages/r1pro-mujoco")}"',
        f'cd "{os.path.join(base, "semantic-scene/mujoco-asset")}" && '
        'find . \\( -name "*.obj" -o -name "*.STL" -o -name "*.dae" \\) | head -5 || true',
    ]
    return cmds


# python 步骤实现 ------------------------------------------------------------

def _step_prepare_env(app):
    fw = sx(app.settings["SEMANTIC"]) + "/semantic-framework"
    if not os.path.isdir(fw):
        return ("fail", f"目录不存在: {fw} (先完成阶段 2)")
    ensure_env_file(app, fw, {"SEMANTIC_ADMIN_PASSWORD": app.settings["SEMANTIC_ADMIN_PASSWORD"]})
    app.log("info", "模型 Key 不必写入 .env, 在 Studio 系统设置里添加; .env 不要提交 Git")
    return ("ok", None)


def _vendor_root(app):
    return sx(app.settings["SEMANTIC"]) + "/semantic-ability/ability-runtime"


def _step_build_af(app):
    """源码编译 AbilityFramework, 产物覆盖 ability-runtime/AbilityFramework (替代 LFS 二进制)"""
    base = sx(app.settings["SEMANTIC"])
    repo = os.path.join(base, "ability-framework/abilityframework")
    if not os.path.isdir(os.path.join(repo, ".git")):
        return ("fail", f"源码仓不存在: {repo} (先完成 2.1/2.2)")
    vendor = _vendor_root(app)
    cmds = [
        "xmake make-version",
        "xmake f -y",
        "xmake -y",
    ]
    return ("shell", {"cmds": cmds, "cwd": repo,
                      "env": {"PATH": _path_with_tools(app)},
                      "post": lambda app2, rc: _install_af(app2, repo, vendor),
                      "verify": [f'test -x "{vendor}/AbilityFramework"']})


def _install_af(app, repo, vendor):
    """找到编译产物, 校验版本后安装到 vendor (原 LFS 二进制备份一次)"""
    cands = []
    for root, _dirs, files in os.walk(os.path.join(repo, "build")):
        if "AbilityFramework" in files:
            cands.append(os.path.join(root, "AbilityFramework"))
    if not cands:
        return ("fail", "未在 build/ 下找到 AbilityFramework 编译产物")
    src_bin = max(cands, key=os.path.getmtime)
    rc, out = _run_quick([src_bin, "--version"], timeout=30)
    if rc != 0:
        return ("fail", f"AbilityFramework 编译产物无法执行: {src_bin}: {out.strip()}")
    ver = out.strip().splitlines()[0] if out.strip() else "(无版本输出)"
    app.log("info", f"编译产物: {src_bin} | {ver}")
    dst = os.path.join(vendor, "AbilityFramework")
    try:
        if os.path.isfile(dst) and not os.path.exists(dst + ".lfs-orig"):
            shutil.copy2(dst, dst + ".lfs-orig")
            app.log("note", "原 LFS 二进制备份为 AbilityFramework.lfs-orig")
        shutil.copy2(src_bin, dst)
        os.chmod(dst, 0o755)
    except Exception as e:
        return ("fail", f"AbilityFramework 安装失败: {e}")
    rc2, out2 = _run_quick([dst, "--version"], timeout=30)
    if rc2 != 0:
        return ("fail", f"安装后的 AbilityFramework 无法执行: {dst}: {out2.strip()}")
    app.log("ok", f"已安装到 {dst}: {out2.strip().splitlines()[0] if out2.strip() else ver}")
    return None


def _step_build_ability_py(app):
    """源码构建 ability_py 与 ability_scaffold Wheel, 安装到 ability-runtime
    (refresh_v050_mujoco.py 按固定文件名查找这两个 Wheel)"""
    base = sx(app.settings["SEMANTIC"])
    repos = {
        "ability_py": os.path.join(base, "ability-framework/ability-py-sdk"),
        "ability_scaffold": os.path.join(base, "ability-framework/ability-scaffold"),
    }
    for name, repo in repos.items():
        if not os.path.isdir(os.path.join(repo, ".git")):
            return ("fail", f"源码仓不存在: {repo} (先完成 2.1/2.2)")
    vendor = _vendor_root(app)
    cache = os.path.join(vendor, f"base-bundles/r1pro-mujoco-{app.settings['BUNDLE_VER']}/wheels")
    cmds = [
        "uv build --wheel",
        'cd "../ability-scaffold" && uv build --wheel',
    ]
    return ("shell", {"cmds": cmds, "cwd": repos["ability_py"],
                      "env": {"PATH": _path_with_tools(app),
                              "UV_DEFAULT_INDEX": app.settings["UV_DEFAULT_INDEX"]},
                      "post": lambda app2, rc: _install_ability_wheels(app2, repos, vendor, cache),
                      "verify": [f'test -f "{vendor}/ability_py-0.4.0-py3-none-any.whl"',
                                 f'test -f "{vendor}/ability_scaffold-1.2.0-py3-none-any.whl"']})


def _check_built_wheel(path):
    """拒绝 LFS 指针、损坏的压缩包和缺少 Wheel 元数据的文件。"""
    name, version = os.path.basename(path).split("-")[:2]
    metadata = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(path) as wheel:
        for entry in ("METADATA", "WHEEL", "RECORD"):
            if f"{metadata}/{entry}" not in wheel.namelist():
                raise ValueError(f"缺少 {metadata}/{entry}")
        bad = wheel.testzip()
        if bad:
            raise ValueError(f"压缩包校验失败: {bad}")


def _install_ability_wheels(app, repos, vendor, cache):
    expects = {
        "ability_py": ("ability_py-0.4.0-py3-none-any.whl", [vendor, cache]),
        "ability_scaffold": ("ability_scaffold-1.2.0-py3-none-any.whl", [vendor]),
    }
    # 在覆盖运行目录前，先验证全部源码产物及目标目录。
    for key, (expect, dst_dirs) in expects.items():
        whl = os.path.join(repos[key], "dist", expect)
        try:
            _check_built_wheel(whl)
        except Exception as e:
            return ("fail", f"源码 Wheel 缺失或无效: {whl}: {e}; 请检查构建版本与版本清单")
        for dst_dir in dst_dirs:
            if not os.path.isdir(dst_dir):
                return ("fail", f"Wheel 目标目录不存在: {dst_dir}")
    for key, (expect, dst_dirs) in expects.items():
        repo = repos[key]
        prefix = expect.split("-")[0] + "-"
        whl = os.path.join(repo, "dist", expect)
        name = expect
        for dst_dir in dst_dirs:
            try:
                dst = os.path.join(dst_dir, name)
                if os.path.exists(dst) and not os.path.exists(dst + ".lfs-orig"):
                    shutil.copy2(dst, dst + ".lfs-orig")
                for o in glob.glob(os.path.join(dst_dir, prefix + "*.whl")):
                    if os.path.basename(o) != name:
                        if not os.path.exists(o + ".lfs-orig"):
                            shutil.copy2(o, o + ".lfs-orig")
                        os.remove(o)
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.copy2(whl, dst)
                _check_built_wheel(dst)
                app.log("ok", f"已安装 {dst}")
            except Exception as e:
                return ("fail", f"Wheel 安装到 {dst_dir} 失败: {e}")
    # 清掉旧 scaffold venv, 让 refresh 用源码构建的 Wheel 重建
    venv = os.path.join(vendor, ".venv")
    if os.path.isdir(venv):
        try:
            shutil.rmtree(venv)
        except OSError as e:
            return ("fail", f"无法清理旧 scaffold .venv: {e}")
        app.log("note", "已移除旧 scaffold .venv, refresh 将用源码 Wheel 重建")
    return None

def _step_wheelcache(app):
    base = sx(app.settings["SEMANTIC"])
    d = os.path.join(base, f"semantic-ability/ability-runtime/base-bundles/r1pro-mujoco-{app.settings['BUNDLE_VER']}")
    if not os.path.isdir(os.path.join(d, "wheels")):
        return ("fail", f"Wheel 缓存缺失: {d}/wheels (回到 2.3 git lfs pull)")
    app.log("ok", f"Wheel 缓存就绪: {d}")
    app.log("info", "含 bundle.yaml + wheels/ (numpy/pinocchio/ruckig/websockets/ability_py 等); "
                    "产品 Wheel (SDK/Ability/Skill SDK) 脚本会现打, 不要拷进 .output/robot-bundles")
    return ("ok", None)


def _deb_extract_file(deb_path, suffix, dest_dir):
    """从 .deb 里解出 data.tar.* 内匹配 suffix 的文件到 dest_dir (纯 stdlib)"""
    import tarfile
    data = open(deb_path, "rb").read()
    if data[:8] != b"!<arch>\n":
        raise RuntimeError("非 ar 归档")
    pos = 8
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        name = hdr[0:16].decode().strip()
        size = int(hdr[48:58].decode().strip())
        body = data[pos + 60: pos + 60 + size]
        pos += 60 + size + (size % 2)
        if name.startswith("data.tar"):
            import io
            with tarfile.open(fileobj=io.BytesIO(body), mode="r:*") as tf:
                out = []
                for m in tf.getmembers():
                    if m.isfile() and m.name.endswith(suffix):
                        out.append(tf.extractfile(m).read())
                        fn = os.path.join(dest_dir, os.path.basename(m.name))
                        open(fn, "wb").write(out[-1])
                return len(out)
    return 0


def _whl_extract_match(app, pkg_spec, want_suffix, dest_dir):
    """pip3 download 指定包 (走国内镜像) 并从 wheel 解出匹配文件"""
    import zipfile
    tmp = tempfile.mkdtemp(prefix="whlfix-")
    r = subprocess.run(["pip3", "download", "--no-deps", "-d", tmp, pkg_spec,
                        "-i", app.settings["UV_DEFAULT_INDEX"]],
                       capture_output=True, text=True, timeout=180)
    wheels = [f for f in os.listdir(tmp) if f.endswith(".whl")] if r.returncode == 0 else []
    if not wheels:
        app.log("warn", f"下载 {pkg_spec} 失败: {(r.stderr or '').strip()[:120]}")
        return 0
    n = 0
    with zipfile.ZipFile(os.path.join(tmp, wheels[0])) as z:
        for name in z.namelist():
            if name.endswith(want_suffix):
                open(os.path.join(dest_dir, os.path.basename(name)), "wb").write(z.read(name))
                n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    return n


def _fix_bundle_deps(app):
    """修复 Bundle venv 的 cmeel 共享库错配 (pinocchio 3.9 需 urdfdom soname 4.0, 而
    cmeel_urdfdom-4.0.0-2 wheel 又缺 RUNPATH 且需 tinyxml2 soname 9)。幂等。"""
    base = sx(app.settings["SEMANTIC"])
    bv = os.path.join(base, "semantic-framework/.output/robot-bundles",
                      f"r1pro-mujoco-{app.settings['BUNDLE_VER']}", "python/venv")
    lib = os.path.join(bv, "lib/python3.13/site-packages/cmeel.prefix/lib")
    if not os.path.isdir(lib):
        return None
    try:
        r = subprocess.run([os.path.join(bv, "bin/python"), "-c", "import pinocchio"],
                           capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    if r.returncode == 0:
        app.log("ok", "Bundle 依赖自洽: pinocchio 可正常导入")
        return None
    last = (r.stderr or "").strip().splitlines()
    app.log("warn", "Bundle 依赖错配: " + (last[-1][:130] if last else "pinocchio 导入失败"))
    urdf4 = sorted(glob.glob(os.path.join(lib, "liburdfdom_sensor.so.4*")))
    os.chmod(lib, os.stat(lib).st_mode | 0o200)
    try:
        if not urdf4:
            n = _whl_extract_match(app, "cmeel-urdfdom==4.0.0", ".so.4.0", lib)
            app.log("ok" if n else "warn", f"补 urdfdom soname 4.0 库: {n} 个文件")
        if not glob.glob(os.path.join(lib, "libtinyxml2.so.9*")):
            got = 0
            tmp = tempfile.mkdtemp(prefix="debfix-")
            for mirror in ("https://mirrors.tuna.tsinghua.edu.cn", "https://mirrors.aliyun.com"):
                url = (mirror + "/debian/pool/main/t/tinyxml2/"
                       "libtinyxml2-9_9.0.0+dfsg-3.1_amd64.deb")
                try:
                    import urllib.request
                    urllib.request.urlretrieve(url, os.path.join(tmp, "t.deb"))
                    got = _deb_extract_file(os.path.join(tmp, "t.deb"), "libtinyxml2.so.9", lib)
                    if got:
                        app.log("ok", f"补 libtinyxml2.so.9: {got} 个文件 ({mirror})")
                        break
                except Exception as e:
                    app.log("note", f"{mirror} 下载失败: {e}")
            if not got:
                app.log("warn", "libtinyxml2.so.9 补齐失败, worker 可能仍报缺库")
        # 修复 urdfdom 4 库缺失的 RUNPATH ($ORIGIN)
        ptmp = tempfile.mkdtemp(prefix="pelf-")
        if _whl_extract_match(app, "patchelf", "/patchelf", ptmp):
            pelf = os.path.join(ptmp, "patchelf")
            os.chmod(pelf, 0o755)
            for f in glob.glob(os.path.join(lib, "liburdfdom_*.so.4.0")):
                subprocess.run([pelf, "--set-rpath", "$ORIGIN", f], capture_output=True)
            app.log("ok", "已为 urdfdom 4 库补 RUNPATH($ORIGIN)")
        shutil.rmtree(ptmp, ignore_errors=True)
    finally:
        os.chmod(lib, 0o555)
    r2 = subprocess.run([os.path.join(bv, "bin/python"), "-c", "import pinocchio"],
                        capture_output=True, text=True, timeout=120)
    if r2.returncode == 0:
        app.log("ok", "Bundle 依赖修复完成: pinocchio 导入成功")
    else:
        last2 = (r2.stderr or "").strip().splitlines()
        app.log("err", "Bundle 依赖修复后仍失败: "
                + (last2[-1][:130] if last2 else "未知"))
    return None


def _prepare_bundle_refresh(app):
    """重跑 5.3 时先停本工作区 Server 和占用活动 Bundle 的实例。"""
    base = sx(app.settings["SEMANTIC"])
    fw = os.path.join(base, "semantic-framework")
    for s in list(getattr(app, "services", [])):
        if s.name == "server":
            app.log("note", f"换 Bundle 前先停安装器托管的 Server (pid {s.proc.pid})")
            app.stop_service(s)
    if hasattr(app, "services"):
        app.services = [s for s in app.services if s.name != "server"]
    if not _stop_pids(app, _workspace_server_pids(fw), "Server"):
        return False
    bundle = os.path.join(fw, ".output/robot-bundles", f"r1pro-mujoco-{app.settings['BUNDLE_VER']}")
    if os.path.isdir(bundle) and not _stop_pids(app, _bundle_user_pids(bundle), "MuJoCo Bundle 进程"):
        return False
    return True


def _step_build_bundle(app):
    base = sx(app.settings["SEMANTIC"])
    fw = os.path.join(base, "semantic-framework")
    rc, out = _run_quick(["uv", "python", "find", "3.13"], env={**app.env, "PATH": _path_with_tools(app)})
    if rc != 0:
        return ("fail", "uv python find 3.13 失败, 先完成步骤 1.4")
    py = out.splitlines()[-1].strip()
    app.vars["PYTHON313"] = py
    app.log("info", f"PYTHON313 = {py}")
    if not _prepare_bundle_refresh(app):
        return ("fail", "无法停掉占用 Bundle 的旧进程; 确认本工作区 Server/实例已退出后重跑")
    idx = shlex.quote(app.settings["UV_DEFAULT_INDEX"])
    cmds = [
        f'"{py}" -m pip --version >/dev/null 2>&1 || "{py}" -m ensurepip --upgrade',
        f'"{py}" -m pip install --upgrade --break-system-packages setuptools wheel --index-url {idx} '
        f'|| "{py}" -m pip install --upgrade setuptools wheel --index-url {idx}',
        f'"{py}" scripts/refresh_v050_mujoco.py build --activate --stop-users --python "{py}"',
    ]
    return ("shell", {"cmds": cmds, "cwd": fw,
                      "env": {"SEMANTIC": base, "PATH": _path_with_tools(app),
                               "UV_DEFAULT_INDEX": app.settings["UV_DEFAULT_INDEX"],
                               **_mirror_env_extra(app)},
                      "post": lambda app2, rc: _fix_bundle_deps(app2) and None,
                      "verify": [f'test -d "{fw}/.output/robot-bundles/r1pro-mujoco-{app.settings["BUNDLE_VER"]}"']})


def _step_enable_robot(app):
    base = sx(app.settings["SEMANTIC"])
    cfg = os.path.join(base, "semantic-framework/.output/configs/semantic-server.yaml")
    if not os.path.isfile(cfg):
        return ("fail", f"不存在: {cfg} (先完成阶段 3 make build/init)")
    patch_server_yaml(app, cfg)
    role = os.path.join(base, "semantic-framework/.output/configs/agents/leader/role.yaml")
    if os.path.isfile(role):
        ensure_leader_allowlist(app, role)
    else:
        app.log("warn", f"未找到 {role} (--activate 未同步 agents 配置?)")
    return ("ok", None)


def _step_web_env(app):
    web = sx(app.settings["SEMANTIC"]) + "/semantic-web"
    if not os.path.isdir(web):
        return ("fail", f"目录不存在: {web} (先完成阶段 2)")
    # Web 前端的 VITE_SERVER_WS 用根地址 (前端自行拼 /ws/studio 等路径);
    # SERVER_WS 设置 (含 /ws/pilot) 是 robot_runtime 的 Pilot 专用地址, 不能混用
    m = re.match(r"^wss?://[^/]+", app.settings["SERVER_WS"].strip())
    web_ws = m.group(0) if m else app.settings["SERVER_WS"]
    ensure_env_file(app, web, {
        "VITE_SERVER_HTTP": app.settings["SERVER_HTTP"],
        "VITE_SERVER_WS": web_ws,
        "VITE_STUDIO_FIXTURES": "false",
    })
    nr = app.settings.get("NPM_REGISTRY", "").strip()
    cmd = "npm ci --registry " + shlex.quote(nr) if nr else "npm ci"
    return ("shell", {"cmds": [cmd], "cwd": web, "env": {"PATH": _path_with_tools(app)}})


def _step_mirror_config(app):
    msgs = []
    s = app.settings
    gp = s.get("GO_PROXY", "").strip()
    if gp:
        rc, _out = _run_quick(["go", "version"], env=app.env)
        if rc == 0:
            rc2, out2 = _run_quick(["go", "env", "-w", "GOPROXY=" + gp], env=app.env)
            app.env["GOPROXY"] = gp
            app.log("ok" if rc2 == 0 else "warn",
                    f"go env -w GOPROXY={gp}" + ("" if rc2 == 0 else f" 失败: {out2}"))
        else:
            app.log("note", "未检测到 go, 跳过 GOPROXY (完成 1.2 后重跑本步)")
            msgs.append("go 未安装")
    nr = s.get("NPM_REGISTRY", "").strip()
    if nr:
        rc, _out = _run_quick(["npm", "-v"], env=app.env)
        if rc == 0:
            rc2, out2 = _run_quick(["npm", "config", "set", "registry", nr], env=app.env)
            app.log("ok" if rc2 == 0 else "warn",
                    f"npm registry -> {nr} (写入 ~/.npmrc)" + ("" if rc2 == 0 else f" 失败: {out2}"))
        else:
            app.log("note", "未检测到 npm, 跳过 registry 配置")
            msgs.append("npm 未安装")
    app.env.update(_mirror_env_extra(app))
    write_env_sh(s)
    app.log("info", f"已同步更新 {ENV_SH}")
    if msgs:
        return ("warn", "; ".join(msgs))
    return ("ok", None)


def _step_publish_skills(app):
    s = app.settings
    fw = sx(s["SEMANTIC"]) + "/semantic-framework"
    if not os.path.isdir(fw):
        return ("fail", f"目录不存在: {fw}")
    payload = json.dumps({"username": "admin", "password": s["SEMANTIC_ADMIN_PASSWORD"]})
    r = subprocess.run(
        ["curl", "-s", "--max-time", "20", s["SERVER_HTTP"] + "/api/v1/auth/login",
         "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True)
    body = r.stdout.strip()
    try:
        token = json.loads(body).get("token")
    except Exception:
        token = None
    if not token:
        app.log("err", f"登录失败 (Server 在跑吗? 密码与 .env 一致吗?): {body[:200]}")
        return ("fail", "无法获取登录 Token")
    app.log("ok", "登录成功, 已获取 Token")
    cmd = "make publish-v050-mujoco-skills"
    return ("shell", {"cmds": [cmd], "cwd": fw,
                      "env": {"SEMANTIC": sx(s["SEMANTIC"]), "SEMANTIC_ACCESS_TOKEN": token,
                              "SERVER_HTTP": s["SERVER_HTTP"], "PATH": _path_with_tools(app)},
                      "post": lambda app2, rc: app2.log("info", "Token 已随步骤结束丢弃, 未写入任何文件") and None})



# 应用状态与执行引擎


class Service:
    def __init__(self, name, proc, logpath, host, port, sid):
        self.name, self.proc, self.logpath = name, proc, logpath
        self.host, self.port, self.sid = host, port, sid
        self.started = time.time()
        self.offset = 0

    def alive(self):
        return self.proc.poll() is None


class App:
    def __init__(self, settings, headless=False):
        self.settings = settings
        self.headless = headless
        self.statuses = load_json(STATUS_FILE, {})
        self.logbuf = deque(maxlen=LOG_LIMIT)
        self.env = dict(os.environ)
        self.vars = {}
        self.steps = build_steps()
        self.bysid = {s["sid"]: s for s in self.steps}
        self.queue = []
        self.cur = None
        self.cur_proc = None
        self.cur_q = None
        self.cur_kind = None
        self.cur_start = 0.0
        self.cur_out = []
        self.services = []
        self.dirty = True
        self.force_current = False
        self.last_health = 0.0
        self.last_ingest = 0.0
        self.aborted = False
        self.full_redraw = False
        self.prompt = None
        self.confirm = None
        self.workspace_prompt = None
        self.clone_workspace = None
        self.cur_used_pw = False
        self.last_auth_fail_sid = None
        self.forms = {}
        self.log_paths = {}
        self.step_log_path = None
        self.log_error = ""
        self.last_step = None
        self.failed_sid = None
        self.env.setdefault("GIT_TERMINAL_PROMPT", "0")

    # ---- 日志 ----
    def _redact(self, text):
        text = plain_log_text(text)
        for key, value in {**self.env, **self.settings, **self.vars}.items():
            if re.search(r"password|token|secret|(?:^|_)pw$", key, re.I) and isinstance(value, str) and len(value) >= 3:
                text = text.replace(value, "[REDACTED]")
        text = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", text)
        text = re.sub(r"glpat-[A-Za-z0-9_-]+", "[REDACTED]", text)
        return text

    def _start_step_log(self, sid):
        self.step_log_path = None
        for directory in (SCRIPT_DIR / LOG_DIRNAME, Path(tempfile.gettempdir()) / f"semantic-installer-{os.getuid()}"):
            try:
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd, path = tempfile.mkstemp(prefix=f"step-{sid}-", suffix=".log", dir=directory)
                os.close(fd)
                self.step_log_path = path
                self.log_paths[sid] = path
                self.log_error = ""
                return
            except OSError as e:
                self.log_error = f"无法写入日志: {e}"

    def form_for(self, step):
        sid = step["sid"]
        if sid not in self.forms:
            form = {"rows": [], "fields": [], "error": ""}
            if step["stage"] == 2:
                manifest, rows = _repo_plan(self)
                if sid == "2.3":
                    rows = [row for row in rows if row["repo"] in
                            ("semantic-scene/mujoco-asset", "semantic-ability/ability-runtime")]
                form["rows"] = rows
                form["fields"] = [("工作区", sx(self.settings["SEMANTIC"])), ("版本清单", manifest or "内置配置")]
                if sid == "2.3":
                    form["fields"].append(("拉取清单", "场景资产 / bundle 配置 / 第三方 Wheel"))
                    form["fields"].append(("Wheel 来源", self.settings.get("RUNTIME_WHEEL_SOURCE", "auto")))
            else:
                keys = {
                    "1.0": ("APT_MIRROR",), "1.1": ("APT_MIRROR", "SUDO_AUTH"),
                    "1.2": ("GO_VERSION", "GO_DL_MIRROR", "GO_PROXY"),
                    "1.3": ("NODE_VERSION", "NODE_MIRROR", "NPM_REGISTRY"),
                    "1.4": ("UV_DEFAULT_INDEX", "GITHUB_PROXY"),
                    "1.5": ("SEMANTIC_MUJOCO_GL",), "1.6": ("GO_PROXY", "NPM_REGISTRY"),
                    "3.1": ("SEMANTIC",),
                }.get(sid, ("SEMANTIC",))
                form["fields"] = [(key, sx(self.settings.get(key, "")) or "未设置") for key in keys]
                if sid == "3.1":
                    form["fields"].append(("管理员密码", "已配置" if self.settings.get("SEMANTIC_ADMIN_PASSWORD") else "未设置"))
            self.forms[sid] = form
        return self.forms[sid]

    def log(self, kind, text=""):
        text = self._redact(text)
        if kind == "err" and not self.step_log_path:
            self._start_step_log(self.cur["sid"] if self.cur else "startup")
        if self.step_log_path:
            try:
                with open(self.step_log_path, "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{kind}] {text}\n")
            except OSError as e:
                self.log_error = f"无法写入日志: {e}"
        if kind == "detail":
            return
        if self.cur and kind == "out" and text.startswith("[wheel "):
            form = self.form_for(self.cur)
            form["fields"] = [(k, v) for k, v in form["fields"] if k != "Wheel 进度"]
            form["fields"].append(("Wheel 进度", text))
            self.dirty = True
            return
        if self.cur and kind == "out" and text.startswith(REPO_EVENT_MARK):
            try:
                local, status = json.loads(text[len(REPO_EVENT_MARK):])
                if status in ("running", "ok", "skip"):
                    for row in self.form_for(self.cur)["rows"]:
                        if row["repo"] == local:
                            row["status"] = status
            except (ValueError, TypeError):
                pass
            self.dirty = True
            return
        if self.cur and kind in ("cmd", "out") and (self.cur["stage"] <= 2 or self.cur["sid"] == "3.1"):
            return
        # [kind, text, 缓存槽]: 缓存 (宽, 前缀宽, 折行结果), 避免每帧全量重排
        self.logbuf.append([kind, text, None])
        self.dirty = True
        if self.headless:
            prefix = {"cmd": "$ ", "ok": "[OK] ", "err": "[FAIL] ", "warn": "[WARN] ",
                      "info": "[INFO] ", "note": "[NOTE] "}.get(kind, "")
            print(prefix + str(text), flush=True)

    # ---- 状态 ----
    def status(self, sid):
        return self.statuses.get(sid, "pending")

    def set_status(self, sid, st):
        self.statuses[sid] = st
        save_json(STATUS_FILE, self.statuses)
        self.dirty = True

    def stage_steps(self, stage):
        return [s for s in self.steps if s["stage"] == stage]

    def stage_done(self, stage):
        return all(self.status(s["sid"]) in DONE_STATES for s in self.stage_steps(stage))

    def stage_missing_prereq(self, stage):
        missing = []
        for st in STAGE_PREREQ.get(stage, []):
            if not self.stage_done(st):
                missing.append(f"阶段{st} {STAGES[st - 1][1]}")
        return missing

    # ---- 入队 ----
    def enqueue_stage(self, stage, auto=False):
        for s in self.stage_steps(stage):
            self.enqueue_step(s, auto=auto)

    def enqueue_step(self, step, auto=False, force=False):
        if step["kind"] in ("manual", "info"):
            if auto:
                self.log("note", f"跳过手动/说明步骤 {step['sid']} {step['title']}")
            else:
                self.show_manual(step)
            return
        self.queue.append((step["sid"], force))
        self.dirty = True

    def show_manual(self, step):
        if step.get("note"):
            self.log("note", f"{step['sid']} {step['title']}: {step['note']}")
        if step.get("manual_text"):
            for ln in step["manual_text"].splitlines():
                self.log("info", ln)
            self.log("note", "确认在 Studio 完成后按 m 标记此步骤完成")

    # ---- 执行 ----
    def pump(self):
        """主循环驱动: 必须在主线程调用"""
        if self.cur:
            self._pump_current()
            return
        if not self.queue:
            return
        sid, force = self.queue.pop(0)
        step = self.bysid[sid]
        self._begin(step, force)

    def _begin(self, step, force):
        self.last_step = step
        self._start_step_log(step["sid"])
        self.forms.pop(step["sid"], None)
        self.log("info", f"开始 {step['sid']} {step['title']}")
        self.force_current = force
        if not force and step.get("skip_check"):
            try:
                reason = step["skip_check"](self)
            except Exception as e:
                reason = None
            if reason:
                self.set_status(step["sid"], "skip")
                self.log("note", f"{step['sid']} {step['title']}: {reason}, 跳过")
                return
        if step.get("note"):
            self.log("note", f"{step['sid']} {step['title']}: {step['note']}")
        self.cur = step
        self.cur_start = time.time()
        self.cur_out = []
        self.aborted = False
        self.cur_used_pw = False
        self.set_status(step["sid"], "running")
        try:
            if step.get("pre"):
                if step["pre"](self) is False:
                    self._finish("fail", "工作区未确认, 已停止后续操作")
                    return
        except Exception as e:
            self.log("detail", traceback.format_exc())
            self._finish("fail", f"pre 钩子异常: {e}")
            return
        try:
            kind = step["kind"]
            if kind == "python":
                self._run_python(step)
            elif kind == "service":
                self._start_service(step)
            else:
                self._run_shell(step)
        except Exception as e:
            self.log("detail", traceback.format_exc())
            self._finish("fail", f"执行失败: {e}")

    def _run_python(self, step):
        try:
            result = step["fn"](self)
        except Exception as e:
            self.log("detail", traceback.format_exc())
            self.log("err", f"异常: {e}")
            self._finish("fail", str(e))
            return
        if not result:
            self._finish("ok")
            return
        tag = result[0]
        if tag == "shell":
            info = result[1]
            step2 = dict(step)
            step2["cmds"] = info.get("cmds", [])
            step2["cwd"] = info.get("cwd")
            step2["env"] = info.get("env")
            step2["verify"] = info.get("verify", [])
            step2["post"] = info.get("post", step.get("post"))
            # 完成回调和校验从 self.cur 读取，必须保留动态生成的步骤。
            self.cur = step2
            self._run_shell(step2)
        else:
            self._finish(tag, result[1] if len(result) > 1 else None)

    def _needs_terminal(self, step, cmds):
        if not step.get("sudo"):
            return False
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        return r.returncode != 0

    def _sudoize(self, cmds):
        """把命令里的 sudo 改为 sudo -S -p '' (密码走 stdin); 返回 (cmds, sudo 次数)"""
        out, count = [], 0
        for c in cmds:
            if "\n" in c:
                lines = []
                for ln in c.split("\n"):
                    ln2, k = re.subn(r"\bsudo\b(?!\s+-S\b)", "sudo -S -p ''", ln)
                    count += k
                    lines.append(ln2)
                out.append("\n".join(lines))
            else:
                c2, k = re.subn(r"\bsudo\b(?!\s+-S\b)", "sudo -S -p ''", c)
                count += k
                out.append(c2)
        return out, count

    def _sudo_pw_valid(self, pw):
        """用 -k 强制重新鉴权来验证密码是否正确"""
        try:
            r = subprocess.run(["sudo", "-S", "-k", "-p", "", "true"],
                               input=pw + "\n", capture_output=True,
                               text=True, timeout=30)
            return r.returncode == 0
        except Exception:
            return False

    def maybe_retry_auth_failed(self):
        """凭证配置完成后, 询问是否重跑刚才因认证失败的步骤"""
        sid = self.last_auth_fail_sid
        self.last_auth_fail_sid = None
        if not sid or self.cur:
            return
        step = self.bysid.get(sid)
        if not step or self.status(sid) in DONE_STATES:
            return
        ask = getattr(self, "confirm", None)
        if ask:
            try:
                ok = ask("自动重试", f"凭证已更新, 立即重跑 {sid} {step['title']}?")
            except Exception:
                ok = False
        else:
            ok = True
        if ok:
            self.log("note", f"== 自动重试 {sid} {step['title']} ==")
            self.enqueue_step(step, force=True)

    def prepare_clone_workspace(self):
        """Resolve the shared clone/build root before evaluating any step commands."""
        if self.headless:
            self.log("note", f"无头模式使用已配置工作区: {sx(self.settings['SEMANTIC'])}")
            return True
        if self.clone_workspace == sx(self.settings["SEMANTIC"]) and os.path.isdir(self.clone_workspace):
            return True
        if not self.workspace_prompt or not self.confirm:
            self.log("err", "无法显示工作区选择对话框")
            return False
        initial = self.clone_workspace or str(SCRIPT_DIR)
        error = ""
        while True:
            chosen = self.workspace_prompt(initial, error)
            if chosen is None:
                self.log("note", "已取消拉取/构建工作区选择")
                return False
            chosen = sx(chosen.strip())
            initial = chosen
            if not chosen or not os.path.isabs(chosen):
                error = "请输入绝对路径, 例如 /data/semantic"
                self.log("err", error)
                continue
            # Existing build commands interpolate paths inside shell double quotes.
            if any(c in chosen for c in ('"', '$', '`', '\\')) or any(ord(c) < 32 for c in chosen):
                error = "路径不能含双引号、美元符、反引号、反斜杠或控制字符"
                self.log("err", error)
                continue
            chosen = os.path.normpath(chosen)
            if os.path.exists(chosen) and not os.path.isdir(chosen):
                error = "路径已存在但不是目录, 请重新填写"
                self.log("err", f"{error}: {chosen}")
                continue
            if not self.confirm("确认拉取和构建目录",
                                f"{chosen}\n将把子仓库拉取到此目录, 后续构建也使用此工作区。\n是否继续?"):
                self.log("note", "已取消拉取/构建目录确认")
                return False
            if not self._ensure_cwd(chosen):
                return False
            settings = {**self.settings, "SEMANTIC": chosen}
            try:
                save_json(SETTINGS_FILE, settings)
                write_env_sh(settings)
            except OSError as e:
                self.log("err", f"保存工作区设置失败: {e}")
                return False
            self.settings["SEMANTIC"] = chosen
            self.env["SEMANTIC"] = chosen
            self.clone_workspace = chosen
            self.forms.pop("2.1", None)
            self.log("ok", f"拉取/构建工作区已确认: {chosen}; 已保存至 {SETTINGS_FILE} 和 {ENV_SH}")
            return True

    def _ensure_cwd(self, cwd):
        """cwd 不存在时询问是否自动创建 (无头模式直接创建); 返回 False 表示拒绝/失败"""
        if not cwd or os.path.isdir(cwd):
            return True
        ask = getattr(self, "confirm", None)
        if ask:
            try:
                ok = ask("目录不存在",
                         f"{cwd}\n该步骤需要在此目录执行。\n是否自动创建该目录并继续?")
            except Exception:
                ok = False
            if not ok:
                self.log("err", f"目录不存在且未创建: {cwd}")
                return False
        else:
            self.log("note", f"无头模式: 目录不存在, 自动创建 {cwd}")
        try:
            os.makedirs(cwd, exist_ok=True)
            self.log("ok", f"已创建目录: {cwd}")
            return True
        except Exception as e:
            self.log("err", f"创建目录失败: {e}")
            return False

    def _run_shell(self, step):
        cmds = step["cmds"]
        if callable(cmds):
            cmds = cmds(self)
        if isinstance(cmds, str):
            cmds = [cmds]
        if not cmds:
            self._finish("ok")
            return
        env = dict(self.env)
        if step.get("env"):
            e = step["env"](self) if callable(step["env"]) else step["env"]
            env.update(e)
        cwd = step["cwd"](self) if callable(step["cwd"]) else step["cwd"]
        if not self._ensure_cwd(cwd):
            self._finish("fail", f"目录不存在: {cwd}")
            return
        use_pw = 0
        if step.get("sudo") and any(re.search(r"(^|\s)sudo\s", c) for c in cmds):
            mode = self.settings.get("SUDO_AUTH", "tui")
            if mode == "tui" and getattr(self, "prompt", None):
                pw = self.vars.get("SUDO_PW")
                if pw is None:
                    pw = self.prompt()
                    if not pw:
                        self._finish("fail", "已取消: 未提供 sudo 密码")
                        return
                    if not self._sudo_pw_valid(pw):
                        self._finish("fail", "sudo 授权未通过或超时；请重跑并输入 Linux 登录密码，或按 e 设置 SUDO_AUTH=terminal")
                        return
                    self.vars["SUDO_PW"] = pw
                    self.log("note", "sudo 密码仅存于本进程内存 (不写盘), P 键可清除")
                cmds, use_pw = self._sudoize(cmds)
            elif self._needs_terminal(step, cmds):
                self._run_in_terminal(step, cmds, cwd, env)
                return
        self.cur_used_pw = use_pw
        self.log("detail", f"工作目录: {cwd or os.getcwd()}")
        script = ["set -eo pipefail"]
        for c in cmds:
            self.log("detail", c)
            shown = c if "\n" not in c else c.splitlines()[0] + " …(脚本)"
            script.append("echo " + shlex.quote(CMD_MARK + shown))
            script.append(c)
        code = "\n".join(script)
        try:
            self.cur_proc = subprocess.Popen(
                ["bash", "-c", code], cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                stdin=subprocess.PIPE if use_pw else subprocess.DEVNULL,
                start_new_session=True, bufsize=1)
        except Exception as e:
            self.log("err", f"启动失败: {e}")
            self._finish("fail", str(e))
            return
        if use_pw:
            # 已提前验证密码；每条 sudo 最多预留一行，不自动重复三次失败验证。
            feed = (self.vars.get("SUDO_PW", "") + "\n") * max(1, use_pw)
            try:
                self.cur_proc.stdin.write(feed)
                self.cur_proc.stdin.flush()
                self.cur_proc.stdin.close()
            except Exception:
                pass
        self.cur_kind = "shell"
        self.cur_eof = False
        self.cur_q = Queue()
        self._start_reader(self.cur_proc, self.cur_q)

    def _start_reader(self, proc, q):
        import threading

        def rd():
            try:
                for line in iter(proc.stdout.readline, ""):
                    q.put(line.rstrip("\n"))
            except Exception:
                pass
            q.put(None)
        t = threading.Thread(target=rd, daemon=True)
        t.start()

    def _run_in_terminal(self, step, cmds, cwd, env):
        """sudo 需要密码时: 临时退出 curses, 在真实终端执行并 tee 到日志文件"""
        self.cur_kind = "term"
        logf = tempfile.NamedTemporaryFile(prefix="semantic-tui-", suffix=".log", delete=False)
        logpath = logf.name
        logf.close()
        script = [
            "set -o pipefail",
            "{", "set -e",
        ]
        for c in cmds:
            shown = c if "\n" not in c else c.splitlines()[0] + " …(脚本)"
            script.append("echo " + shlex.quote(CMD_MARK + shown))
            script.append(c)
        script += ["}", f'2>&1 | tee "{logpath}"',
                   f'rc=${{PIPESTATUS[0]}}', f'echo "$rc" > "{logpath}.rc"', 'exit "$rc"']
        code = "\n".join(script)
        if not self.headless:
            print("\n[sudo 需要密码, 已切换到终端模式, 请按提示输入密码]\n", flush=True)
            curses.def_prog_mode()
            curses.endwin()
        try:
            rc = subprocess.call(["bash", "-c", code], cwd=cwd, env=env)
        finally:
            if not self.headless:
                curses.reset_prog_mode()
                self.full_redraw = True
        try:
            with open(logpath, "r", errors="replace") as f:
                lines = f.read().splitlines()[-400:]
            for ln in lines:
                if ln.startswith(CMD_MARK):
                    self.log("cmd", ln[len(CMD_MARK):])
                else:
                    self.log("out", ln)
            os.unlink(logpath)
            rcfile = logpath + ".rc"
            if os.path.exists(rcfile):
                os.unlink(rcfile)
        except Exception:
            pass
        self._finish("ok" if rc == 0 else "fail", f"rc={rc}")

    def _start_service(self, step):
        svc = step["service"](self) if callable(step["service"]) else step["service"]
        cwd = svc.get("cwd")
        if not self._ensure_cwd(cwd):
            self._finish("fail", f"目录不存在: {cwd}")
            return
        name = svc["name"]
        for s in list(self.services):
            if s.name == name:
                self.log("note", f"发现安装器已托管的 [{name}] (pid {s.proc.pid}), 先停止")
                self.stop_service(s)
        self.services = [x for x in self.services if x.name != name or not x.alive()]
        base = sx(self.settings["SEMANTIC"])
        leftover = []
        if name == "server":
            leftover = _workspace_server_pids(os.path.join(base, "semantic-framework"))
        elif name == "web":
            leftover = _workspace_web_pids(os.path.join(base, "semantic-web"))
        if leftover and not _stop_pids(self, leftover, name):
            self._finish("fail", f"无法停掉旧的 {name}")
            return
        host, port = url_host_port(svc.get("health", ""))
        if not _wait_port_free(self, host, port):
            self._finish("fail", f"{host}:{port} 仍被占用, 先停掉占用端口的进程")
            return
        env = dict(self.env)
        env.update(svc.get("env", {}))
        tmpdir = env.get("TMPDIR")
        if tmpdir:
            os.makedirs(tmpdir, exist_ok=True)
        logdir = Path(sx(self.settings["SEMANTIC"])) / LOG_DIRNAME
        logdir.mkdir(parents=True, exist_ok=True)
        logpath = logdir / f"{name}.log"
        self.log("cmd", f"[{name}] {svc['start']}  (后台运行, 日志: {logpath})")
        try:
            fh = open(logpath, "ab", buffering=0)
            proc = subprocess.Popen(["bash", "-c", svc["start"]], cwd=cwd, env=env,
                                    stdout=fh, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        except Exception as e:
            self._finish("fail", f"启动失败: {e}")
            return
        s = Service(svc["name"], proc, str(logpath), host, port, step["sid"])
        s.timeout = svc.get("timeout", 240)
        s.started = time.time()
        self.services = [x for x in self.services if x.sid != step["sid"] and x.alive()]
        self.services.append(s)
        self.cur_kind = "svc"
        self.cur_proc = proc
        self.cur_start = time.time()

    def _pump_current(self):
        if self.cur_kind == "shell":
            # 单次排水设上限, 剩余留给下一轮 (120ms 内再排), 避免长输出卡住主循环
            MAX_DRAIN = 400
            drained = 0
            while drained < MAX_DRAIN:
                try:
                    line = self.cur_q.get_nowait()
                except Empty:
                    break
                drained += 1
                if line is None:
                    self.cur_eof = True
                    continue
                if line.startswith(CMD_MARK):
                    self.log("cmd", line[len(CMD_MARK):])
                    self.cur_out.append(line[len(CMD_MARK):])
                else:
                    self.log("out", line)
                    self.cur_out.append(line)
            rc = self.cur_proc.poll()
            if rc is not None:
                # 进程已退出: 排空到读到 EOF 标记为止 (最多等 2s), 防丢尾部输出
                deadline = time.time() + 2
                eof = self.cur_eof
                while not eof and time.time() < deadline:
                    try:
                        line = self.cur_q.get_nowait()
                    except Empty:
                        time.sleep(0.02)
                        continue
                    if line is None:
                        eof = True
                        continue
                    if line.startswith(CMD_MARK):
                        self.log("cmd", line[len(CMD_MARK):])
                        self.cur_out.append(line[len(CMD_MARK):])
                    else:
                        self.log("out", line)
                        self.cur_out.append(line)
                if eof and self.cur_proc.stdout:
                    self.cur_proc.stdout.close()
                out_text = "\n".join(self.cur_out[-40:])
                if rc != 0:
                    low = out_text.lower()
                    if any(h in low for h in ("could not read username",
                                              "authentication failed",
                                              "access denied", "http 403")):
                        self.last_auth_fail_sid = self.cur["sid"]
                        self.log("note", "看起来是 GitLab 凭证问题: 按 g 打开凭证助手 "
                                        "(OAuth 自动登录 / 粘贴 PAT), 配好后会自动重跑本步骤")
                    if getattr(self, "cur_used_pw", 0) and re.search(
                            r"incorrect password|authentication failure|a password is required|"
                            r"no password was provided|not in the sudoers|错误密码|对不起，请重试|需要密码|未提供密码",
                            out_text, re.I):
                        self.vars.pop("SUDO_PW", None)
                        self.log("err", "sudo 授权失败，缓存已清除；请重跑或设置 SUDO_AUTH=terminal")
                if rc != 0 and self.cur.get("retry"):
                    try:
                        extra = self.cur["retry"](self, out_text)
                    except Exception:
                        extra = None
                    if extra:
                        extra_arg = extra[0] if isinstance(extra, tuple) else extra
                        self.log("warn", f"失败(rc={rc}), 按规则重试: 追加 {extra_arg}")
                        old = self.cur
                        old_cmds = old["cmds"](self) if callable(old["cmds"]) else old["cmds"]
                        old["cmds"] = [c + " " + extra_arg for c in old_cmds]
                        self.cur = None
                        self.cur_proc = None
                        self.cur_kind = None
                        self.queue.insert(0, (old["sid"], True))
                        return
                self._finish("ok" if rc == 0 else "fail", f"rc={rc}")
            return
        if self.cur_kind == "svc":
            nowt = time.time()
            if nowt - self.last_ingest > 1.0:
                self.last_ingest = nowt
                for s in self.services:
                    self._ingest_service_log(s, limit=40)
            if nowt - self.last_health > 1.0:
                self.last_health = nowt
                svc = [x for x in self.services if x.sid == self.cur["sid"]]
                if svc:
                    s = svc[-1]
                    if not s.alive():
                        self._ingest_service_log(s, limit=80)
                        tail = self._tail(s.logpath, 10)
                        self._finish("fail", f"进程提前退出: {tail}")
                        return
                    try:
                        with socket.create_connection((s.host, s.port), timeout=0.2):
                            self._finish("ok", f"健康检查通过 ({s.host}:{s.port})")
                            self.log("note", f"[{s.name}] 持续后台运行; 日志 {s.logpath}; 选中后按 L 查看尾部")
                            return
                    except OSError:
                        pass
                    if nowt - self.cur_start > s.timeout:
                        self.stop_service(s)
                        self._finish("fail", f"健康检查超时 ({s.timeout}s, {s.host}:{s.port})")
            return

    def _ingest_service_log(self, s, limit=40):
        try:
            size = os.path.getsize(s.logpath)
            if size <= s.offset:
                return
            with open(s.logpath, "rb") as f:
                f.seek(s.offset)
                data = f.read(200000)
                s.offset = f.tell()
            text = data.decode("utf-8", errors="replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            for ln in lines[-limit:]:
                self.log("out", f"[{s.name}] {ln}")
        except Exception:
            pass

    def _tail(self, path, n):
        try:
            with open(path, "r", errors="replace") as f:
                return " | ".join(f.read().splitlines()[-n:])
        except Exception:
            return path

    def stop_service(self, s):
        try:
            os.killpg(os.getpgid(s.proc.pid), signal.SIGTERM)
        except Exception:
            try:
                s.proc.terminate()
            except Exception:
                pass
        deadline = time.time() + 5
        while time.time() < deadline:
            if s.proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            os.killpg(os.getpgid(s.proc.pid), signal.SIGKILL)
        except Exception:
            try:
                s.proc.kill()
            except Exception:
                pass
        s.proc.poll()

    def stop_all_services(self):
        for s in list(self.services):
            if s.alive():
                self.log("note", f"停止服务 [{s.name}] (pid {s.proc.pid})")
                self.stop_service(s)
        self.services = []

    def _finish(self, status, msg=None):
        step = self.cur
        if step is None:
            return
        dur = time.time() - self.cur_start
        post = step.get("post")
        if post and status in ("ok", "warn"):
            try:
                r = post(self, 0)
                if isinstance(r, tuple) and r[0] in ("warn", "fail"):
                    status = r[0]
                    msg = r[1]
            except Exception as e:
                self.log("detail", traceback.format_exc())
                status, msg = "fail", f"post 钩子异常: {e}"
                self.log("err", msg)
        if status == "ok" and (step.get("verify") or (step.get("kind") == "python")):
            verified = self._run_verify(step)
            if verified:
                status, msg = verified, "产物校验未通过，详见步骤日志"
        if status == "fail":
            self.log("err", f"{step['sid']} 失败 ({dur:.1f}s): {msg or ''}")
        elif status == "warn":
            self.log("warn", f"{step['sid']} 警告 ({dur:.1f}s): {msg or ''}")
        else:
            self.log("ok", f"{step['sid']} {step['title']} 完成 ({dur:.1f}s)")
        if step["stage"] <= 2 or step["sid"] == "3.1":
            form = self.form_for(step)
            for row in form["rows"]:
                if row["status"] == "running" or (status == "ok" and row["status"] == "pending"):
                    row["status"] = status
            if status == "fail":
                detail = next((line for line in reversed(self.cur_out)
                               if re.search(r"fatal:|error:|permission denied|not found|sudo:|错误密码|对不起，请重试", line, re.I)), msg or "步骤失败")
                form["error"] = self._redact(detail).splitlines()[0][:180]
        self.log("info" if status != "fail" else "err", f"最终结果: {status}; {msg or ''}; 日志: {self.step_log_path or self.log_error}")
        self.set_status(step["sid"], status)
        if status == "fail":
            self.failed_sid = step["sid"]
            self.log("warn", "已停止后续步骤; 修复后重跑本步骤或所在阶段")
            self.queue.clear()
            if self.aborted:
                self.log("note", "已按用户要求中止")
        self.cur = None
        self.cur_proc = None
        self.cur_q = None
        self.cur_kind = None

    def _run_verify(self, step):
        vf = step.get("verify")
        if not vf:
            return None
        cmds = vf(self) if callable(vf) else vf
        failed = []
        for c in cmds:
            self.log("cmd", f"[校验] {c}")
            try:
                r = subprocess.run(["bash", "-c", c], capture_output=True, text=True,
                                   env=self.env, timeout=120)
                out = (r.stdout + r.stderr).strip()
                for ln in out.splitlines()[:10]:
                    self.log("out", ln)
                if r.returncode != 0:
                    failed.append(c)
            except Exception as e:
                failed.append(f"{c} ({e})")
        if failed:
            self.log("warn", "校验未通过: " + " ; ".join(failed[:3]))
            return "warn" if not step.get("verify_required", True) else "fail"
        self.log("ok", "校验通过")
        return None

    def abort(self):
        if self.cur_kind == "shell" and self.cur_proc:
            self.aborted = True
            try:
                os.killpg(os.getpgid(self.cur_proc.pid), signal.SIGTERM)
            except Exception:
                pass
        elif self.cur_kind == "svc" and self.cur_proc:
            self.aborted = True
            self.stop_all_services()
            self._finish("fail", "用户中止")
        self.queue.clear()
        self.log("note", "已中止队列")

    def run_queue_sync(self, sids):
        """无头模式: 阻塞跑完一组步骤"""
        for sid in sids:
            step = self.bysid[sid]
            if step["kind"] in ("manual", "info"):
                self.show_manual(step)
                continue
            self.queue.append((sid, False))
        while self.queue or self.cur:
            self.pump()
            time.sleep(0.05)



# UI


GLYPH = {"pending": "·", "running": "▶", "ok": "✓", "fail": "✗",
         "warn": "!", "skip": "-", "done": "M"}
GLYPH_COLOR = {"pending": 0, "running": -1, "ok": 1, "fail": 2,
               "warn": 4, "skip": 0, "done": 5}  # 颜色对编号; -1 = 仅加粗

HELP_TEXT = """Semantic 安装器: 按键与要点

[按键]
  ↑/↓ 或 j/k     上下移动
  Enter          运行: 阶段=整段顺序执行, 步骤=单步 (单步会跳过 skip 检查强制执行)
  a              从阶段 1 开始连续执行所有 (尊重 skip 检查; 手动步骤跳过)
  A              从当前选中项连续执行到末尾
  v              仅运行校验命令 (当前阶段/步骤)
  e              环境变量设置 (路径/版本/镜像/渲染/端口/分支), 保存并生成 semantic-env.sh
  L              查看选中服务步骤的日志尾部
  x              停止本工具启动的所有后台服务
  g              GitLab 凭证助手 (OAuth 浏览器登录自动取令牌 / 粘贴 PAT / 清除)
  P              清除已缓存的 sudo 密码
  m              标记手动步骤 (7.1) 完成 / 取消
  c              中止当前运行并清空队列
  C              清空日志
  r              重置全部步骤状态
  Tab            焦点在 步骤树 / 日志 间切换
  PgUp/PgDn/Home/End  日志滚动 (End 回到跟随模式)
  q              退出 (询问是否停止后台服务)
  ?              本帮助

[文档要点 / 坑]
  * 不要装: Docker, 系统 apt Python, golangci-lint; unzip/pkg-config 用不上
  * MuJoCo Runtime 的 Python 用 uv 拉 3.10-3.12; Robot Bundle (cp313 Wheel) 要 3.13
  * SQLite 走 Go 纯实现, 不需要系统 sqlite3
  * GitLab 上 Deployment 项目名是 semantic-deployment, 本地目录必须叫
    semantic-robot-deployment (刷新脚本认这个名字); clone semantic-robot-deployment.git 会 404
  * ability-runtime 只有 main 分支, 不用切分支; clone 后要 git lfs pull
  * 运行配置只改 .output 这份; robot_runtime.bundles_dir 指活动 Catalog
    (.output/robot-bundles), 不是 base-bundles
  * 模型 Key 不写 .env, 在 Studio 系统设置里加; .env 不要提交 Git
  * EGL 起不来: 装 libosmesa6, 并在设置里把 SEMANTIC_MUJOCO_GL 改为 osmesa
  * 国内源: 1.0 切 apt 阿里源; Go 走 GO_DL_MIRROR + GOPROXY(goproxy.cn);
    Node 走 npmmirror 二进制; npm registry 用 npmmirror; uv 三策略回退
    (astral.sh -> GITHUB_PROXY 代理 -> pip 国内源); 解释器下载走 UV_PYTHON_INSTALL_MIRROR;
    全部可在 e 设置里置空切回直连, 或换成清华源等
  * sudo 鉴权: 默认 tui 模式, 在 TUI 内弹掩码密码框, 经 sudo -S 从 stdin 鉴权;
    密码仅存本进程内存且一次输入全程复用, P 键随时清除;
    设置 SUDO_AUTH=terminal 可改回“临时退出到真实终端输密码”模式
  * GitLab 凭证: g 键打开助手; OAuth 方式首次会引导注册应用 (展示表单值 → 浏览器创建 →
    粘贴 ID/Secret 自动保存, 团队可共享同一应用), 之后每次登录只需在浏览器点一次“授权”;
    令牌自动写入 git credential store (~/.git-credentials, 0600);
    也可用 PAT 方式 (预填创建页, 粘贴 Token); clone 认证失败会提示按 g
  * 端口: HTTP 8080 / WS 8081 / MuJoCo ~8090 / Ability 18100-18199 / Web 3000
  * 登录: admin + .env 里的 SEMANTIC_ADMIN_PASSWORD
  * 第 4.2 步 runtime install 提示已存在时, 本工具会自动加 --replace 重试
  * sudo 需要密码时自动切换终端模式 (TUI 暂时让位, 输入密码后返回)
"""


class UI:
    def __init__(self, app):
        self.app = app
        self.focus = "tree"
        self.rows = []
        self.sel = 0
        self.log_offset = 0  # 0 = 跟随底部
        self.quit = False
        self.msg = ""
        self.stdscr = None
        self.inp = CursesInput()
        self._win_key = None
        self._form_sid = None
        self._showing_form = False
        app.prompt = self.password_prompt
        app.confirm = self.confirm_ask
        app.workspace_prompt = self.workspace_prompt

    # ---------- 绘制 ----------
    def draw(self, stdscr):
        self.stdscr = stdscr
        if self.app.failed_sid:
            self.sel = next((i for i, (kind, value, _) in enumerate(self._rows())
                             if kind == "step" and value["sid"] == self.app.failed_sid), self.sel)
            self.app.failed_sid = None
        H, W = stdscr.getmaxyx()
        if H < 20 or W < 90:
            stdscr.erase()
            stdscr.addstr(0, 0, "终端太小, 请至少 90x20", curses.A_BOLD)
            stdscr.refresh()
            return
        if getattr(self.app, "full_redraw", False):
            stdscr.clearok(True)
            self.app.full_redraw = False
        self._layout(H, W)
        stdscr.erase()
        # 先画顶栏/底栏并推送 stdscr, 再刷新子窗;
        # 若最后再 stdscr.refresh() 会用空白把子窗整体覆盖
        self._draw_top(H, W)
        self._draw_bottom(H, W)
        stdscr.noutrefresh()
        self._draw_tree()
        self._draw_log()

    def _layout(self, H, W):
        self.tree_rows = H - 4
        lw = max(30, min(46, dwidth(max((s["title"] for s in self.app.steps), key=dwidth)) + 12))
        self.lw = min(lw, W // 2)
        key = (self.tree_rows, self.lw, W)
        if self._win_key != key:
            self._win_key = key
            self.tree_win = curses.newwin(self.tree_rows, self.lw, 1, 0)
            self.log_win = curses.newwin(self.tree_rows, W - self.lw, 1, self.lw)

    def _draw_top(self, H, W):
        s = self.app.settings
        left = " Semantic 安装器 《新版Semantic安装步骤》"
        right = f"{sx(s['SEMANTIC'])}  "
        self.stdscr.addstr(0, 0, trunc(left, W - dwidth(right) - 1), curses.A_BOLD | curses.color_pair(3))
        self.stdscr.addstr(0, max(0, W - dwidth(right) - 1), trunc(right, W - 1), curses.color_pair(0) | curses.A_DIM)

    def _rows(self):
        rows = []
        for num, title in STAGES:
            rows.append(("stage", num, title))
            for s in self.app.stage_steps(num):
                rows.append(("step", s, None))
        return rows

    def _draw_tree(self):
        win = self.tree_win
        win.erase()
        win.box()
        rows = self._rows()
        self.rows = rows
        # 滚动窗口
        first = max(0, min(self.sel - self.tree_rows + 3, len(rows) - self.tree_rows + 2))
        first = max(0, min(first, self.sel))
        y = 1
        for idx in range(first, len(rows)):
            if y >= self.tree_rows - 1:
                break
            kind, a, b = rows[idx]
            if kind == "stage":
                num, title = a, b
                sts = [self.app.status(s["sid"]) for s in self.app.stage_steps(num)]
                done = sum(1 for x in sts if x in DONE_STATES)
                g = "✗" if "fail" in sts else ("▶" if "running" in sts else ("✓" if done == len(sts) else "·"))
                text = f" {num} {title} {done}/{len(sts)} {g}"
                attr = curses.A_BOLD
                if "fail" in sts:
                    attr |= curses.color_pair(2)
                elif done == len(sts):
                    attr |= curses.color_pair(1)
                w = self.lw - 2
                if idx == self.sel and self.focus == "tree":
                    win.addstr(y, 1, trunc(text, w).ljust(w)[:w], attr | curses.A_REVERSE)
                else:
                    win.addstr(y, 1, trunc(text, w), attr)
            else:
                step = a
                st = self.app.status(step["sid"])
                g = GLYPH.get(st, "·")
                cp = GLYPH_COLOR.get(st, 0)
                if cp < 0:
                    attr = curses.A_BOLD
                else:
                    attr = curses.color_pair(cp) if cp else 0
                    if st == "fail":
                        attr |= curses.A_BOLD
                text = f"   {step['sid']} {g} {step['title']}"
                w = self.lw - 2
                if idx == self.sel and self.focus == "tree":
                    win.addstr(y, 1, trunc(text, w).ljust(w)[:w], attr | curses.A_REVERSE)
                else:
                    win.addstr(y, 1, trunc(text, w), attr)
            y += 1
        win.refresh()

    def _log_tail_pairs(self, need):
        """从最新向旧收集 need 行已折行日志 (per-entry 缓存, 只处理尾部, O(可见行));
        全量重排会在日志多时拖慢主循环、卡住左侧按键"""
        color_map = {"cmd": 6, "ok": 1, "err": 2, "warn": 4, "info": 5, "note": 3, "out": 0}
        w = self.log_win.getmaxyx()[1] - 4 if self.log_win else 96
        rows = []
        for entry in reversed(self.app.logbuf):
            if len(rows) >= need:
                break
            kind, text, cache = entry
            if kind == "cmd":
                prefix = now() + " $ "
            elif kind == "out":
                prefix = ""
            else:
                prefix = now() + " "
            prefix_w = dwidth(prefix)
            if cache is None or cache[0] != w or cache[1] != prefix_w:
                cache = (w, prefix_w, wrap_cells(text, max(10, w - prefix_w)))
                entry[2] = cache
            lines = cache[2]
            cp = color_map.get(kind, 0)
            for i in range(len(lines) - 1, -1, -1):
                ln = lines[i]
                rows.append((cp, (prefix + ln) if i == 0 else (" " * prefix_w + ln)))
                if len(rows) >= need:
                    break
        rows.reverse()
        return rows

    def _draw_log(self):
        step = self.app.cur
        if step is None and self.rows:
            kind, selected, _ = self.rows[self.sel]
            if kind == "step":
                step = selected
            else:
                last = self.app.last_step
                step = last if last and last["stage"] == selected else self.app.stage_steps(selected)[0]
        if step and (step["stage"] <= 2 or step["sid"] == "3.1"):
            self._showing_form = True
            self._draw_status_form(step)
            return
        self._showing_form = False
        win = self.log_win
        win.erase()
        win.box()
        WH, WW = win.getmaxyx()
        title = " 日志 "
        if self.focus == "log":
            title = " 日志 (滚动: PgUp/PgDn, End 跟随) "
        win.addstr(0, 2, trunc(title, WW - 4), curses.A_BOLD | curses.color_pair(3))
        avail = WH - 2
        rows = self._log_tail_pairs(avail + self.log_offset + 1)
        total = len(rows)
        start = max(0, total - avail - self.log_offset)
        end = min(total, start + avail)
        y = 1
        for cp, text in rows[start:end]:
            if y >= WH - 1:
                break
            try:
                win.addstr(y, 1, trunc(text, WW - 2), curses.color_pair(cp))
            except curses.error:
                pass
            y += 1
        if self.log_offset > 0:
            pct = int(100 * start / max(1, total))
            win.addstr(WH - 1, 2, f" 向上翻 {self.log_offset} 行 ({pct}%) ", curses.color_pair(3))
        win.refresh()

    def _draw_status_form(self, step):
        win = self.log_win
        win.erase()
        win.box()
        height, width = win.getmaxyx()
        if self._form_sid != step["sid"]:
            self._form_sid = step["sid"]
            self.log_offset = 0
        form = self.app.form_for(step)
        labels = {"pending": "待执行", "running": "进行中", "ok": "已完成", "skip": "已跳过",
                  "fail": "失败", "warn": "需检查", "done": "已完成"}
        title = "拉取清单" if step["stage"] == 2 else "配置与执行状态"
        win.addstr(0, 2, trunc(f" {title} ", width - 4), curses.A_BOLD | curses.color_pair(3))
        status = self.app.status(step["sid"])
        lines = []

        def add(text, color=0):
            for line in wrap_cells(self.app._redact(text), max(10, width - 4)):
                lines.append((color, line))

        add(f"步骤: {step['sid']} {step['title']}", 3)
        add(f"状态: {labels.get(status, status)}", 2 if status == "fail" else 1)
        if form["error"]:
            add("故障: " + form["error"], 2)
        log_path = self.app.log_paths.get(step["sid"])
        if log_path:
            add("日志文件: " + log_path, 3)
        if self.app.log_error:
            add(self.app.log_error, 2)
        for key, value in form["fields"]:
            add(f"{key}: {value}")
        if form["rows"]:
            done = sum(row["status"] in ("ok", "skip") for row in form["rows"])
            add(f"仓库进度: {done}/{len(form['rows'])}", 3)
            for row in form["rows"]:
                state = row["status"]
                add(f"[{labels.get(state, state)}] {row['repo']}  {row['ref'] or '默认版本'}",
                    2 if state == "fail" else 1 if state == "ok" else 0)
                add("  远端: " + row["url"])
        cap = height - 2
        self.log_offset = max(0, min(self.log_offset, max(0, len(lines) - cap)))
        for i, (color, text) in enumerate(lines[self.log_offset:self.log_offset + cap], 1):
            win.addstr(i, 2, trunc(text, width - 4), curses.color_pair(color))
        win.addstr(height - 1, 2, trunc(" Tab 切换焦点 · ↑↓/PgUp/PgDn 翻页 · e 编辑配置 ", width - 4), curses.color_pair(3))
        win.refresh()

    def _draw_bottom(self, H, W):
        app = self.app
        line1 = " Enter:运行 a:全程 A:续行 v:校验 e:设置 g:凭证 L:服务日志 x:停服务 m:手动完成 c:中止 C:清屏 r:重置 P:清sudo密码 Tab:焦点 ?:帮助 q:退出"
        self.stdscr.addstr(H - 2, 0, trunc(line1, W - 1), curses.color_pair(3) | curses.A_DIM)
        if app.cur:
            dur = time.time() - app.cur_start
            stat = f"▶ {app.cur['sid']} {app.cur['title']} … {dur:.0f}s"
            attr = curses.color_pair(4) | curses.A_BOLD
        else:
            alive = sum(1 for s2 in app.services if s2.alive())
            svc = f" | 后台服务: {alive} 个运行中" if alive else ""
            stat = "空闲" + svc
            attr = curses.color_pair(1) if not alive else curses.color_pair(5)
        if self.msg:
            stat = self.msg
            attr = curses.color_pair(4)
        self.stdscr.addstr(H - 1, 0, trunc(" " + stat, W - 1), attr)

    # ---------- 主循环 ----------
    def run(self, stdscr):
        curses.curs_set(0)
        self.inp.restore(stdscr)
        while not self.quit:
            if getattr(self.app, "full_redraw", False):
                self.inp.restore(stdscr)
            if self.app.dirty:
                self.draw(stdscr)
                self.app.dirty = False
            keys = self.inp.read_nav_burst(stdscr)
            self.app.pump()
            if not keys:
                continue
            for ch in keys:
                if self.quit:
                    break
                self.handle_key(ch, stdscr)
            self.app.dirty = True

    def handle_key(self, ch, stdscr):
        app = self.app
        if ch == curses.KEY_RESIZE:
            self.app.full_redraw = True
            return
        if ch in (ord("q"), ord("Q")):
            self.try_quit(stdscr)
            return
        if ch in (ord("?"),):
            self.help_overlay(stdscr)
            return
        if ch in (ord("e"), ord("E")):
            self.settings_form(stdscr)
            return
        if ch == 9:  # Tab
            self.focus = "log" if self.focus == "tree" else "tree"
            return
        if ch in (ord("C"),):
            app.logbuf.clear()
            return
        if ch in (ord("c"),):
            if app.cur or app.queue:
                app.abort()
            else:
                self.msg = "没有正在运行的任务"
            return
        if self.focus == "log":
            self.handle_log_key(ch)
            return
        # 树焦点
        if ch in (curses.KEY_UP, ord("k")):
            self.sel = max(0, self.sel - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.sel = min(len(self.rows) - 1, self.sel + 1)
        elif ch == curses.KEY_ENTER or ch in (10, 13):
            self.activate(stdscr)
        elif ch in (ord("a"),):
            self.msg = "连续执行: 全部"
            app.log("note", "== 连续执行所有阶段 ==")
            for num, _t in STAGES:
                app.enqueue_stage(num, auto=True)
        elif ch in (ord("A"),):
            if not self.rows:
                return
            kind, a, _b = self.rows[self.sel]
            stage = a if kind == "stage" else int(a["sid"].split(".")[0])
            app.log("note", f"== 从阶段 {stage} 连续执行 ==")
            for num, _t in STAGES:
                if num >= stage:
                    app.enqueue_stage(num, auto=True)
        elif ch in (ord("v"),):
            self.verify_only(stdscr)
        elif ch in (ord("m"),):
            kind, a, _b = self.rows[self.sel] if self.rows else (None, None, None)
            if kind == "step" and a["kind"] == "manual":
                cur = app.status(a["sid"])
                app.set_status(a["sid"], "pending" if cur == "done" else "done")
        elif ch in (ord("L"),):
            self.dump_service_log()
        elif ch in (ord("g"), ord("G")):
            self.credential_menu(stdscr)
        elif ch in (ord("P"),):
            if self.app.vars.pop("SUDO_PW", None) is not None:
                self.app.log("note", "已清除缓存的 sudo 密码")
            else:
                self.msg = "没有缓存的 sudo 密码"
        elif ch in (ord("x"),):
            if app.services:
                if self.confirm(stdscr, "停止后台服务", "停止本工具启动的所有后台服务?"):
                    app.stop_all_services()
            else:
                self.msg = "没有已启动的服务"

    def handle_log_key(self, ch):
        WH = self.log_win.getmaxyx()[0] - 2 if hasattr(self, "log_win") else 20
        page = max(1, WH - 2)
        if self._showing_form:
            if ch in (curses.KEY_UP, ord("k")):
                self.log_offset = max(0, self.log_offset - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.log_offset += 1
            elif ch == curses.KEY_PPAGE:
                self.log_offset = max(0, self.log_offset - page)
            elif ch == curses.KEY_NPAGE:
                self.log_offset += page
            elif ch == curses.KEY_HOME:
                self.log_offset = 0
            elif ch in (curses.KEY_END, ord("G"), ord("g")):
                self.log_offset = 999999
            return
        if ch in (curses.KEY_UP, ord("k")):
            self.log_offset += 1
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.log_offset = max(0, self.log_offset - 1)
        elif ch == curses.KEY_PPAGE:
            self.log_offset += page
        elif ch == curses.KEY_NPAGE:
            self.log_offset = max(0, self.log_offset - page)
        elif ch == curses.KEY_HOME:
            self.log_offset = 999999
        elif ch in (curses.KEY_END, ord("G"), ord("g")):
            self.log_offset = 0

    def activate(self, stdscr):
        app = self.app
        if not self.rows or app.cur:
            self.msg = " busy" if app.cur else " 无可运行项"
            return
        kind, a, _b = self.rows[self.sel]
        if kind == "stage":
            missing = app.stage_missing_prereq(a)
            if missing and not self.confirm(
                    stdscr, "前置阶段未完成",
                    "以下前置未完成, 仍要运行?\n  " + "\n  ".join(missing[:4]) + ("\n  ..." if len(missing) > 4 else "")):
                return
            app.log("note", f"== 运行阶段 {a} {STAGES[a - 1][1]} ==")
            app.enqueue_stage(a)
        else:
            step = a
            if step["kind"] in ("manual", "info"):
                app.show_manual(step)
                return
            if step.get("confirm") and not self.confirm(stdscr, "确认执行", step["confirm"]):
                return
            app.log("note", f"== 单步执行 {step['sid']} {step['title']} (强制, 不做 skip 检查) ==")
            app.enqueue_step(step, force=True)

    def verify_only(self, stdscr):
        app = self.app
        if app.cur:
            self.msg = "busy"
            return
        if not self.rows:
            return
        kind, a, _b = self.rows[self.sel]
        steps = app.stage_steps(a) if kind == "stage" else [a]
        app.log("note", "== 仅校验 ==")
        for step in steps:
            vf = step.get("verify")
            if not vf:
                continue
            cmds = vf(app) if callable(vf) else vf
            for c in cmds:
                app.log("cmd", f"[校验:{step['sid']}] {c}")
                r = subprocess.run(["bash", "-c", c], capture_output=True, text=True, env=app.env, timeout=120)
                for ln in (r.stdout + r.stderr).strip().splitlines()[:6]:
                    app.log("out", ln)
                app.log("ok" if r.returncode == 0 else "warn",
                        f"{step['sid']} {'通过' if r.returncode == 0 else '未通过'}: {c[:60]}")

    def dump_service_log(self):
        app = self.app
        if not self.rows:
            return
        kind, a, _b = self.rows[self.sel]
        sid = a if kind == "stage" else a["sid"]
        cands = [s for s in app.services if s.sid == sid] if kind == "step" else app.services
        if not cands:
            self.msg = "该步骤无运行中的服务"
            return
        s = cands[-1]
        app.log("note", f"== [{s.name}] 日志尾部 (完整日志: {s.logpath}) ==")
        for ln in self._tail_n(s.logpath, 60):
            app.log("out", f"[{s.name}] {ln}")

    def _tail_n(self, path, n):
        try:
            with open(path, "r", errors="replace") as f:
                return f.read().splitlines()[-n:]
        except Exception:
            return [f"(无法读取 {path})"]

    def try_quit(self, stdscr):
        alive = [s for s in self.app.services if s.alive()]
        if alive:
            names = ", ".join(s.name for s in alive)
            ans = self.choice(stdscr, "退出", f"仍有后台服务: {names}",
                              [("y", "停止服务并退出"), ("n", "保留服务退出"), (None, "取消")])
            if ans == "y":
                self.app.stop_all_services()
                self.quit = True
            elif ans == "n":
                self.quit = True
            return
        if self.app.cur:
            if not self.confirm(stdscr, "退出", "有任务在运行, 中止并退出?"):
                return
            self.app.abort()
        self.quit = True

    # ---------- 对话框 ----------
    def _modal(self, stdscr, w, h, title):
        H, W = stdscr.getmaxyx()
        x = max(0, (W - w) // 2)
        y = max(0, (H - h) // 2)
        win = curses.newwin(h, w, y, x)
        win.erase()
        win.box()
        win.addstr(0, 2, trunc(f" {title} ", w - 4), curses.A_BOLD | curses.color_pair(3))
        return win, y, x

    def confirm(self, stdscr, title, text):
        lines = []
        for ln in text.splitlines():
            lines.extend(wrap_cells(ln, 56))
        h = min(20, 6 + len(lines))
        win, _y, _x = self._modal(stdscr, 62, h, title)
        for i, ln in enumerate(lines[:h - 4]):
            win.addstr(1 + i, 2, trunc(ln, 58))
        win.addstr(h - 2, 2, " [y] 确认    其他键取消 ", curses.A_BOLD)
        win.refresh()
        self.inp.block(stdscr)
        try:
            ch = self.inp.read_key(stdscr)
        finally:
            self.inp.restore(stdscr)
        return ch in (ord("y"), ord("Y"))

    def choice(self, stdscr, title, text, options):
        lines = wrap_cells(text, 56)
        h = min(20, 7 + len(lines))
        win, _y, _x = self._modal(stdscr, 62, h, title)
        for i, ln in enumerate(lines[:h - 5]):
            win.addstr(1 + i, 2, trunc(ln, 58))
        y = h - 2 - len(options) + 1
        for i, (key, label) in enumerate(options):
            win.addstr(y + i, 2, f" [{key or 'Esc'}] {label}" if key else f" [Esc] {label}")
        win.refresh()
        self.inp.block(stdscr)
        try:
            ch = self.inp.read_key(stdscr)
        finally:
            self.inp.restore(stdscr)
        for key, _label in options:
            if key and ch == ord(key):
                return key
        return None

    def input_dialog(self, stdscr, title, prompt, initial="", mask=False):
        win, _y, _x = self._modal(stdscr, 64, 8, title)
        win.addstr(1, 2, trunc(prompt, 60))
        buf = list(initial)
        self.inp.block(stdscr)
        curses.curs_set(1)
        try:
            while True:
                win.addstr(3, 2, " " * 60)
                full = "".join(buf)[-56:]
                shown = "*" * len(full) if mask else full
                win.addstr(3, 2, trunc(shown, 60), curses.A_REVERSE)
                win.addstr(6, 2, " Enter 保存    Esc 取消 ", curses.A_DIM)
                win.refresh()
                ch = self.inp.read_key(stdscr)
                if ch is None:
                    continue
                if ch == 27:
                    return None
                if ch in (10, 13, curses.KEY_ENTER):
                    return "".join(buf)
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    if buf:
                        buf.pop()
                elif ch == curses.KEY_LEFT:
                    pass
                elif isinstance(ch, int) and ch >= 32 and not (
                        curses.KEY_MIN <= ch <= curses.KEY_MAX):
                    char = chr(ch)
                    if char.isprintable():
                        buf.append(char)
        finally:
            curses.curs_set(0)
            self.inp.restore(stdscr)

    def password_prompt(self):
        """App 回调: 请求 sudo 密码 (掩码输入, 仅存内存)"""
        if self.stdscr is None:
            return None
        user = os.environ.get("USER", "")
        pw = self.input_dialog(
            self.stdscr, "sudo 鉴权",
            f"输入用户 {user} 的 sudo 密码 (掩码输入, 仅内存保存, P 键清除)",
            initial="", mask=True)
        self.app.dirty = True
        return pw

    def confirm_ask(self, title, text):
        """App 回调: 通用确认框"""
        if self.stdscr is None:
            return False
        r = self.confirm(self.stdscr, title, text)
        self.app.dirty = True
        return r

    def workspace_prompt(self, initial, error=""):
        """Use the script's repository as the initial clone/build directory."""
        if self.stdscr is None:
            return None
        chosen = self.input_dialog(
            self.stdscr, "选择拉取和构建目录",
            error or "当前仓库目录? Enter 保留, 或填写其他绝对路径:",
            initial=initial)
        self.app.dirty = True
        return chosen

    # ---------- GitLab 凭证助手 ----------
    def credential_menu(self, stdscr):
        app = self.app
        s = app.settings
        oauth_ready = bool(s.get("GITLAB_OAUTH_CLIENT_ID", "").strip()
                           and s.get("GITLAB_OAUTH_CLIENT_SECRET", "").strip())
        hint = "OAuth: " + ("已配置, 自动登录" if oauth_ready else "首次会引导注册应用并自动保存")
        ans = self.choice(stdscr, "GitLab 凭证助手", f"目标: {s['GITLAB']}\n{hint}", [
            ("o", "OAuth 登录: 打开浏览器 → 登录 → 自动获取令牌"),
            ("p", "PAT: 预填创建页 → 点“复制”自动读取" if clip_available()
             else "PAT: 预填创建页 → 手动粘贴 Token"),
            ("c", "清除已保存的 GitLab 凭证"),
        ])
        app.dirty = True
        if ans == "o":
            self.oauth_login()
            app.maybe_retry_auth_failed()
        elif ans == "p":
            self.pat_login()
            app.maybe_retry_auth_failed()
        elif ans == "c":
            _clear_git_credential(app, s["GITLAB"])

    def _oauth_register_assist(self, root, redirect):
        """一次性注册引导: 展示表单值 → 打开应用页 → 就地粘贴 ID/Secret → 保存并继续授权"""
        app, s = self.app, self.app.settings
        appspath = pick_page_path(app, root, APPS_PAGE_PATHS, "APPS_PAGE_PATH")
        if self.stdscr is None:
            app.log("warn", "无头模式无法交互注册 OAuth 应用; 手动创建:")
            app.log("info", f"  {root}{appspath}")
            app.log("info", f"  Redirect URI: {redirect}; Scopes: read_user/read_repository/write_repository")
            app.log("info", "  把 ID/Secret 写入 installer-settings.json 后重试")
            open_browser(app, root + appspath)
            return None, None
        self.message_box("首次使用: 注册 OAuth 应用 (仅需一次, 团队可共享)", [
            "浏览器即将打开 GitLab 应用页, 按下面数值填写:",
            "",
            f"  Name:        semantic-installer",
            f"  Redirect URI: {redirect}",
            "  Scopes:      勾选 read_user / read_repository / write_repository",
            "",
            "创建后把 Application ID 和 Secret 粘贴回这里,",
            "之后登录只需在浏览器点一次“授权”。",
        ])
        open_browser(app, root + appspath)
        cid = self.input_dialog(self.stdscr, "粘贴 Application ID",
                                "GitLab 应用创建完成后显示的 Application ID:")
        if not cid or not cid.strip():
            app.log("note", "已取消 OAuth 应用注册")
            return None, None
        sec = self.input_dialog(self.stdscr, "粘贴 Secret",
                                "应用的 Secret (只显示一次, 掩码输入):", mask=True)
        if not sec or not sec.strip():
            app.log("note", "已取消 OAuth 应用注册")
            return None, None
        cid, sec = cid.strip(), sec.strip()
        s["GITLAB_OAUTH_CLIENT_ID"] = cid
        s["GITLAB_OAUTH_CLIENT_SECRET"] = sec
        save_json(SETTINGS_FILE, s)
        write_env_sh(s)
        app.log("ok", "OAuth 应用已保存到设置; 应用非个人专属, 团队可共用同一组 ID/Secret")
        self.app.dirty = True
        return cid, sec

    def message_box(self, title, lines):
        if self.stdscr is None:
            return
        wrapped = []
        for ln in lines:
            wrapped.extend(wrap_cells(ln, 56) or [""])
        H, W = self.stdscr.getmaxyx()
        h = min(H - 4, 7 + len(wrapped))
        win, _y, _x = self._modal(self.stdscr, 62, max(8, h), title)
        for i, ln in enumerate(wrapped[:h - 4]):
            win.addstr(1 + i, 2, trunc(ln, 58))
        win.addstr(max(3, h - 2), 2, " 按任意键继续 ", curses.A_DIM)
        win.refresh()
        self.inp.block(self.stdscr)
        try:
            self.inp.read_key(self.stdscr)
        finally:
            self.inp.restore(self.stdscr)

    def oauth_login(self):
        import urllib.parse as _up
        app, s = self.app, self.app.settings
        cid = s.get("GITLAB_OAUTH_CLIENT_ID", "").strip()
        sec = s.get("GITLAB_OAUTH_CLIENT_SECRET", "").strip()
        try:
            port = int(s.get("OAUTH_CALLBACK_PORT", "8377"))
        except ValueError:
            port = 8377
        redirect = f"http://127.0.0.1:{port}/callback"
        root = gitlab_root(s["GITLAB"])
        if not (cid and sec):
            cid, sec = self._oauth_register_assist(root, redirect)
            if not (cid and sec):
                return
        try:
            srv, result, state = _oauth_callback_server(app, port, None)
        except OSError as e:
            app.log("err", f"本地回调端口 {port} 无法监听: {e}; "
                        "请换 OAUTH_CALLBACK_PORT 并同步修改应用 Redirect URI")
            return
        url = (root + "/oauth/authorize?client_id=" + _up.quote(cid)
               + "&redirect_uri=" + _up.quote(redirect, safe="")
               + "&response_type=code"
               + "&scope=" + _up.quote("read_user read_repository write_repository")
               + "&state=" + state)
        open_browser(app, url)
        code, deadline = None, time.time() + 300
        if self.stdscr is None:
            try:
                kind, val = result.get(timeout=300)
                if kind == "code":
                    code = val
                else:
                    app.log("err", f"OAuth 回调错误: {val}")
            except Exception:
                pass
        else:
            self.stdscr.timeout(250)
            try:
                while time.time() < deadline:
                    try:
                        kind, val = result.get_nowait()
                    except Exception:
                        kind = None
                    if kind == "code":
                        code = val
                        break
                    if kind == "error":
                        app.log("err", f"OAuth 回调错误: {val}")
                        break
                    self._draw_wait(f" 等待 GitLab 登录回调 ({int(deadline - time.time())}s 超时, Esc 取消) "
                                    f"若浏览器未开请手动访问日志中的 URL")
                    if self.stdscr.getch() == 27:
                        app.log("note", "已取消 OAuth 登录")
                        break
            finally:
                self.inp.restore(self.stdscr)
                srv.shutdown()
                app.dirty = True
        if not code:
            return
        token = _oauth_token(app, root, cid, sec, code, redirect)
        if token:
            user = s.get("GITLAB_USER", "oauth2").strip() or "oauth2"
            _git_store_credential(app, s["GITLAB"], user, token)

    def pat_login(self):
        app, s = self.app, self.app.settings
        root = gitlab_root(s["GITLAB"])
        path = pick_page_path(app, root, PAT_PAGE_PATHS, "PAT_PAGE_PATH")
        url = (root + path
               + "?name=semantic-installer"
               + "&scopes=read_repository,write_repository")
        open_browser(app, url)
        others = [p for p in PAT_PAGE_PATHS + [""] if p and p != path]
        for alt in others:
            app.log("note", "若浏览器 404, 手动打开备用: " + root + alt
                    + "?name=semantic-installer&scopes=read_repository,write_repository")
        app.log("note", f"仍 404 则打开无参数页面手动填写: {root + path}")
        app.log("info", "名称与 scopes 已尽量预填 (老版本 GitLab 可能需要手动勾选); "
                        "过期时间自选; 创建后点页面上的“复制”按钮即可")
        if self.stdscr is None:
            return
        token = None
        if clip_available():
            token = self._wait_clipboard_pat()
            if token:
                app.log("ok", f"已从剪贴板自动读取 Token ({token[:11]}…)")
        else:
            app.log("note", "未找到剪贴板工具 (wl-paste/xclip/xsel), "
                            "安装后可全自动读取; 现在退回手动粘贴")
        if token == "CANCEL":
            app.log("note", "已取消 PAT 流程")
            return
        if not token:
            token = self.input_dialog(self.stdscr, "粘贴 PAT",
                                      "复制 Token 后粘贴到这里:")
            if not token or not token.strip():
                app.log("note", "已取消 PAT 输入")
                return
            token = token.strip()
        user = self.input_dialog(self.stdscr, "凭证用户名",
                                 "HTTPS 凭证用户名 (PAT 一般用 oauth2 即可)",
                                 initial=s.get("GITLAB_USER", "oauth2"))
        user = (user or "oauth2").strip() or "oauth2"
        _git_store_credential(app, s["GITLAB"], user, token)

    def _wait_clipboard_pat(self):
        """轮询剪贴板等 Token; 返回 token / None(手动粘贴) / 'CANCEL'"""
        app = self.app
        baseline = read_clipboard() or ""
        deadline = time.time() + 300
        self.stdscr.timeout(250)
        try:
            while time.time() < deadline:
                cand = _pat_from_clipboard(baseline)
                if cand:
                    return cand
                self._draw_wait(f" 等待剪贴板出现 Token (创建后点“复制”即自动读取; "
                                f"Enter 手动粘贴, Esc 取消) {int(deadline - time.time())}s")
                ch = self.stdscr.getch()
                if ch == 27:
                    return "CANCEL"
                if ch in (10, 13):
                    return None
        finally:
            self.inp.restore(self.stdscr)
            app.dirty = True
        return None

    def _draw_wait(self, text):
        s = self.stdscr
        try:
            H, W = s.getmaxyx()
            s.addstr(H - 1, 0, " " * (W - 1))
            s.addstr(H - 1, 0, trunc(text, W - 1), curses.color_pair(4) | curses.A_BOLD)
            s.refresh()
        except curses.error:
            pass

    def help_overlay(self, stdscr):
        H, W = stdscr.getmaxyx()
        h, w = min(H - 2, 40), min(W - 2, 78)
        win = curses.newwin(h, w, 1, 1)
        lines = []
        for ln in HELP_TEXT.splitlines():
            lines.extend(wrap_cells(ln, w - 4) or [""])
        top = 0
        self.inp.block(stdscr)
        try:
            while True:
                win.erase()
                win.box()
                win.addstr(0, 2, " 帮助 (↑↓ 滚动, q 关闭) ", curses.A_BOLD | curses.color_pair(3))
                for i in range(min(h - 2, len(lines) - top)):
                    try:
                        win.addstr(1 + i, 2, trunc(lines[top + i], w - 3))
                    except curses.error:
                        pass
                win.refresh()
                for ch in self.inp.read_nav_burst(stdscr):
                    if ch in (27, ord("q"), ord("Q")):
                        return
                    if ch == curses.KEY_UP:
                        top = max(0, top - 1)
                    elif ch == curses.KEY_DOWN:
                        top = min(max(0, len(lines) - h + 2), top + 1)
        finally:
            self.inp.restore(stdscr)

    def settings_form(self, stdscr):
        app = self.app
        keys = [k for _g, ks in SETTINGS_GROUPS for k in ks]
        rows = []
        for gname, ks in SETTINGS_GROUPS:
            rows.append(("group", gname, ""))
            for k in ks:
                rows.append(("key", k, app.settings.get(k, "")))
        sel = 0
        top = 0
        self.inp.block(stdscr)
        try:
            while True:
                H, W = stdscr.getmaxyx()
                h, w = H - 4, min(W - 4, 76)
                win = curses.newwin(h, w, 2, 2)
                win.erase()
                win.box()
                win.addstr(0, 2, " 环境变量设置 (Enter 编辑, s 保存并生成 semantic-env.sh, Esc 返回) ",
                           curses.A_BOLD | curses.color_pair(3))
                avail = h - 3
                top = max(0, min(top, len(rows) - avail))
                top = min(top, sel)
                y = 1
                for idx in range(top, len(rows)):
                    if y >= h - 2:
                        break
                    kind, k, v = rows[idx]
                    if kind == "group":
                        win.addstr(y, 2, f"— {k} —", curses.A_BOLD | curses.color_pair(5))
                    else:
                        kw = 30
                        vtext = trunc(v, w - kw - 6)
                        line = f" {k:<{kw}} {vtext}"
                        attr = curses.A_REVERSE if idx == sel else 0
                        win.addstr(y, 2, trunc(line, w - 3), attr)
                    y += 1
                win.addstr(h - 2, 2, trunc(f" 保存于 {SETTINGS_FILE}", w - 4), curses.A_DIM)
                win.refresh()
                done = False
                for ch in self.inp.read_nav_burst(stdscr):
                    if ch == 27:
                        save_json(SETTINGS_FILE, app.settings)
                        write_env_sh(app.settings)
                        app.log("ok", f"设置已保存: {SETTINGS_FILE}; 并生成 {ENV_SH}")
                        done = True
                        break
                    if ch in (curses.KEY_UP, ord("k")):
                        sel = max(0, sel - 1)
                    elif ch in (curses.KEY_DOWN, ord("j")):
                        sel = min(len(rows) - 1, sel + 1)
                    elif ch in (curses.KEY_PPAGE,):
                        sel = max(0, sel - 10)
                    elif ch in (curses.KEY_NPAGE,):
                        sel = min(len(rows) - 1, sel + 10)
                    elif ch in (ord("s"), ord("S")):
                        save_json(SETTINGS_FILE, app.settings)
                        write_env_sh(app.settings)
                        app.log("ok", f"设置已保存: {SETTINGS_FILE}; 并生成 {ENV_SH}")
                    elif ch in (10, 13, curses.KEY_ENTER):
                        kind, k, v = rows[sel]
                        if kind == "key":
                            nv = self.input_dialog(stdscr, f"编辑 {k}", SETTINGS_DESC.get(k, ""), v)
                            self.inp.block(stdscr)
                            if nv is not None:
                                app.settings[k] = nv.strip()
                                app.forms.clear()
                                rows[sel] = ("key", k, nv.strip())
                if done:
                    return
        finally:
            self.inp.restore(stdscr)



# 入口


def init_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = 0
    curses.init_pair(1, curses.COLOR_GREEN, bg)
    curses.init_pair(2, curses.COLOR_RED, bg)
    curses.init_pair(3, curses.COLOR_CYAN, bg)
    curses.init_pair(4, curses.COLOR_YELLOW, bg)
    curses.init_pair(5, curses.COLOR_MAGENTA, bg)
    curses.init_pair(6, curses.COLOR_BLUE, bg)


def run_tui(app):
    locale.setlocale(locale.LC_ALL, "")
    ui = UI(app)
    app.log("info", f"设置文件: {SETTINGS_FILE} (e 键修改环境变量)")
    app.log("info", f"步骤状态文件: {STATUS_FILE}; source 用环境脚本: {ENV_SH}")
    app.log("note", "流程来自《新版Semantic安装步骤》: 1 系统依赖 → 2 拉代码 → 3 构建 Server → "
                    "4 登记 Runtime → 5 Robot 执行栈 → 6 启动 → 7 Studio 手动 → 8 日常再开")
    app.log("note", "sudo 步骤默认在 TUI 内弹掩码密码框 (sudo -S, 一次输入全程复用, P 键清除); "
                    "SUDO_AUTH=terminal 可改回终端模式")

    os.environ.setdefault("ESCDELAY", str(ESC_GATHER_MS))
    prepare_terminal()

    # 进入 curses 前保存 tty 原始模式; 退出时无条件写回, 不依赖 ncurses 内部状态
    try:
        saved_termios = termios.tcgetattr(sys.__stdin__.fileno())
    except Exception:
        saved_termios = None

    # SIGTERM/SIGHUP 默认直接终止进程 (finally 不会执行), 转成异常保证终端被恢复
    def _bail(signum, _frame):
        raise SystemExit(128 + signum)

    for _sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(_sig, _bail)

    stdscr = curses.initscr()
    ok = False
    try:
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        try:
            curses.set_escdelay(ESC_GATHER_MS)
        except Exception:
            pass
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        init_colors()
        ui.run(stdscr)
        ok = True
    finally:
        # 恢复顺序须与 curses.wrapper 一致: 先退出输入模式, 最后 endwin。
        # 若先 endwin, 其后的 nocbreak/keypad 会把 termios 的 ECHO 位重新写回关闭状态,
        # 退出后终端无回显 (实测复现)。
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        try:
            stdscr.keypad(False)
        except curses.error:
            pass
        for fn in (curses.nocbreak, curses.echo, curses.endwin):
            try:
                fn()
            except curses.error:
                pass
        if saved_termios is not None:
            try:
                termios.tcsetattr(sys.__stdin__.fileno(), termios.TCSADRAIN, saved_termios)
            except Exception:
                pass
        if not ok:
            print("TUI 异常退出; 若终端显示错乱请执行 reset", file=sys.stderr)


def main(argv):
    ap = argparse.ArgumentParser(description="Semantic 安装器 TUI (《新版Semantic安装步骤》)")
    ap.add_argument("--list", action="store_true", help="列出全部阶段与步骤")
    ap.add_argument("--run-all", action="store_true", help="无头模式: 顺序执行全部")
    ap.add_argument("--stage", type=int, action="append", help="无头模式: 执行指定阶段 (可多次)")
    ap.add_argument("--reset-status", action="store_true", help="清空步骤状态")
    args = ap.parse_args()

    if args.reset_status:
        save_json(STATUS_FILE, {})
        print("步骤状态已清空")
        return 0

    stored = load_json(SETTINGS_FILE, {})
    settings = dict(DEFAULT_SETTINGS)
    settings.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
    save_json(SETTINGS_FILE, settings)
    write_env_sh(settings)

    if args.list:
        print(f"{'步骤':<6}{'状态':<9}标题")
        for num, title in STAGES:
            print(f"阶段 {num}  {title}")
            for s in build_steps():
                if s["stage"] == num:
                    print(f"  {s['sid']:<6}{GLYPH.get('pending'):<7}{s['title']}")
        return 0

    app = App(settings, headless=bool(args.run_all or args.stage))

    if args.run_all or args.stage:
        sids = []
        wanted = args.stage or [n for n, _t in STAGES]
        for n in wanted:
            for s in app.stage_steps(n):
                sids.append(s["sid"])
        app.log("note", "无头模式开始 (手动步骤只打印说明)")
        app.run_queue_sync(sids)
        alive = [s for s in app.services if s.alive()]
        for s in alive:
            print(f"[服务] {s.name} 运行中 (pid {s.proc.pid}), 日志: {s.logpath}")
        return 0

    run_tui(app)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
