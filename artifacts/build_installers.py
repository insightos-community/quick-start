#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Generate standalone repository entry scripts from the canonical installers."""
import argparse
from pathlib import Path

from build_english_installer import render

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Reject stale generated installers')
    args = parser.parse_args()
    english = render()
    outputs = {
        HERE.parent/'install.sh': (HERE/'install.sh').read_text(),
        HERE.parent/'install-en.sh': english,
        HERE/'install-en.sh': english,
    }
    for path, content in outputs.items():
        if args.check:
            if not path.is_file() or path.read_text() != content or path.stat().st_mode & 0o111 != 0o111:
                raise SystemExit(f'{path.name} is stale; run python3 artifacts/build_installers.py')
        else:
            path.write_text(content)
            path.chmod(0o755)


if __name__ == '__main__':
    main()
