#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Select a tested EGL driver, then exec the SAME Python with that environment."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

PROBE = Path(__file__).with_name("probe.py")
DRIVER_ENV = ("LIBGL_ALWAYS_SOFTWARE", "GALLIUM_DRIVER", "MESA_LOADER_DRIVER_OVERRIDE",
              "LIBGL_DRIVERS_PATH", "__EGL_VENDOR_LIBRARY_FILENAMES",
              "__EGL_VENDOR_LIBRARY_DIRS", "DRI_PRIME", "EGL_PLATFORM")


def libc_family():
    libraries = {Path(line.split()[-1]).name for line in
                 Path("/proc/self/maps").read_text().splitlines() if "/" in line}
    if any(name.startswith(("ld-musl-", "libc.musl-")) for name in libraries):
        return "musl"
    if platform.libc_ver()[0] == "glibc":
        return "glibc"
    raise ValueError("Cannot identify this Python's libc")


def environment(base, profile, prefix, runtime, libc):
    env = dict(base)
    env.update(MUJOCO_GL="egl", SEMANTIC_MUJOCO_GL="egl", PYOPENGL_PLATFORM="egl")
    env.pop("MUJOCO_EGL_DEVICE_ID", None)
    if profile != "system":
        if libc != "musl":
            raise ValueError("Bundled musl Mesa must be used with a musl Python")
        if prefix is None or not (prefix / "lib/libEGL.so.1").is_file():
            raise ValueError("--mesa-prefix must contain the musl Mesa lib/libEGL.so.1")
        for name in DRIVER_ENV:
            env.pop(name, None)
        paths = [str(prefix / "lib")]
        # Keep application-pinned shared dependencies (e.g. released zlib)
        # ahead of the collected Mesa dependency fallback directory.
        if base.get("LD_LIBRARY_PATH"):
            paths.append(base["LD_LIBRARY_PATH"])
        if runtime:
            if not (runtime / "lib").is_dir():
                raise ValueError("--mesa-runtime must contain a lib directory")
            paths.append(str(runtime / "lib"))
        env["LD_LIBRARY_PATH"] = ":".join(paths)
        if profile == "software":
            env.update(LIBGL_ALWAYS_SOFTWARE="1", GALLIUM_DRIVER="llvmpipe")
    return env


def run_probe(env, list_devices=False):
    try:
        result = subprocess.run([sys.executable, str(PROBE)] + (["--list"] if list_devices else []),
                                env=env, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"error": "EGL probe timed out after 30 seconds"}
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        report = {"error": f"EGL probe exited {result.returncode}: {result.stderr[-2000:]}"}
    if result.returncode and "error" not in report:
        report["error"] = f"EGL probe exited {result.returncode}"
    return report


def select(profile, base, prefix=None, runtime=None, device=None, libc=None, probe=run_probe):
    libc = libc or libc_family()
    if device is not None and (device < 0 or profile == "software"):
        raise ValueError("A nonnegative --device is only valid for GPU profiles")
    if profile == "auto":
        profiles = ["mesa-gpu", "software"] if libc == "musl" else ["system"]
        if device is not None:
            profiles = profiles[:1]  # Explicit device requests never silently fall back.
    else:
        profiles = [profile]
    attempts = []
    for candidate in profiles:
        env = environment(base, candidate, prefix, runtime, libc)
        listing = probe(env, True)
        if "error" in listing:
            attempts.append({"profile": candidate, **listing})
            continue
        indices = [device] if device is not None else range(listing["devices"])
        for index in indices:
            trial = {**env, "MUJOCO_EGL_DEVICE_ID": str(index)}
            result = probe(trial)
            if "error" not in result:
                if candidate != "system":
                    for library in ("libEGL.so", "libgallium-"):
                        paths = [Path(p) for p in result["libraries"] if Path(p).name.startswith(library)]
                        if not paths or any(not p.is_relative_to(prefix) for p in paths):
                            result["error"] = f"Unexpected {library} origin: {paths}"
                if (candidate == "mesa-gpu" or device is not None) and result["software"]:
                    result["error"] = "Driver returned software rendering; GPU acceleration is required"
                if candidate == "software" and not result["software"]:
                    result["error"] = "Software profile did not produce a software renderer"
            attempts.append({"profile": candidate, "device": index, **result})
            if "error" not in result:
                return trial, {"requested": profile, "selected": candidate, "libc": libc,
                               "device": index, "opengl": result, "attempts": attempts}
    raise RuntimeError(json.dumps({"error": "No usable rendering profile", "attempts": attempts}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("auto", "system", "mesa-gpu", "software"), default="auto")
    parser.add_argument("--mesa-prefix", type=Path)
    parser.add_argument("--mesa-runtime", type=Path)
    parser.add_argument("--device", type=int, help="EGL device index, not PCI or CUDA index")
    parser.add_argument("--check", action="store_true", help="Print diagnostics without starting an application")
    parser.add_argument("--report", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by Python arguments, e.g. -m plugin_mujoco")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.check and not command:
        parser.error("Provide --check or Python arguments after --")
    try:
        env, report = select(args.profile, os.environ,
                             args.mesa_prefix.resolve() if args.mesa_prefix else None,
                             args.mesa_runtime.resolve() if args.mesa_runtime else None,
                             args.device)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    encoded = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(encoded + "\n")
    print(encoded, file=sys.stdout if args.check else sys.stderr, flush=True)
    if not args.check:
        os.execve(sys.executable, [sys.executable, *command], env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
