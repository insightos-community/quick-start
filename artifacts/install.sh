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
# BEGIN GENERATED PLATFORM ROUTER
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
# Darwin routes before Python detection: the verified archive supplies Python.
semantic_macos_dispatch() (
  local selected_tag='' selected_source=auto instance_dir="$HOME/Library/Application Support/Semantic"
  local action=install show_help=0 explicit_base=0
  local forwarded=()
  while (($#)); do
    case "$1" in
      --tag|--version)
        [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { echo "Missing value for $1" >&2; exit 2; }
        [[ -z "$selected_tag" ]] || { echo 'Use only one --tag or --version.' >&2; exit 2; }
        selected_tag="$2"; shift 2 ;;
      --tag=*|--version=*)
        [[ -z "$selected_tag" ]] || { echo 'Use only one --tag or --version.' >&2; exit 2; }
        selected_tag="${1#*=}"; [[ -n "$selected_tag" ]] || exit 2; shift ;;
      --source) selected_source="${2:?Missing --source}"; shift 2 ;;
      --source=*) selected_source="${1#*=}"; shift ;;
      --dir) instance_dir="${2:?Missing --dir}"; shift 2 ;;
      --dir=*) instance_dir="${1#*=}"; shift ;;
      --musl|--musl-runtime|--musl-runtime=*) echo 'musl requires Linux x86_64; macOS uses its native arm64 Release.' >&2; exit 2 ;;
      --base-url) forwarded+=("$1" "${2:?Missing --base-url}"); explicit_base=1; shift 2 ;;
      --base-url=*) forwarded+=("$1"); explicit_base=1; shift ;;
      --ticket|--ticket=*) echo 'macOS supports public HTTPS mirrors or an offline --package with --sha256; private tickets require a local package.' >&2; exit 2 ;;
      --uninstall|uninstall) [[ "$action" == install ]] || exit 2; action=uninstall; shift ;;
      --configure-existing) [[ "$action" == install ]] || exit 2; action=configure; shift ;;
      --help|-h) show_help=1; shift ;;
      *) forwarded+=("$1"); shift ;;
    esac
  done
  [[ "$selected_source" != auto || "$explicit_base" != 1 ]] || selected_source=oss
  case "$selected_source" in
    auto) selected_source=oss ;; # Language default, generated for English.
    github|oss) ;;
    *) echo 'Use --source auto|github|oss.' >&2; exit 2 ;;
  esac
  if ((show_help)); then
    echo 'Semantic macOS: [--tag macos-v0.1.0-rc.4] [--source auto|github|oss] [--base-url HTTPS_URL] [--dir PATH] [--yes]'
    echo 'Native Apple Silicon, macOS 15.5+. Uses bundled Python; no Homebrew/Python setup required.'
    echo 'Offline: --package ARCHIVE --sha256 HASH. Management: --uninstall / --configure-existing --dir PATH.'
    echo 'Linux tags: v0.1.0 (glibc), musl-v0.1.0-2 (musl); run those on Linux x86_64.'
    exit 0
  fi
  if [[ -n "$selected_tag" && "$selected_tag" != stable && ! "$selected_tag" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]]; then
    echo 'Use a macos-vMAJOR.MINOR.PATCH[-SUFFIX] tag on macOS.' >&2; exit 2
  fi
  if [[ "$action" == uninstall ]]; then
    semantic_native_macos --uninstall --dir "$instance_dir" ${forwarded[@]+"${forwarded[@]}"}
  elif [[ "$action" == configure ]]; then
    [[ -f "$instance_dir/.semantic-install-root" && -x "$instance_dir/current/python/bin/python3.13" ]] || { echo 'No managed installation at --dir.' >&2; exit 2; }
    "$instance_dir/current/python/bin/python3.13" -B "$instance_dir/bin/semantic-manager/installer.py" configure --payload "$instance_dir/current" --dir "$instance_dir" ${forwarded[@]+"${forwarded[@]}"}
  else
    [[ "$selected_tag" != stable ]] || selected_tag=''
    local version_args=()
    [[ -z "$selected_tag" ]] || version_args=(--tag "$selected_tag")
    semantic_native_macos ${version_args[@]+"${version_args[@]}"} --source "$selected_source" --dir "$instance_dir" ${forwarded[@]+"${forwarded[@]}"}
  fi
)

semantic_native_macos() (
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'This installer requires native Apple Silicon macOS.' >&2
  exit 1
fi
release_tag='macos-v0.1.0-rc.4'
archive_path=''
download_source=auto
download_base='https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic'
explicit_base=0
expected_sha=''
instance_dir="$HOME/Library/Application Support/Semantic"
cache_dir="${XDG_CACHE_HOME:-$HOME/Library/Caches}/semantic/installers"
action=install
no_start=0
web_host=127.0.0.1
http_port=8034
http_port_explicit=0
ws_port=8035
ws_port_explicit=0
web_port=3000
web_port_explicit=0
runtime_port=8036
runtime_port_explicit=0
ability_port_first=18100
ability_port_last=18199
options=()
while (($#)); do
  case "$1" in
    --source) download_source="${2:?Missing source}"; shift 2 ;;
    --source=*) download_source="${1#*=}"; shift ;;
    --base-url) download_base="${2:?Missing base URL}"; explicit_base=1; shift 2 ;;
    --base-url=*) download_base="${1#*=}"; explicit_base=1; shift ;;
    --tag) release_tag="${2:?Missing tag}"; shift 2 ;;
    --tag=*) release_tag="${1#*=}"; shift ;;
    --package) archive_path="${2:?Missing package path}"; shift 2 ;;
    --package=*) archive_path="${1#*=}"; shift ;;
    --sha256) expected_sha="${2:?Missing SHA256}"; shift 2 ;;
    --sha256=*) expected_sha="${1#*=}"; shift ;;
    --cache-dir) cache_dir="${2:?Missing cache directory}"; shift 2 ;;
    --cache-dir=*) cache_dir="${1#*=}"; shift ;;
    --dir) instance_dir="${2:?Missing instance directory}"; shift 2 ;;
    --dir=*) instance_dir="${1#*=}"; shift ;;
    --uninstall|uninstall) action=uninstall; shift ;;
    --no-start) no_start=1; options+=("$1"); shift ;;
    --lan) web_host=0.0.0.0; options+=("$1"); shift ;;
    --http-port|--ws-port|--web-port|--runtime-port|--web-host|--ability-port-first|--ability-port-last)
      flag="$1"; value="${2:?Missing option value}"
      case "$flag" in
        --http-port) http_port="$value"; http_port_explicit=1 ;; --ws-port) ws_port="$value"; ws_port_explicit=1 ;;
        --web-port) web_port="$value"; web_port_explicit=1 ;; --runtime-port) runtime_port="$value"; runtime_port_explicit=1 ;;
        --web-host) web_host="$value" ;;
        --ability-port-first) ability_port_first="$value" ;; --ability-port-last) ability_port_last="$value" ;;
      esac
      options+=("$flag" "$value"); shift 2 ;;
    --http-port=*|--ws-port=*|--web-port=*|--runtime-port=*|--web-host=*|--ability-port-first=*|--ability-port-last=*)
      flag="${1%%=*}"; value="${1#*=}"
      case "$flag" in
        --http-port) http_port="$value"; http_port_explicit=1 ;; --ws-port) ws_port="$value"; ws_port_explicit=1 ;;
        --web-port) web_port="$value"; web_port_explicit=1 ;; --runtime-port) runtime_port="$value"; runtime_port_explicit=1 ;;
        --web-host) web_host="$value" ;;
        --ability-port-first) ability_port_first="$value" ;; --ability-port-last) ability_port_last="$value" ;;
      esac
      options+=("$flag" "$value"); shift ;;
    --help|-h)
      echo 'Usage: bash install-macos.sh [--tag macos-vVERSION] [--dir PATH] [--yes] [--no-start]'
      echo 'HTTP API default: 8034; override with --http-port PORT. Existing instances retain their configured port.'
      echo 'Sources: --source auto|github|oss; auto uses GitHub, or an explicit --base-url HTTPS mirror.'
      echo 'Offline: --package ARCHIVE --sha256 SHA256. Cache: --cache-dir PATH (verified archives survive failed installs).'
      echo 'Uninstall: --uninstall --dir PATH [--yes] [--purge] [--dry-run]; uses installed files, no archive download.'
      exit 0 ;;
    *) options+=("$1"); shift ;;
  esac
done
[[ "$instance_dir" == /* && ! -L "$instance_dir" && "$instance_dir" != / && "$instance_dir" != "$HOME" ]] || { echo 'Use an absolute instance --dir, not a symlink or home directory.' >&2; exit 2; }
if [[ "$action" == uninstall ]]; then
  [[ -f "$instance_dir/.semantic-install-root" && -f "$instance_dir/install.json" ]] || { echo 'No managed installation at --dir.' >&2; exit 2; }
  if [[ -x "$instance_dir/bin/semanticctl" ]]; then
    "$instance_dir/bin/semanticctl" uninstall ${options[@]+"${options[@]}"}
  else
    # Failed installs may have copied Python but not yet created semanticctl.
    found=0
    for python in "$instance_dir"/releases/*/python/bin/python3.13; do
      release="${python%/python/bin/python3.13}"
      if [[ -x "$python" && -f "$release/uninstall.py" ]]; then
        "$python" -I -B -c 'import sys; sys.path.insert(0, sys.argv[1]); from uninstall import uninstall_entry; uninstall_entry(sys.argv[2:])' "$release" --dir "$instance_dir" ${options[@]+"${options[@]}"}
        found=1; break
      fi
    done
    [[ "$found" == 1 ]] || { echo 'Installed Python/management files are missing; no archive was downloaded.' >&2; exit 2; }
  fi
  exit 0
fi
case "$download_source" in
  auto) if ((explicit_base)); then download_source=oss; else download_source=github; fi ;;
  github) ((explicit_base == 0)) || { echo '--source github cannot be combined with --base-url' >&2; exit 2; } ;;
  oss) ;;
  *) echo 'Use --source auto|github|oss' >&2; exit 2 ;;
esac
[[ "$download_base" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~/-]*)?$ ]] || { echo 'Use an HTTPS mirror URL without credentials, query or fragment' >&2; exit 2; }
[[ "$release_tag" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || { echo 'Invalid release tag' >&2; exit 1; }
# Retain existing port assignments without requiring system Python on macOS.
if [[ -f "$instance_dir/.semantic-install-root" && -f "$instance_dir/install.json" ]]; then
  found=0
  for python in "$instance_dir"/releases/*/python/bin/python3.13; do
    if [[ -x "$python" ]]; then
      saved=$("$python" -I -B -c 'import json,sys; s=json.load(open(sys.argv[1])); print(*(s[k+"_port"] for k in ("http","ws","web","runtime")))' "$instance_dir/install.json")
      read -r saved_http saved_ws saved_web saved_runtime <<< "$saved"
      ((http_port_explicit)) || http_port="$saved_http"
      ((ws_port_explicit)) || ws_port="$saved_ws"
      ((web_port_explicit)) || web_port="$saved_web"
      ((runtime_port_explicit)) || runtime_port="$saved_runtime"
      found=1; break
    fi
  done
  [[ "$found" == 1 || "$http_port_explicit$ws_port_explicit$web_port_explicit$runtime_port_explicit" == 1111 ]] || { echo 'Installed Python is missing; specify the original ports to retry.' >&2; exit 2; }
fi
options+=(--http-port "$http_port" --ws-port "$ws_port" --web-port "$web_port" --runtime-port "$runtime_port")
for port in "$http_port" "$ws_port" "$web_port" "$runtime_port"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || { echo 'Ports must be numbers between 1024 and 65535' >&2; exit 2; }
done
for port in "$ability_port_first" "$ability_port_last"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || { echo 'Invalid Ability port range' >&2; exit 2; }
done
ability_port_first=$((10#$ability_port_first)); ability_port_last=$((10#$ability_port_last))
((ability_port_first <= ability_port_last)) || { echo 'Invalid Ability port range' >&2; exit 2; }
for port in "$http_port" "$ws_port" "$web_port" "$runtime_port"; do
  ((10#$port < ability_port_first || 10#$port > ability_port_last)) || { echo 'Component port overlaps the Ability range' >&2; exit 2; }
done
http_port=$((10#$http_port)); ws_port=$((10#$ws_port)); web_port=$((10#$web_port)); runtime_port=$((10#$runtime_port))
[[ "$http_port" != "$ws_port" && "$http_port" != "$web_port" && "$http_port" != "$runtime_port" && "$ws_port" != "$web_port" && "$ws_port" != "$runtime_port" && "$web_port" != "$runtime_port" ]] || { echo 'Ports must be distinct' >&2; exit 2; }
# Existing instances can use their bundled Python for identity-aware checks.
preflight_done=0
if [[ -z "$archive_path" && -f "$instance_dir/.semantic-install-root" ]]; then
  for python in "$instance_dir"/releases/*/python/bin/python3.13; do
    release="${python%/python/bin/python3.13}"
    if [[ -x "$python" && -f "$release/uninstall.py" ]]; then
      "$python" -I -B - "$release" "$instance_dir" ${options[@]+"${options[@]}"} <<'SEMANTIC_PREFLIGHT'
# BEGIN GENERATED PREFLIGHT
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
# END GENERATED PREFLIGHT
import sys
sys.path.insert(0, sys.argv[1])
from uninstall import uninstall_managed
bootstrap_preflight(['--dir', sys.argv[2], *sys.argv[3:]], uninstall_managed, default_host='127.0.0.1')
SEMANTIC_PREFLIGHT
      preflight_done=1
      break
    fi
  done
fi
# System lsof supplies an early check without requiring a preinstalled Python.
# Use lsof when no installed Python is available, including early failed installs.
if [[ -z "$archive_path" && "$preflight_done" == 0 ]]; then
  command -v lsof >/dev/null || { echo 'System lsof is required for the port preflight.' >&2; exit 2; }
  for name in http ws web runtime; do
    [[ "$no_start" == 0 || "$name" == runtime ]] || continue
    case "$name" in http) port="$http_port" ;; ws) port="$ws_port" ;; web) port="$web_port" ;; runtime) port="$runtime_port" ;; esac
    host=127.0.0.1; [[ "$name" != web ]] || host="$web_host"
    listeners="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -Fn)" || [[ $? == 1 ]]
    if printf '%s\n' "$listeners" | awk -v host="$host" -v port="$port" '
      /^n/ {address=substr($0,2); if (host=="0.0.0.0" || address=="*:"port || address==host":"port || address=="[::]:"port) busy=1}
      END {exit !busy}'; then
      echo "Port $port ($name) is occupied; stop its service or use --$name-port PORT. No archive was downloaded." >&2
      exit 2
    fi
  done
fi
task_tmp="$(mktemp -d "${TMPDIR:-/tmp}/semantic-download.XXXXXXXX")"
staged=''
trap 'rm -rf -- "$task_tmp"; [[ -z "$staged" ]] || rm -f -- "$staged"' EXIT
if [[ -z "$archive_path" ]]; then
  archive_name="semantic-${release_tag#macos-v}-macos-arm64.tar.gz"
  if [[ "$download_source" == oss ]]; then
    release_url="${download_base%/}/releases/${release_tag#macos-v}/macos-arm64"
  else
    release_url="https://github.com/insightos-community/quick-start/releases/download/$release_tag"
  fi
  echo "[>] Download source: $download_source ($release_tag)" >&2
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 "$release_url/SHA256SUMS" -o "$task_tmp/SHA256SUMS"
  expected_sha="$(awk -v name="$archive_name" '$2 == name {print $1}' "$task_tmp/SHA256SUMS")"
  [[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || { echo 'A valid SHA256 is required' >&2; exit 1; }
  [[ "$cache_dir" == /* ]] || { echo 'Cache directory must be absolute' >&2; exit 2; }
  parent="$cache_dir"
  while [[ "$parent" != / ]]; do
    [[ ! -L "$parent" ]] || { echo 'Cache path must not contain symlinks' >&2; exit 2; }
    parent="${parent%/*}"; [[ -n "$parent" ]] || parent=/
  done
  (umask 077; mkdir -p "$cache_dir")
  [[ -z "$(find "$cache_dir" -prune \( -perm -0020 -o -perm -0002 \) -print)" ]] || { echo 'Cache directory must not be writable by other users' >&2; exit 2; }
  [[ -O "$cache_dir" ]] || { echo 'Cache directory must belong to you' >&2; exit 2; }
  archive_path="$cache_dir/$expected_sha.tar.gz"
  [[ ! -L "$archive_path" ]] || { echo 'Cached archive must not be a symlink' >&2; exit 2; }
  if [[ -f "$archive_path" && "$(shasum -a 256 "$archive_path" | awk '{print $1}')" == "$expected_sha" ]]; then
    echo "[OK] Using verified cached archive: $archive_path" >&2
  else
    staged="$(mktemp "$cache_dir/.download.XXXXXXXX")"
    curl --fail --location --proto '=https' --tlsv1.2 --retry 3 "$release_url/$archive_name" -o "$staged"
    [[ "$(shasum -a 256 "$staged" | awk '{print $1}')" == "$expected_sha" ]] || { echo 'SHA256 mismatch; download was not cached' >&2; exit 1; }
    mv -f "$staged" "$archive_path"; staged=''
    echo "[OK] Archive cached for retries: $archive_path" >&2
  fi
fi
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || { echo 'A valid SHA256 is required' >&2; exit 1; }
actual_sha="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
[[ "$actual_sha" == "$expected_sha" ]] || { echo 'SHA256 mismatch' >&2; exit 1; }
# Published archives contain only regular files. Reject links and escaping names
# before using the system tar, so bootstrapping never needs a preinstalled Python.
tar -tzf "$archive_path" > "$task_tmp/entries"
awk '/^\// || /(^|\/)\.\.($|\/)/ {exit 1}' "$task_tmp/entries"
tar -tvzf "$archive_path" > "$task_tmp/types"
awk 'substr($0,1,1) != "-" && substr($0,1,1) != "d" {exit 1}' "$task_tmp/types"
mkdir "$task_tmp/payload"
tar -xzf "$archive_path" -C "$task_tmp/payload"
if [[ -n "${SEMANTIC_BOOTSTRAP_MANAGER:-}" ]]; then
  "$task_tmp/payload/python/bin/python3.13" -B "$SEMANTIC_BOOTSTRAP_MANAGER/installer.py" install --payload "$task_tmp/payload" --dir "$instance_dir" ${options[@]+"${options[@]}"}
else
  bash "$task_tmp/payload/install.command" --dir "$instance_dir" ${options[@]+"${options[@]}"}
fi

)
# END GENERATED PLATFORM ROUTER
# BEGIN GENERATED COMPONENT CONFIG
semantic_write_manager() {
  mkdir -p "$1"
  cat > "$1/installer.py" <<'SEMANTIC_MANAGER_SOURCE'
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
from install_support import COMPONENT_DEFAULTS, component_values, read_component_config, validate_components, component_yaml, export_components
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
    # Finder may add view metadata after the verified archive is extracted.
    actual = {p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()
              and not (platform.system() == 'Darwin' and p.name == '.DS_Store' and not p.is_symlink())}
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


def check_port(port, host='127.0.0.1'):
    with socket.socket() as s:
        # Match the server's reuse behavior: TIME_WAIT is not an active listener.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            if platform.system() == 'Darwin' and macos_listener_conflict(port, host):
                raise OSError('Active listener already exists')
            s.bind((host, port))
            s.listen(1)  # Also detect BSD wildcard/specific-address listener conflicts.
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


def preflight_install_ports(root, args, state, host):
    """Check before dependency installation or payload deployment, preserving retries."""
    from uninstall import uninstall_managed
    owned = uninstall_managed(root) if state else {}
    records = services(root)
    for name in ('http', 'ws', 'web', 'runtime'):
        if name == 'runtime' and state.get('ready'):
            continue
        if name != 'runtime' and getattr(args, 'no_start', False):
            continue
        service = 'web' if name == 'web' else 'server'
        if name != 'runtime' and records.get(service, {}).get('pid') in owned:
            continue
        check_port(getattr(args, name+'_port'), host if name == 'web' else '127.0.0.1')


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
    old = load(root/'install.json') if (root/'install.json').exists() else {}
    previous_values = configured_components(root, old)
    values = apply_component_options(a, previous_values)
    if old.get('configured') and any(previous_values[k] != values[k] for k in ('ability_port_first', 'ability_port_last')):
        raise ValueError('Use reconfigure to change the Ability port range')
    for key, value in values.items():
        setattr(a, key, value)
    ports = [a.http_port, a.ws_port, a.web_port, a.runtime_port]
    if len(set(ports)) != len(ports) or any(p < 1024 or p > 65535 for p in ports):
        raise ValueError('端口必须是不同的 1024～65535 数字')
    runtime_mode = getattr(a, 'musl_runtime', None) or old.get('musl_runtime') or ('bundled' if manifest.get('musl_runtime') else 'system')
    check_platform(manifest, getattr(a, 'musl', False), runtime_mode)
    if old.get('musl_runtime') and old['musl_runtime'] != runtime_mode:
        raise ValueError('Changing musl runtime requires a new --dir')
    default_host = '127.0.0.1' if manifest.get('platform') == 'macos-arm64' else '0.0.0.0'
    host = web_host(a.web_host or (old.get('web_host', '127.0.0.1') if old else default_host))
    if a.web_host and old:
        if host != old.get('web_host', '127.0.0.1'):
            raise ValueError('已有实例请使用 --configure-existing --lan/--web-host 修改监听地址')
    preflight_install_ports(root, a, old, host)
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
        for key in ('ability_port_first', 'ability_port_last'):
            if state.get('configured') and state.get(key, values[key]) != values[key]:
                raise ValueError('Use reconfigure to change the Ability port range')
            state[key] = values[key]
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
                    server_http_url=f'http://127.0.0.1:{a.http_port}', server_websocket_url=f'ws://127.0.0.1:{a.ws_port}/ws/pilot',
                    ability_port_first=a.ability_port_first, ability_port_last=a.ability_port_last)
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
        replace_config(root/'configs/components.yaml', component_yaml(values).encode())
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
        source = (Path(__file__).resolve().parent if name.endswith('.py') else payload)/name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        target.chmod(0o600)
    launcher = root/'bin/semanticctl'
    if launcher.is_symlink() or (launcher.exists() and launcher.stat().st_nlink != 1):
        raise ValueError('管理入口链接异常')
    python_command = shlex.quote(str(root/'current/python/bin/python3.13')) if platform.system() == 'Darwin' else 'python3'
    launcher.write_text('#!/bin/sh\nexec '+python_command+' -B '+shlex.quote(str(manager/'installer.py'))+
                        ' control --root '+shlex.quote(str(root))+' "$@"\n')
    launcher.chmod(0o755)


def configured_components(root, state):
    values = component_values(state)
    path = root/'configs/semantic-server.yaml'
    if path.is_file():
        cfg = load(path)
        values.update({k: cfg.get('robot_runtime', {}).get(k, values[k])
                       for k in ('ability_port_first', 'ability_port_last')})
    return values


def apply_component_options(a, values):
    values = dict(values)
    if getattr(a, 'config', None):
        values.update(read_component_config(a.config))
    for key in COMPONENT_DEFAULTS:
        if getattr(a, key, None) is not None:
            values[key] = getattr(a, key)
    return validate_components(values)


def component_updates(root, old, values):
    config = root/'configs/semantic-server.yaml'
    cfg = load(config)
    cfg['server'].update(http_addr=f"127.0.0.1:{values['http_port']}", ws_addr=f"127.0.0.1:{values['ws_port']}")
    cfg['robot_runtime'].update(server_http_url=f"http://127.0.0.1:{values['http_port']}",
        server_websocket_url=f"ws://127.0.0.1:{values['ws_port']}/ws/pilot",
        ability_port_first=values['ability_port_first'], ability_port_last=values['ability_port_last'])
    updates = {config: (json.dumps(cfg, ensure_ascii=False, indent=2)+'\n').encode()}
    runtime = root/'runtimes.d/local-native-mujoco.yaml'
    if old['runtime_port'] != values['runtime_port']:
        text = runtime.read_text()
        pattern = r'(?m)^endpoint:\s*[\'\"]?http://127\.0\.0\.1:'+str(old['runtime_port'])+r'[\'\"]?\s*$'
        text, count = re.subn(pattern, 'endpoint: http://127.0.0.1:'+str(values['runtime_port']), text)
        if count != 1:
            raise ValueError('Managed MuJoCo endpoint differs from install state; reconcile it before reconfigure')
        updates[runtime] = text.encode()
    # The supervisor reuses rendered instances on restart. Update their actual
    # connection configurations too; never edit credentials, logs or execution evidence.
    paths = set((root/'robots').glob('*/.instance-configs/*.yaml'))
    for name in ('instance.yaml', 'robot-deployment.yaml'):
        paths.update((root/'robots').glob('*/*/'+name))
    if paths and any(old[k] != values[k] for k in ('ability_port_first', 'ability_port_last')):
        raise ValueError('Existing Robot configurations have allocated Ability ports; use a new installation directory to change the Ability range')
    for path in paths:
        text = original = path.read_text()
        for key, protocols in (('http_port', ('http',)), ('ws_port', ('http', 'ws')), ('runtime_port', ('http', 'ws'))):
            if old[key] == values[key]:
                continue
            for protocol in protocols:
                pattern = re.escape(f'{protocol}://127.0.0.1:{old[key]}')+r'(?=[/\s\'\"\},]|$)'
                text = re.sub(pattern, f'{protocol}://127.0.0.1:{values[key]}', text)
        if text != original:
            updates[path] = text.encode()
    return updates


def replace_config(path, data):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Configuration path contains a symlink: '+str(path))
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('Configuration must be a regular, unlinked file: '+str(path))
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.configure-', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def configure_existing(a):
    global INSTALL_LOG
    from uninstall import uninstall_root, uninstall_managed, uninstall_processes
    root, state = uninstall_root(a.dir)
    release = root/'releases'/state['version']
    if not state.get('ready') or not (release/'bin/semantic-server').is_file():
        raise ValueError('Reconfigure requires a completed installation')
    apply_component_options(a, configured_components(root, state))
    with (root/'run/install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = load(root/'install.json')
        old = configured_components(root, state)
        values = apply_component_options(a, old)
        owned = uninstall_managed(root)
        busy = uninstall_processes(root, owned)
        if busy:
            raise ValueError('Stop all scenes and Robot Runtime before reconfigure; active instance processes: '+', '.join(str(row['pid']) for row in busy))
        updates = component_updates(root, old, values)
        records = services(root)
        owned_ports = {old[k] for name, keys in [('server', ('http_port','ws_port')), ('web', ('web_port',))]
                       if records.get(name, {}).get('pid') in owned for k in keys}
        for key in ('http_port', 'ws_port', 'web_port', 'runtime_port'):
            if values[key] not in owned_ports:
                check_port(values[key], values['web_host'] if key == 'web_port' else '127.0.0.1')
        labels = dict(http_port='HTTP', ws_port='WS', web_port='Web', runtime_port='MuJoCo',
                      ability_port_first='AF first', ability_port_last='AF last', web_host='Web host')
        settings_form('Reconfigure components', [(labels[key], str(value)) for key, value in values.items()])
        confirm('Apply component configuration and restart managed services?', a.yes)
        state.update(values)
        updates[root/'install.json'] = (json.dumps(state, ensure_ascii=False, indent=2)+'\n').encode()
        updates[root/'configs/components.yaml'] = component_yaml(values).encode()
        backup = root/'configs'/('reconfigure-backup-'+str(time.time_ns()))
        backup.mkdir(mode=0o700)
        originals = {}
        for path in updates:
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError('Configuration contains a symlink: '+str(path))
            originals[path] = path.read_bytes() if path.exists() else None
            if originals[path] is not None:
                target = backup/path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(originals[path]); target.chmod(0o600)
        # Upgrade only the manager shipped with this trusted bootstrap.
        install_manager(root, release)
        INSTALL_LOG = root/'logs'/f'configure-{time.time_ns()}.log'
        INSTALL_LOG.touch(mode=0o600)
        stop_names = ['web', 'server'] if any(old[k] != values[k] for k in COMPONENT_DEFAULTS if k not in ('web_host', 'web_port')) else ['web']
        stopped = False
        try:
            stop_owned(root, stop_names)
            stopped = True
            if uninstall_processes(root, uninstall_managed(root)):
                raise ValueError('Instance still has active processes; configuration was not changed')
            remaining = uninstall_managed(root)
            kept_ports = {old[k] for name, keys in [('server', ('http_port', 'ws_port')), ('web', ('web_port',))]
                          if services(root).get(name, {}).get('pid') in remaining for k in keys}
            for key in ('http_port', 'ws_port', 'web_port', 'runtime_port'):
                if values[key] not in kept_ports:
                    check_port(values[key], values['web_host'] if key == 'web_port' else '127.0.0.1')
            for path, data in updates.items():
                replace_config(path, data)
            if not a.no_start:
                start(root, quiet=True)
        except Exception:
            if stopped:
                stop_owned(root, stop_names)
                for path, data in originals.items():
                    if data is None:
                        path.unlink(missing_ok=True)
                    else:
                        replace_config(path, data)
                if owned:
                    start(root, quiet=True)
            raise
        message = desktop_shortcuts(root, state, a.desktop)
        write_json(root/'install.json', state)
        print('Configuration backup: '+str(backup))
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
    def component_options(p, web=True):
        p.add_argument('-f', '--config', type=Path)
        for key in COMPONENT_DEFAULTS:
            if key == 'web_host':
                if web: p.add_argument('--web-host', type=web_host)
            else:
                p.add_argument('--'+key.replace('_', '-'), type=int)
    component_options(p, web=False)
    p = commands.add_parser('configure')
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    p.add_argument('--yes', action='store_true')
    p.add_argument('--no-start', action='store_true')
    presentation_options(p)
    component_options(p, web=False)
    p = commands.add_parser('export-config')
    p.add_argument('--dir', default=str(Path.home()/'.local/share/semantic'))
    p.add_argument('--output', default='-')
    component_options(p)
    p = commands.add_parser('control')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('action', choices=['start', 'stop', 'status', 'doctor', 'logs', 'welcome', 'uninstall', 'export-config', 'reconfigure'])
    p.add_argument('--output', default='-')
    p.add_argument('--no-start', action='store_true')
    p.set_defaults(desktop='auto')
    component_options(p)
    p.add_argument('--yes', action='store_true', help='uninstall: 跳过确认')
    p.add_argument('--purge', action='store_true', help='uninstall: 删除全部实例数据')
    p.add_argument('--dry-run', action='store_true', help='uninstall: 只显示计划')
    a = parser.parse_args()
    if a.command == 'control' and a.action not in ('uninstall', 'reconfigure') and (a.yes or a.purge or a.dry_run):
        parser.error('--yes/--purge/--dry-run 仅用于 uninstall')
    if a.command == 'export-config' or (a.command == 'control' and a.action == 'export-config'):
        root = a.root if a.command == 'control' else Path(a.dir).expanduser()
        state = load(root/'install.json') if (root/'.semantic-install-root').is_file() and (root/'install.json').is_file() else {}
        export_components(a.output, apply_component_options(a, configured_components(root, state)))
    elif a.command == 'control' and a.action == 'reconfigure':
        a.dir = str(a.root)
        a.payload = a.root/'current'
        configure_existing(a)
    elif a.command == 'install':
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
SEMANTIC_MANAGER_SOURCE
  cat > "$1/install_support.py" <<'SEMANTIC_MANAGER_SOURCE'
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
    if sys.platform == 'darwin':
        return 'macOS：使用 bin/semanticctl 管理；浏览器访问上方地址（跳过桌面快捷方式）'
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


# The component file is deliberately a flat, scalar-only YAML mapping. Keeping
# this grammar small lets the macOS bootstrap read it before Python is installed.
COMPONENT_DEFAULTS = dict(http_port=8034, ws_port=8035, web_port=3000,
                          runtime_port=8036, ability_port_first=18100,
                          ability_port_last=18199, web_host='0.0.0.0')


def component_values(state=None):
    values = dict(COMPONENT_DEFAULTS)
    if sys.platform == 'darwin':
        values['web_host'] = '127.0.0.1'
    if state and 'web_host' not in state:
        values['web_host'] = '127.0.0.1'
    values.update({k: v for k, v in (state or {}).items() if k in values})
    return values


def read_component_config(path):
    import re
    values = {}
    text = Path(path).read_text(encoding='utf-8')
    if len(text) > 16384:
        raise ValueError('Component YAML exceeds 16 KiB')
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split('#', 1)[0].strip()
        if not line or line in ('---', '...'):
            continue
        match = re.fullmatch(r'([a-z_]+):\s*(?:([0-9.]+)|"([0-9.]+)"|\'([0-9.]+)\')', line)
        if not match:
            raise ValueError(f'Invalid component YAML at line {number}; use flat scalar key: value entries')
        key, *parts = match.groups()
        if key not in {'schema_version', *COMPONENT_DEFAULTS} or key in values:
            raise ValueError('Unknown or duplicate component key: '+key)
        value = next(part for part in parts if part is not None)
        values[key] = value if key == 'web_host' else int(value)
    if values.pop('schema_version', None) != 1:
        raise ValueError('Component YAML requires schema_version: 1')
    return values


def validate_components(values):
    ports = [values[k] for k in ('http_port', 'ws_port', 'web_port', 'runtime_port')]
    if any(type(p) is not int or not 1024 <= p <= 65535 for p in ports) or len(set(ports)) != 4:
        raise ValueError('Component ports must be distinct integers between 1024 and 65535')
    first, last = values['ability_port_first'], values['ability_port_last']
    if type(first) is not int or type(last) is not int or not 1024 <= first <= last <= 65535:
        raise ValueError('Invalid Ability port range')
    if any(first <= port <= last for port in ports):
        raise ValueError('Component ports overlap the Ability port range')
    web_host(values['web_host'])
    return values


def component_yaml(values):
    validate_components(values)
    return ('# Semantic component ports. CLI options override this file. No secrets.\n'
            '# Flat YAML scalars only; comments and quoted scalars are supported.\n'
            'schema_version: 1\n'+''.join(f'{key}: {values[key]}\n' for key in COMPONENT_DEFAULTS))


def export_components(path, values):
    text = component_yaml(values)
    if str(path) == '-':
        print(text, end='')
        return
    # Never overwrite an edited configuration without an explicit new filename.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(text)
SEMANTIC_MANAGER_SOURCE
  cat > "$1/uninstall.py" <<'SEMANTIC_MANAGER_SOURCE'
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
import ctypes
import platform
import subprocess
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
    for mount in mounted_paths():
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
    if platform.system() == 'Darwin':
        return mac_process(pid)[0]
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
        executable = Path(mac_process(pid)[1]).resolve(strict=True) if platform.system() == 'Darwin' else Path(f'/proc/{pid}/exe').resolve(strict=True)
        expected = 'semantic-server' if name == 'server' else 'semantic-web-gateway'
        if executable.name != expected or root/'releases' not in executable.parents:
            raise ValueError('托管 PID 与实例程序不匹配，拒绝停止')
        owned[pid] = ticks
    return owned


def uninstall_processes(root, allowed=()):
    if platform.system() == 'Darwin':
        return mac_processes(root, allowed)
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


def mounted_paths():
    if platform.system() != 'Darwin':
        return [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    output = subprocess.check_output(['/sbin/mount'], text=True, timeout=10)
    return [line.split(' on ', 1)[1].rsplit(' (', 1)[0] for line in output.splitlines() if ' on ' in line]


class MacProcessInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('flags', 'status', 'xstatus', 'pid', 'ppid',
                'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'jobc', 'tdev', 'tpgid', 'nice')]
    _fields_ += [('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


def mac_process(pid):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    info = MacProcessInfo()
    size = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size == 0:
        # ESRCH is normal for an exited child; inaccessible live processes are not.
        if ctypes.get_errno() in (0, 3):
            return None, ''
        raise OSError(ctypes.get_errno(), 'Cannot inspect process identity')
    if size != ctypes.sizeof(info) or info.pid != pid:
        raise RuntimeError('Unexpected macOS process information ABI')
    if info.status == 5:
        return None, ''
    path = ctypes.create_string_buffer(4096)
    if lib.proc_pidpath(pid, path, len(path)) <= 0:
        raise OSError(ctypes.get_errno(), 'Cannot inspect process executable')
    return f'{info.start_sec}:{info.start_usec}', os.fsdecode(path.value)


def mac_processes(root, allowed):
    # lsof inspects executable mappings, working directories and open files.
    # Recursive lookup covers Python workers whose executable lives elsewhere.
    command = ['/usr/sbin/lsof', '-nP', '-Fpcn', '+D', str(root)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise RuntimeError('Cannot inspect open installation files: ' + result.stderr.strip())
    rows = {}
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
            rows.setdefault(pid, {'pid': pid, 'command': '', 'reasons': []})
        elif pid is not None and line.startswith('c'):
            rows[pid]['command'] = line[1:]
        elif pid is not None and line.startswith('n'):
            rows[pid]['reasons'].append('Open file: '+line[1:])
    return [row for pid, row in sorted(rows.items()) if pid not in {*allowed, os.getpid()} and row['reasons']]
SEMANTIC_MANAGER_SOURCE
}
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
# Shared pre-routing configuration. Works with the system Bash/awk on macOS.
semantic_config_entry() (
  local config='' output='' action=install root="$HOME/.local/share/semantic" python='' manager=''
  [[ "$(uname -s)" != Darwin ]] || root="$HOME/Library/Application Support/Semantic"
  local args=() config_args=() key value line parsed
  while (($#)); do
    case "$1" in
      -f|--config) config="${2:?Missing config file}"; shift 2 ;;
      --config=*) config="${1#*=}"; shift ;;
      --export-config) output="${2:?Missing output path (or - for stdout)}"; shift 2 ;;
      --export-config=*) output="${1#*=}"; shift ;;
      reconfigure|--reconfigure|--configure-existing) action=reconfigure; shift ;;
      --package|--sha256|--source|--tag|--version|--base-url|--cache-dir|--ticket)
        args+=("$1" "${2:?Missing option value}"); shift 2 ;;
      --dir) root="${2:?Missing directory}"; args+=("$1" "$2"); shift 2 ;;
      --dir=*) root="${1#*=}"; args+=("$1"); shift ;;
      *) args+=("$1"); shift ;;
    esac
  done
  if [[ -n "$config" ]]; then
    [[ -f "$config" && -r "$config" ]] || { echo 'Component YAML is not a readable file' >&2; exit 2; }
    # Emit separate argv tokens, never source/eval user-provided YAML.
    parsed=$(awk '
      BEGIN { count=0 }
      { sub(/\r$/, ""); count+=length($0)+1; if(count>16384) {print "Component YAML exceeds 16 KiB" > "/dev/stderr"; exit 2}
        sub(/#.*/, ""); gsub(/^[ \t]+|[ \t]+$/, ""); if($0=="" || $0=="---" || $0=="...") next
        if($0 !~ /^[a-z_]+:[ \t]*[0-9.]+$/ && $0 !~ /^[a-z_]+:[ \t]*"[0-9.]+"$/ && $0 !~ /^[a-z_]+:[ \t]*\047[0-9.]+\047$/) { print "Invalid flat component YAML at line " NR > "/dev/stderr"; exit 2 }
        key=$0; sub(/:.*/, "", key); value=$0; sub(/^[^:]+:[ \t]*/, "", value); gsub(/["\047]/, "", value)
        if(key !~ /^(schema_version|http_port|ws_port|web_port|runtime_port|ability_port_first|ability_port_last|web_host)$/ || seen[key]++) {print "Unknown or duplicate component key: " key > "/dev/stderr"; exit 2}
        if(key=="schema_version") {schema=value; next}
        gsub(/_/, "-", key); print "--" key; print value
      }
      END {if(schema!="1") {print "Component YAML requires schema_version: 1" > "/dev/stderr"; exit 2}}
    ' "$config") || exit 2
    while IFS= read -r line; do [[ -z "$line" ]] || config_args+=("$line"); done <<< "$parsed"
  fi
  for line in ${args[@]+"${args[@]}"}; do
    if [[ "$line" == --lan ]]; then
      local filtered=() skip=0
      for value in ${config_args[@]+"${config_args[@]}"}; do
        if ((skip)); then skip=0; continue; fi
        if [[ "$value" == --web-host ]]; then skip=1; else filtered+=("$value"); fi
      done
      config_args=(${filtered[@]+"${filtered[@]}"})
    fi
  done
  # Carry the current manager so older release archives gain configuration support.
  {
    manager=$(mktemp -d "${TMPDIR:-/tmp}/semantic-manager.XXXXXXXX")
    trap 'rm -rf -- "$manager"' EXIT
    semantic_write_manager "$manager"
    export SEMANTIC_BOOTSTRAP_MANAGER="$manager"
  }
  if [[ -n "$output" || "$action" == reconfigure ]]; then
    if [[ "$(uname -s)" == Darwin ]]; then
      for python in "$root"/current/python/bin/python3.13 "$root"/releases/*/python/bin/python3.13; do
        [[ ! -x "$python" ]] || break
      done
      if [[ ! -x "$python" ]]; then
        if [[ -n "$output" && "$action" != reconfigure && ! -e "$root/install.json" ]]; then
          if [[ "$output" == - ]]; then semantic_default_yaml ${config_args[@]+"${config_args[@]}"} ${args[@]+"${args[@]}"}; else (umask 077; set -C; semantic_default_yaml ${config_args[@]+"${config_args[@]}"} ${args[@]+"${args[@]}"} > "$output"); fi
          exit
        fi
        echo 'For a new Mac, export defaults without --dir/-f; reconfigure requires an installed instance.' >&2; exit 2
      fi
    else
      python=$(command -v python3) || { echo 'Python 3.10+ is required' >&2; exit 2; }
    fi
    if [[ -n "$output" ]]; then
      "$python" -B "$manager/installer.py" export-config --dir "$root" --output "$output" ${config_args[@]+"${config_args[@]}"} ${args[@]+"${args[@]}"}
    else
      local filtered=() skip=0
      for line in ${args[@]+"${args[@]}"}; do
        if ((skip)); then skip=0; continue; fi
        case "$line" in
          --package|--sha256|--source|--tag|--version|--base-url|--cache-dir|--ticket|--musl-runtime) skip=1 ;;
          --package=*|--sha256=*|--source=*|--tag=*|--version=*|--base-url=*|--cache-dir=*|--ticket=*|--musl-runtime=*|--musl) ;;
          *) filtered+=("$line") ;;
        esac
      done
      args=(${filtered[@]+"${filtered[@]}"})
      "$python" -B "$manager/installer.py" configure --payload "$root/current" --dir "$root" ${config_args[@]+"${config_args[@]}"} ${args[@]+"${args[@]}"}
    fi
    exit
  fi
  if [[ -n "$config" && "$(uname -s)" != Darwin ]]; then
    python3 -B - "$manager" "$config" <<'SEMANTIC_VALIDATE'
import sys
sys.path.insert(0, sys.argv[1])
from install_support import read_component_config
read_component_config(sys.argv[2])
SEMANTIC_VALIDATE
  fi
  main ${config_args[@]+"${config_args[@]}"} ${args[@]+"${args[@]}"}
)

semantic_default_yaml() {
  printf '%s\n' "$@" | awk '
    BEGIN {v["http_port"]=8034; v["ws_port"]=8035; v["web_port"]=3000; v["runtime_port"]=8036; v["ability_port_first"]=18100; v["ability_port_last"]=18199; v["web_host"]="127.0.0.1"}
    {if($0=="") next; if(pending!="") {if(pending!="dir") v[pending]=$0; pending=""; next}
     text=$0; sub(/^--/, "", text); key=text; sub(/=.*/, "", key); gsub(/-/, "_", key)
     if(!(key in v) && key!="dir") {print "Unsupported export option: " $0 > "/dev/stderr"; failed=1; exit 2}
     if(index(text,"=")) {sub(/^[^=]*=/,"",text); if(key!="dir") v[key]=text} else pending=key}
    END {if(failed) exit 2; if(pending!="") exit 2
      n=split("http_port ws_port web_port runtime_port ability_port_first ability_port_last web_host",keys," ")
      for(i=1;i<n;i++) {x=v[keys[i]]; if(x!~/^[0-9]+$/ || x+0<1024 || x+0>65535) {print "Invalid component port" > "/dev/stderr"; exit 2} v[keys[i]]=x+0}
      if(v["ability_port_first"]>v["ability_port_last"]) exit 2
      for(i=1;i<=4;i++) {x=v[keys[i]]; if(seen[x]++ || (x>=v["ability_port_first"] && x<=v["ability_port_last"])) {print "Conflicting component ports" > "/dev/stderr"; exit 2}}
      if(split(v["web_host"],ip,".")!=4) exit 2
      for(i=1;i<=4;i++) if(ip[i]!~/^[0-9]+$/ || ip[i]+0>255 || (length(ip[i])>1 && substr(ip[i],1,1)=="0")) exit 2
      if(ip[1]+0>=224) exit 2
      print "# Semantic component ports. CLI options override this file. No secrets."
      print "schema_version: 1"; for(i=1;i<=n;i++) print keys[i] ": " v[keys[i]]
    }'
}
# END GENERATED COMPONENT CONFIG
main() {
  if [[ "$(uname -s)" == Darwin ]]; then
    semantic_macos_dispatch "$@"
    return
  fi
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
import ctypes
import platform
import subprocess
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
    for mount in mounted_paths():
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
    if platform.system() == 'Darwin':
        return mac_process(pid)[0]
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
        executable = Path(mac_process(pid)[1]).resolve(strict=True) if platform.system() == 'Darwin' else Path(f'/proc/{pid}/exe').resolve(strict=True)
        expected = 'semantic-server' if name == 'server' else 'semantic-web-gateway'
        if executable.name != expected or root/'releases' not in executable.parents:
            raise ValueError('托管 PID 与实例程序不匹配，拒绝停止')
        owned[pid] = ticks
    return owned


def uninstall_processes(root, allowed=()):
    if platform.system() == 'Darwin':
        return mac_processes(root, allowed)
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


def mounted_paths():
    if platform.system() != 'Darwin':
        return [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    output = subprocess.check_output(['/sbin/mount'], text=True, timeout=10)
    return [line.split(' on ', 1)[1].rsplit(' (', 1)[0] for line in output.splitlines() if ' on ' in line]


class MacProcessInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('flags', 'status', 'xstatus', 'pid', 'ppid',
                'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'jobc', 'tdev', 'tpgid', 'nice')]
    _fields_ += [('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


def mac_process(pid):
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    info = MacProcessInfo()
    size = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size == 0:
        # ESRCH is normal for an exited child; inaccessible live processes are not.
        if ctypes.get_errno() in (0, 3):
            return None, ''
        raise OSError(ctypes.get_errno(), 'Cannot inspect process identity')
    if size != ctypes.sizeof(info) or info.pid != pid:
        raise RuntimeError('Unexpected macOS process information ABI')
    if info.status == 5:
        return None, ''
    path = ctypes.create_string_buffer(4096)
    if lib.proc_pidpath(pid, path, len(path)) <= 0:
        raise OSError(ctypes.get_errno(), 'Cannot inspect process executable')
    return f'{info.start_sec}:{info.start_usec}', os.fsdecode(path.value)


def mac_processes(root, allowed):
    # lsof inspects executable mappings, working directories and open files.
    # Recursive lookup covers Python workers whose executable lives elsewhere.
    command = ['/usr/sbin/lsof', '-nP', '-Fpcn', '+D', str(root)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise RuntimeError('Cannot inspect open installation files: ' + result.stderr.strip())
    rows = {}
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
            rows.setdefault(pid, {'pid': pid, 'command': '', 'reasons': []})
        elif pid is not None and line.startswith('c'):
            rows[pid]['command'] = line[1:]
        elif pid is not None and line.startswith('n'):
            rows[pid]['reasons'].append('Open file: '+line[1:])
    return [row for pid, row in sorted(rows.items()) if pid not in {*allowed, os.getpid()} and row['reasons']]
# END EMBEDDED UNINSTALLER
arguments = sys.argv[1:]
if arguments and arguments[0] == 'uninstall':
    arguments = ['--uninstall', *arguments[1:]]
if '--uninstall' in arguments:
    arguments.remove('--uninstall')
    management = argparse.ArgumentParser(add_help=False)
    for option in ('--tag', '--version', '--source', '--cache-dir', '--base-url', '--ticket', '--package', '--sha256', '--musl-runtime'):
        management.add_argument(option)
    management.add_argument('--musl', action='store_true')
    _, arguments = management.parse_known_args(arguments)
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
p.add_argument('--tag', help='Exact GitHub Release tag; infers glibc/musl/macOS platform')
p.add_argument('--source', choices=['auto', 'github', 'oss'], default='auto')
p.add_argument('--musl', action='store_true', help='Opt in to musl; default installs remain glibc')
p.add_argument('--musl-runtime', choices=['bundled', 'system'])
p.add_argument('--package', type=pathlib.Path)
p.add_argument('--ticket', type=pathlib.Path, help='Private OSS download ticket; no long-lived credentials required')
p.add_argument('--sha256')
p.add_argument('--cache-dir', type=pathlib.Path, default=pathlib.Path(os.environ.get('XDG_CACHE_HOME', str(pathlib.Path.home()/'.cache')))/'semantic/installers')
p.add_argument('--allow-http', action='store_true', help='Only for local/private test mirrors')
p.add_argument('--configure-existing', action='store_true', help='Only update installed instance management, LAN access and shortcuts; preserve app version/data')
p.add_argument('-h', '--help', action='store_true')
a, rest = p.parse_known_args()
if a.tag:
    if any(arg == '--version' or arg.startswith('--version=') for arg in arguments):
        p.error('Use either --tag or --version')
    if not re.fullmatch(r'(?:v[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._+-]*|musl-v[0-9]+\.[0-9]+\.[0-9]+-[1-9][0-9]*|macos-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)', a.tag):
        p.error('Invalid Release tag')
    a.version = a.tag
if a.version.startswith('macos-v'):
    p.error('macOS tags require native Apple Silicon macOS')
if a.version.startswith('musl-v'):
    a.musl = True
if a.musl and a.tag and not a.tag.startswith('musl-v'):
    p.error('--musl requires a musl-v tag')
explicit_base = any(arg == '--base-url' or arg.startswith('--base-url=') for arg in arguments)
if a.source == 'github' and (explicit_base or a.ticket):
    p.error('--source github cannot be combined with --base-url or --ticket')
use_github = a.source == 'github' or (a.source == 'auto' and not a.ticket and not explicit_base and not a.base_url)
if a.musl_runtime and not a.musl:
    raise SystemExit('--musl-runtime requires --musl')
if a.musl_runtime and not a.configure_existing:
    rest = ['--musl-runtime', a.musl_runtime, *rest]
if a.musl and not a.configure_existing:
    rest = ['--musl', *rest]
if a.help:
    print('Semantic: --base-url HTTPS_URL [--version VERSION] | --package FILE [--sha256 HASH]')
    print('Tags: --tag v0.1.0 | --tag musl-v0.1.0-2 | --tag macos-v0.1.0-rc.4')
    print('Sources: --source auto|github|oss; Chinese defaults to OSS; English defaults to GitHub. Both support explicit source selection for all platforms.')
    print('musl: --musl [--musl-runtime bundled|system] [--render-backend auto|mesa-gpu|software]; Linux x86_64; bundled works on glibc hosts')
    print('安装选项: --dir ABS_PATH --yes --no-start --install-system-deps')
    print('网络: 新安装 Web 默认 0.0.0.0:3000（含本机与局域网）；API/WS 保持本机')
    print('自定义: --web-host IPv4 --web-port PORT；仅本机用 --web-host 127.0.0.1')
    print('桌面入口: 自动检测；--desktop-shortcut 强制创建 / --no-desktop-shortcut 跳过')
    print('已有实例: --configure-existing --dir ABS_PATH --lan（只更新管理工具，不升级业务产物）')
    print('Components: --export-config FILE (or -) exports YAML; -f FILE loads it; reconfigure --dir PATH -f FILE applies it offline.')
    print('Cache: verified archives persist across retries; --cache-dir ABS_PATH selects their location.')
    print('离线卸载: --uninstall --dir ABS_PATH [--purge] [--yes] [--dry-run]')
    print('私有 OSS: --ticket /绝对路径/download.json（由 oss_client.py 生成的限时下载票据）')
    print('端口: --http-port 8034 --ws-port 8035 --web-port 3000 --runtime-port 8036')
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
# BEGIN GENERATED GITHUB HELPERS
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

# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""GitHub Release and LFS helpers embedded in the standalone English installer."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

GITHUB_INSTALLER_REPO = 'insightos-community/quick-start'
GITHUB_ASSET_REPO = 'insightos-community/mujoco-asset'
GITHUB_DEFAULT_TAG = 'v0.1.0'
GITHUB_MUSL_TAG = 'musl-v0.1.0-2'
GITHUB_BASELINE_COMMIT = 'ee0619eae2bce808d4b76b829dfb937440a964a4'
LFS_POINTER_PREFIX = b'version https://git-lfs.github.com/spec/v1\n'


def github_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def github_archive(work, version, download, requested_sha=None, musl=False, archive_download=None):
    tag = GITHUB_DEFAULT_TAG if version == 'stable' else 'v' + version.removeprefix('v')
    if not musl and not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9._+-]*)', tag):
        raise ValueError('Invalid GitHub release version')
    release_version = tag[1:]
    target_platform = 'linux-x86_64'
    if musl:
        tag = GITHUB_MUSL_TAG if version == 'stable' else version
        match = re.fullmatch(r'musl-v([0-9]+\.[0-9]+\.[0-9]+)-([1-9][0-9]*)', tag)
        if not match:
            raise ValueError('Use --version musl-vMAJOR.MINOR.PATCH-REVISION with --musl')
        release_version = match[1] + '-musl.' + match[2]
        target_platform = 'linux-musl-x86_64'
    base = f'https://github.com/{GITHUB_INSTALLER_REPO}/releases/download/{tag}/'
    download(base+'SHA256SUMS', work/'SHA256SUMS', 1024*1024)
    sums = {}
    for line in (work/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        if not re.fullmatch(r'[a-f0-9]{64}', checksum) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]*', name) or name in sums:
            raise ValueError('Invalid GitHub release checksum inventory')
        sums[name] = checksum
    download(base+'release.json', work/'release.json', 1024*1024)
    if github_digest(work/'release.json') != sums.get('release.json'):
        raise ValueError('GitHub release metadata checksum mismatch')
    metadata = json.loads((work/'release.json').read_text())
    if (metadata.get('tag') != tag or metadata.get('version') != release_version or
            metadata.get('component') != 'semantic-installer' or metadata.get('platform') != target_platform):
        raise ValueError('GitHub release identity or platform mismatch')
    if musl and metadata.get('libc') != 'musl':
        raise ValueError('Release does not declare musl support')
    if tag == GITHUB_DEFAULT_TAG and metadata.get('source_commit') != GITHUB_BASELINE_COMMIT:
        raise ValueError('GitHub release differs from the verified source baseline')
    name = f'semantic-{release_version}-{target_platform}.tar.gz'
    expected = sums.get(name)
    if expected is None or (requested_sha and requested_sha != expected):
        raise ValueError('GitHub archive checksum is missing or differs from --sha256')
    archive = work/name
    if archive_download:
        archive = archive_download(base+name, expected)
    else:
        download(base+name, archive, 8*1024**3)
    # The canonical bootstrap verifies this digest again before extracting anything.
    if github_digest(archive) != expected:
        raise ValueError('GitHub archive SHA256 mismatch')
    return archive, expected


class GithubHTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('GitHub LFS refuses non-HTTPS redirects')
        redirected = super().redirect_request(request, response, code, message, headers, newurl)
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(request.full_url).netloc:
            for name in list(redirected.headers):
                if name.lower() in ('authorization', 'cookie'):
                    redirected.remove_header(name)
        return redirected


def github_open(request):
    if urllib.parse.urlsplit(request.full_url).scheme != 'https':
        raise ValueError('GitHub LFS requires HTTPS')
    return urllib.request.build_opener(GithubHTTPSRedirect()).open(request, timeout=60)


def github_lfs_object(pointer, destination, expected):
    match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?', pointer)
    if not match:
        raise ValueError('Invalid Git LFS pointer')
    oid, size = match[1].decode(), int(match[2])
    if oid != expected or not 0 < size <= 2*1024**3:
        raise ValueError('LFS pointer differs from the verified payload inventory')
    data = json.dumps({'operation':'download', 'transfers':['basic'], 'objects':[{'oid':oid,'size':size}]}).encode()
    request = urllib.request.Request(f'https://github.com/{GITHUB_ASSET_REPO}.git/info/lfs/objects/batch',
                                    data=data, headers={'Accept':'application/vnd.git-lfs+json', 'Content-Type':'application/vnd.git-lfs+json'})
    with github_open(request) as response:
        batch = json.loads(response.read(1024*1024))
    objects = batch.get('objects', [])
    if len(objects) != 1 or objects[0].get('oid') != oid or objects[0].get('size') != size or 'error' in objects[0]:
        raise ValueError('GitHub LFS returned an unexpected object')
    action = objects[0]['actions']['download']
    request = urllib.request.Request(action['href'], headers=action.get('header', {}))
    count = 0
    with github_open(request) as response, destination.open('wb') as target:
        while block := response.read(1024*1024):
            count += len(block)
            if count > size:
                raise ValueError('GitHub LFS object exceeds its declared size')
            target.write(block)
    if count != size or github_digest(destination) != oid:
        raise ValueError('GitHub LFS size or SHA256 mismatch')


def hydrate_github_assets(payload, download):
    """Restore missing/LFS-pointer assets using immutable pins and original file hashes.

    Complete Release archives already contain the LFS objects, so need no extra
    model downloads. Neither files.json nor the archive itself is rewritten.
    """
    if not (payload/'release-lock.json').is_file():
        return 0  # Older explicitly supplied packages have no GitHub provenance.
    records = json.loads((payload/'files.json').read_text())
    pending = []
    for name, checksum in records.items():
        if not name.startswith('assets/mujoco/'):
            continue
        relative = Path(name.removeprefix('assets/mujoco/'))
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or not re.fullmatch(r'[a-f0-9]{64}', checksum):
            raise ValueError('Invalid asset inventory path or checksum')
        target = payload/name
        if target.is_file():
            with target.open('rb') as source:
                if not source.read(128).startswith(LFS_POINTER_PREFIX):
                    continue
        # Generated release metadata is not a Git-tracked asset.
        if relative.parts[0] not in ('robot','scene','assets','asset-catalog.v1.json'):
            raise ValueError('Missing non-source asset metadata')
        pending.append((relative, target, checksum))
    if not pending:
        return 0
    pin = json.loads((payload/'release-lock.json').read_text())['semantic-scene/mujoco-asset']
    commit = pin['source_commit']
    if pin['repository'] != GITHUB_ASSET_REPO or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Invalid pinned GitHub asset repository')
    with tempfile.TemporaryDirectory(prefix='github-lfs-', dir=payload.parent) as temporary:
        for relative, target, checksum in pending:
            staged = Path(temporary)/'asset'
            url = f'https://raw.githubusercontent.com/{GITHUB_ASSET_REPO}/{commit}/' + urllib.parse.quote(relative.as_posix(), safe='/')
            download(url, staged, 2*1024**3)
            with staged.open('rb') as source:
                pointer = source.read(1024)
            if pointer.startswith(LFS_POINTER_PREFIX):
                github_lfs_object(pointer, staged, checksum)
            if github_digest(staged) != checksum:
                raise ValueError('GitHub asset differs from the verified payload SHA256')
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            target.chmod(0o644)
    return len(pending)
# END GENERATED GITHUB HELPERS
if not a.configure_existing:
    rest = installation_arguments(rest)
def archive_download(url, sha):
    if not a.configure_existing:
        bootstrap_preflight(rest, uninstall_managed)
    return cached_archive(url, sha, a.cache_dir, download, status)
with tempfile.TemporaryDirectory(prefix='semantic-download-') as temporary:
    work = pathlib.Path(temporary)
    if a.package:
        archive = a.package.expanduser().resolve(strict=True)
        sidecar = pathlib.Path(str(archive) + '.sha256')
        expected = a.sha256 or (sidecar.read_text().split()[0] if sidecar.exists() else '')
    elif use_github:
        archive, expected = github_archive(work, a.version, download, a.sha256, musl=a.musl, archive_download=archive_download)
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
            selected_platform = 'linux-musl-x86_64' if a.musl else 'linux-x86_64'
            channel = 'musl-stable' if a.musl else 'stable'
            oss_version = a.version
            if a.version.startswith('musl-v'):
                version, revision = a.version.removeprefix('musl-v').rsplit('-', 1)
                oss_version = version + '-musl.' + revision
            elif a.version.startswith('v'):
                oss_version = a.version.removeprefix('v')
            suffix = f'channels/{channel}.json' if oss_version == 'stable' else f'releases/{oss_version}/{selected_platform}/manifest.json'
            download(a.base_url.rstrip('/') + '/' + suffix, work/'manifest.json', 1024*1024)
            m = json.loads((work/'manifest.json').read_text())
        if m.get('platform') != ('linux-musl-x86_64' if a.musl else 'linux-x86_64'): raise ValueError('不支持的制品平台')
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
        archive = archive_download(url, expected)
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
    result = subprocess.run([sys.executable, '-B', str(pathlib.Path(os.environ.get('SEMANTIC_BOOTSTRAP_MANAGER', str(payload)))/'installer.py'), 'configure' if a.configure_existing else 'install', '--payload', str(payload), *rest])
    raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
PY
}
semantic_config_entry "$@"
