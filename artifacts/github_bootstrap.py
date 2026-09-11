# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""GitHub Release and LFS helpers embedded in the standalone English installer."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

GITHUB_INSTALLER_REPO = 'insightos-community/quick-start'
GITHUB_ASSET_REPO = 'insightos-community/mujoco-asset'
GITHUB_DEFAULT_TAG = 'v0.1.0'
GITHUB_BASELINE_COMMIT = 'ee0619eae2bce808d4b76b829dfb937440a964a4'
LFS_POINTER_PREFIX = b'version https://git-lfs.github.com/spec/v1\n'


def github_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def github_archive(work, version, download, requested_sha=None):
    tag = GITHUB_DEFAULT_TAG if version == 'stable' else 'v' + version.removeprefix('v')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9._+-]*)', tag):
        raise ValueError('Invalid GitHub release version')
    base = f'https://github.com/{GITHUB_INSTALLER_REPO}/releases/download/{tag}/'
    download(base+'SHA256SUMS', work/'SHA256SUMS', 1024*1024)
    sums = {}
    for line in (work/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        if not re.fullmatch(r'[a-f0-9]{64}', checksum) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]*', name) or name in sums:
            raise ValueError('Invalid GitHub release checksum inventory')
        sums[name] = checksum
    download(base+'release.json', work/'release.json', 1024*1024)
    if github_digest(work/'release.json') != sums.get('release.json'):
        raise ValueError('GitHub release metadata checksum mismatch')
    metadata = json.loads((work/'release.json').read_text())
    if (metadata.get('tag') != tag or metadata.get('version') != tag[1:] or
            metadata.get('component') != 'semantic-installer' or metadata.get('platform') != 'linux-x86_64'):
        raise ValueError('GitHub release identity or platform mismatch')
    if tag == GITHUB_DEFAULT_TAG and metadata.get('source_commit') != GITHUB_BASELINE_COMMIT:
        raise ValueError('GitHub release differs from the verified source baseline')
    name = f'semantic-{tag[1:]}-linux-x86_64.tar.gz'
    expected = sums.get(name)
    if expected is None or (requested_sha and requested_sha != expected):
        raise ValueError('GitHub archive checksum is missing or differs from --sha256')
    archive = work/name
    download(base+name, archive, 8*1024**3)
    # The canonical bootstrap verifies this digest again before extracting anything.
    if github_digest(archive) != expected:
        raise ValueError('GitHub archive SHA256 mismatch')
    return archive, expected


class GithubHTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('GitHub LFS refuses non-HTTPS redirects')
        redirected = super().redirect_request(request, response, code, message, headers, newurl)
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(request.full_url).netloc:
            for name in list(redirected.headers):
                if name.lower() in ('authorization', 'cookie'):
                    redirected.remove_header(name)
        return redirected


def github_open(request):
    if urllib.parse.urlsplit(request.full_url).scheme != 'https':
        raise ValueError('GitHub LFS requires HTTPS')
    return urllib.request.build_opener(GithubHTTPSRedirect()).open(request, timeout=60)


def github_lfs_object(pointer, destination, expected):
    match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?', pointer)
    if not match:
        raise ValueError('Invalid Git LFS pointer')
    oid, size = match[1].decode(), int(match[2])
    if oid != expected or not 0 < size <= 2*1024**3:
        raise ValueError('LFS pointer differs from the verified payload inventory')
    data = json.dumps({'operation':'download', 'transfers':['basic'], 'objects':[{'oid':oid,'size':size}]}).encode()
    request = urllib.request.Request(f'https://github.com/{GITHUB_ASSET_REPO}.git/info/lfs/objects/batch',
                                    data=data, headers={'Accept':'application/vnd.git-lfs+json', 'Content-Type':'application/vnd.git-lfs+json'})
    with github_open(request) as response:
        batch = json.loads(response.read(1024*1024))
    objects = batch.get('objects', [])
    if len(objects) != 1 or objects[0].get('oid') != oid or objects[0].get('size') != size or 'error' in objects[0]:
        raise ValueError('GitHub LFS returned an unexpected object')
    action = objects[0]['actions']['download']
    request = urllib.request.Request(action['href'], headers=action.get('header', {}))
    count = 0
    with github_open(request) as response, destination.open('wb') as target:
        while block := response.read(1024*1024):
            count += len(block)
            if count > size:
                raise ValueError('GitHub LFS object exceeds its declared size')
            target.write(block)
    if count != size or github_digest(destination) != oid:
        raise ValueError('GitHub LFS size or SHA256 mismatch')


def hydrate_github_assets(payload, download):
    """Restore missing/LFS-pointer assets using immutable pins and original file hashes.

    Complete Release archives already contain the LFS objects, so need no extra
    model downloads. Neither files.json nor the archive itself is rewritten.
    """
    if not (payload/'release-lock.json').is_file():
        return 0  # Older explicitly supplied packages have no GitHub provenance.
    records = json.loads((payload/'files.json').read_text())
    pending = []
    for name, checksum in records.items():
        if not name.startswith('assets/mujoco/'):
            continue
        relative = Path(name.removeprefix('assets/mujoco/'))
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or not re.fullmatch(r'[a-f0-9]{64}', checksum):
            raise ValueError('Invalid asset inventory path or checksum')
        target = payload/name
        if target.is_file():
            with target.open('rb') as source:
                if not source.read(128).startswith(LFS_POINTER_PREFIX):
                    continue
        # Generated release metadata is not a Git-tracked asset.
        if relative.parts[0] not in ('robot','scene','assets','asset-catalog.v1.json'):
            raise ValueError('Missing non-source asset metadata')
        pending.append((relative, target, checksum))
    if not pending:
        return 0
    pin = json.loads((payload/'release-lock.json').read_text())['semantic-scene/mujoco-asset']
    commit = pin['source_commit']
    if pin['repository'] != GITHUB_ASSET_REPO or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Invalid pinned GitHub asset repository')
    with tempfile.TemporaryDirectory(prefix='github-lfs-', dir=payload.parent) as temporary:
        for relative, target, checksum in pending:
            staged = Path(temporary)/'asset'
            url = f'https://raw.githubusercontent.com/{GITHUB_ASSET_REPO}/{commit}/' + urllib.parse.quote(relative.as_posix(), safe='/')
            download(url, staged, 2*1024**3)
            with staged.open('rb') as source:
                pointer = source.read(1024)
            if pointer.startswith(LFS_POINTER_PREFIX):
                github_lfs_object(pointer, staged, checksum)
            if github_digest(staged) != checksum:
                raise ValueError('GitHub asset differs from the verified payload SHA256')
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            target.chmod(0o644)
    return len(pending)
