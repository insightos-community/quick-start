#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
package_dir="$PWD"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'Semantic requires an Apple Silicon Mac running macOS 15.5 or newer.' >&2
  exit 1
fi
exec "$package_dir/python/bin/python3.13" -B "$package_dir/installer.py" install \
  --payload "$package_dir" --dir "$HOME/Library/Application Support/Semantic" --web-host 127.0.0.1 "$@"
