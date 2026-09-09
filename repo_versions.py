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
Semantic 子仓库版本清单 TUI (repo-versions)

- 展示 semantic 工程全部子仓库清单: 配置 ref(清单) / 当前 ref(工作区实际) / 漂移标记
- 每个仓库可输入或从远端分支/Tag 列表选择确定的 branch / tag
- 保存为 repo-versions.json 持久化, 下次启动自动加载
- c/C 一键把工作区各仓库 checkout 到清单 ref (支持中间版本本地测试)
- a 记录(采纳)当前各仓库 HEAD 为清单 (稳定后随 quick-start 提交/打 tag 即版本锁定)
- semantic_installer.py 的 2.2 步骤优先读取本清单构建, 不再依赖硬编码分支

用法:
    python3 repo_versions.py [--config repo-versions.json] [--semantic $SEMANTIC]
    python3 repo_versions.py --freeze v0.5.0 [--semantic $SEMANTIC]   # 生成发布快照
"""

import argparse
import curses
import json
import os
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from repo_profiles import effective_manifest, load_profile
from terminal_compat import prepare_terminal

# 与 semantic_installer.REPOS 保持一致: (本地目录, 默认分支; None=main 不切)
REPOS = [
    ("semantic-framework", "feature/robot-ability-binding"),
    ("semantic-web", "feature/v050-device-workbench"),
    ("semantic-docs", "feature/v050-robot-runtime-docs"),
    ("semantic-ability/r1pro-ability", "feature/r1pro-seven-abilities"),
    ("semantic-robotsdk/robot-sdk", "feature/v040-robot-sdk-core"),
    ("semantic-skill/robot-skill", "feature/robot-skill-skeleton"),
    ("semantic-simulation/mujoco-runtime", "feature/v060-r1pro-tote-gripper-runtime"),
    ("semantic-scene/mujoco-asset", "feature/v060-r1pro-tote-gripper-assets"),
    ("semantic-robot-deployment", "feature/v050-r1pro-runtime-bundle"),
    ("semantic-ability/ability-runtime", None),
    ("ability-framework/abilityframework", "v2.1.0"),
    ("ability-framework/ability-py-sdk", "v0.4.0"),
    ("ability-framework/ability-scaffold", "v1.2.0"),
]

MARK = {"ok": "✓", "drift": "≠", "missing": "?", "unset": "·"}


def sx(p):
    return os.path.expandvars(os.path.expanduser(p or ""))


def run(cmd, cwd=None, timeout=60, env=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def load_manifest(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return {"version": 1, "updated": "", "repos": {}}
    repos = d.get("repos") if isinstance(d, dict) else None
    if not isinstance(repos, dict):
        raise ValueError("manifest 的 repos 必须是对象")
    for local, entry in repos.items():
        if not local or Path(local).is_absolute() or ".." in Path(local).parts or local == ".":
            raise ValueError(f"非法仓库相对目录: {local}")
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key, ""), str) for key in ("url", "ref", "commit")
        ):
            raise ValueError(f"{local}: 仓库配置必须是对象, url/ref/commit 必须是字符串")
    return d


def repo_names(data):
    """有清单时以清单为准; 兼容尚未创建清单的旧工作区。"""
    return list(data["repos"]) if data["repos"] else [local for local, _ in REPOS]


def freeze_release(base, data, name, outdir="releases"):
    """把工作区各仓库当前 HEAD 固化为 commit 级发布快照 (可复现构建的事实来源)"""
    rel = {"version": 1, "release": name, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "repos": {}}
    for local in repo_names(data):
        kind, ref, commit = current_ref(repo_dir(base, local))
        if kind == "missing":
            continue
        rel["repos"][local] = {**data["repos"].get(local, {}),
                               "ref": ref, "kind": kind, "commit": commit}
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2)
    return path, len(rel["repos"])


def save_manifest(path, data):
    data["version"] = 1
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data["updated"]


def repo_dir(base, local):
    return os.path.join(base, local)


def remote_url(path, entry=None):
    """清单 URL 优先; 旧清单回退本地 origin (含 worktree/submodule)。"""
    url = (entry or {}).get("url", "").strip()
    if url:
        return sx(url)
    if not os.path.exists(os.path.join(path, ".git")):
        return ""
    rc, out = run(["git", "-C", path, "remote", "get-url", "origin"])
    return out.splitlines()[0] if rc == 0 and out else ""


def remote_short(path, entry=None):
    """清单或本地 origin 的短地址; 无需克隆。"""
    url = remote_url(path, entry)
    if not url:
        return "-"
    for pfx in ("https://", "http://", "ssh://git@"):
        if url.startswith(pfx):
            url = url[len(pfx):]
            break
    url = url.split("@")[-1]
    url = url.split("/", 1)[1] if "/" in url else url
    url = url.removesuffix(".git")
    if url.startswith("kernel/"):
        url = url[len("kernel/"):]
    if len(url) > 32:
        url = url[:31] + "…"
    if os.path.exists(os.path.join(path, ".git")):
        rc2, _u = run(["git", "-C", path, "remote", "get-url", "upstream"])
        if rc2 == 0:
            url += " ↑"
    return url


def current_ref(path):
    """返回 (类型, ref, commit8); 目录不存在 -> (missing, '', '')"""
    if not os.path.exists(os.path.join(path, ".git")):
        return ("missing", "", "")
    rc, out = run(["git", "-C", path, "symbolic-ref", "--quiet", "--short", "HEAD"])
    if rc == 0 and out:
        rc2, c = run(["git", "-C", path, "rev-parse", "--short", "HEAD"])
        return ("branch", out, c[:8])
    rc, out = run(["git", "-C", path, "describe", "--tags", "--exact-match"])
    if rc == 0 and out:
        rc2, c = run(["git", "-C", path, "rev-parse", "--short", "HEAD"])
        return ("tag", out.splitlines()[-1], c[:8])
    rc, c = run(["git", "-C", path, "rev-parse", "--short", "HEAD"])
    return ("commit", c[:8], c[:8])


def remote_refs(path, entry=None):
    """直接查询 URL, 返回 ([(kind, name)], 错误); 空仓库与连接失败分开。"""
    url = remote_url(path, entry)
    if not url:
        return [], "未配置 url, 且本地仓库没有可用的 origin"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    # 已配置 SSH 命令时保留用户设置; 默认禁止在 curses 中弹出认证提示。
    if not env.get("GIT_SSH_COMMAND") and not env.get("GIT_SSH"):
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes"
    cmd = ["git"]
    if os.path.exists(os.path.join(path, ".git")):
        cmd += ["-C", path]
    rc, out = run(cmd + ["ls-remote", "--heads", "--tags", "--", url], timeout=20, env=env)
    if rc != 0:
        return [], out or f"git ls-remote 失败 (退出码 {rc})"
    seen, refs = set(), []
    for ln in out.splitlines():
        parts = ln.split("\t")
        if len(parts) != 2:
            continue
        ref = parts[1]
        if ref.endswith("^{}"):
            continue
        if ref.startswith("refs/heads/"):
            k, n = "branch", ref[len("refs/heads/"):]
        elif ref.startswith("refs/tags/"):
            k, n = "tag", ref[len("refs/tags/"):]
        else:
            continue
        if (k, n) not in seen:
            seen.add((k, n))
            refs.append((k, n))
    refs.sort(key=lambda x: (x[0], x[1]))
    return refs, ""


def checkout(path, ref):
    rc1, o1 = run(["git", "-C", path, "fetch", "origin", "--tags", "--prune"], timeout=300)
    if rc1 != 0:
        return False, o1[:400]
    rc2, o2 = run(["git", "-C", path, "checkout", "-q", ref], timeout=120)
    if rc2 != 0:
        rc2b, o2b = run(["git", "-C", path, "switch", "-C", ref, "--track", f"origin/{ref}"], timeout=120)
        if rc2b != 0:
            return False, (o1 + "\n" + o2 + "\n" + o2b).strip()[:400]
        o2 = o2b
    rc3, c = run(["git", "-C", path, "rev-parse", "--short", "HEAD"])
    return True, c[:8]


def adopt_all(base, data):
    n = 0
    for local in repo_names(data):
        kind, ref, commit = current_ref(repo_dir(base, local))
        if kind in ("branch", "tag") and ref:
            data["repos"].setdefault(local, {}).update(ref=ref, commit=commit)
            n += 1
        elif kind == "commit":
            data["repos"].setdefault(local, {}).update(ref=commit, commit=commit)
            n += 1
    return n


# ---------------- TUI ----------------

def norm_key(ch):
    if isinstance(ch, str) and len(ch) == 1:
        return ord(ch)
    return ch


def clip_cells(text, width):
    """按终端列宽截断, 避免中文或长远端地址覆盖边框。"""
    result = []
    for ch in text:
        size = 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in "WF" else 1)
        if size > width:
            break
        result.append(ch)
        width -= size
    return "".join(result)


class TUI:
    def __init__(self, cfg_path, base, profile=None):
        self.cfg_path = cfg_path
        self.base = base
        self.profile = profile
        self.data = load_manifest(cfg_path)
        self.sel = 0
        self.logs = []
        self.quit = False
        self.focus = "table"
        self.log_offset = 0
        self.dirty = True
        self.states = {}
        self.remotes = {}
        self.repo_names = repo_names(self.effective_data())
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.pending = {}
        self.discovered = {}

    def effective_data(self):
        return effective_manifest(self.data, self.profile)

    def entry(self, local):
        return self.effective_data()["repos"].get(local, {})

    def log(self, msg):
        self.logs.append((time.strftime("%H:%M:%S"), msg))
        self.logs = self.logs[-500:]
        self.dirty = True

    def refresh_states(self):
        self.repo_names = repo_names(self.effective_data())
        self.sel = min(self.sel, len(self.repo_names) - 1)
        for local in self.repo_names:
            d = repo_dir(self.base, local)
            self.states[local] = current_ref(d)
            self.remotes[local] = remote_short(d, self.entry(local))
        self.dirty = True

    def discover_remotes(self):
        for future in self.pending.values():
            future.cancel()
        self.discovered.clear()
        self.pending = {
            local: self.executor.submit(remote_refs, repo_dir(self.base, local),
                                        dict(self.entry(local)))
            for local in self.repo_names
        }
        self.log(f"正在从服务器发现 {len(self.pending)} 个清单仓库的分支/Tag…")

    def poll_remotes(self):
        for local, future in list(self.pending.items()):
            if not future.done():
                continue
            try:
                refs, error = future.result()
            except Exception as e:
                refs, error = [], str(e)
            self.discovered[local] = (refs, error)
            del self.pending[local]
            if error:
                self.log(f"[{local}] 远端查询失败: {error}")
            else:
                branches = sum(k == "branch" for k, _ in refs)
                self.log(f"[{local}] 已发现 {branches} 个分支 / {len(refs) - branches} 个 Tag")

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

    def row_status(self, local):
        conf = self.data["repos"].get(local, {}).get("ref", "")
        kind, cur, _c = self.states.get(local, ("missing", "", ""))
        if not conf:
            return "unset"
        if kind == "missing":
            return "missing"
        return "ok" if conf == cur else "drift"

    # ---- 绘制 ----
    def draw(self, stdscr):
        H, W = stdscr.getmaxyx()
        if H < 16 or W < 100:
            stdscr.erase()
            stdscr.addstr(0, 0, "终端太小, 请至少 100x16", curses.A_BOLD)
            stdscr.refresh()
            return
        stdscr.erase()
        source = self.profile.name if self.profile else "manifest"
        head = f" 子仓库版本清单 [{source}]  工作区: {self.base}  配置: {self.cfg_path}"
        stdscr.addstr(0, 0, clip_cells(head, W - 1), curses.A_BOLD | curses.color_pair(3))
        # 顶栏/底栏先写入 stdscr 并 noutrefresh, 再刷新子窗;
        # 若末尾再 stdscr.refresh() 会用空白把两个子窗整体盖掉 (只剩上下两栏)
        keys = " Enter:改ref p:远端选择 c:同步选中 C:同步全部 a:采纳当前 s:保存 r:重载 ?:帮助 q:退出"
        stdscr.addstr(H - 1, 0, clip_cells(keys, W - 1), curses.color_pair(3) | curses.A_DIM)
        stdscr.noutrefresh()
        th = max(6, min(H - 7, len(self.repo_names) + 4))  # 为日志保留可见行
        # 表格窗
        tw = curses.newwin(th, W, 1, 0)
        tw.box()
        tw.addstr(0, 2, " 仓库 (↑↓ 选择, Enter 输入, p 远端列表, c 同步, a 采纳当前, s 保存) ",
                  curses.A_BOLD | curses.color_pair(3))
        cols = f" {'':2} {'仓库':<36} {'远端':<32} {'清单 ref':<28} {'工作区当前'}"
        tw.addstr(1, 1, clip_cells(cols, W - 4), curses.A_BOLD)
        first = max(0, min(self.sel - th + 4, len(self.repo_names) - th + 3))
        first = max(0, min(first, self.sel))
        y = 2
        for i in range(first, len(self.repo_names)):
            if y >= th - 1:
                break
            local = self.repo_names[i]
            st = self.row_status(local)
            conf = self.data["repos"].get(local, {}).get("ref", "") or "-"
            kind, cur, commit = self.states.get(local, ("missing", "", ""))
            cur_txt = {"branch": f"{cur}", "tag": f"{cur} (tag)",
                       "commit": f"{cur} (detached)", "missing": "目录缺失"}[kind] if kind != "missing" else "目录缺失"
            if commit and kind in ("branch", "tag"):
                cur_txt += f" @{commit}"
            mark = MARK[st]
            rem = self.remotes.get(local, "-")
            line = f" {mark:<2} {local:<38} {rem:<34} {conf:<30} {cur_txt}"
            attr = {"ok": curses.color_pair(1), "drift": curses.color_pair(4),
                    "missing": curses.color_pair(2), "unset": 0}[st]
            if i == self.sel:
                attr |= curses.A_REVERSE
            tw.addstr(y, 1, clip_cells(line, W - 3), attr)
            y += 1
        tw.refresh()
        # 日志窗
        lw = curses.newwin(H - th - 2, W, th + 1, 0)
        LW, LWW = lw.getmaxyx()
        lw.box()
        lw.addstr(0, 2, " 操作日志 ", curses.A_BOLD | curses.color_pair(3))
        shown = []
        for ts, msg in self.logs[-60:]:
            for seg in str(msg).splitlines()[:6]:
                shown.append(f"{ts} {seg}")
        start = max(0, len(shown) - (LW - 2) - self.log_offset)
        for i, ln in enumerate(shown[start:start + LW - 2]):
            lw.addstr(1 + i, 1, clip_cells(ln, LWW - 2))
        lw.refresh()

    # ---- 对话框 ----
    def modal(self, stdscr, w, h, title):
        H, W = stdscr.getmaxyx()
        x, y = max(0, (W - w) // 2), max(0, (H - h) // 2)
        win = curses.newwin(h, w, y, x)
        win.erase()
        win.box()
        win.addstr(0, 2, clip_cells(f" {title} ", w - 4), curses.A_BOLD | curses.color_pair(3))
        return win

    def input_dlg(self, stdscr, title, prompt, initial=""):
        win = self.modal(stdscr, 70, 7, title)
        win.addstr(1, 2, prompt[:66])
        buf = list(initial)
        stdscr.timeout(-1)
        curses.curs_set(1)
        try:
            while True:
                win.addstr(3, 2, " " * 66)
                win.addstr(3, 2, "".join(buf)[-62:], curses.A_REVERSE)
                win.addstr(5, 2, " Enter 保存    Esc 取消 ", curses.A_DIM)
                win.refresh()
                ch = stdscr.get_wch()
                if ch == "\x1b":
                    return None
                if ch in ("\n", "\r"):
                    return "".join(buf).strip()
                if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if buf:
                        buf.pop()
                elif isinstance(ch, str) and ch.isprintable():
                    buf.append(ch)
        finally:
            curses.curs_set(0)
            stdscr.timeout(120)

    def confirm(self, stdscr, title, text):
        win = self.modal(stdscr, 64, 6, title)
        win.addstr(1, 2, text[:60])
        win.addstr(4, 2, " [y] 确认    其他取消 ", curses.A_BOLD)
        win.refresh()
        stdscr.timeout(-1)
        try:
            ch = norm_key(stdscr.get_wch())
        finally:
            stdscr.timeout(120)
        return ch == ord("y")

    def picker(self, stdscr, local):
        self.poll_remotes()
        if local in self.pending:
            self.log(f"[{local}] 正在查询远端, 完成后按 p 选择")
            return None
        refs, error = self.discovered.get(local, ([], "尚未查询, 按 r 重试"))
        if error:
            self.log(f"[{local}] {error}; 配好地址/凭证后按 r 重试")
            return None
        if not refs:
            self.log(f"[{local}] 远端可访问, 但没有分支或 Tag (空仓库)")
            return None
        sel = 0
        top = 0
        stdscr.timeout(-1)
        try:
            while True:
                H, W = stdscr.getmaxyx()
                h, w = H - 4, min(W - 4, 60)
                win = self.modal(stdscr, w, h, f"{local}: 选择 branch / tag  (↑↓ 选, 输入过滤, Enter 确认, Esc 取消)")
                flt = getattr(self, "_flt", "")
                items = [(k, n) for k, n in refs if flt in n]
                if sel >= len(items):
                    sel = max(0, len(items) - 1)
                win.addstr(1, 2, f"过滤: {flt}"[:w - 22], curses.A_REVERSE)
                # 滚动窗口: 可见容量 cap = h-4 行; 保证 sel 始终在窗口内
                cap = max(1, h - 4)
                if sel < top:
                    top = sel
                if sel > top + cap - 1:
                    top = sel - cap + 1
                top = max(0, top)
                for i in range(top, min(len(items), top + cap)):
                    y = 2 + i - top
                    k, n = items[i]
                    mark = "B" if k == "branch" else "T"
                    attr = curses.A_REVERSE if i == sel else (curses.color_pair(5) if k == "tag" else 0)
                    win.addstr(y, 2, f" [{mark}] {n}"[:w - 4], attr)
                info = f"{sel + 1}/{len(items)}"
                if top > 0:
                    info = "↑更多 " + info
                if top + cap < len(items):
                    info += " ↓更多"
                win.addstr(1, w - len(info) - 3, info, curses.color_pair(4))
                win.refresh()
                ch = norm_key(stdscr.get_wch())
                if ch == 27:
                    return None
                if ch in (10, 13) and items:
                    return items[sel][1]
                if ch in (curses.KEY_UP, ord("k")):
                    sel = max(0, sel - 1)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    sel = min(len(items) - 1, sel + 1)
                elif ch == curses.KEY_PPAGE:
                    sel = max(0, sel - cap)
                elif ch == curses.KEY_NPAGE:
                    sel = min(len(items) - 1, sel + cap)
                elif ch == curses.KEY_HOME:
                    sel = 0
                elif ch in (curses.KEY_END, ord("G")):
                    sel = len(items) - 1
                elif ch == curses.KEY_BACKSPACE or ch in (127, 8):
                    self._flt = flt[:-1]
                elif 32 <= ch < 127:
                    self._flt = flt + chr(ch)
        finally:
            stdscr.timeout(120)
            self._flt = ""

    # ---- 动作 ----
    def do_edit(self, stdscr, local):
        cur = self.data["repos"].get(local, {}).get("ref", "")
        v = self.input_dlg(stdscr, f"{local}: 设置 ref (branch/tag/commit)",
                           "输入分支名 / Tag / commit:", initial=cur)
        if v is None:
            return
        if not v:
            self.data["repos"].setdefault(local, {}).update(ref="", commit="")
            self.log(f"[{local}] 已清除清单 ref")
        else:
            self.data["repos"].setdefault(local, {}).update(ref=v, commit="")
            self.log(f"[{local}] 清单 ref -> {v}")

    def do_pick(self, stdscr, local):
        v = self.picker(stdscr, local)
        if v:
            self.data["repos"].setdefault(local, {}).update(ref=v, commit="")
            self.log(f"[{local}] 清单 ref -> {v} (来自远端列表)")

    def do_sync(self, local):
        conf = self.data["repos"].get(local, {}).get("ref", "")
        if not conf:
            self.log(f"[{local}] 未设置清单 ref, 跳过")
            return
        d = repo_dir(self.base, local)
        if not os.path.exists(os.path.join(d, ".git")):
            self.log(f"[{local}] 本地未克隆; 请先用安装器克隆到 {d}")
            return
        configured_url = remote_url(d, self.entry(local))
        if configured_url != remote_url(d):
            self.log(f"[{local}] 清单 url 与本地 origin 不同, 请确认仓库来源后再同步")
            return
        self.log(f"[{local}] fetch + checkout {conf} …")
        ok, info = checkout(d, conf)
        if ok:
            self.data["repos"][local]["commit"] = info
            self.log(f"[{local}] 已同步到 {conf} @ {info}")
        else:
            self.log(f"[{local}] 同步失败: {info[:200]}")
        self.states[local] = current_ref(d)

    def do_sync_all(self):
        for local in self.repo_names:
            if self.data["repos"].get(local, {}).get("ref"):
                self.do_sync(local)

    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(120)
        try:
            curses.start_color()
            curses.use_default_colors()
            for i, c in ((1, curses.COLOR_GREEN), (2, curses.COLOR_RED),
                         (3, curses.COLOR_CYAN), (4, curses.COLOR_YELLOW),
                         (5, curses.COLOR_MAGENTA)):
                curses.init_pair(i, c, -1)
        except Exception:
            pass
        self.refresh_states()
        self.log(f"已加载 {self.cfg_path} ({len(self.data['repos'])} 项); 工作区 {self.base}")
        if self.profile:
            self.log(f"远端来源: {self.profile.name} ({self.profile.source})")
            self.log(self.profile.selection)
        self.discover_remotes()
        while not self.quit:
            self.poll_remotes()
            if self.dirty:
                self.draw(stdscr)
                self.dirty = False
            try:
                ch = norm_key(stdscr.get_wch())
            except curses.error:
                ch = -1
            if ch == -1:
                continue
            self.dirty = True
            local = self.repo_names[self.sel]
            if ch in (ord("q"), 27):
                if self.dirty_changed() and not self.confirm(stdscr, "退出", "有未保存修改, 仍退出?"):
                    continue
                self.quit = True
            elif ch in (curses.KEY_UP, ord("k")):
                self.sel = max(0, self.sel - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.sel = min(len(self.repo_names) - 1, self.sel + 1)
            elif ch in (10, 13):
                self.do_edit(stdscr, local)
                self.refresh_states()
            elif ch == ord("p"):
                self.do_pick(stdscr, local)
                self.refresh_states()
            elif ch == ord("c"):
                self.do_sync(local)
            elif ch == ord("C"):
                self.do_sync_all()
            elif ch == ord("a"):
                selected = self.effective_data()
                n = adopt_all(self.base, selected)
                if self.profile:
                    for name, entry in selected["repos"].items():
                        if entry.get("commit"):
                            self.data["repos"].setdefault(name, {}).update(
                                ref=entry.get("ref", ""), commit=entry["commit"])
                self.log(f"已采纳当前 {n} 个仓库的 HEAD 为清单 ref")
                self.refresh_states()
            elif ch == ord("s"):
                ts = save_manifest(self.cfg_path, self.data)
                self.log(f"已保存 {self.cfg_path} ({ts})")
            elif ch == ord("r"):
                try:
                    data = load_manifest(self.cfg_path)
                    profile = load_profile(self.profile.requested_path or None) if self.profile else None
                except (OSError, ValueError) as e:
                    self.log(f"清单加载失败: {e}")
                    continue
                self.data, self.profile = data, profile
                self.refresh_states()
                self.discover_remotes()
                self.log("已重新加载清单")
            elif ch == ord("?"):
                self.help_dlg(stdscr)

    def dirty_changed(self):
        try:
            saved = load_manifest(self.cfg_path)
        except (OSError, ValueError):
            return True
        return self.data != saved

    def help_dlg(self, stdscr):
        win = self.modal(stdscr, 74, 14, "帮助")
        lines = [
            " ↑↓ 选择   Enter 输入 ref(branch/tag/commit, 留空清除)",
            " p  从启动时发现的远端分支/Tag 列表选择 (无需本地克隆)",
            " c  同步选中仓库: fetch + checkout 到清单 ref",
            " C  同步全部已配置仓库",
            " a  采纳工作区各仓库当前 HEAD 为清单 (稳定后提交本文件)",
            " s  保存清单   r  重新加载并查询远端   q  退出",
            "",
            " 清单 repo-versions.json 随 quick-start 提交/打 tag,",
            " 即可锁定全部子仓库版本; semantic_installer 2.2 优先读它构建。",
            " ≠=工作区与清单不一致  ?=目录缺失  ·=未配置",
        ]
        for i, ln in enumerate(lines):
            win.addstr(1 + i, 2, ln[:70])
        win.refresh()
        stdscr.timeout(-1)
        try:
            stdscr.get_wch()
        finally:
            stdscr.timeout(120)


def default_config_path(base):
    """清单自动寻址: 脚本目录 -> 同级 quick-start 目录 -> $SEMANTIC;
    都不存在时回脚本目录 (保存时新建)。避免镜像副本各自为政、清单被"重新初始化"。"""
    here = Path(__file__).resolve().parent
    cands = [here / "repo-versions.json",
             here.parent / "quick-start" / "repo-versions.json",
             Path(base) / "repo-versions.json"]
    for c in cands:
        if c.is_file():
            return str(c)
    return str(cands[0])


def main():
    ap = argparse.ArgumentParser(description="Semantic 子仓库版本清单 TUI")
    env_args = ap.add_mutually_exclusive_group()
    env_args.add_argument("--env", "--env-file", dest="env_file", help="手动指定远端来源配置 (默认按本仓库 origin/upstream 自动识别, 否则读 .env)")
    env_args.add_argument("--no-env", action="store_true", help="仅使用 manifest/本地 origin, 不加载 .env")
    ap.add_argument("--show-config", action="store_true", help="输出生效的仓库列表/URL/版本后退出 (不访问网络)")
    ap.add_argument("--config", default=None, help="清单文件 (默认脚本目录 repo-versions.json)")
    ap.add_argument("--semantic", default=None, help="工作区根目录 (默认 $SEMANTIC 或 $HOME/workspace/semantic)")
    ap.add_argument("--freeze", default=None, metavar="NAME",
                    help="非交互: 把工作区各仓库当前 HEAD 固化为 releases/<NAME>.json 发布快照")
    args = ap.parse_args()
    try:
        profile = None if args.no_env else load_profile(args.env_file)
        base = sx(args.semantic or (profile.semantic if profile else "")
                  or os.environ.get("SEMANTIC") or "$HOME/workspace/semantic")
        cfg = sx(args.config or os.environ.get("REPO_VERSIONS_FILE")
                 or (profile.manifest if profile else "")) or default_config_path(base)
        data = load_manifest(cfg)
        if args.show_config:
            print(json.dumps({"profile": profile.name if profile else "manifest",
                              "env_file": str(profile.source) if profile else None,
                              "selection": profile.selection if profile else "未加载 env",
                              "config": cfg, "semantic": base,
                              "repos": effective_manifest(data, profile)["repos"]},
                             ensure_ascii=False, indent=2))
            return 0
        if args.freeze:
            path, n = freeze_release(base, effective_manifest(data, profile), args.freeze)
            print(f"发布快照已生成: {path} ({n} 个仓库, 已锁定到 commit)")
            return 0
        t = TUI(cfg, base, profile)
    except (OSError, ValueError) as e:
        print(f"清单加载失败: {e}", file=sys.stderr)
        return 1
    try:
        prepare_terminal()
        curses.wrapper(lambda s: t.run(s))
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
