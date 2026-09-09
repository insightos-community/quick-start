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

"""Read repository profiles from dotenv files without executing shell code."""

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def read_env(path, inherited=None):
    """Single-line KEY=value, quotes, comments, export and ${VAR:-default}."""
    values = dict(os.environ if inherited is None else inherited)
    assigned = {}
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, sep, raw = line.partition("=")
            key = key.strip()
            if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"{path}:{number}: 需要 KEY=value")
            try:
                tokens = shlex.split(raw, comments=True, posix=True)
                if len(tokens) > 1:
                    raise ValueError("包含空格的值请使用引号")
                value = tokens[0] if tokens else ""
                if "$(" in value or "`" in value:
                    raise ValueError("不支持命令替换")

                def expand(match):
                    name = match[1] or match[3]
                    default = match[2]
                    if default is not None:
                        return values.get(name) or default
                    if name not in values:
                        raise ValueError(f"变量 {name} 尚未定义")
                    return values[name]

                # Single quotes are literal, just as in shell dotenv files.
                if not raw.lstrip().startswith("'"):
                    value = VARIABLE.sub(expand, value)
            except ValueError as e:
                raise ValueError(f"{path}:{number}: {e}") from e
            values[key] = assigned[key] = value
    return assigned


def url_key(local):
    return "REPO_URL_" + re.sub(r"[^A-Za-z0-9]", "_", local).upper()


@dataclass
class RepoProfile:
    source: Path
    name: str
    urls: dict
    manifest: str = ""
    semantic: str = ""
    selection: str = ""
    requested_path: str = ""


def remote_location(url):
    """Extract host/path from HTTPS, ssh:// or Git's user@host:path notation."""
    if "://" not in url:
        match = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", url)
        if not match:
            return "", []
        url = f"ssh://{match[1]}/{match[2]}"
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("ssh", "https", "http", "git"):
            return "", []
        return (parsed.hostname or "").lower(), parsed.path.strip("/").removesuffix(".git").split("/")
    except ValueError:
        return "", []


def detect_profile(script_dir):
    """Inspect the repository containing the script, never contact the server."""
    for remote in ("origin", "upstream"):
        try:
            result = subprocess.run(
                ["git", "-C", str(script_dir), "remote", "get-url", remote],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or not result.stdout.strip():
            continue
        host, parts = remote_location(result.stdout.strip())
        gitlab_host, _ = remote_location(os.environ.get(
            "GITLAB_SSH_ROOT", "ssh://git@gitlab.example.invalid:22"))
        if host == gitlab_host and len(parts) >= 2:
            if parts[0] == "staging":
                return "staging.env", {}, f"自动识别 {remote}: staging"
            if parts[:2] in (["example", "semantic"], ["example", "ability"]) and len(parts) >= 3:
                return "upstream.env", {}, f"自动识别 {remote}: {'/'.join(parts[:-1])}"
        if host == "github.com" and len(parts) == 2 and all(parts):
            return "github.env", {"GITHUB_ORG": parts[0]}, f"自动识别 {remote}: github.com/{parts[0]}"
        # An existing origin defines this checkout, even if its source is unknown.
        # Do not accidentally select the upstream of an unrelated fork.
        return None
    return None


def load_profile(path=None, *, cwd=None, script_dir=None):
    """Explicit file > detected Git source > cwd/.env > script/.env > legacy mode."""
    cwd = Path(cwd or Path.cwd())
    script_dir = Path(script_dir or Path(__file__).resolve().parent)
    requested_path = str(Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()) if path is not None else ""
    inherited = dict(os.environ)
    selection = "手动指定 env"
    if path is None:
        detected = detect_profile(script_dir)
        if detected:
            filename, defaults, selection = detected
            path = script_dir / filename
            # Explicit environment settings still override inferred defaults.
            inherited = {**defaults, **{k: v for k, v in os.environ.items() if v or k not in defaults}}
        else:
            selection = "来源未识别, 回退 .env"
            path = next((p for p in (cwd / ".env", script_dir / ".env") if p.is_file()), None)
        if path is None:
            return None
    source = Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
    values = read_env(source, inherited)
    # .env can select one of the three standalone profiles. No recursive includes.
    if values.get("REPO_ENV_FILE"):
        selected = Path(values["REPO_ENV_FILE"]).expanduser()
        if not selected.is_absolute():
            selected = source.parent / selected
        profile_values = read_env(selected, {**inherited, **values})
        if profile_values.get("REPO_ENV_FILE"):
            raise ValueError(f"{selected}: 不支持嵌套 REPO_ENV_FILE")
        values = {**values, **profile_values}
        source = selected.resolve()
    if "REPO_LIST" not in values:
        raise ValueError(f"{source}: 缺少 REPO_LIST; 请配置仓库列表或 REPO_ENV_FILE")
    for key in values.get("REPO_REQUIRED_VARS", "").split():
        if not values.get(key, "").strip():
            raise ValueError(f"{source}: 请先填写 {key}, 再查询此远端来源")
    urls = {}
    keys = set()
    for local in values["REPO_LIST"].split():
        key = url_key(local)
        if Path(local).is_absolute() or ".." in Path(local).parts or local == ".":
            raise ValueError(f"{source}: 非法仓库相对目录 {local}")
        if key in keys:
            raise ValueError(f"{source}: 重复仓库或环境变量名称冲突: {local}")
        url = values.get(key, "").strip()
        if not url:
            raise ValueError(f"{source}: {local} 缺少 {key}")
        keys.add(key)
        urls[local] = url
    if not urls:
        raise ValueError(f"{source}: REPO_LIST 不能为空")
    manifest = values.get("REPO_VERSIONS_FILE", "").strip()
    if manifest:
        manifest_path = Path(manifest).expanduser()
        manifest = str(manifest_path if manifest_path.is_absolute() else source.parent / manifest_path)
    semantic = values.get("SEMANTIC", "").strip()
    if semantic:
        semantic_path = Path(semantic).expanduser()
        semantic = str(semantic_path if semantic_path.is_absolute() else source.parent / semantic_path)
    return RepoProfile(source, values.get("REPO_PROFILE", source.stem), urls, manifest, semantic,
                       selection, requested_path)


def effective_manifest(data, profile):
    """Return selected repositories with effective URLs; never mutate saved refs/URLs."""
    if profile is None:
        return data
    return {**data, "repos": {
        local: {**data["repos"].get(local, {}), "url": url}
        for local, url in profile.urls.items()
    }}
