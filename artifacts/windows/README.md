# Native Windows installer preview

The Windows x64 installer is under integration validation. No qualified Windows
installer release has been published yet; Windows desktop GPU rendering remains
unverified. The existing Linux/musl/macOS entry points continue to use their
platform installers.

## Native installation and management

`build.py` assembles an offline ZIP with CPython 3.13.15, NumPy 2.3.5, native
Framework/supervisor/AbilityFramework executables, application-local CRT DLLs,
seven native Ability archives, three Skills and a MuJoCo Runtime pack. The public
Windows wheels and custom Pinocchio/EigenPy/Coal wheels share the bundled base
Python. Robot and Runtime use separate virtual environments for lifecycle isolation.

From a successfully verified, extracted ZIP, use Command Prompt:

```bat
install.cmd --export-config components.yaml
install.cmd --yes --dir "%LOCALAPPDATA%\Semantic" -f components.yaml
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" status
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" reconfigure -f components.yaml
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" stop
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" start
"%LOCALAPPDATA%\Semantic\bin\semanticctl.cmd" uninstall --yes
```

Defaults are Web 3000, API 8034, WebSocket 8035, Runtime 8036 and Ability
18100–18199. Reconfiguration updates the corresponding service URLs and rendered
Robot configurations. A failed restart restores the prior configuration. Release
active scenes normally in the Web UI before stopping, reconfiguring or uninstalling.
An existing Robot installation keeps its allocated Ability port range.

Installation checks ports before writing the payload and can resume copying from
the extracted local ZIP. The installed management commands do not download an
archive. Uninstall waits for the installed Python to exit, then removes program
files and writes its result to the printed temporary path. It preserves configuration,
data and logs; add `--purge` only to delete the entire instance permanently.
No administrator privileges or Unix tools are required by the installer.

## Reproduce the assembly

Use native Windows x64, Git, Go 1.25.8, uv 0.12.12 and the compiler recipes in the
pinned component repositories. [sources.json](sources.json) records exact source
commits. The [preview workflow](../../.github/workflows/windows-installer.yml)
builds the Framework, Pilot, Gateway and supervisor, then consumes successful
native AbilityFramework, Ability and Pinocchio CI outputs at their pinned revisions.
`fetch_native.py` checks the producing run's revision and success; native package
manifests and wheel hashes are checked again during assembly. CI artifact retention
is finite: these inputs must become durable component releases before this recipe
is used as a long-term release channel.

With those sources checked out under `sources/` and the native outputs available:

```powershell
$env:PYTHONUTF8 = '1'
uv python install 3.13.15
uv run --no-project --python 3.13.15 python artifacts/windows/fetch_native.py native
# Put semantic.exe, semantic-server.exe, semantic-pilot.exe,
# semantic-robot-instance.exe and semantic-web-gateway.exe in native/bin.
uv run --no-project --python 3.13.15 --with PyYAML==6.0.2 python artifacts/windows/build.py --version 0.1.0-windows-preview.1 --output .output/windows --work .work/windows --sources sources --binaries native/bin --abilities native/abilities/windows --pin-wheels native/pin
uv run --no-project --python 3.13.15 --with PyYAML==6.0.2 python artifacts/windows/smoke.py --payload .work/windows/payload --root "$env:LOCALAPPDATA/Semantic Windows verification" --report .output/windows/windows-installation.json
```

The integration workflow checks offline installation/retry, a real project with
seven healthy Abilities, installed Skills and an online Pilot, port reconfiguration,
normal scene release, service restart and local uninstall. An uploaded package is
still a preview until desktop rendering has been checked on a physical Windows host.

## Focused manager verification

[windows-manager.yml](../../.github/workflows/windows-manager.yml) exercises real
Server and Gateway processes in Chinese/space/apostrophe paths, configuration
rollback, SQLite unlock, exclusive directory locks, reusable TCP listeners,
process identity, graceful stop and offline cleanup. Its Runtime metadata fixture
does not launch a Robot; the complete project check belongs to the preview workflow.
A stale PID, missing stop endpoint or stop timeout preserves the process.

Build Framework from its pinned checkout using `docs/platforms/windows.md`, then:

```powershell
$env:SEMANTIC_NATIVE_BIN = 'C:\path\to\framework\.output\bin'
$env:CGO_ENABLED = '0'
go build -trimpath -o "$env:SEMANTIC_NATIVE_BIN/semantic-web-gateway.exe" artifacts/gateway/main.go artifacts/gateway/stop_windows.go
uv run --python 3.13.15 --with PyYAML==6.0.2 --no-project python tests/test_windows_manager_ports.py
```

`public-requirements.lock` contains only public CPython 3.13 Windows wheels;
assembly adds the custom native math and local project wheels to a complete lock.
To reproduce the public input set:

```powershell
uv pip compile artifacts/windows/public-requirements.in --python-version 3.13 --python-platform x86_64-pc-windows-msvc --only-binary :all: --generate-hashes -o artifacts/windows/public-requirements.lock
uv run --no-project --isolated --python 3.13.15 --with pip==25.2 python -m pip download --platform win_amd64 --python-version 313 --implementation cp --abi cp313 --only-binary=:all: --require-hashes -r artifacts/windows/public-requirements.lock -d public-wheelhouse
```
