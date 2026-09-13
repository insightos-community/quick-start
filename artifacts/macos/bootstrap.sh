#!/bin/bash
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'This installer requires native Apple Silicon macOS.' >&2
  exit 1
fi
release_tag='macos-v0.1.0-rc.3'
archive_path=''
expected_sha=''
options=()
while (($#)); do
  case "$1" in
    --tag) release_tag="${2:?Missing tag}"; shift 2 ;;
    --package) archive_path="${2:?Missing package path}"; shift 2 ;;
    --sha256) expected_sha="${2:?Missing SHA256}"; shift 2 ;;
    --help|-h)
      echo 'Usage: bash install-macos.sh [--tag macos-vVERSION] [--dir PATH] [--yes] [--no-start]'
      echo 'Offline: --package ARCHIVE --sha256 SHA256. Further options are passed to the installer.'
      exit 0 ;;
    *) options+=("$1"); shift ;;
  esac
done
[[ "$release_tag" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]] || { echo 'Invalid release tag' >&2; exit 1; }
task_tmp="$(mktemp -d "${TMPDIR:-/tmp}/semantic-download.XXXXXXXX")"
trap 'rm -rf -- "$task_tmp"' EXIT
if [[ -z "$archive_path" ]]; then
  archive_name="semantic-${release_tag#macos-v}-macos-arm64.tar.gz"
  release_url="https://github.com/insightos-community/quick-start/releases/download/$release_tag"
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 "$release_url/SHA256SUMS" -o "$task_tmp/SHA256SUMS"
  expected_sha="$(awk -v name="$archive_name" '$2 == name {print $1}' "$task_tmp/SHA256SUMS")"
  archive_path="$task_tmp/$archive_name"
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 "$release_url/$archive_name" -o "$archive_path"
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
bash "$task_tmp/payload/install.command" "${options[@]}"
