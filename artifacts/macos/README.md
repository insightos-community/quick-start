# Native macOS development

Initial target: Apple Silicon (arm64), validated on the GitHub `macos-15`
runner. This directory starts the native port; it is not a released macOS
installer, and the public installation scripts still require Linux.

The shared dependency baseline uses CPython 3.13.15, NumPy 2.3.5,
Pinocchio 3.9.0, Ruckig 0.19.4 and MuJoCo 3.4.0. The lock includes hashes
for transitive dependencies and CI only accepts binary wheels. It does
not require a Linux VM, musl, or Rosetta.

On an Apple Silicon Mac with uv available:

```sh
uv venv --python 3.13.15 .venv-macos
uv pip sync --python .venv-macos/bin/python --require-hashes --only-binary :all: artifacts/macos/requirements.lock
.venv-macos/bin/python artifacts/macos/smoke.py
```

`Native macOS foundation` validates Pinocchio dynamics, Ruckig trajectories
and MuJoCo physics in that same environment, and builds/tests the pinned
Framework and gateway as native arm64 executables. CI artifacts are development
outputs, not signed application bundles or production releases.

MuJoCo Runtime's native macOS workflow tests the service and CPU physics.
CGL rendering and the real pallet scene have a separate physical-Mac qualification
job: the standard hosted runner returned `CGLError: invalid pixel format`. CGL uses macOS OpenGL; the Linux Mesa/EGL bundle is not needed.
Hosted-runner rendering evidence alone does not qualify physical Apple GPU
performance. Validate the real pallet scene and camera streams on a physical
Mac before advertising full simulation support.

AbilityFramework network discovery and system load sampling are being ported and
compiled in its own macOS CI. Remaining installer work includes validating and
packaging its native dependencies, replacing Linux `/proc` process identity checks, packaging
Mach-O/dylib dependencies, portable service management, and signing/notarization
for distribution. Linux's current release manifest remains the supported default.

A dedicated Mac mini is not a runtime requirement: each user runs Semantic on
their own Mac. GitHub macOS runners can build/test the port. A physical MacBook,
iMac or Mac mini is useful for desktop installation, graphics and long-running
validation; it need not be a separate server.
