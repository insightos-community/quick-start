#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Download a verified installer Release and forward options to its artifact installer."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

from fetch_releases import download, fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='Other arguments, such as --dir, --yes and --install-system-deps, are forwarded to install.sh.')
    parser.add_argument('--tag')
    parser.add_argument('--musl', action='store_true', help='Select the additional musl release')
    parser.add_argument('--cache', type=Path, default=Path.home()/'.cache/semantic/installers')
    args, options = parser.parse_known_args()
    if args.musl:
        return subprocess.run(['bash', str(Path(__file__).with_name('install.sh')), '--musl',
                               '--version', args.tag or 'stable', *options]).returncode
    args.tag = args.tag or 'v0.1.0'
    if not re.fullmatch(r'v[0-9][0-9A-Za-z._+-]*', args.tag):
        parser.error('Invalid release tag')
    # The verified baseline has a fixed source SHA. Other explicitly requested versions
    # resolve their tag and must agree with the publisher's release metadata.
    with tempfile.TemporaryDirectory(prefix='semantic-release-') as temporary:
        temporary = Path(temporary)
        if args.tag == 'v0.1.0':
            commit = 'ee0619eae2bce808d4b76b829dfb937440a964a4'
        else:
            download(f'https://api.github.com/repos/insightos-community/quick-start/commits/{args.tag}',temporary/'commit.json',4*1024**2)
            commit = json.loads((temporary/'commit.json').read_text())['sha']
        manifest = temporary/'manifest.json'
        manifest.write_text(json.dumps({'repos':{'quick-start':{'url':'https://github.com/insightos-community/quick-start.git','ref':args.tag,'commit':commit}}}))
        record = fetch(manifest,args.cache)['quick-start']
        directory = Path(record['directory'])
        archive = directory/f'semantic-{args.tag[1:]}-linux-x86_64.tar.gz'
        if archive.name not in record['assets'] or 'install.sh' not in record['assets']:
            raise ValueError('Release does not contain a complete installer')
        return subprocess.run(['bash',str(directory/'install.sh'),'--package',str(archive),'--sha256',record['assets'][archive.name],*options]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
