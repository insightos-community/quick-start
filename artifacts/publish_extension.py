#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Publish one staged extension to OSS and mirror it to a GitHub Release.

Input is the staging tree produced by ``build_extension.py``. OSS is the primary
channel: every object under ``extensions/<id>/<version>/`` is immutable and the
mutable ``extensions/<id>/stable.json`` pointer is promoted only after all
immutable objects verify. GitHub is a mirror whose flat assets carry the files
that fit under its 2 GiB per-asset limit; oversized artifacts stay OSS-only.

The GitHub leg shells out to ``gh``; the OSS leg reuses ``oss_client.Store`` so
the publish discipline (metadata sha256, ACL check, forbid overwrite) is shared.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

from oss_client import DEFAULT_CONFIG, Store, digest, read_config, root_error, \
    extension_prefix, extension_pointer

import importlib.util

_spec = importlib.util.spec_from_file_location('extension_manifest', HERE/'runtime/extension.py')
extension = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extension)

SAFE_ASSET = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')


def load_staging(staging, identifier, version):
    """Read and validate the staged manifest; return ``(folder, manifest, parsed)``."""
    folder = Path(staging)/'extensions'/identifier/version
    manifest_path = folder/extension.MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f'staging 缺少清单: {manifest_path}')
    text = manifest_path.read_text()
    parsed = extension.parse(text, source='oss')
    if parsed['id'] != identifier or parsed['version'] != version:
        raise ValueError(f'staging 清单身份不符: {parsed["id"]} {parsed["version"]}')
    return folder, json.loads(text), parsed


def manifest_artifacts(parsed):
    """``(label, artifact)`` for the runtime pack and every component, in order."""
    rows = [('runtime', parsed['runtime']['pack'])]
    rows += [(f"{item['role']}/{item['id']}", item) for item in parsed['components']]
    return rows


def mirror_assets(folder, parsed):
    """GitHub Release assets: the manifest plus every artifact GitHub may carry."""
    paths = [folder/extension.MANIFEST_NAME]
    for label, artifact in manifest_artifacts(parsed):
        hosts = artifact.get('hosts') or list(extension.SOURCES)
        if 'github' not in hosts:
            continue
        if artifact['size'] > extension.GITHUB_ASSET_LIMIT:
            continue
        paths.append(folder/extension.artifact_name(artifact))
    return paths


def sha256sums(paths):
    """The ``sha256sum -c`` body for the given files, in the order supplied."""
    return ''.join(f'{digest(path)}  {Path(path).name}\n' for path in paths)


def github_asset_names(paths):
    """Validate every asset name is flat and safe; return them in order."""
    names = []
    for path in paths:
        name = Path(path).name
        if not SAFE_ASSET.fullmatch(name):
            raise ValueError('GitHub 资产名不安全或含目录: ' + name)
        if name in names:
            raise ValueError('GitHub 资产名重复: ' + name)
        names.append(name)
    return names


def release_metadata(parsed, identifier, version, assets):
    """A ``release.json`` recording the tag, channel and per-file digests."""
    return {
        'schema_version': 1,
        'id': identifier,
        'version': version,
        'tag': extension.github_tag(identifier, version),
        'channel': 'github',
        'manifest_sha256': digest(assets[0]),
        'assets': [{'name': Path(path).name, 'size': Path(path).stat().st_size,
                    'sha256': digest(path)}
                   for path in assets],
    }


def immutable_objects(folder, identifier, version):
    """``(relative OSS key, path)`` for every immutable staged object."""
    prefix = extension_prefix(identifier, version)
    objects = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        objects.append((prefix + '/' + path.name, path))
    return objects


def publish_oss(store, folder, identifier, version, report=print):
    """Upload the immutable prefix, then promote ``stable.json`` last."""
    for relative, path in immutable_objects(folder, identifier, version):
        store.upload(path, relative)
    pointer = folder.parent/extension.STABLE_POINTER
    if not pointer.is_file():
        raise FileNotFoundError(f'staging 缺少稳定版指针: {pointer}')
    store.upload(pointer, extension_pointer(identifier), mutable=True)
    report('已发布 OSS:', extension_pointer(identifier), '->', version)


def github_command(tag, assets):
    """The ``gh release create`` argv that uploads flat assets."""
    return ['gh', 'release', 'create', tag, '--title', tag, '--notes',
            f'Immutable mirror of extension {tag}.', *[str(path) for path in assets]]


def publish_github(folder, parsed, identifier, version, repo, runner=None, report=print):
    """Create a GitHub Release with the mirrorable assets; returns the tag.

    ``--repo`` selects the target repository; the tag is ``ext-<id>-v<version>``.
    """
    tag = extension.github_tag(identifier, version)
    if not re.fullmatch(r'ext-[a-z0-9-]+-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', tag):
        raise ValueError('非法的扩展 Release tag: ' + tag)
    runner = runner or (lambda command: subprocess.run(command, check=True))
    with tempfile.TemporaryDirectory(prefix='semantic-extension-release-') as work:
        work = Path(work)
        assets = mirror_assets(folder, parsed)
        github_asset_names(assets)
        (work/'SHA256SUMS').write_bytes(sha256sums(assets).encode())
        assets = assets + [work/'SHA256SUMS']
        metadata = release_metadata(parsed, identifier, version, assets)
        (work/'release.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        assets = assets + [work/'release.json']
        github_asset_names(assets)
        command = github_command(tag, assets)
        report('GitHub Release:', tag, 'repo', repo, f'{len(assets)} 个资产')
        runner(command + ['--repo', repo])
    return tag


def publish(staging, identifier, version, channels, repo=None, config=DEFAULT_CONFIG,
            runner=None, report=print):
    """Publish the staged extension to the requested channels."""
    folder, _, parsed = load_staging(staging, identifier, version)
    if 'oss' in channels:
        store = Store(read_config(config))
        publish_oss(store, folder, identifier, version, report=report)
    if 'github' in channels:
        publish_github(folder, parsed, identifier, version, repo or extension.DEFAULT_GITHUB_REPO,
                       runner=runner, report=report)
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--staging', type=Path, required=True, help='build_extension.py 的输出目录')
    parser.add_argument('--channel', default='oss', help='逗号分隔：oss,github')
    parser.add_argument('--repo', default=extension.DEFAULT_GITHUB_REPO, help='GitHub 镜像仓库')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    channels = [part.strip() for part in args.channel.split(',') if part.strip()]
    unknown = [part for part in channels if part not in extension.SOURCES]
    if unknown:
        raise ValueError('未知通道: ' + ', '.join(unknown))
    staging = args.staging.expanduser().resolve()
    if not (staging/'extensions'/args.id).is_dir():
        raise ValueError(f'{staging} 下没有 extensions/{args.id}')
    publish(staging, args.id, args.version, channels, repo=args.repo, config=args.config)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        error = root_error(error)
        if isinstance(error, (ValueError, RuntimeError, FileNotFoundError)):
            print('publish_extension 失败:', error, file=sys.stderr)
        else:
            print('publish_extension 失败:', type(error).__name__,
                  'status=', getattr(error, 'status_code', None), file=sys.stderr)
        raise SystemExit(1)
