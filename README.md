# Semantic Quick Start

[English](README.md) | [简体中文](README.zh-CN.md)

> This source snapshot excludes Galaxea models and has no default prebuilt download channel. See [publication scope](PUBLICATION.md). R1 Pro simulation requires separately obtained and adapted models.

🚀 Build and run Semantic: a workspace that connects a web Studio, an orchestration server, robot skills, abilities, and simulation. This repository coordinates 13 component repositories; it is not the server itself.

## Start here

Start with the public source workspace below. The [artifact installer guide](artifacts/README.md) describes tooling for separately supplied packages; this snapshot does not publish a complete binary deployment archive.

```bash
git clone https://github.com/insightos-community/quick-start.git
cd quick-start
python3 semantic_installer.py --list
```

The existing deployment baseline targets **Linux x86_64** and was verified on **Ubuntu 24.04**. Removing external models means this public snapshot is not a complete out-of-the-box R1 Pro simulation deployment. System dependency installation may require sudo.

## 🛠 Build from source

Use Linux, Git + Git LFS, and Python with curses support. The source installer's system setup targets Ubuntu/apt; component builds additionally use Go 1.23+, Node.js 22, uv, and xmake. Native MuJoCo and Robot workers use separate Python environments (3.10 and 3.13).

```bash
python3 semantic_installer.py --list
python3 semantic_installer.py
```

Confirm the workspace directory and repository URLs before starting. Configure versions in [repo-versions.json](repo-versions.json); the installer checks out the manifest revisions. Settings, credentials, and generated output belong outside version control.

| Order | Work | Output |
|---|---|---|
| 1–2 | Configure tools, clone repositories, fetch required LFS assets | Source workspace + assets |
| 3 | Build Server and Pilot; initialize configuration | `semantic-framework/.output/` |
| 4 | Prepare and register native MuJoCo | Runtime registration + isolated environment |
| 5 | Build AbilityFramework and Python Wheels; assemble and activate Robot Bundle | Runtime seed + Robot Bundle + catalog |
| 6 | Start Server/Web; publish Robot Skills | Web Studio + versioned Skill registry |
| 7 | Configure models, project, scene and Robot in Studio | Runnable task environment |

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

Releases and future mirror synchronization stay on the verified maintenance baseline, not the newest upstream/default branch. Use the exact tags and commits in `repo-versions.json`; see the [release policy](maintenance/release-policy.md) and [v0.1.2 record](maintenance/v0.1.2.md).

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
- Keep passwords and model keys local. Do not expose development services to untrusted networks.

[Detailed TUI guide](semantic-installer-README.md) · [Troubleshooting notes](NOTES.md)

## License

Copyright 2026 InsightOS. First-party code is covered by [Apache-2.0](LICENSE); see [NOTICE](NOTICE) and [license scope](LICENSE_SCOPE.md) for third-party code, models, and binary assets.
