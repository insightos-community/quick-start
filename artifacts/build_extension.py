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

"""Backfill real digests into an extension manifest and stage a release tree.

Reads the versioned manifest template ``extensions/<id>/extension.json``, fills
every artifact's ``sha256`` and ``size`` from the built packages, marks artifacts
past GitHub's 2 GiB asset limit as OSS-only, and writes an immutable staging
tree::

    <output>/extensions/<id>/<version>/extension.json
    <output>/extensions/<id>/<version>/<artifact>      (hardlink, or a copy)
    <output>/extensions/<id>/stable.json               ({"version": ...})

Artifact URLs are always rewritten to a bare file name, so one manifest serves
both the OSS prefix and the flat GitHub Release. The staged manifest is re-parsed
with ``extension.parse`` and re-verified with ``extension.stage_artifact`` before
the command exits, so a broken digest never reaches a channel.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
EXTENSIONS = REPO_ROOT/'extensions'

import importlib.util

_spec = importlib.util.spec_from_file_location('extension_manifest', HERE/'runtime/extension.py')
extension = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extension)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while block := handle.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def artifact_records(manifest):
    """Yield ``(label, record, url)`` for the runtime pack and components."""
    rows = [('runtime.pack', manifest['runtime']['pack'])]
    for index, component in enumerate(manifest['components']):
        rows.append((f"components[{index}] {component['role']}", component))
    return [(label, record, record['url']) for label, record in rows]


def mark_oss_only(record, size):
    """GitHub refuses a single asset at or above 2 GiB; pin such artifacts to OSS."""
    if size > extension.GITHUB_ASSET_LIMIT:
        record['hosts'] = ['oss']
        return True
    return False


def backfill(manifest, package_dir, report=print):
    """Fill ``sha256``/``size`` from ``package_dir``; return the staged inventory."""
    package_dir = Path(package_dir)
    inventory, names = [], set()
    for label, record, url in artifact_records(manifest):
        if '/' in url or '\\' in url or not url:
            raise ValueError(f'{label}: 产物名必须是平铺文件名，便于 GitHub Release 平铺上传')
        name = url
        if name in names:
            raise ValueError(f'{label}: 产物名重复: {name}')
        names.add(name)
        source = package_dir/name
        if not source.is_file():
            raise FileNotFoundError(f'{label}: 缺少产物 {source}')
        size, checksum = source.stat().st_size, digest(source)
        record['url'] = name
        record['sha256'] = checksum
        record['size'] = size
        oss_only = mark_oss_only(record, size)
        inventory.append({'label': label, 'name': name, 'size': size,
                          'sha256': checksum, 'path': source, 'oss_only': oss_only})
        report(f'回填 {label}: {name} {size} bytes {checksum[:12]}…' +
               ('（仅 OSS，超过 GitHub 2 GiB 上限）' if oss_only else ''))
    return inventory


def place(source, target, link=True):
    """Hardlink ``source`` to ``target`` when possible; fall back to a copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    if link:
        try:
            os.link(source, target)
            return 'link'
        except OSError:
            pass
    shutil.copyfile(source, target)
    return 'copy'


def stage(manifest, inventory, output, version, link=True, report=print):
    """Write the immutable staging tree and return the version directory."""
    output = Path(output).resolve()
    folder = output/'extensions'/manifest['id']/version
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for item in inventory:
        place(item['path'], folder/item['name'], link=link)
    manifest_path = folder/extension.MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    pointer = output/'extensions'/manifest['id']/extension.STABLE_POINTER
    pointer.write_text(json.dumps({'id': manifest['id'], 'version': version,
                                   'tag': extension.github_tag(manifest['id'], version)},
                                  ensure_ascii=False, indent=2) + '\n')
    report(f'staging: {folder}')
    return folder


def verify_staged(folder, version, report=print):
    """Re-parse and re-verify the staged manifest; raise on any inconsistency."""
    parsed = extension.parse((folder/extension.MANIFEST_NAME).read_text(),
                             source='oss')
    if parsed['version'] != version:
        raise ValueError(f'staged manifest version {parsed["version"]} != {version}')
    artifacts = [('runtime.pack', parsed['runtime']['pack'])]
    artifacts += [(f"{item['role']}/{item['id']}", item) for item in parsed['components']]
    for label, artifact in artifacts:
        path = extension.stage_artifact(artifact, folder/extension.artifact_name(artifact))
        report(f'校验 {label}: {path.name} 一致')
    return parsed


def build(identifier, version, package_dir, output, manifest_path=None, link=True,
          report=print):
    """Backfill, stage and verify one extension; returns the version directory."""
    output = Path(output).resolve()
    if output == REPO_ROOT or REPO_ROOT in output.parents:
        raise ValueError('staging 输出必须放在仓库之外，避免把多 GB 产物带进版本库')
    template_path = Path(manifest_path) if manifest_path else EXTENSIONS/identifier/extension.MANIFEST_NAME
    if not template_path.is_file():
        raise FileNotFoundError(f'缺少清单模板: {template_path}')
    manifest = json.loads(template_path.read_text())
    if manifest.get('id') != identifier:
        raise ValueError(f'清单 id({manifest.get("id")}) 与请求的 ({identifier}) 不一致')
    manifest['version'] = version
    inventory = backfill(manifest, package_dir, report=report)
    folder = stage(manifest, inventory, output, version, link=link, report=report)
    verify_staged(folder, version, report=report)
    report(f'完成: {identifier} {version}，{len(inventory)} 个产物已入 staging')
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--id', required=True, help='扩展标识，例如 libero / isaac')
    parser.add_argument('--version', required=True, help='扩展版本，例如 0.1.0')
    parser.add_argument('--package-dir', dest='package_dir', type=Path, required=True,
                        help='六个产物所在目录')
    parser.add_argument('--output', type=Path, required=True, help='staging 输出目录（在仓库外）')
    parser.add_argument('--manifest', type=Path, help='覆盖清单模板路径')
    parser.add_argument('--copy', action='store_true', help='复制产物而不是硬链接')
    args = parser.parse_args()
    build(args.id, args.version, args.package_dir, args.output,
          manifest_path=args.manifest, link=not args.copy)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('build_extension 失败:', error, file=sys.stderr)
        raise SystemExit(1)
