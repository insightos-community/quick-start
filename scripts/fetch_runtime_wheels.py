#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Populate the existing offline bundle cache without changing its pinned bytes.

The checked-out commit's LFS pointers supply filenames, sizes and SHA-256 locks.
Ordinary wheels may come from a package index; patched wheels and unavailable
exact builds fall back to that commit's LFS objects. First-party outputs are built
from source elsewhere. This tool never installs packages into the host Python.
"""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


SPECIAL = {"cmeel_tinyxml2_9", "cmeel_urdfdom"}
POINTER = b"version https://git-lfs.github.com/spec/v1\n"


def source_built(name):
    return re.fullmatch(r"AbilityFramework|ability_(?:py|scaffold)-.*\.whl", Path(name).name) is not None


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-C", str(repo), "-c", "core.quotePath=false", *args],
        text=True, timeout=60).strip()


def inventory(repo):
    entries = []
    revision = git(repo, "rev-parse", "HEAD")
    for name in git(repo, "lfs", "ls-files", "--name-only", revision).splitlines():
        if source_built(name):
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not re.fullmatch(r"[A-Za-z0-9_./+-]+", name):
            raise ValueError("Unsafe asset path in committed LFS manifest")
        raw = git(repo, "show", f"{revision}:{name}")
        match = re.fullmatch(r"version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)", raw)
        if not match:
            raise ValueError(f"Invalid LFS lock: {name}")
        entries.append({"path": name, "sha256": match[1], "size": int(match[2])})
    if not entries:
        raise ValueError("No third-party LFS assets found in the checked-out runtime revision")
    return revision, entries


def matches(path, entry):
    if not path.is_file() or path.stat().st_size != entry["size"]:
        return False
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == entry["sha256"]


def wheel_spec(name):
    # The committed filename pins the exact build and platform; hashes reject a
    # resolver selecting a different build with the same package version.
    parts = Path(name).name.removesuffix(".whl").split("-")
    if not name.endswith(".whl") or len(parts) not in (5, 6):
        return None
    dist, version = parts[:2]
    if dist in SPECIAL or not re.fullmatch(r"[A-Za-z0-9_.+!]+", version):
        return None
    py, abi, platform = parts[-3:]
    if py not in ("py3", "cp313"):
        return None
    args = ["--python-version", "3.13", "--implementation", "cp", "--abi", "cp313", "--abi", "none"]
    for tag in platform.split("."):
        args += ["--platform", tag]
    return f"{dist}=={version}", args


def download_wheel(entry, destination, index):
    spec = wheel_spec(entry["path"])
    if spec is None:
        return False
    requirement, target = spec
    # Temporary files are on the same filesystem for atomic publication. Failed
    # downloads never replace a pointer or an existing cache file.
    with tempfile.TemporaryDirectory(prefix=".wheel-fetch-", dir=destination.parent) as tmp:
        temp = Path(tmp)
        lock = temp / "requirements.txt"
        lock.write_text(f"{requirement} --hash=sha256:{entry['sha256']}\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_")}
        env.update(PIP_CONFIG_FILE=os.devnull, PIP_INDEX_URL=index or "https://pypi.org/simple")
        # Keep a single explicit index in the sanitized environment, never in
        # process arguments (the configured URL may contain credentials).
        cmd = [sys.executable, "-m", "pip", "download"]
        cmd += ["--disable-pip-version-check", "--no-input", "--no-deps", "--only-binary=:all:",
                "--require-hashes", "--retries", "0", "--timeout", "15", "--progress-bar", "off",
                *target, "-r", str(lock), "--dest", str(temp)]
        try:
            result = subprocess.run(cmd, env=env, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=90)
        except subprocess.TimeoutExpired:
            print("Package download timed out; using pinned LFS fallback", flush=True)
            return False
        if result.returncode:
            # Detailed diagnostics go to the installer's private step log, not
            # its form; strip URL credentials before printing.
            diagnostic = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", result.stdout or "")
            print(diagnostic[-2500:], flush=True)
            return False
        candidate = temp / destination.name
        if not matches(candidate, entry):
            print("Index result differs from the committed filename/hash; using LFS", flush=True)
            return False
        candidate.replace(destination)
        return True


def install_cached_wheel(repo, entry, candidate):
    # Import into Git LFS's content-addressed cache, then let LFS materialize the
    # original pointer. Directly replacing a pointer with a pip download leaves
    # stale index stat data in some Git/LFS versions. Do not git-add files: that
    # could replace the user's staged changes.
    with candidate.open("rb") as stream:
        # The clean filter may reopen its filename after sniffing stdin. Pass
        # the actual downloaded file, not the still-small destination pointer.
        result = subprocess.run(["git", "-C", str(repo), "lfs", "clean", "--", str(candidate)],
                                stdin=stream, stdout=subprocess.PIPE, check=True, timeout=60)
    expected = (f"version https://git-lfs.github.com/spec/v1\noid sha256:{entry['sha256']}\n"
                f"size {entry['size']}\n").encode()
    if result.stdout != expected:
        raise ValueError(f"LFS cache import differs from the revision lock: {entry['path']}")
    subprocess.run(["git", "-C", str(repo), "lfs", "checkout", "--", entry["path"]],
                   check=True, timeout=60)


def fetch(repo, source="auto", index=""):
    repo = Path(repo).resolve()
    revision, entries = inventory(repo)
    fallback = []
    failures = 0
    for number, entry in enumerate(entries, 1):
        destination = repo / entry["path"]
        if not destination.resolve().is_relative_to(repo) or destination.is_symlink():
            raise ValueError(f"Asset path escapes repository or is a symlink: {entry['path']}")
        if matches(destination, entry):
            print(f"[wheel {number}/{len(entries)}] cached: {destination.name}", flush=True)
            continue
        if destination.exists():
            with destination.open("rb") as stream:
                if not stream.read(len(POINTER)).startswith(POINTER):
                    raise ValueError(f"Local modified/corrupt asset preserved; move it aside before retrying: {entry['path']}")
        if source == "offline":
            raise ValueError(f"Offline cache missing or mismatched: {entry['path']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"[wheel {number}/{len(entries)}] preparing: {destination.name}", flush=True)
        if source == "auto" and failures < 3 and wheel_spec(entry["path"]):
            with tempfile.TemporaryDirectory(prefix=".wheel-import-", dir=destination.parent) as tmp:
                candidate = Path(tmp) / destination.name
                if download_wheel(entry, candidate, index):
                    install_cached_wheel(repo, entry, candidate)
                    print(f"[wheel {number}/{len(entries)}] package index: {destination.name}", flush=True)
                    continue
            failures += 1
            if failures == 3:
                print("Package index failed 3 times; remaining missing assets will use LFS", flush=True)
        fallback.append(entry)
    if fallback:
        if git(repo, "rev-parse", "HEAD") != revision:
            raise ValueError("Repository revision changed while downloading; retry after checkout finishes")
        print(f"[wheel LFS] downloading {len(fallback)} pinned assets", flush=True)
        subprocess.run(["git", "-C", str(repo), "lfs", "pull", "-I",
                        ",".join(e["path"] for e in fallback), "-X", ""],
                       check=True, timeout=600, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if git(repo, "rev-parse", "HEAD") != revision:
        raise ValueError("Repository revision changed while downloading; retry after checkout finishes")
    for entry in entries:
        if not matches(repo / entry["path"], entry):
            raise ValueError(f"SHA-256/size verification failed: {entry['path']}")
    print(f"[wheel {len(entries)}/{len(entries)}] verified; offline bundle cache ready", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", choices=("auto", "lfs", "offline"), default="auto")
    args = parser.parse_args()
    try:
        fetch(args.repo, args.source, os.environ.get("UV_DEFAULT_INDEX", ""))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: Runtime asset preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
