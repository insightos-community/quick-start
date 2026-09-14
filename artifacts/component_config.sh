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
      config_args=("${filtered[@]}")
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
      args=("${filtered[@]}")
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
