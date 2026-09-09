#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Check local bilingual entry pages and common public-document privacy risks.

This is a documentation check, not a history/media/credential security audit.
Only file names and rule names are reported; matched content is never printed.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


RULES = {
    "internal-host": re.compile(r"\b(?:git|gitlab)\.[a-z0-9.-]+|\b[a-z0-9.-]+\.feishu\.cn", re.I),
    "personal-home": re.compile(r"/home/[a-zA-Z][\w.-]*/"),
    "private-ip": re.compile(
        r"(?<![\d.])(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?![\d.])"
    ),
    "ssh-host": re.compile(r"\b[a-zA-Z][\w.-]*@(?:\d{1,3}\.){3}\d{1,3}\b"),
    "token": re.compile(r"\b(?:AKIA[A-Z0-9]{16}|LTAI[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,})\b"),
    "conflict-marker": re.compile(r"^(?:<<<<<<< |>>>>>>> |=======$)", re.M),
}


def check(root):
    manifest = json.loads((root / "repo-versions.json").read_text())
    repositories = [root] + [root / name for name in manifest["repos"]]
    errors = []
    checked = 0
    for repo in repositories:
        if not (repo / "README.md").is_file():
            errors.append((repo.relative_to(root), "missing-repository-or-readme"))
            continue
        checked += 1
        for filename in ("README.md", "README.zh-CN.md", "README.reference.md"):
            path = repo / filename
            if not path.is_file():
                errors.append((path.relative_to(root), "missing-language-or-reference"))
                continue
            content = path.read_text()
            if filename != "README.reference.md":
                for target in ("README.md", "README.zh-CN.md"):
                    if f"]({target})" not in content:
                        errors.append((path.relative_to(root), "missing-language-link"))
            for link in re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", content):
                parsed = urlsplit(link.strip("<>"))
                if parsed.scheme or link.startswith(("/", "#")):
                    continue
                target = unquote(parsed.path)
                if target and not (path.parent / target).exists():
                    errors.append((path.relative_to(root), "broken-local-link"))
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", "*.md"],
            capture_output=True, check=True,
        )
        names = set(result.stdout.decode().rstrip("\0").split("\0"))
        names.update(("README.md", "README.zh-CN.md", "README.reference.md"))
        if repo == root:
            names.add("maintenance/open-source-readiness.md")
        for name in sorted(names):
            if not name or name.startswith(("_vendor/", "assets/vendor/")):
                continue
            path = repo / name
            if not path.is_file():
                continue
            content = path.read_text()
            for label, pattern in RULES.items():
                if pattern.search(content):
                    errors.append((path.relative_to(root), label))
    return checked, sorted(set(errors), key=lambda item: (str(item[0]), item[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    checked, errors = check(args.root.resolve())
    for path, rule in errors:
        print(f"{path}: {rule}")
    print(f"Checked {checked} repositories; {len(errors)} documentation findings.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
