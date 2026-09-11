# Optional musl distribution

`install.sh --musl` and `install-en.sh --musl` select an additional GitHub Release for Linux x86_64. The existing default glibc package and OSS stable channel remain separate.

The distribution reuses the static application binaries, Web, models, skills and abilities from the verified `v0.1.0` installer. It replaces the Python stack with the official relocatable musl CPython 3.13.15 and musl uv 0.12.12. Robot and native MuJoCo have separate virtual environments referencing that same Python base, both with NumPy 2.3.5. Native MuJoCo's Python 3.13 wheels are built from the pinned adaptation in `mujoco-runtime`; older Python versions retain their original NumPy requirement.

`releases.json` records repository, tag, source commit and SHA-256 for every dependency release. `python-wheels.json` pins upstream PyPI wheel URLs and hashes. `upstream.json` pins the base installer, official CPython/uv distributions, MuJoCo application source and unchanged Alpine GCC runtimes. The final archive contains these locks, upstream notices, individual build manifests and `native-linkage.json`. Prefix symlinks are validated on extraction and converted to regular files in the final installer payload.

| Components | Delivery |
|---|---|
| Pinocchio 3.9.0; Boost, EigenPy, Coal, URDFDOM, OctoMap, console_bridge | Source-built Pinocchio prefix Release, including dependency source revisions and notices |
| Ruckig 0.19.4 | Audited CPython 3.13 musllinux wheel |
| Assimp, Qhull, TinyXML2, zlib | Individual source-built prefix Releases |
| MuJoCo 3.4.0 and Python GLFW binding | Source-built musllinux MuJoCo wheel and pure Python GLFW wheel |
| Mesa 25.2.7, LLVM 21.1.2, libdrm, SPIRV-Tools | Individual source-built prefix Releases |
| libelf (elfutils), Expat, libffi, libxml2, xz, Zstandard | Individual source-built prefix Releases |
| libgcc, libstdc++, libgomp | Unmodified Alpine 3.23 GCC 15.2.0-r2 runtimes with source/build recipe and license references |
| musl loader / libc | Pinned unmodified Alpine musl 1.2.5-r23, private to the instance |
| CPython and uv | Official upstream musl Releases; no fork required |

Mesa and libdrm originate on freedesktop GitLab, and elfutils was imported from its verified official source tarball. Their GitHub repositories preserve upstream origin metadata; these are source imports rather than GitHub-native forks. The other upstream libraries are GitHub forks under `insightos-community`.

## Selecting the musl runtime

New releases default to `--musl-runtime bundled`, including musl 1.2.5-r23 from the pinned Alpine image. Its binary SHA-256, upstream source archive/hash, distribution build recipe and copyright notice accompany the package. The loader and libc stay inside the instance; system `/lib` and global library settings are untouched.

`--musl-runtime system` uses the host loader at `/lib/ld-musl-x86_64.so.1` and requires musl 1.2+. Reinstalls retain the choice; switching modes requires a new directory. Older `musl-v0.1.0-1` packages still require the system loader because they do not contain the bundled runtime.

The archive retains immutable Python originals and a template with a reserved ELF interpreter field. Installation derives `python3.13-bundled` beside the existing Python standard library and fills that field with the instance's loader path. Both virtual environments use that interpreter through managed PATH entries. Its RPATH finds the bundled libraries without exposing a musl `LD_LIBRARY_PATH` to host tar, zstd or shells. Child Python processes follow the same ELF interpreter. Original payload hashes remain valid on reinstall; generated launcher integrity is checked before reuse. Instances should not be moved to a different path.

## Rendering

The included EGL/GLES Mesa build contains llvmpipe, iris, crocus, radeonsi and nouveau. `--render-backend auto` probes GPU devices with real RGB/depth rendering and falls back to llvmpipe; `software` forces llvmpipe, and `mesa-gpu` fails if hardware rendering cannot be verified. Selection is repeated when managed services start. The report is saved in the instance's `configs/musl-render.json`.

Local AMD radeonsi and software rendering have been exercised. Intel and Nouveau need hardware validation. Proprietary NVIDIA userspace drivers are not part of this musl package; use the default glibc installation for that path. The package targets headless EGL simulation, not an X11/Wayland desktop viewer. Kernel GPU drivers, firmware and `/dev/dri` permissions belong to the host.

## Build and release

`.github/workflows/musl-release.yml` assembles pinned assets inside the pinned Alpine image, audits ELF objects for glibc dependencies (including wheel contents), tests the Python 3.13 application, and installs the actual archive offline in Alpine using bundled and system musl, and in an Ubuntu 22.04 container without a system musl loader. The glibc fixture also verifies that Python subprocesses work and host tar/zstd are unaffected. The clean test exercises server/Web APIs, scene installation, management, Pinocchio/Coal/Ruckig operations and MuJoCo RGB/depth rendering. The English script also performs a real offline installation.

Only a successful `musl-vMAJOR.MINOR.PATCH-REVISION` tag build publishes a prerelease, without replacing the default latest Release. Pull requests and manual runs validate artifacts without publishing. Published assets are never overwritten.

For a local build, use the same pinned container, mount this checkout at `/src` read-only and a new working directory at `/work`, set `MUSL_TAG=musl-v0.1.0-2` and `MUSL_VERSION=0.1.0-musl.2`, then run `sh /src/artifacts/musl/build.sh`. The target host needs Bash and Python 3.10+ to start the bootstrap. `--install-system-deps` uses its configured package repositories; no source URL is replaced.
