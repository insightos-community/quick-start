# Semantic Quick Start

[English](README.md) | [简体中文](README.zh-CN.md)

> R1 Pro maintenance models are now available through the pinned asset repository's Git LFS. See [publication scope](PUBLICATION.md) for third-party attribution. Component and installer archives are published through GitHub Releases with their original notices.

🚀 Build and run Semantic: a workspace that connects a web Studio, an orchestration server, robot skills, abilities, and simulation. This repository coordinates 13 component repositories; it is not the server itself.

## Start here

Use the Release installer from current main on Linux x86_64 with Python 3.10+:

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
python3 semantic_installer.py --release --install-system-deps
```

This downloads the `v0.1.0` installer, verifies checksums and source identity, then installs without cloning the 13 components or requiring Go, Node or xmake. Initial installation downloads isolated Python environments. Set `--dir` for a separate instance. The Release installer generates a random password for `admin`; use `semanticctl welcome` to view it.

CI assembles the component Releases pinned by `repo-versions.json` and smoke-tests Web/API, skill versions, MuJoCo Runtime registration and repeat installation. This does not certify physical robots, GPU execution or LLM task completion. See [release CI](docs/release-ci.md).

For a source build from the verified baseline, check out the existing tag:

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
git checkout v0.1.0
python3 semantic_installer.py --list
```

The existing deployment baseline targets **Linux x86_64** and was verified on **Ubuntu 24.04**. Model downloads do not replace the source build, Bundle activation and Skill publication steps. System dependency installation may require sudo.

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
