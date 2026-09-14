# Windows native installer work

This directory contains development inputs and manager primitives. It does not
yet provide a Windows installer, an installation command, or a qualified GPU build.

`windows_ports.py` provides an exclusive installation-directory lock, conservative
Windows TCP port checks, process creation/executable identity, and graceful stop
through Framework's named event. A missing endpoint, stale identity, or stop
timeout preserves the process. No administrator privileges or Unix tools are used.
The existing Linux/macOS installer does not import this adapter yet.

The [native workflow](../../.github/workflows/windows-manager.yml) builds the
pinned Framework source and tests the Python adapter against the real Server:
initialization in a Chinese/space/apostrophe path, two start/stop cycles, stale
identity rejection, and SQLite unlock. It also tests cross-process lock contention,
crash recovery, occupied reusable TCP sockets, and preservation of an unrelated
process without a stop endpoint. These tests contain no active Robot instance.
The Windows Web gateway uses the same stop event; native tests cover static
assets, SPA routes, Windows path syntax rejection, and two graceful restart cycles.

To reproduce on Windows, build `semantic.exe` and `semantic-server.exe` from
Framework commit `c966d90b859644c0da1880c1c05fbbdcc1e557bc` using its
`docs/platforms/windows.md`, then run from this checkout with Go 1.25.8 and uv 0.12.12:

```powershell
$env:SEMANTIC_NATIVE_BIN = 'C:\path\to\framework\.output\bin'
$env:CGO_ENABLED = '0'
go build -trimpath -o "$env:SEMANTIC_NATIVE_BIN/semantic-web-gateway.exe" artifacts/gateway/main.go artifacts/gateway/stop_windows.go
uv run --python 3.13.15 --with PyYAML==6.0.2 --no-project python tests/test_windows_manager_ports.py
```

`public-requirements.lock` pins the public CPython 3.13 Windows wheel set with
hashes. It excludes the custom Pinocchio/EigenPy/Coal/private-DLL wheels and local
project wheels; it must not be presented as the complete offline installer lock.
Regenerate and download the public set with:

```powershell
uv pip compile artifacts/windows/public-requirements.in --python-version 3.13 --python-platform x86_64-pc-windows-msvc --only-binary :all: --generate-hashes -o artifacts/windows/public-requirements.lock
uv run --no-project --isolated --python 3.13.15 --with pip==25.2 python -m pip download --platform win_amd64 --python-version 313 --implementation cp --abi cp313 --only-binary=:all: --require-hashes -r artifacts/windows/public-requirements.lock -d public-wheelhouse
```

Remaining integration includes payload assembly, configuration/reconfiguration,
offline installation and uninstall, Robot/Ability/Skill lifecycle, and Windows 11
desktop rendering. The normal `install.sh` and `install-en.sh` remain Linux/macOS
entry points until the Windows package is verified and published.
