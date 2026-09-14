#!/bin/bash
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
