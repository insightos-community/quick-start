# Native macOS installer

Target: Apple Silicon arm64, macOS 15.5 or newer. The first installer is an
unsigned preview archive; physical Mac CGL graphics qualification is pending.
Intel Mac and optional LIBERO/Robosuite profiles are outside this release.

## Install

Download `semantic-0.1.0-rc.3-macos-arm64.tar.gz` from the
[preview release](https://github.com/insightos-community/quick-start/releases/tag/macos-v0.1.0-rc.3),
verify its SHA-256 against `SHA256SUMS`, extract it, and run:

```bash
bash install.command --yes
# or choose an instance directory
bash install.command --dir "$HOME/semantic" --yes
```

The release's `install-macos.sh` downloads and verifies the same archive using
system curl, shasum and tar; it needs no preinstalled Python. For offline use:

```bash
bash install-macos.sh --package /absolute/path/semantic-0.1.0-rc.3-macos-arm64.tar.gz \
  --sha256 SHA256_FROM_RELEASE --dir "$HOME/semantic" --yes
```

Default directory: `~/Library/Application Support/Semantic`. Default Web URL:
http://127.0.0.1:3000. The admin password is generated during installation;
`bin/semanticctl welcome` shows it in the terminal. Other management commands:
`start`, `stop`, `status`, `doctor`, `logs`, `uninstall`.
Uninstall preserves configuration/data unless `--purge` is explicitly passed.
Different releases require separate installation directories; automatic database
migration and in-place upgrades are not supported by this preview.

No Homebrew, compiler or package-source change is required. Python 3.13.15 and
all wheels are bundled. Robot and simulation use separate virtual environments
sharing one Python base and the same locked dependency versions, including
NumPy 2.3.5, Pinocchio 3.9.0, Ruckig 0.19.4 and MuJoCo 3.4.0.

## Reproduce

`.github/workflows/macos-installer.yml` builds Framework, deployment launcher and
AbilityFramework from exact commits recorded in `sources.json`. It reuses
verified component Releases pinned by the root `repo-versions.json` for Web,
assets, Python SDK wheels, abilities and skills. Runtime wheels are built from
the pinned native macOS source. Every downloaded component asset is checked
against its Release inventory and source identity.

`installer-requirements.lock` pins the complete third-party Python set with
upstream hashes. The assembler repairs upstream Mach-O build-directory and
Linux `$ORIGIN` search paths, applies ad-hoc integrity signatures, regenerates
wheel RECORD entries and derives the bundled lock from the resulting wheel
hashes. `wheel-relocation.json` records original and modified SHA-256 values
and every load-command change. It can be regenerated from `installer-requirements.in` with:

```bash
uv pip compile artifacts/macos/installer-requirements.in --python-version 3.13 \
  --python-platform aarch64-apple-darwin --only-binary :all: --generate-hashes \
  -o artifacts/macos/installer-requirements.lock
```

The Pinocchio wheels require the selected `cmeel-urdfdom==4.0.1` and
`cmeel-tinyxml2==10.0.0` ABI combination. Do not substitute the Linux compatibility
wheel or upgrade these independently without real import and URDF tests.

The installer workflow checks native Mach-O architecture/linkage, installs the
actual archive in a directory with spaces, starts the Server/Web and a native
MuJoCo scene through the CLI, verifies authentication, shared Python and math,
then checks stop/start, repeat installation and data-preserving uninstall.
Read the released `validation.json` for what the producing run executed.

`macos-v*` tags publish the tested archive, download script, checksum inventory,
component source manifest, linkage report and validation report as a GitHub
prerelease. PR/workflow_dispatch runs produce downloadable Actions artifacts.

## Graphics qualification

MuJoCo uses system CGL/OpenGL on macOS. The standard hosted runner previously
failed to create a CGL context (`invalid pixel format`), so CI physics or scene
startup does not imply RGB/depth rendering or GPU performance was verified.
Use an Apple Silicon Mac with a working graphics session to execute the
`mujoco-runtime` repository's optional `semantic-graphics` workflow before
promoting this preview to a fully qualified graphics release.

The earlier `macos-native.yml`, `requirements.lock` and `smoke.py` retain the
smaller dependency-foundation checks. Their binaries are development evidence,
not substitutes for the complete installer archive.

## Reproduce from source and Releases

See the [three-platform build guide](../../README.build.md) for complete local/CI commands, pinned versions, output paths and all component/dependency repository recipes.

## Rendering backend compatibility

The Web client requests `render_backend: auto`, so the Runtime uses its configured
`cgl` backend on macOS. This also works when the browser and Runtime run on
different operating systems. An explicitly requested incompatible backend is
still rejected. Preview rc.2 fixes the rc.1 Web default that requested Linux EGL.
Install rc.2 into a **new `--dir`**; the preview installer rejects overwriting a
different version and does not migrate databases automatically. Stop the old
installation before using the same ports, keep its configuration/user data, and
reload the browser page to load the updated Web assets.

The rc.3 installer fixes Robot instance supervisor exits caused by x86_64 metadata in the seven Python Ability packages. Native CI now starts all project robots and checks AbilityFramework, all seven abilities, Pilot, Robot Skill installation and Robot Runtime readiness. The offline wheelhouse includes Pydantic 2.13.4 required by the three bundled Skills. Stop your old instance and install this release into a new directory; existing databases are not migrated automatically.
