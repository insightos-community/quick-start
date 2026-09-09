# Build and troubleshooting notes

[English overview](README.md) | [中文概览](README.zh-CN.md)

These notes cover the current quick-start build chain. Use the manifest and actual tool output as the version authority, not an old incident's branch or issue number.

## Environments and assets

- Native MuJoCo uses a separate Python 3.10 environment; Robot Bundle Wheels use Python 3.13.
- AbilityFramework, ability-py, and ability-scaffold are built from source. Fetch scene assets and remaining third-party Wheels with Git LFS.
- A Wheel must be a valid archive, not an LFS pointer. Quick-start validates archives and copies the SDK Wheel to both the runtime seed root and selected base bundle.
- Do not upgrade native Wheels independently: Pinocchio, urdfdom, tinyxml2, and related shared-library versions must match the bundle.
- Source system setup uses apt. For deployment using other package managers, consult [artifact portability](artifacts/PORTABILITY.md).

## Running the stack

- Keep temporary package files and their destination on a compatible filesystem. A cross-device rename can fail with `EXDEV`; the installer configures a workspace temporary directory.
- Web uses the WebSocket base URL; Pilot uses its dedicated `/ws/pilot` endpoint.
- Build and activate the Robot Bundle before startup, then publish required Robot Skills after Server starts. These operations are independent.
- Configure model-provider credentials in Studio, not in tracked files. Login uses the administrator password configured for the instance.
- After rebuilding or changing active runtime configuration, restart affected services and refresh the browser.

## Recovery

Each step writes a log under `.tui-logs/`. Read the failing step's log before rerunning it. Validate source products before restarting Bundle assembly.

Inspect a cleanup preview before applying any workflow/database cleanup. Stop affected tasks and Robots first, retain backups, and never treat an apparently idle process as proof that it is safe to delete.
