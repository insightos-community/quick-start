# Reproduce the installer and its dependencies

This is the entry point for rebuilding the **Linux glibc x86_64**, **Linux musl
x86_64** and **macOS/macOSX Apple Silicon arm64** distributions. Commands below
run real repository scripts; installing a Release and rebuilding one are separate
operations. Use a fresh normal Git clone and a new output directory per recipe.
A linked worktree's `.git` pointer may point outside a container mount.

## Platform and version matrix

| Distribution | Verified reference | Build environment | Python/dependencies |
|---|---|---|---|
| Default Linux/glibc | `v0.1.0` component lock; assembler snapshot below | Ubuntu 24.04 x86_64; Go 1.25.8, uv 0.12.12 | Robot Python 3.13 and native Runtime Python 3.10.19; the complete stack has a glibc baseline even though application ELF binaries are static |
| Optional Linux/musl | `musl-v0.1.0-2` | Pinned Python 3.13 / Alpine 3.23 amd64 Docker image | Bundled CPython 3.13.15, NumPy 2.3.5, musl loader and Mesa; Robot/Runtime venvs share the same Python base |
| macOS preview | `macos-v0.1.0-rc.3` | Native Apple Silicon, macOS 15.5+; Go 1.25.8, uv 0.12.12, xmake 3.1.1 and Xcode Command Line Tools | Bundled Python 3.13.15/NumPy 2.3.5, locked macOS wheels and native applications; system CGL |

The default glibc installer requires glibc >=2.28 and still downloads its Python
runtime on installation. The musl/macOS archives carry their own Python and
wheelhouse. Build-time network access is required in all three recipes. Native
Mach-O, musllinux and manylinux/glibc artifacts are not interchangeable.

The macOS preview passed native installation, scene startup, API, numerical and
lifecycle tests. Physical Mac CGL RGB/depth rendering, GPU performance and full
LLM-driven tasks remain unqualified. No Developer ID notarization is included.
The musl GPU scope and host driver requirements are in [Mesa notes](artifacts/mesa/README.md).

## Source locks and reproduction boundaries

- [repo-versions.json](repo-versions.json): the 13 component source tags/commits used by the default installer; the macOS assembler reuses its architecture-independent components.
- [musl/releases.json](artifacts/musl/releases.json): dependency Release tags, source commits and asset SHA-256 values.
- [musl/upstream.json](artifacts/musl/upstream.json) and [python-wheels.json](artifacts/musl/python-wheels.json): base installer, CPython, uv, Runtime adaptation, loader/compiler runtimes and wheels.
- [macOS sources.json](artifacts/macos/sources.json): the four native source revisions. [installer-requirements.lock](artifacts/macos/installer-requirements.lock) pins the full third-party macOS wheel set.

Use the locks from the selected tag, not a mixture of current branch files and
older binaries. For component releases, `release.json` distinguishes the
application `source_commit` from the automation `build_recipe_commit`; check out
both when reconstructing a historical CI run. macOS `wheel-relocation.json`
records original/modified hashes after Mach-O repair and wheel RECORD regeneration.

These instructions reproduce source selection, build configuration and checks.
They do not promise identical archive bytes: timestamps, hosted runner images,
OS package repositories and some build-time dependencies can change. Preserve
build logs, package inventories and manifests. Published SHA-256 values verify
downloaded assets; a fresh rebuild may legitimately have a different hash.

## Linux glibc x86_64

Install Go **1.25.8**, uv **0.12.12**, Python 3 with PyYAML, Git, curl, tar, zstd and
binutils on an Ubuntu 24.04 x86_64 build host. The smoke test also needs the system
EGL/OpenGL/Mesa runtime (CI installs `libegl1 libgl1 libgl1-mesa-dri`). Use your
configured package repositories; no alternate mirror is required by this guide.

The normal assembly downloads already-verified component Releases and compiles
only the Web gateway. Component source-build recipes are indexed below.
The original `v0.1.0` tag predates `build_from_releases.py`. Therefore this recipe
pins the assembler and installer source to `04cbf4a918c0da7502269386e7742ed038cf0d36`,
which passed the Linux installer CI. Its component tags/commits match the
`v0.1.0` lock (the Framework repository URL spelling was corrected). This rebuilds
the current installer from those component Releases; it does not reconstruct the
historical quick-start source tree or archive bytes.

```bash
git clone https://github.com/insightos-community/quick-start.git quick-start-glibc
cd quick-start-glibc
git checkout --detach 04cbf4a918c0da7502269386e7742ed038cf0d36
export GITHUB_SHA="$(git rev-parse HEAD)"
uv venv --python 3.13.15 .venv-build
uv pip install --python .venv-build/bin/python PyYAML==6.0.2
REPRO_VERSION=0.1.0-repro.1
.venv-build/bin/python artifacts/build_from_releases.py \
  --manifest repo-versions.json --quick-start . \
  --cache "$PWD/.build/component-releases" --version "$REPRO_VERSION" \
  --output "artifacts/releases/$REPRO_VERSION/linux-x86_64"
(cd "artifacts/releases/$REPRO_VERSION/linux-x86_64" && sha256sum -c SHA256SUMS)
.venv-build/bin/python artifacts/smoke_release.py \
  --package "artifacts/releases/$REPRO_VERSION/linux-x86_64/semantic-$REPRO_VERSION-linux-x86_64.tar.gz" \
  --dir "$PWD/.build/glibc-install-smoke"
```

The smoke script starts services on test ports and exercises installation and
management. Run it on a disposable build/test host. It needs network access for
the default Python setup; it is not an offline-dependency claim.

Scripts: [build_from_releases.py](artifacts/build_from_releases.py),
[fetch_releases.py](artifacts/fetch_releases.py), [smoke_release.py](artifacts/smoke_release.py).
The older all-source route uses [build_native.py](artifacts/build_native.py) and
[build_release.py](artifacts/build_release.py) after the source workspace has been
built; see [artifact build prerequisites](artifacts/README.md#在构建机生成发布包).

## Linux musl x86_64

Use Docker on a Linux x86_64 host with at least the CI allocation (two CPU cores,
12 GiB RAM and sufficient disk for all downloaded prefixes and expanded assets).
This reproduces the optional installer by assembling pinned dependency Releases;
it does not rebuild LLVM/Mesa/Pinocchio from source on every installer build.

```bash
git clone https://github.com/insightos-community/quick-start.git quick-start-musl
cd quick-start-musl
git checkout --detach musl-v0.1.0-2
REPRO_IMAGE='python:3.13-alpine3.23@sha256:75f27d686432419c9d42420b2b9ef605868c7a0682a6be10a6601fad46c2df01'
REPRO_WORK="$(mktemp -d "${TMPDIR:-/tmp}/semantic-musl.XXXXXXXX")"
export MUSL_TAG=musl-v0.1.0-2
export MUSL_VERSION=0.1.0-musl.2
docker run --rm --platform linux/amd64 --cpus=2 --memory=12g --memory-swap=12g --pids-limit=1024 \
  -e MUSL_TAG -e MUSL_VERSION \
  --mount "type=bind,src=$PWD,dst=/src,readonly" \
  --mount "type=bind,src=$REPRO_WORK,dst=/work" \
  "$REPRO_IMAGE" sh /src/artifacts/musl/build.sh
(cd "$REPRO_WORK/dist" && sha256sum -c SHA256SUMS)
```

Output: `$REPRO_WORK/dist/semantic-0.1.0-musl.2-linux-musl-x86_64.tar.gz`,
checksum inventories and manifests. Logs: `$REPRO_WORK/logs/`.

Reproduce the offline installation tests with bundled and host musl:

```bash
mkdir -p "artifacts/releases/$MUSL_VERSION/linux-musl-x86_64"
cp "$REPRO_WORK/dist/"* "artifacts/releases/$MUSL_VERSION/linux-musl-x86_64/"
docker build --platform linux/amd64 -t semantic-musl-smoke -f artifacts/musl/Clean.Dockerfile .
docker run --rm --platform linux/amd64 --network none --cpus=2 --memory=8g --pids-limit=1024 \
  -e MUSL_VERSION \
  --mount "type=bind,src=$PWD,dst=/src,readonly" \
  --mount "type=bind,src=$REPRO_WORK,dst=/work" \
  semantic-musl-smoke sh -ec '
    python /src/artifacts/musl/smoke.py --package "/work/dist/semantic-$MUSL_VERSION-linux-musl-x86_64.tar.gz" --dir /work/install-smoke
    python /src/artifacts/musl/smoke.py --musl-runtime system --package "/work/dist/semantic-$MUSL_VERSION-linux-musl-x86_64.tar.gz" --dir /work/system-smoke
  '
docker build --platform linux/amd64 -t semantic-musl-glibc-smoke -f artifacts/musl/Glibc.Dockerfile artifacts/musl
docker run --rm --platform linux/amd64 --network none --cpus=2 --memory=8g --pids-limit=1024 \
  -e MUSL_VERSION \
  --mount "type=bind,src=$PWD,dst=/src,readonly" \
  --mount "type=bind,src=$REPRO_WORK,dst=/work" \
  semantic-musl-glibc-smoke sh -ec '
    test ! -e /lib/ld-musl-x86_64.so.1
    python3 /src/artifacts/musl/smoke.py --musl-runtime bundled --package "/work/dist/semantic-$MUSL_VERSION-linux-musl-x86_64.tar.gz" --dir /work/glibc-smoke
  '
```

The second fixture checks bundled musl on a glibc host without a system musl
loader. See [musl-release.yml](.github/workflows/musl-release.yml) for the additional
English bootstrap tests and complete diagnostics. A new output directory is
required for a second run. Docker emulation on Apple Silicon is not native Linux
build qualification and is not the macOS installer build route.

## macOS Apple Silicon

Use a native Apple Silicon Mac running macOS 15.5+ with Xcode Command Line Tools,
Go **1.25.8**, uv **0.12.12**, xmake **3.1.1**, CMake, Ninja, pkg-config, Perl,
Autoconf, Automake and Libtool. The hosted `macos-15` workflow provisions the
versioned tools. A dedicated Mac mini is not needed for hosted builds; physical
GPU/rendering acceptance needs access to an actual Mac with a graphics session.

```bash
git clone https://github.com/insightos-community/quick-start.git quick-start-macos
cd quick-start-macos
git checkout --detach macos-v0.1.0-rc.3
test "$(uname -s)" = Darwin
test "$(uname -m)" = arm64
uv python install 3.13.15
uv venv --managed-python --python 3.13.15 .build-venv
uv pip install --python .build-venv/bin/python PyYAML==6.0.2
mkdir -p sources native/bin
.build-venv/bin/python - <<'PYTHON'
import json, subprocess
from pathlib import Path
for name, pin in json.loads(Path('artifacts/macos/sources.json').read_text()).items():
    path = Path('sources') / name
    subprocess.run(['git', 'clone', 'https://github.com/' + pin['repository'] + '.git', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'checkout', '--detach', pin['commit']], check=True)
PYTHON
(
  cd sources/Semantic-Framework
  go test -p 2 ./... -count=1 -timeout=10m
  for name in semantic-server semantic-pilot semantic; do
    CGO_ENABLED=1 go build -p 2 -trimpath -o "../../native/bin/$name" "./cmd/$name"
  done
)
CGO_ENABLED=0 go build -trimpath -o native/bin/semantic-web-gateway artifacts/gateway/main.go
(
  cd sources/AbilityFramework
  xmake f -y -p macosx -a arm64 -m release --fwk-static=n --enable-test=y --use-cpptrace=n
  xmake build -y -j 3 AbilityFramework
  xmake build -y -j 3 test
  xmake run test
)
cp sources/AbilityFramework/build/macosx/arm64/release/AbilityFramework native/bin/
(
  cd sources/semantic-deployment
  go test ./... -count=1 -timeout=5m
  CGO_ENABLED=0 go build -trimpath -o ../../native/bin/semantic-robot-instance ./cmd/semantic-robot-instance
)
REPRO_WORK="$(mktemp -d "${TMPDIR:-/tmp}/semantic-macos.XXXXXXXX")"
.build-venv/bin/python artifacts/macos/build.py --version 0.1.0-rc.3 \
  --output dist-macos --work "$REPRO_WORK/build" --sources sources --binaries native/bin
.build-venv/bin/python artifacts/macos/smoke_installer.py \
  --package dist-macos/semantic-0.1.0-rc.3-macos-arm64.tar.gz \
  --root "$REPRO_WORK/Semantic Installer Smoke" --report dist-macos/validation.json
shasum -a 256 dist-macos/validation.json dist-macos/installed-linkage.json dist-macos/loaded-libraries.json \
  | sed 's@dist-macos/@@' >> dist-macos/SHA256SUMS
(cd dist-macos && shasum -a 256 -c SHA256SUMS)
```

Output: `dist-macos/`, including the installer archive, `install-macos.sh`, locked
sources, Mach-O reports, wheel-relocation records and validation report. The
assembler enforces the pinned source revisions, repairs relocatable Python/wheel
paths and applies ad-hoc integrity signatures. It does not require Developer ID
credentials and does not create a notarized DMG. The smoke test installs, starts
and removes programs in its dedicated test directory while preserving test data.

Scripts: [build.py](artifacts/macos/build.py), [relocate_wheels.py](artifacts/macos/relocate_wheels.py),
[smoke_installer.py](artifacts/macos/smoke_installer.py), [loaded_libraries.py](artifacts/macos/loaded_libraries.py).
Do not replace the selected TinyXML2/URDFDOM/Pinocchio wheel versions independently.
A successful build/import does not prove physical GPU rendering.

## Run builds with GitHub Actions

GitHub CLI authentication and workflow write access are needed to dispatch runs.
For read-only users, clone and execute the local recipes. A GitHub token in
`GH_TOKEN` is optional for local public Release downloads and helps avoid API rate
limits; the source/build scripts do not need OSS credentials.

The following musl dispatch runs checks without publishing. For macOS, create a
non-tag reproduction branch because a `macos-v*` tag dispatch enters publishing:

```bash
gh workflow run musl-release.yml --repo insightos-community/quick-start --ref musl-v0.1.0-2
# In a quick-start clone; requires permission to create a new branch in that repo.
gh auth setup-git
git push origin 'macos-v0.1.0-rc.3^{commit}:refs/heads/reproduce/macos-installer'
gh workflow run macos-installer.yml --repo insightos-community/quick-start --ref reproduce/macos-installer
gh run list --repo insightos-community/quick-start --limit 10
# Set REPRO_RUN_ID to the desired run from the list.
gh run watch "$REPRO_RUN_ID" --repo insightos-community/quick-start --exit-status
gh run download "$REPRO_RUN_ID" --repo insightos-community/quick-start --dir downloaded-artifacts
```

The glibc workflow is [installer-release.yml](.github/workflows/installer-release.yml).
Its dispatch requires `-f tag=...` and includes a publishing job. Use the local
glibc recipe for reproduction without a publish attempt. New `v*`, `musl-v*` and
`macos-v*` tag pushes are release operations, not arbitrary build-version strings.
Existing published releases are not overwritten by the release pipeline.

## Build order and repository index

Rebuild the component/dependency you are changing first, run its checks and retain
its source/asset manifests. Publish it under a new tag, then update the appropriate
quick-start lock (including hashes) on a review branch and rebuild the installer.
Do not edit an immutable old tag or copy a new binary under an old asset hash.

The Pinocchio musl script builds its pinned Boost/EigenPy/Coal/URDFDOM/OctoMap/
console_bridge chain. The remaining native libraries have their own musl Release
scripts. Mesa's build uses Alpine development dependencies; final installer
assembly selects the pinned runtime library Releases and checks real loading.
Source compilation of every dependency is therefore a separate step from final
installer assembly. The repository guides below specify which path is in use.

| Repository | Build guide | Role |
|---|---|---|
| Semantic-Framework | [Platform scripts and commands](https://github.com/insightos-community/Semantic-Framework/blob/main/README.build.md) | Project component |
| semantic-web | [Platform scripts and commands](https://github.com/insightos-community/semantic-web/blob/main/README.build.md) | Project component |
| semantic-docs | [Platform scripts and commands](https://github.com/insightos-community/semantic-docs/blob/main/README.build.md) | Project component |
| r1pro-ability | [Platform scripts and commands](https://github.com/insightos-community/r1pro-ability/blob/main/README.build.md) | Project component |
| robot-sdk | [Platform scripts and commands](https://github.com/insightos-community/robot-sdk/blob/main/README.build.md) | Project component |
| robot-skill | [Platform scripts and commands](https://github.com/insightos-community/robot-skill/blob/main/README.build.md) | Project component |
| mujoco-runtime | [Platform scripts and commands](https://github.com/insightos-community/mujoco-runtime/blob/main/README.build.md) | Project component |
| mujoco-asset | [Platform scripts and commands](https://github.com/insightos-community/mujoco-asset/blob/main/README.build.md) | Project component |
| semantic-deployment | [Platform scripts and commands](https://github.com/insightos-community/semantic-deployment/blob/main/README.build.md) | Project component |
| ability-runtime | [Platform scripts and commands](https://github.com/insightos-community/ability-runtime/blob/main/README.build.md) | Project component |
| AbilityFramework | [Platform scripts and commands](https://github.com/insightos-community/AbilityFramework/blob/main/README.build.md) | Project component |
| Ability-SDK-Python | [Platform scripts and commands](https://github.com/insightos-community/Ability-SDK-Python/blob/main/README.build.md) | Project component |
| ability-scaffold | [Platform scripts and commands](https://github.com/insightos-community/ability-scaffold/blob/main/README.build.md) | Project component |
| SPIRV-Tools | [Platform scripts and commands](https://github.com/insightos-community/SPIRV-Tools/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| assimp | [Platform scripts and commands](https://github.com/insightos-community/assimp/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| elfutils | [Platform scripts and commands](https://github.com/insightos-community/elfutils/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| libdrm | [Platform scripts and commands](https://github.com/insightos-community/libdrm/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| libexpat | [Platform scripts and commands](https://github.com/insightos-community/libexpat/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| libffi | [Platform scripts and commands](https://github.com/insightos-community/libffi/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| libxml2 | [Platform scripts and commands](https://github.com/insightos-community/libxml2/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| llvm-project | [Platform scripts and commands](https://github.com/insightos-community/llvm-project/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| mesa | [Platform scripts and commands](https://github.com/insightos-community/mesa/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| mujoco | [Platform scripts and commands](https://github.com/insightos-community/mujoco/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| pinocchio | [Platform scripts and commands](https://github.com/insightos-community/pinocchio/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| qhull | [Platform scripts and commands](https://github.com/insightos-community/qhull/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| ruckig | [Platform scripts and commands](https://github.com/insightos-community/ruckig/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| tinyxml2 | [Platform scripts and commands](https://github.com/insightos-community/tinyxml2/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| xz | [Platform scripts and commands](https://github.com/insightos-community/xz/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| zlib | [Platform scripts and commands](https://github.com/insightos-community/zlib/blob/insightos/musl/README.build.md) | Native dependency / musl release |
| zstd | [Platform scripts and commands](https://github.com/insightos-community/zstd/blob/insightos/musl/README.build.md) | Native dependency / musl release |
