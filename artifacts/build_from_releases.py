#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Assemble the installer from pinned component Releases; compile only its tiny Web gateway."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

import yaml
from build_native import elf_report, require_static
from fetch_releases import digest, download, extract, fetch

HERE = Path(__file__).resolve().parent


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)


def build(args):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', args.version):
        raise ValueError('Version must be SemVer')
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Output must be a new directory')
    records = fetch(args.manifest, args.cache)
    with tempfile.TemporaryDirectory(prefix='semantic-assembly-') as temporary:
        temporary = Path(temporary)
        payload = temporary/'payload'
        payload.mkdir()
        components = {}
        for local, record in records.items():
            directory = Path(record['directory'])
            metadata = json.loads((directory/'release.json').read_text())
            for dep in metadata.get('dependencies', []):
                matches = [r for k, r in records.items() if k == dep.get('component') or r['repository'] == dep.get('repository')]
                if len(matches) != 1 or matches[0]['source_commit'] != dep['source_commit']:
                    raise ValueError('Incompatible component dependency: '+local)
            # All component payload archives use their component identity, not Python sdist names.
            archive = f"{record['component']}-{record['tag']}-{record['platform']}.tar.gz"
            if archive in record['assets']:
                dest = temporary/'components'/record['component']
                extract(directory/archive, dest)
                components[local] = dest
            notice = payload/'notices'/record['component']
            for root in (directory, components.get(local)):
                if root is None:
                    continue
                for p in root.iterdir():
                    if p.name.startswith(('LICENSE', 'NOTICE')) or p.name in ('third-party-licenses','ASSET_PROVENANCE.md','EXTERNAL_MODELS.md'):
                        copy(p, notice/p.name)
        framework = components['semantic-framework']
        copy(framework/'bin', payload/'bin')
        copy(components['semantic-web']/'web', payload/'web')
        if not (payload/'web/index.html').is_file():
            raise ValueError('Missing production Web')
        copy(components['semantic-scene/mujoco-asset'], payload/'assets/mujoco')
        deployment = components['semantic-robot-deployment']
        bundle_name = 'r1pro-mujoco-0.5.0-dev'
        bundle = payload/'robot-bundles'/bundle_name
        copy(deployment/'type-packages/r1pro-mujoco', bundle)
        for source in (deployment/'bin/semantic-robot-instance', framework/'bin/semantic-pilot',
                       components['ability-framework/abilityframework']/'bin/AbilityFramework'):
            copy(source, bundle/'bin'/source.name)
        copy(components['semantic-ability/r1pro-ability']/'abilities', bundle/'abilities')
        wheel_sources = {}
        for record in records.values():
            for p in Path(record['directory']).glob('*.whl'):
                wheel_sources[p.name] = p
        for p in components['semantic-ability/ability-runtime'].rglob('*.whl'):
            if p.name in wheel_sources and digest(p) != digest(wheel_sources[p.name]):
                raise ValueError('Conflicting wheel: '+p.name)
            wheel_sources[p.name] = p
        spec = yaml.safe_load((bundle/'bundle.yaml').read_text())
        for relative in spec['spec']['artifacts']['pythonWheels']:
            if not re.fullmatch(r'wheels/[A-Za-z0-9_.+-]+\.whl', relative):
                raise ValueError('Invalid bundle wheel path')
            wheel = wheel_sources[Path(relative).name]
            with zipfile.ZipFile(wheel) as archive:
                if archive.testzip():
                    raise ValueError('Corrupt wheel: '+wheel.name)
            copy(wheel, bundle/relative)
        for ability in spec['spec']['artifacts']['abilities']:
            if not (bundle/ability['file']).is_file():
                raise ValueError('Missing ability ZIP')
        copy(components['semantic-skill/robot-skill']/'robot-skills', payload/'robot-skills')
        skills = []
        for p in sorted((payload/'robot-skills').glob('*.zip')):
            with zipfile.ZipFile(p) as archive:
                if archive.testzip():
                    raise ValueError('Corrupt skill ZIP')
                meta = yaml.safe_load(archive.read('SKILL.md').decode().split('---', 2)[1])
            skills.append(dict(name=meta['name'], version=str(meta['version']), path='robot-skills/'+p.name))
        defaults = yaml.safe_load((bundle/'templates/robot-deployment.yaml.tmpl').read_text().split('\nrobot_skills:\n',1)[1])
        if {s['name']: s['version'] for s in skills} != {s['name']: str(s['version']) for s in defaults}:
            raise ValueError('Skill ZIP versions differ from the deployment template')
        pack = 'runtime-packs/native-mujoco-0.4.0-dev.0.runtime.tar.zst'
        copy(components['semantic-simulation/mujoco-runtime']/Path(pack).name, payload/pack)
        pin = records['semantic-framework']
        download(f"https://raw.githubusercontent.com/{pin['repository']}/{pin['source_commit']}/configs/semantic-server.yaml", temporary/'server.yaml', 1024**2)
        write_json(payload/'defaults/server.json', yaml.safe_load((temporary/'server.yaml').read_text()))
        source = args.quick_start.resolve()
        for name in ('installer.py','install_support.py','uninstall.py'):
            copy(source/'artifacts/runtime'/name, payload/name)
        for name in ('ios.png','banner.json'):
            copy(source/'artifacts/assets'/name, payload/'assets'/name)
        copy(source/'LICENSE', payload/'LICENSE')
        copy(args.manifest, payload/'repo-versions.json')
        subprocess.run(['go','build','-trimpath','-o',str(payload/'bin/semantic-web-gateway'),str(source/'artifacts/gateway/main.go')],
                       env={**os.environ,'CGO_ENABLED':'0'}, check=True)
        uv = Path(shutil.which('uv')).resolve()
        uv_version = subprocess.check_output([str(uv),'--version'], text=True).split()[1]
        if uv_version != '0.12.12':
            raise ValueError('Assembly requires uv 0.12.12')
        copy(uv, payload/'bin/uv')
        for license in ('LICENSE-APACHE','LICENSE-MIT'):
            download(f'https://raw.githubusercontent.com/astral-sh/uv/0.12.12/{license}',payload/'notices/uv'/license,1024**2)
        linkage = {}
        for p in sorted(payload.rglob('*')):
            if p.is_file():
                with p.open('rb') as stream:
                    native = stream.read(4) == b'\x7fELF'
                if native:
                    report = elf_report(p) if p.name == 'uv' else require_static(p)
                    if report['machine'] != 'x86_64' or (report['minimum_glibc'] and tuple(map(int,report['minimum_glibc'].split('.'))) > (2,28)):
                        raise ValueError('Unsupported native platform: '+str(p))
                    linkage[p.relative_to(payload).as_posix()] = report
        write_json(payload/'native-linkage.json', linkage)
        lock = {k: {field: value for field,value in record.items() if field != 'directory'} for k,record in records.items()}
        write_json(payload/'release-lock.json',lock)
        meta = dict(schema_version=1,component='semantic-installer',tag=os.environ.get('TARGET_TAG',''),
                    source_commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
                    build_recipe_commit=os.environ.get('GITHUB_SHA',''),runner='ubuntu-24.04',
                    workflow_run=f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}",
                    validation_scope='Component release checks plus installer smoke validation; excludes GPU, physical robots and LLM task execution.',
                    version=args.version,platform='linux-x86_64',minimum_glibc='2.28',native_linkage='static',
                    distribution='component-releases',bundle_name=bundle_name,robot_python='3.13',runtime_python='3.10.19',
                    runtime_pack=pack,robot_skills=skills,uv_version=uv_version,source_revisions=lock)
        write_json(payload/'release.json',meta)
        write_json(payload/'files.json',{p.relative_to(payload).as_posix():digest(p) for p in sorted(payload.rglob('*')) if p.is_file()})
        output.mkdir(parents=True)
        archive = output/f'semantic-{args.version}-linux-x86_64.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
            for p in sorted(payload.rglob('*')):
                if p.is_file():
                    tar.add(p,arcname=p.relative_to(payload).as_posix(),recursive=False)
        checksum=digest(archive)
        Path(str(archive)+'.sha256').write_text(f'{checksum}  {archive.name}\n')
        for name in ('release.json','release-lock.json','repo-versions.json'):
            copy(payload/name,output/name)
        copy(source/'artifacts/install.sh',output/'install.sh')
        manifest=dict(schema_version=1,version=args.version,platform='linux-x86_64',distribution='component-releases',
                      archive=f'releases/{args.version}/linux-x86_64/{archive.name}',sha256=checksum,size=archive.stat().st_size)
        write_json(output/'manifest.json',manifest)
        (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
        print(archive)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=HERE.parent/'repo-versions.json')
    parser.add_argument('--cache',type=Path,default=Path.home()/'.cache/semantic/releases')
    parser.add_argument('--quick-start',type=Path,default=HERE.parent)
    parser.add_argument('--version',required=True)
    parser.add_argument('--output',type=Path,required=True)
    build(parser.parse_args())
