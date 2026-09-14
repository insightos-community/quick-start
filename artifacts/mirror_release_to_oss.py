#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Mirror verified glibc/musl/macOS GitHub release assets to OSS without rebuilding."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from oss_client import DEFAULT_CONFIG, Store, digest, read_config, root_error

REPOSITORY = 'insightos-community/quick-start'


def identity(tag):
    match = re.fullmatch(r'musl-v([0-9]+\.[0-9]+\.[0-9]+)-([1-9][0-9]*)', tag)
    if match:
        return match[1]+'-musl.'+match[2], 'linux-musl-x86_64'
    match = re.fullmatch(r'macos-v([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)', tag)
    if match:
        return match[1], 'macos-arm64'
    match = re.fullmatch(r'v([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)', tag)
    if match:
        return match[1], 'linux-x86_64'
    raise ValueError('Use an explicit vVERSION, musl-vVERSION-REVISION or macos-vVERSION tag')


def metadata(tag):
    for attempt in range(3):
        result = subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/releases/tags/{tag}'],
                                capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            break
        time.sleep(attempt+1)
    if result.returncode:
        raise RuntimeError('GitHub release lookup failed; check gh authentication/connectivity')
    release = json.loads(result.stdout)
    if release['tag_name'] != tag or release['draft']:
        raise ValueError('Expected a published release of the selected tag')
    return release


def stage(tag, output, release):
    version, platform = identity(tag)
    folder = output/tag
    if folder.is_symlink():
        raise ValueError('Refusing a symlink release cache directory')
    folder.mkdir(parents=True, exist_ok=True)
    assets = {}
    base = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
    for asset in release['assets']:
        name = asset['name']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) or name in assets:
            raise ValueError('Unsafe or duplicate release asset name')
        if asset['browser_download_url'] != base+name:
            raise ValueError('Asset URL is outside the selected release')
        checksum = asset.get('digest', '')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', checksum or '') or not 0 < asset['size'] < 8*1024**3:
            raise ValueError('Release asset requires GitHub size and SHA256 metadata')
        target = folder/name
        if target.is_symlink():
            raise ValueError('Refusing a symlink in the download cache')
        if not (target.is_file() and target.stat().st_size == asset['size'] and digest(target) == checksum[7:]):
            fd, temporary = tempfile.mkstemp(prefix='.download-', dir=folder)
            os.close(fd)
            temporary = Path(temporary)
            try:
                print('Download:', tag, name, flush=True)
                subprocess.run(['curl', '--http1.1', '--fail', '--silent', '--show-error', '--location',
                    '--proto', '=https', '--proto-redir', '=https', '--retry', '3', '--retry-all-errors',
                    '--connect-timeout', '15', '--max-time', '1800', base+name, '-o', str(temporary)], check=True)
                if temporary.stat().st_size != asset['size'] or digest(temporary) != checksum[7:]:
                    raise ValueError('GitHub asset checksum/size mismatch: '+name)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        assets[name] = asset
    manifest = json.loads((folder/'manifest.json').read_text())
    archive = f'semantic-{version}-{platform}.tar.gz'
    if (manifest['version'], manifest['platform']) != (version, platform) or manifest['archive'] not in (archive, f'releases/{version}/{platform}/{archive}'):
        raise ValueError('Manifest identity differs from selected release')
    if assets[archive]['digest'] != 'sha256:'+manifest['sha256'] or assets[archive]['size'] != manifest['size']:
        raise ValueError('Manifest archive differs from GitHub metadata')
    sums = {}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split(None, 1)
        name = name.strip().removeprefix('*')
        if name not in assets or name in sums or assets[name]['digest'] != 'sha256:'+checksum:
            raise ValueError('Invalid release SHA256SUMS record')
        sums[name] = checksum
    if not {archive, 'manifest.json'}.issubset(sums):
        raise ValueError('Release SHA256SUMS must cover archive and manifest')
    print('Verified:', tag, archive, manifest['sha256'], flush=True)
    return manifest, [folder/name for name in assets]


def publish(store, tag, manifest, files):
    version, platform = identity(tag)
    prefix = f'releases/{version}/{platform}'
    # Preserve every GitHub asset byte-for-byte, including its SHA256SUMS.
    # Publish the manifest last, once all referenced immutable objects verify.
    for path in sorted(files, key=lambda p: (p.name == 'manifest.json', p.name)):
        store.upload(path, prefix+'/'+path.name)
    if platform in ('linux-musl-x86_64', 'linux-x86_64'):
        with tempfile.TemporaryDirectory() as temporary:
            channel_name = 'musl-stable.json' if platform == 'linux-musl-x86_64' else 'stable.json'
            channel = Path(temporary)/channel_name
            channel.write_text(json.dumps({**manifest, 'archive':prefix+'/'+Path(manifest['archive']).name}, indent=2)+'\n')
            store.upload(channel, 'channels/'+channel_name, mutable=True)
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'publish'])
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True, help='Download cache outside the checkout')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    identity(args.tag)
    output = args.output.expanduser().resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output == checkout or checkout in output.parents:
        raise ValueError('Download cache must be outside the checkout')
    output.mkdir(parents=True, exist_ok=True)
    with (output/'.mirror.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = metadata(args.tag)
        manifest, files = stage(args.tag, output, release)
        if args.action == 'publish':
            store = Store(read_config(args.config))
            prefix = publish(store, args.tag, manifest, files)
            print('Published:', store.values['OSS_DOWNLOAD_BASE'].rstrip('/')+'/'+prefix, flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        error = root_error(error)
        if isinstance(error, (ValueError, RuntimeError)):
            print(str(error))
        else:
            # SDK exceptions can contain signed URLs; never print their repr.
            print('Mirror failed:', type(error).__name__, 'status=',getattr(error,'status_code',None))
        raise SystemExit(1)
