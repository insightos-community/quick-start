#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Publish verified assets through a draft, without replacing a published release."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path("release-assets")
metadata = json.loads((root / "release.json").read_text())
tag = os.environ["TARGET_TAG"]
repo = os.environ["GITHUB_REPOSITORY"]
if metadata["tag"] != tag:
    raise SystemExit("Artifact tag mismatch")
for line in (root / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ", 1)
    if Path(name).name != name or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit("Artifact checksum mismatch")
def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)
remote_sha = gh("api", f"repos/{repo}/commits/{tag}", "--jq", ".sha").strip()
if remote_sha != metadata["source_commit"]:
    raise SystemExit("Remote tag moved since the build")
existing = subprocess.run(["gh", "release", "view", tag, "--repo", repo, "--json", "isDraft"], capture_output=True, text=True)
if existing.returncode == 0 and not json.loads(existing.stdout)["isDraft"]:
    raise SystemExit("Release already published; refusing to overwrite assets")
notes = Path("release-notes.md")
notes.write_text(
    f"Built from `{tag}` (`{remote_sha}`) on GitHub-hosted Ubuntu 24.04.\n\n"
    f"Build recipe: `{metadata['build_recipe_commit']}`. [Workflow run]({metadata['workflow_run']}).\n\n"
    "Download the component archive or Python wheel below. Verify downloads with `sha256sum -c SHA256SUMS`. "
    "See `release.json` for source identity and platform information.\n\n"
    + metadata.get("backend_routing", "") + "\n\n"
    + metadata["validation_scope"] + "\n"
)
if existing.returncode:
    gh("release", "create", tag, "--repo", repo, "--verify-tag", "--draft", "--title", tag, "--notes-file", str(notes))
else:
    gh("release", "edit", tag, "--repo", repo, "--notes-file", str(notes))
gh("release", "upload", tag, "--repo", repo, "--clobber", *[str(p) for p in sorted(root.iterdir())])
gh("release", "edit", tag, "--repo", repo, "--draft=false")
print(gh("release", "view", tag, "--repo", repo, "--json", "url", "--jq", ".url"))
