# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
# Darwin routes before Python detection: the verified archive supplies Python.
semantic_macos_dispatch() (
  local selected_tag='' selected_source=auto instance_dir="$HOME/Library/Application Support/Semantic"
  local action=install show_help=0
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
      --base-url|--base-url=*|--ticket|--ticket=*) echo 'macOS OSS artifacts are not published. Use --source github or an offline --package with --sha256.' >&2; exit 2 ;;
      --uninstall|uninstall) [[ "$action" == install ]] || exit 2; action=uninstall; shift ;;
      --configure-existing) [[ "$action" == install ]] || exit 2; action=configure; shift ;;
      --help|-h) show_help=1; shift ;;
      *) forwarded+=("$1"); shift ;;
    esac
  done
  case "$selected_source" in
    auto|github) ;;
    oss) echo 'macOS OSS artifacts are not published; use --source github.' >&2; exit 2 ;;
    *) echo 'Use --source auto|github|oss.' >&2; exit 2 ;;
  esac
  if ((show_help)); then
    echo 'Semantic macOS: [--tag macos-v0.1.0-rc.2] [--source auto|github] [--dir PATH] [--yes]'
    echo 'Native Apple Silicon, macOS 15.5+. Uses bundled Python; no Homebrew/Python setup required.'
    echo 'Offline: --package ARCHIVE --sha256 HASH. Management: --uninstall / --configure-existing --dir PATH.'
    echo 'Linux tags: v0.1.0 (glibc), musl-v0.1.0-2 (musl); run those on Linux x86_64.'
    exit 0
  fi
  if [[ -n "$selected_tag" && "$selected_tag" != stable && ! "$selected_tag" =~ ^macos-v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$ ]]; then
    echo 'Use a macos-vMAJOR.MINOR.PATCH[-SUFFIX] tag on macOS.' >&2; exit 2
  fi
  if [[ "$action" == uninstall ]]; then
    [[ -f "$instance_dir/.semantic-install-root" && -x "$instance_dir/bin/semanticctl" ]] || { echo 'No managed installation at --dir.' >&2; exit 2; }
    "$instance_dir/bin/semanticctl" uninstall ${forwarded[@]+"${forwarded[@]}"}
  elif [[ "$action" == configure ]]; then
    [[ -f "$instance_dir/.semantic-install-root" && -x "$instance_dir/current/python/bin/python3.13" ]] || { echo 'No managed installation at --dir.' >&2; exit 2; }
    "$instance_dir/current/python/bin/python3.13" -B "$instance_dir/bin/semantic-manager/installer.py" configure --payload "$instance_dir/current" --dir "$instance_dir" ${forwarded[@]+"${forwarded[@]}"}
  else
    [[ "$selected_tag" != stable ]] || selected_tag=''
    local version_args=()
    [[ -z "$selected_tag" ]] || version_args=(--tag "$selected_tag")
    semantic_native_macos ${version_args[@]+"${version_args[@]}"} --dir "$instance_dir" ${forwarded[@]+"${forwarded[@]}"}
  fi
)
