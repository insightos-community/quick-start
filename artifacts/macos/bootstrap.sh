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
expected_sha=''
instance_dir="$HOME/Library/Application Support/Semantic"
cache_dir="${XDG_CACHE_HOME:-$HOME/Library/Caches}/semantic/installers"
action=install
no_start=0
web_host=127.0.0.1
http_port=8080
ws_port=8081
web_port=3000
runtime_port=8090
options=()
while (($#)); do
  case "$1" in
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
    --http-port|--ws-port|--web-port|--runtime-port|--web-host)
      flag="$1"; value="${2:?Missing option value}"
      case "$flag" in
        --http-port) http_port="$value" ;; --ws-port) ws_port="$value" ;;
        --web-port) web_port="$value" ;; --runtime-port) runtime_port="$value" ;;
        --web-host) web_host="$value" ;;
      esac
      options+=("$flag" "$value"); shift 2 ;;
    --http-port=*|--ws-port=*|--web-port=*|--runtime-port=*|--web-host=*)
      flag="${1%%=*}"; value="${1#*=}"
      case "$flag" in
        --http-port) http_port="$value" ;; --ws-port) ws_port="$value" ;;
        --web-port) web_port="$value" ;; --runtime-port) runtime_port="$value" ;;
        --web-host) web_host="$value" ;;
      esac
      options+=("$flag" "$value"); shift ;;
    --help|-h)
      echo 'Usage: bash install-macos.sh [--tag macos-vVERSION] [--dir PATH] [--yes] [--no-start]'
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
[[ "$release_tag" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || { echo 'Invalid release tag' >&2; exit 1; }
for port in "$http_port" "$ws_port" "$web_port" "$runtime_port"; do
  [[ "$port" =~ ^[0-9]{1,5}$ ]] && ((10#$port >= 1024 && 10#$port <= 65535)) || { echo 'Ports must be numbers between 1024 and 65535' >&2; exit 2; }
done
http_port=$((10#$http_port)); ws_port=$((10#$ws_port)); web_port=$((10#$web_port)); runtime_port=$((10#$runtime_port))
[[ "$http_port" != "$ws_port" && "$http_port" != "$web_port" && "$http_port" != "$runtime_port" && "$ws_port" != "$web_port" && "$ws_port" != "$runtime_port" && "$web_port" != "$runtime_port" ]] || { echo 'Ports must be distinct' >&2; exit 2; }
# System lsof supplies an early check without requiring a preinstalled Python.
# Existing instances are checked by the manager, which can identify their own services.
if [[ -z "$archive_path" && ! -f "$instance_dir/.semantic-install-root" ]]; then
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
  release_url="https://github.com/insightos-community/quick-start/releases/download/$release_tag"
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
bash "$task_tmp/payload/install.command" --dir "$instance_dir" ${options[@]+"${options[@]}"}
