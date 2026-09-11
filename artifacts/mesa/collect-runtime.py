#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Audit and collect the Mesa ELF dependency closure inside a musl container.

This collects local validation libraries, not a license-complete release archive.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def collect(prefix, output):
    output.mkdir(parents=True, exist_ok=False)
    runtime = output / "lib"
    runtime.mkdir()
    pending = []
    for path in prefix.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    pending.append(path)
    if not pending:
        raise ValueError("No Mesa ELF files found")
    seen, reports = set(), []
    env = {**os.environ, "LD_LIBRARY_PATH": str(prefix / "lib")}
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        versions = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        if re.search(r"\bGLIBC_[0-9]", versions):
            raise ValueError(f"glibc dependency in {path}")
        dynamic = subprocess.check_output(["readelf", "-d", str(path)], text=True)
        deps = subprocess.run(["ldd", str(path)], env=env, text=True, capture_output=True, check=True)
        reports.append({"path": str(path), "needed": re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "ldd": deps.stdout})
        for name, location in re.findall(r"^\s*(\S+) => (/\S+)", deps.stdout, re.M):
            if name.startswith("libc.musl-"):
                continue
            dependency = Path(location).resolve()
            pending.append(dependency)
            if not dependency.is_relative_to(prefix):
                destination = runtime / name
                if destination.exists() and destination.read_bytes() != dependency.read_bytes():
                    raise ValueError(f"Conflicting dependencies for {name}")
                shutil.copyfile(dependency, destination)
    (output / "elf-audit.json").write_text(json.dumps(reports, indent=2) + "\n")
    (output / "apk-packages.txt").write_text(subprocess.check_output(["apk", "info", "-v"], text=True))
    print(f"PASS: {len(reports)} ELF files without GLIBC symbol requirements; "
          f"{len(list(runtime.iterdir()))} external libraries collected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collect(args.prefix.resolve(), args.output.resolve())
