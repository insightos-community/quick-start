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

"""Extract a self-contained, source-free Semantic release from a built workspace.

Build machine requires Python + PyYAML, uv, Go, Node/npm, tar and zstd.
Only allowlisted artifacts are copied; never copy a live .output or an existing venv.
"""
import argparse
from dataclasses import replace
from email.parser import BytesParser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

import yaml
from build_native import elf_report, require_static

HERE = Path(__file__).resolve().parent
POINTER = b'version https://git-lfs.github.com/spec/v1'


def reject_external_models(name):
    parts = Path(name).parts
    approved = {'r1_pro', 'r1_pro_chassis', 'r1_pro_no_wheels', 'r1_pro_tote_gripper'}
    if (len(parts) >= 2 and parts[0] == 'robot' and parts[1].startswith('r1_pro')
            and parts[1] not in approved):
        raise ValueError('Unapproved Galaxea model variant; see EXTERNAL_MODELS.md')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024*1024): h.update(block)
    return h.hexdigest()


def json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def run(args, cwd=None, env=None):
    print('构建:', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def copy_file(source, dest):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f'需要普通产物文件: {source}')
    with source.open('rb') as f:
        if f.read(128).startswith(POINTER):
            raise ValueError(f'LFS 指针未替换为真实产物: {source}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    dest.chmod(0o755 if os.access(source, os.X_OK) else 0o644)


def copy_tree(source, dest):
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'拒绝复制符号链接: {path}')
        if path.is_file():
            copy_file(path, dest/path.relative_to(source))


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip(): raise ValueError(f'损坏的 Wheel: {path}')
        names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(names) != 1: raise ValueError(f'Wheel 缺少唯一元数据: {path}')
        metadata = BytesParser().parsebytes(archive.read(names[0]))
        return metadata['Name'], metadata['Version']


def build_runtime(workspace, output, python):
    """Reuse the native Runtime Pack schema; replace source-path locks with wheel-only pins."""
    runtime = workspace/'semantic-simulation/mujoco-runtime'
    spec = importlib.util.spec_from_file_location('semantic_runtime_pack_builder', runtime/'tools/build_runtime_pack.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    profile = replace(module.profile_table()['native-mujoco'], python=python)
    with tempfile.TemporaryDirectory(prefix='native-pack-', dir=HERE/'.build') as tmp:
        stage = Path(tmp)
        wheels = module.build_wheels(profile, stage, '0.4.0-dev.0')
        house = stage/'wheelhouse'
        house.mkdir()
        run(['uv', 'build', '--wheel', '--project', runtime/'packages/mujoco-visuals', '--out-dir', house])
        # uv.lock is the source of dependency versions, but local path entries cannot be shipped.
        exported = subprocess.check_output(['uv', 'export', '--project', str(runtime), '--frozen', '--no-dev',
            '--no-hashes', '--no-emit-project', '--no-emit-package', 'semantic-mujoco-visuals'], text=True)
        requirements = stage/'build-requirements.txt'
        lines = [line for line in exported.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        if any(not re.match(r'^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==', line) for line in lines):
            raise ValueError('Runtime 依赖锁包含未固定版本或源码路径')
        requirements.write_text('\n'.join(lines)+'\n')
        run(['uv', 'run', '--isolated', '--no-project', '--python', python, '--with', 'pip',
             'python', '-m', 'pip', 'download', '--only-binary=:all:', '--dest', house, '-r', requirements])
        dependencies = sorted(house.glob('*.whl'))
        lock = stage/'locks/requirements.lock'
        lock.parent.mkdir()
        lock.write_text('\n'.join(f'{name}=={version}' for name, version in sorted(wheel_metadata(w) for w in dependencies))+'\n')
        catalog, resources, smoke, verification = module.copy_metadata(profile, '0.4.0-dev.0', stage)
        # Runtime repo's authoring fixtures can lag behind the running Framework schema.
        # Ship the current Framework's validated native scene documents, not its live .output.
        (stage/'catalog').rename(stage/'legacy-catalog')
        catalog = stage/'catalog/catalog.yaml'
        catalog.parent.mkdir()
        copy_tree(workspace/'semantic-framework/configs/scenes.d/authoring/depalletizing-r1pro',
                  stage/'catalog/authoring/depalletizing-r1pro')
        doc = yaml.safe_load((workspace/'semantic-framework/configs/scenes.d/mujoco-platforms.yaml').read_text())
        doc['entries'] = [e for e in doc['entries'] if e['compatible_runtime_profile'] == 'native-mujoco']
        resources = sorted(p for p in (stage/'catalog').rglob('*') if p.is_file())
        # Current asset catalog is a development snapshot with this exact spelling.
        asset_version = json.loads((workspace/'semantic-scene/mujoco-asset/asset-catalog.v1.json').read_text())['catalog_version']
        doc['catalog_version'] = asset_version
        for entry in doc['entries']:
            for version in entry['versions']:
                if 'authoring' in version:
                    version['authoring']['asset_catalog_version'] = asset_version
        catalog.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
        record = lambda p: module.file_record(stage, p)
        manifest = dict(schema_version=1, pack_id=profile.pack_id, pack_version='0.4.0-dev.0',
            profile=profile.profile, runner=profile.runner, python_version=python, endpoint=profile.endpoint,
            hardware_requirements=profile.hardware_requirements, requirements_lock=record(lock),
            wheels=list(map(record, wheels)), wheelhouse=list(map(record, dependencies)),
            scene_catalog=record(catalog), scene_resources=list(map(record, resources)),
            licenses=list(map(record, sorted((stage/'licenses').iterdir()))), verification_files=[record(verification)],
            smoke_scene_key='palletizing_depalletizing_tote_v1', smoke_request=record(smoke),
            content_requirements=profile.content_requirements)
        (stage/'runtime-pack.yaml').write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False))
        output.parent.mkdir(parents=True, exist_ok=True)
        run(['tar', '--zstd', '-cf', output, '-C', stage, 'runtime-pack.yaml', 'wheels', 'wheelhouse',
             'locks', 'catalog', 'licenses', 'verification', 'smoke'])


def build(a):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('当前发布流程仅支持 Linux x86_64')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', a.version):
        raise ValueError('版本必须为 SemVer')
    workspace = a.workspace.resolve()
    native = a.native_dir.resolve()
    native_reports = {name: require_static(native/name) for name in
                      ('AbilityFramework', 'semantic-server', 'semantic', 'semantic-pilot', 'semantic-robot-instance')}
    output = HERE/'releases'/a.version/'linux-x86_64'
    if output.exists():
        raise ValueError('发布目录已存在，不覆盖；请使用新的 --version')
    (HERE/'.build').mkdir(exist_ok=True)
    framework = workspace/'semantic-framework'
    bundle_source = framework/'.output/robot-bundles/r1pro-mujoco-0.5.0-dev'
    for path in [framework/'.output/bin/semantic', bundle_source/'bundle.yaml']:
        if not path.is_file(): raise ValueError(f'先完成 TUI 构建: {path}')
    with tempfile.TemporaryDirectory(prefix='release-', dir=HERE/'.build') as temporary:
        payload = Path(temporary)/'payload'
        payload.mkdir()
        for name in ('semantic', 'semantic-server', 'semantic-pilot'):
            copy_file(native/name, payload/'bin'/name)
        copy_file(Path(shutil.which('uv')).resolve(), payload/'bin/uv')
        copy_file(HERE/'runtime/installer.py', payload/'installer.py')
        for name in ('install_support.py', 'uninstall.py'):
            copy_file(HERE/'runtime'/name, payload/name)
        for name in ('ios.png', 'banner.json'):
            copy_file(HERE/'assets'/name, payload/'assets'/name)
        run(['go', 'build', '-trimpath', '-o', payload/'bin/semantic-web-gateway', HERE/'gateway/main.go'],
            env={**os.environ, 'CGO_ENABLED': '0'})
        web = workspace/'semantic-web'
        if not a.skip_web_build:
            run(['npm', 'run', 'build', '--', '--outDir', str(payload/'web')], cwd=web,
                env={**os.environ, 'VITE_STUDIO_FIXTURES': 'false', 'VITE_DEVICE_FIXTURES': 'false'})
        else:
            copy_tree(web/'dist', payload/'web')
        if not (payload/'web/index.html').is_file(): raise ValueError('Web 生产构建缺失')
        bundle = payload/'robot-bundles'/bundle_source.name
        spec = yaml.safe_load((bundle_source/'bundle.yaml').read_text())
        for directory in ('bin', 'abilities', 'templates', 'wheels'):
            copy_tree(bundle_source/directory, bundle/directory)
        for name in ('AbilityFramework', 'semantic-pilot', 'semantic-robot-instance'):
            copy_file(native/name, bundle/'bin'/name)
        for name in ('bundle.yaml', 'python-requirements.lock'):
            copy_file(bundle_source/name, bundle/name)
        for name in spec['spec']['artifacts']['pythonWheels']:
            wheel_metadata(bundle/name)
        # Build-time validation prevents the missing-version readiness timeout recurring.
        skills = []
        versions = {}
        for archive in sorted((framework/'.output/v050-mujoco-refresh/robot-skills').glob('*.zip')):
            with zipfile.ZipFile(archive) as z:
                if z.testzip(): raise ValueError('损坏的 Skill ZIP')
                entries = [n for n in z.namelist() if n.endswith('/SKILL.md') or n == 'SKILL.md']
                if len(entries) != 1: raise ValueError('Skill 必须包含唯一 SKILL.md')
                metadata = yaml.safe_load(z.read(entries[0]).decode().split('---', 2)[1])
            name, version = metadata['name'], str(metadata['version'])
            if name in versions: raise ValueError('同一技能存在多个版本，请清理构建暂存目录后重建')
            versions[name] = version
            relative = 'robot-skills/'+archive.name
            copy_file(archive, payload/relative)
            skills.append(dict(name=name, version=version, path=relative))
        if set(versions) != {'grasp-object', 'semantic-navigation', 'place-object'}:
            raise ValueError('需要三个完整的 Robot Skill 发布包')
        template = (bundle/'templates/robot-deployment.yaml.tmpl').read_text()
        defaults = yaml.safe_load(template.split('\nrobot_skills:\n', 1)[1])
        if {x['name']: str(x['version']) for x in defaults} != versions:
            raise ValueError('Bundle 模板的技能版本与发布包不一致，禁止生成发布包')
        asset = workspace/'semantic-scene/mujoco-asset'
        tracked = subprocess.check_output(['git', '-C', str(asset), 'ls-files', '-z']).decode().split('\0')
        for name in filter(None, tracked):
            reject_external_models(name)
            if Path(name).parts[0] in ('robot', 'scene', 'assets') or name in (
                    'asset-catalog.v1.json', 'README.md', 'README.zh-CN.md', 'LICENSE', 'LICENSE.md',
                    'NOTICE', 'LICENSE_SCOPE.md', 'ASSET_PROVENANCE.md', 'EXTERNAL_MODELS.md'):
                copy_file(asset/name, payload/'assets/mujoco'/name)
        pack = payload/'runtime-packs/native-mujoco-0.4.0-dev.0.runtime.tar.zst'
        if a.runtime_pack:
            copy_file(a.runtime_pack.resolve(), pack)
        else:
            build_runtime(workspace, pack, a.runtime_python)
            # Explicitly reusable via --runtime-pack; not automatically reused across source changes.
            copy_file(pack, HERE/'.build/native-mujoco.runtime.tar.zst')
        cfg = yaml.safe_load((framework/'configs/semantic-server.yaml').read_text())
        json_file(payload/'defaults/server.json', cfg)
        provenance = {}
        for name in ('semantic-framework', 'semantic-web', 'semantic-robot-deployment', 'semantic-skill/robot-skill',
                     'semantic-simulation/mujoco-runtime', 'semantic-scene/mujoco-asset', 'ability-framework/abilityframework'):
            repo = workspace/name
            provenance[name] = dict(commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
                modified=bool(subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'], text=True)))
        # All application executables must be static; uv remains a low-baseline glibc tool.
        elf_records = {}
        for path in payload.rglob('*'):
            if path.is_file():
                with path.open('rb') as f:
                    is_elf = f.read(4) == b'\x7fELF'
                if is_elf:
                    report = elf_report(path)
                    if path != payload/'bin/uv':
                        require_static(path)
                    elif report['minimum_glibc'] and tuple(map(int, report['minimum_glibc'].split('.'))) > (2, 28):
                        raise ValueError('uv 构建的 glibc 基线高于 2.28；请更换兼容版本')
                    elf_records[path.relative_to(payload).as_posix()] = report
        json_file(payload/'native-linkage.json', elf_records)
        json_file(payload/'release.json', dict(schema_version=1, version=a.version, platform='linux-x86_64',
            minimum_glibc='2.28', native_linkage='static', native_binaries=native_reports,
            distribution='internal-only', bundle_name=bundle_source.name,
            robot_python='3.13', runtime_python=a.runtime_python, runtime_pack=pack.relative_to(payload).as_posix(),
            robot_skills=skills, source_revisions=provenance, created_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
        (payload/'DISTRIBUTION-NOTICE.txt').write_text(
            'Internal deployment snapshot. Assets include distribution_status=internal-only and pending licenses.\n'
            'Do not publicly redistribute until code, wheels, meshes and model licenses have been reviewed.\n'
            'No credentials, databases, user sessions, existing virtualenvs or source worktrees are included.\n')
        copy_file(HERE/'runtime/installer.py', payload/'installer.py')
        records = {p.relative_to(payload).as_posix(): digest(p) for p in sorted(payload.rglob('*')) if p.is_file()}
        json_file(payload/'files.json', records)
        output.mkdir(parents=True)
        archive = output/f'semantic-{a.version}-linux-x86_64.tar.gz'
        print('压缩发布包…', flush=True)
        with tarfile.open(archive, 'w:gz', compresslevel=3) as tar:
            for path in sorted(payload.rglob('*')):
                if path.is_file():
                    info = tar.gettarinfo(str(path), arcname=path.relative_to(payload).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    with path.open('rb') as f: tar.addfile(info, f)
        checksum = digest(archive)
        Path(str(archive)+'.sha256').write_text(f'{checksum}  {archive.name}\n')
        meta = dict(schema_version=1, version=a.version, platform='linux-x86_64', distribution='internal-only',
                    archive=archive.relative_to(HERE).as_posix(), sha256=checksum, size=archive.stat().st_size)
        json_file(output/'manifest.json', meta)
        shutil.copyfile(payload/'release.json', output/'release.json')
        json_file(HERE/'channels/stable.json', meta)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print('发布包已生成；没有上传任何文件。')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, default=HERE.parent)
    p.add_argument('--version', required=True)
    p.add_argument('--runtime-python', default='3.10.19')
    p.add_argument('--runtime-pack', type=Path, help='Reuse a previously verified native Runtime Pack')
    p.add_argument('--native-dir', type=Path, default=HERE/'.build/native-static',
                   help='Directory produced by build_native.py; dynamic application binaries are rejected')
    p.add_argument('--skip-web-build', action='store_true')
    build(p.parse_args())
