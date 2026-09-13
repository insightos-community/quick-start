# Semantic Quick Start

[English](README.md) | [简体中文](README.zh-CN.md)

> R1 Pro maintenance models are now available through the pinned asset repository's Git LFS. See [publication scope](PUBLICATION.md) for third-party attribution. Component and installer archives are published through GitHub Releases with their original notices.

🚀 Build and run Semantic: a workspace that connects a web Studio, an orchestration server, robot skills, abilities, and simulation. This repository coordinates 13 component repositories; it is not the server itself.

A native **macOS Apple Silicon / macOS 15.5+** installer preview is also available. See [installation and validation scope](#native-macos-installer-apple-silicon-preview); physical Mac graphics qualification is pending.

## Start here

Install prebuilt Semantic on **Linux x86_64** (verified on **Ubuntu 24.04**). You need Bash, curl and Python 3.10+. Choose a download source:

| Download source | Standalone script | Default version |
|---|---|---|
| Alibaba Cloud OSS | [install.sh](install.sh), Chinese prompts | OSS `stable` channel |
| GitHub Releases | [install-en.sh](install-en.sh), English prompts | Verified `v0.1.0` Release |

### Install from Alibaba Cloud OSS

```bash
curl -fsSL https://semantic.insightos.cn/install.sh -o install.sh
bash install.sh --install-system-deps
```

The installer reads the public OSS channel manifest, downloads the archive from Alibaba Cloud OSS and verifies its SHA-256. No OSS account or credentials are required. Use `--version <OSS-version>` to select an existing OSS release, or `--base-url <HTTPS-URL>` to use another artifact server.

### Install from GitHub Releases

```bash
curl -fsSL https://raw.githubusercontent.com/insightos-community/quick-start/main/install-en.sh -o install-en.sh
bash install-en.sh --version v0.1.0 --install-system-deps
```

The installer downloads the [GitHub Release](https://github.com/insightos-community/quick-start/releases/tag/v0.1.0), verifies checksums and release identity, and checks the fixed source commit for `v0.1.0`. Missing model files or LFS pointers are restored through the pinned GitHub asset revision and Git LFS, with size and SHA-256 verification. No component checkout or Git LFS client is required. `--version` selects a GitHub tag; omitting it also selects `v0.1.0`.

The two channels have separate version names and publication schedules; OSS `stable` does not necessarily contain the same build as GitHub `v0.1.0`.

### Optional musl installation (bundled or system runtime)

The default installation remains glibc-based. On **Linux x86_64**, select the additional musl Release. New releases use bundled musl by default and also work on glibc hosts:

```bash
curl -fsSL https://raw.githubusercontent.com/insightos-community/quick-start/main/install-en.sh -o install-en.sh
bash install-en.sh --musl --musl-runtime bundled --install-system-deps
```

Use `--musl-runtime bundled` for the included musl 1.2.5, or `--musl-runtime system` for the host `/lib/ld-musl-x86_64.so.1` (musl 1.2+). New releases default to `bundled`; reinstalls retain the selected mode. Changing modes requires a new `--dir`. Nothing is installed into system `/lib`, and global library paths are unchanged.

The Chinese `install.sh` also accepts `--musl`; this option defaults to GitHub Releases in both scripts. It includes one relocatable CPython 3.13.15 base and NumPy 2.3.5 for the separate Robot and MuJoCo environments, plus the verified musl robot libraries and Mesa. No Python download or source compilation is required during installation. Alpine dependencies use the machine's existing APK repositories; the installer does not rewrite package sources.

`--render-backend auto` tests Mesa GPU rendering and falls back to llvmpipe. Use `--render-backend software` to force software rendering, or `--render-backend mesa-gpu` to require a working GPU. AMD radeonsi was tested locally; Intel and Nouveau drivers are included but have not been tested on hardware. NVIDIA's proprietary driver path remains available through the default glibc installation. See [musl release contents and validation](artifacts/musl/README.md).

Use a separate `--dir` when trying another variant. `--musl --version musl-v0.1.0-2` selects the pinned optional Release; the normal `v0.1.0` installer and OSS stable channel are unchanged.

### Run from a checkout and manage an instance

The scripts are also included at the repository root on current `main`. After cloning this repository, choose one:

```bash
bash ./install.sh --install-system-deps     # Alibaba Cloud OSS
bash ./install-en.sh --install-system-deps  # GitHub Releases
```

Each script can run by itself outside the checkout; it does not fetch additional installer code. Review the downloaded script and run `bash install.sh --help` or `bash install-en.sh --help` for options. No Go, Node or xmake build is needed. The default glibc installation downloads isolated Python environments. `--install-system-deps` may require sudo and uses the machine's configured system package sources without rewriting them. The English installer also preserves the user's uv configuration and package indexes.

Use `--dir /absolute/instance/path` for a separate instance. Prebuilt installations use the username `admin` and generate a random password; run `~/.local/share/semantic/bin/semanticctl welcome` to view it (adjust the path for a custom `--dir`). Manage services with `semanticctl start|stop|status|doctor`; see [installation management](artifacts/README.md).

For a source build instead, use the verified public baseline:

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
git checkout v0.1.0
python3 semantic_installer.py --list
```

The root shell scripts are available on current `main`; the existing `v0.1.0` source tag is unchanged. Source builds still require Bundle activation and Skill publication after downloading models.

## 🛠 Build from source

Use Linux, Git + Git LFS, and Python with curses support. The source installer's system setup targets Ubuntu/apt; component builds additionally use Go 1.23+, Node.js 22, uv, and xmake. Native MuJoCo and Robot workers use separate Python environments (3.10 and 3.13).

```bash
python3 semantic_installer.py --list
python3 semantic_installer.py
```

Confirm the workspace directory and repository URLs before starting. Configure versions in [repo-versions.json](repo-versions.json); the installer checks out the manifest revisions. Settings, credentials, and generated output belong outside version control.

Step 2.3 fetches scene assets through Git LFS. Runtime Wheels reuse verified local
files first, then use `pip download` with the checked-out revision's filenames,
sizes and SHA-256 hashes. The index follows `UV_DEFAULT_INDEX`; unavailable exact
builds and the patched TinyXML2/urdfdom Wheels fall back to Git LFS. Downloads fill
the existing offline Bundle cache, not the host Python environment. In settings,
`RUNTIME_WHEEL_SOURCE=auto` is the default; `lfs` bypasses the package index and
`offline` only checks the runtime cache (scene assets still use LFS). No dependency
versions are upgraded. Modified cache files are preserved and reported for review.

Step 2.3 also downloads the approved R1 Pro model payloads (XML/URDF, profiles and
meshes). Step 2.4 checks the model entry files and referenced assets. Keep the
chassis and tote/gripper directories together; do not select the older model-free
asset tag. Third-party models retain their own rights and attribution.

| Order | Work | Output |
|---|---|---|
| 1–2 | Configure tools, clone repositories, fetch required LFS assets | Source workspace + assets |
| 3 | Build Server and Pilot; initialize configuration | `semantic-framework/.output/` |
| 4 | Prepare and register native MuJoCo | Runtime registration + isolated environment |
| 5 | Build AbilityFramework and Python Wheels; assemble and activate Robot Bundle | Runtime seed + Robot Bundle + catalog |
| 6 | Start Server/Web; publish Robot Skills | Web Studio + versioned Skill registry |
| 7 | Practical example: plan a depalletizing/palletizing scenario through chat | Reviewable task plan |

After starting Server, sign in with the default username `admin` and password `test-admin-pass`. If changed, use `SEMANTIC_ADMIN_PASSWORD` from `.env`.

**Bundle activation and Skill publication are separate steps.** A compiled bundle alone does not install the skills requested by a Robot.

## Workspace map

| Directory | Responsibility |
|---|---|
| `semantic-framework/` | Server, Pilot, management CLI |
| `semantic-web/` · `semantic-docs/` | Studio UI and documentation site |
| `semantic-robotsdk/robot-sdk/` | Robot-independent contracts and robot adapters |
| `semantic-ability/r1pro-ability/` | R1 Pro semantic abilities |
| `semantic-skill/robot-skill/` | Skill worker SDK and task-level skills |
| `semantic-simulation/mujoco-runtime/` · `semantic-scene/mujoco-asset/` | Physics runtime and separately governed assets |
| `semantic-robot-deployment/` | Bundle packaging and per-Robot supervision |
| `semantic-ability/ability-runtime/` | Build inputs and offline dependency cache |
| `ability-framework/{abilityframework,ability-py-sdk,ability-scaffold}/` | Ability host, Python SDK, package generator |

Each component has its own English/Chinese README. Repository names and local directory names are not always identical; preserve this layout for cross-repository builds.

## Versions and daily use

**Recommended build version: `v0.1.0`.** Run `git checkout v0.1.0` before building with the installer. The [repo-versions.json at this tag](https://github.com/insightos-community/quick-start/blob/v0.1.0/repo-versions.json) is the usable, verified component baseline and pins all 13 repositories to tags and commit SHAs. For an existing clone, run `git fetch origin --tags` first.

Releases and future mirror synchronization stay on the verified maintenance baseline, not the newest upstream/default branch. Use the exact tags and commits in `repo-versions.json`; see the [release policy](maintenance/release-policy.md) and [v0.1.3 record](maintenance/v0.1.3.md).

```bash
# The public organization and repository mappings are configured by default.
python3 repo_versions.py --env github.env --show-config
python3 -m unittest discover -s tests
```

The profile selects remotes for `repo_versions.py`, not an installer command-line option. Before distributing a workspace, prepare a manifest with publicly accessible URLs and matching revisions. See the [repository configuration reference](README.reference.md) and [publication checklist](maintenance/open-source-readiness.md).

In the TUI, `e` edits settings, Enter runs a step, `L` opens service logs, and `x` stops managed services. Prebuilt installations instead use `semanticctl start|stop|status|doctor`; see [installation management](artifacts/README.md).

## Troubleshooting

- Invalid Wheel: rerun source build/copy steps 5.1–5.2; an LFS pointer is not a binary.
- Robot offline or missing Skill: check Runtime registration, active Bundle, and exact published Skill versions.
- A failed step stops the queue; inspect `.tui-logs/` before rerunning it.
- Sudo authentication uses your Linux account password, not the Web admin password.
  It is validated before installation; failures appear in the status form. Use
  `SUDO_AUTH=terminal` if the TUI input does not work in your terminal.
- Keep passwords and model keys local. Do not expose development services to untrusted networks.

[Detailed TUI guide](semantic-installer-README.md) · [Troubleshooting notes](NOTES.md)

## License

Copyright 2026 InsightOS. First-party code is covered by [Apache-2.0](LICENSE); see [NOTICE](NOTICE) and [license scope](LICENSE_SCOPE.md) for third-party code, models, and binary assets.


### Native macOS installer (Apple Silicon preview)

The macOS package targets **Apple Silicon / macOS 15.5+** and bundles Python
3.13.15, NumPy 2.3.5, native services, offline Python wheels and MuJoCo assets.
It does not require Homebrew, system Python or a compiler. Download the
`semantic-*-macos-arm64.tar.gz` archive from the
[macOS preview release](https://github.com/insightos-community/quick-start/releases/tag/macos-v0.1.0-rc.2),
extract it, then run:

```bash
bash install.command --yes
```

The default directory is `~/Library/Application Support/Semantic`; Web listens
on `http://127.0.0.1:3000`. Use the installed `bin/semanticctl` to start, stop,
check status or uninstall. `semanticctl welcome` shows the generated admin
password in the terminal. For an explicit destination, pass `--dir "$HOME/semantic"`.
The release also includes `install-macos.sh` for verified archive downloads.

This is an unsigned preview. See its `validation.json` for executed checks;
physical Mac CGL rendering and complete AI-driven pallet tasks remain pending.
Intel Mac, LIBERO/Robosuite and hardware vendor drivers are outside this release.
See [macOS build details](artifacts/macos/README.md).

## Reproducible platform builds

See [glibc, musl and macOS build instructions](README.build.md) for pinned source revisions, exact scripts, tool requirements, local commands, CI reproduction and platform support boundaries.
