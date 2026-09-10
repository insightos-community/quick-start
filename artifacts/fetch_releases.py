#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Download component releases pinned by repo-versions.json, verifying every asset."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def download(url, destination, limit=2 * 1024**3):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('Downloads require HTTPS')
    headers = {'User-Agent': 'Semantic-Installer'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token and urllib.parse.urlsplit(url).netloc == 'api.github.com':
        headers['Authorization'] = 'Bearer ' + token
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                    count = 0
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > limit:
                            raise ValueError('Download exceeds size limit')
                        output.write(block)
            temporary.replace(destination)
            return
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
        finally:
            if 'temporary' in locals():
                temporary.unlink(missing_ok=True)


def checksums(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        checksum, name = line.split('  ', 1)
        if not re.fullmatch(r'[0-9a-f]{64}', checksum) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]*', name):
            raise ValueError('Invalid checksum entry')
        if name in result:
            raise ValueError('Duplicate checksum entry')
        result[name] = checksum
    if 'release.json' not in result:
        raise ValueError('Missing release identity checksum')
    return result


def extract(archive, destination):
    """Only regular files/directories, with no duplicate or escaping paths."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Extraction destination must be new')
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        seen = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in member.name:
                raise ValueError('Unsafe archive path')
            if not (member.isfile() or member.isdir()) or str(path) in seen:
                raise ValueError('Archive contains links, special files or duplicate paths')
            seen.add(str(path))
            total += member.size
            if total > 8 * 1024**3:
                raise ValueError('Archive exceeds extracted size limit')
        destination.mkdir(parents=True)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def fetch(manifest, cache):
    manifest = json.loads(Path(manifest).read_text())
    records = {}
    cache = Path(cache)
    for local, pin in manifest['repos'].items():
        match = re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git', pin['url'])
        if not match or not re.fullmatch(r'v[0-9][0-9A-Za-z._+-]*', pin['ref']) or not re.fullmatch(r'[0-9a-f]{40}', pin['commit']):
            raise ValueError('Invalid repository pin: ' + local)
        repo = match[1].replace('/Sementic-Framework', '/Semantic-Framework')
        tag = pin['ref']
        directory = cache / repo.replace('/', '--') / tag
        directory.mkdir(parents=True, exist_ok=True)
        print(f'Download {repo}@{tag}', flush=True)
        download(f'https://api.github.com/repos/{repo}/releases/tags/{tag}', directory/'github-release.json', 4*1024**2)
        release = json.loads((directory/'github-release.json').read_text())
        if release['draft'] or release['tag_name'] != tag:
            raise ValueError('Unexpected release identity')
        assets = {a['name']: a for a in release['assets']}
        if len(assets) != len(release['assets']) or 'SHA256SUMS' not in assets:
            raise ValueError('Release has ambiguous or missing assets')
        download(assets['SHA256SUMS']['browser_download_url'], directory/'SHA256SUMS', 1024**2)
        sums = checksums(directory/'SHA256SUMS')
        if set(assets) != set(sums) | {'SHA256SUMS'}:
            raise ValueError('Release assets differ from checksum inventory')
        for name, checksum in sums.items():
            path = directory/name
            if not path.is_file() or digest(path) != checksum:
                download(assets[name]['browser_download_url'], path)
            if digest(path) != checksum:
                raise ValueError('Release checksum mismatch: ' + name)
        identity = json.loads((directory/'release.json').read_text())
        if identity['tag'] != tag or identity['source_commit'] != pin['commit']:
            raise ValueError('Release source differs from pinned manifest: ' + local)
        records[local] = dict(repository=repo, tag=tag, source_commit=pin['commit'],
                              component=identity['component'], platform=identity['platform'],
                              assets=sums, directory=str(directory.resolve()))
    (cache/'release-lock.json').write_text(json.dumps(records, indent=2)+'\n')
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1]/'repo-versions.json')
    parser.add_argument('--cache', type=Path, default=Path.home()/'.cache/semantic/releases')
    args = parser.parse_args()
    fetch(args.manifest, args.cache)
