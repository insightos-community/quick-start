#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Assemble a native arm64 installer from pinned sources and component releases."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from fetch_releases import digest, download, extract, fetch


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True, symlinks=False)
    else:
        shutil.copy2(source, target)


def archive(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, 'w:gz', compresslevel=3, dereference=True) as tar:
        for p in sorted(source.rglob('*')):
            if p.is_file():
                tar.add(p, arcname=p.relative_to(source).as_posix(), recursive=False)


def relocate_python(root, original):
    """uv fixes libpython's install name for its own prefix; undo that for shipping."""
    changed = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        with path.open('rb') as f:
            if f.read(4) not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
                continue
        commands = []
        identity = subprocess.run(['otool', '-D', str(path)], capture_output=True, text=True, check=True).stdout.splitlines()[1:]
        identity = [line.strip() for line in identity if line.strip()]
        libraries = subprocess.check_output(['otool', '-L', str(path)], text=True).splitlines()[1:]
        for line in libraries:
            library = line.strip().split(' (', 1)[0]
            if not library.startswith(str(original)+'/'):
                continue
            target = root/Path(library).relative_to(original)
            if not target.is_file():
                raise ValueError('Missing relocated Python library: '+library)
            if library in identity:
                commands += ['-id', '@rpath/'+target.name]
            else:
                commands += ['-change', library, '@loader_path/'+os.path.relpath(target, path.parent)]
        load = subprocess.check_output(['otool', '-l', str(path)], text=True)
        for rpath in re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', load):
            if rpath.startswith(str(original)+'/'):
                target = root/Path(rpath).relative_to(original)
                commands += ['-rpath', rpath, '@loader_path/'+os.path.relpath(target, path.parent)]
        if commands:
            run('install_name_tool', *commands, path)
            # Apple Silicon requires a valid code signature after load commands change.
            # An ad-hoc integrity signature is not Developer ID signing/notarization.
            run('codesign', '--force', '--sign', '-', path)
            changed.append(path.relative_to(root).as_posix())
    run(root/'bin/python3.13', '-I', '-B', '-c',
        'import sys,ssl,sqlite3; from pathlib import Path; assert Path(sys.base_prefix).resolve()==Path(sys.argv[1]).resolve()', root)
    return changed


def native_report(root):
    reports = {}
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        with p.open('rb') as f:
            magic = f.read(4)
        if magic == b'\x7fELF':
            raise ValueError('Linux executable in macOS payload: '+str(p))
        if magic not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
            continue
        architectures = subprocess.check_output(['lipo', '-archs', str(p)], text=True).strip()
        if 'arm64' not in architectures.split():
            raise ValueError('Missing arm64: '+str(p))
        output = subprocess.check_output(['otool', '-L', str(p)], text=True)
        libraries = [line.strip().split(' (', 1)[0] for line in output.splitlines()[1:]]
        for lib in libraries:
            if lib.startswith('/') and not lib.startswith(('/usr/lib/', '/System/Library/')):
                raise ValueError(f'Nonportable library in {p}: {lib}')
        load_commands = subprocess.check_output(['otool', '-l', str(p)], text=True)
        versions = re.findall(r'\bminos ([0-9.]+)', load_commands)
        versions += re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([0-9.]+)', load_commands)
        if any(tuple(map(int, v.split('.'))) > (15, 5, 0) for v in versions):
            raise ValueError('Binary requires newer macOS than declared: '+str(p))
        rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', load_commands)
        if any(r.startswith('/') and not r.startswith(('/usr/lib/', '/System/Library/')) for r in rpaths):
            raise ValueError('Absolute build-time rpath: '+str(p))
        reports[p.relative_to(root).as_posix()] = dict(architectures=architectures, libraries=libraries,
                                                     minimum_macos=versions, rpaths=rpaths)
    return reports


def build(a):
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise ValueError('Build on native Apple Silicon macOS')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', a.version):
        raise ValueError('Invalid version')
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    payload = work/'payload'
    payload.mkdir()
    # Reuse architecture-independent component releases. Native executables are
    # built separately from the source revisions in sources.json by this workflow.
    manifest = json.loads((ROOT/'repo-versions.json').read_text())
    keys = ['semantic-web', 'semantic-scene/mujoco-asset', 'semantic-robot-deployment',
            'semantic-ability/r1pro-ability', 'semantic-robotsdk/robot-sdk',
            'semantic-skill/robot-skill', 'ability-framework/ability-py-sdk',
            'ability-framework/ability-scaffold']
    manifest['repos'] = {k: manifest['repos'][k] for k in keys}
    write(work/'component-versions.json', manifest)
    records = fetch(work/'component-versions.json', work/'downloads')
    components = {}
    wheelhouse = work/'wheelhouse'
    wheelhouse.mkdir()
    for key, record in records.items():
        directory = Path(record['directory'])
        name = f"{record['component']}-{record['tag']}-{record['platform']}.tar.gz"
        if (directory/name).exists():
            dest = work/'components'/record['component']
            extract(directory/name, dest)
            components[key] = dest
        for wheel in directory.glob('*-none-any.whl'):
            copy(wheel, wheelhouse/wheel.name)
        for source in (directory, components.get(key)):
            if source:
                for p in source.iterdir():
                    if p.name.startswith(('LICENSE', 'NOTICE')) or p.name in ('third-party-licenses', 'ASSET_PROVENANCE.md', 'EXTERNAL_MODELS.md'):
                        copy(p, payload/'notices'/record['component']/p.name)
    copy(components['semantic-web']/'web', payload/'web')
    copy(components['semantic-scene/mujoco-asset'], payload/'assets/mujoco')
    copy(components['semantic-skill/robot-skill']/'robot-skills', payload/'robot-skills')
    bundle_name = 'r1pro-mujoco-0.5.0-dev'
    bundle = payload/'robot-bundles'/bundle_name
    copy(components['semantic-robot-deployment']/'type-packages/r1pro-mujoco', bundle)
    copy(components['semantic-ability/r1pro-ability']/'abilities', bundle/'abilities')
    # The source archives were checked out at exact commits by Actions.
    sources = a.sources.resolve()
    pins = json.loads((HERE/'sources.json').read_text())
    for name, pin in pins.items():
        source = sources/name
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != pin['commit']:
            raise ValueError('Source revision mismatch: '+name)
        for p in source.iterdir():
            if p.name.startswith(('LICENSE', 'NOTICE')):
                copy(p, payload/'notices'/name/p.name)
        for p in source.rglob('*'):
            if p.is_file() and '.git' not in p.parts and p.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                copy(p, payload/'notices'/name/p.relative_to(source))
    for p in a.binaries.resolve().glob('*'):
        copy(p, payload/'bin'/p.name)
    for name in ('semantic-robot-instance', 'semantic-pilot', 'AbilityFramework'):
        copy(payload/'bin'/name, bundle/'bin'/name)
    uv = Path(shutil.which('uv')).resolve()
    if subprocess.check_output([str(uv), '--version'], text=True).split()[1] != '0.12.12':
        raise ValueError('Assembly requires uv 0.12.12')
    copy(uv, payload/'bin/uv')
    for license in ('LICENSE-APACHE', 'LICENSE-MIT'):
        download(f'https://raw.githubusercontent.com/astral-sh/uv/0.12.12/{license}', payload/'notices/uv'/license, 1024**2)
    python = Path(subprocess.check_output(['uv', 'python', 'find', '--managed-python', '3.13.15'], text=True).strip())
    prefix = Path(subprocess.check_output([str(python), '-c', 'import sys; print(sys.base_prefix)'], text=True).strip())
    copy(prefix, payload/'python')
    write(payload/'python-relocation.json', relocate_python(payload/'python', prefix))
    # Only installer dependencies are resolved here; the target installs offline.
    run('uv', 'run', '--no-project', '--isolated', '--python', '3.13.15', '--with', 'pip==25.2',
        'python', '-m', 'pip', 'download', '--only-binary=:all:', '--require-hashes',
        '-r', HERE/'installer-requirements.lock', '-d', wheelhouse)
    runtime = sources/'mujoco-runtime'
    for project in (runtime, runtime/'packages/mujoco-visuals'):
        run('uv', 'build', '--wheel', '--project', project, '--out-dir', wheelhouse)
    for wheel in wheelhouse.glob('*.whl'):
        with zipfile.ZipFile(wheel) as z:
            if z.testzip():
                raise ValueError('Corrupt wheel '+wheel.name)
            if not wheel.name.endswith('-none-any.whl') and 'macosx_' not in wheel.name:
                raise ValueError('Non-macOS wheel '+wheel.name)
        copy(wheel, bundle/'wheels'/wheel.name)
    spec = yaml.safe_load((bundle/'bundle.yaml').read_text())
    spec['spec']['platform'] = {'os': 'darwin', 'arch': 'arm64'}
    spec['spec']['artifacts']['pythonWheels'] = ['wheels/'+p.name for p in sorted(wheelhouse.glob('*.whl'))]
    (bundle/'bundle.yaml').write_text(yaml.safe_dump(spec, sort_keys=False))
    copy(HERE/'installer-requirements.lock', bundle/'python-requirements.lock')
    for entry in spec['spec']['artifacts']['abilities']:
        if not (bundle/entry['file']).is_file():
            raise ValueError('Missing ability: '+str(entry))
    # Build a native gzip runtime pack using the upstream schema and catalog.
    module_spec = importlib.util.spec_from_file_location('runtime_builder', runtime/'tools/build_runtime_pack.py')
    builder = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = builder
    module_spec.loader.exec_module(builder)
    profile = builder.profile_table()['native-mujoco']
    stage = work/'runtime-pack'
    stage.mkdir()
    catalog, resources, smoke, verification = builder.copy_metadata(profile, '0.4.0-dev.0', stage)
    # Match the existing Linux component release recipe: raw Runtime fixtures
    # predate the current Framework scene-document schema.
    shutil.rmtree(stage/'catalog')
    copy(sources/'Semantic-Framework/configs/scenes.d/authoring/depalletizing-r1pro',
         stage/'catalog/authoring/depalletizing-r1pro')
    catalog = stage/'catalog/catalog.yaml'
    resources = sorted(p for p in (stage/'catalog').rglob('*') if p.is_file())
    document = yaml.safe_load((sources/'Semantic-Framework/configs/scenes.d/mujoco-platforms.yaml').read_text())
    document['entries'] = [entry for entry in document['entries'] if entry['compatible_runtime_profile']=='native-mujoco']
    asset_version = json.loads((payload/'assets/mujoco/asset-catalog.v1.json').read_text())['catalog_version']
    document['catalog_version'] = asset_version
    for entry in document['entries']:
        for version in entry['versions']:
            if 'authoring' in version:
                version['authoring']['asset_catalog_version'] = asset_version
    catalog.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    request = json.loads(smoke.read_text()); request['render_backend'] = 'cgl'; write(smoke, request)
    write(verification, {'source_commit': pins['mujoco-runtime']['commit'], 'python_version': '3.13.15', 'platform': 'macos-arm64'})
    local_runtime = []
    deps = []
    for wheel in wheelhouse.glob('*.whl'):
        if wheel.name.startswith(('semantic_plugin_mujoco-', 'semantic_mujoco_visuals-')):
            dest = stage/'wheels'/wheel.name; local_runtime.append(dest)
        else:
            dest = stage/'wheelhouse'/wheel.name; deps.append(dest)
        copy(wheel, dest)
    lock = stage/'locks/requirements.lock'
    copy(HERE/'installer-requirements.lock', lock)
    record = lambda p: builder.file_record(stage, p)
    pack_meta = dict(schema_version=1, pack_id='native-mujoco', pack_version='0.4.0-dev.0',
        profile=profile.profile, runner=profile.runner, python_version='3.13.15', endpoint=profile.endpoint,
        hardware_requirements={'architecture':'arm64', 'renderer':'cgl', 'gpu':'optional'},
        requirements_lock=record(lock), wheels=list(map(record, local_runtime)), wheelhouse=list(map(record, deps)),
        scene_catalog=record(catalog), scene_resources=list(map(record, resources)),
        licenses=list(map(record, sorted((stage/'licenses').iterdir()))), verification_files=[record(verification)],
        smoke_scene_key='palletizing_depalletizing_tote_v1', smoke_request=record(smoke), content_requirements=profile.content_requirements)
    (stage/'runtime-pack.yaml').write_text(yaml.safe_dump(pack_meta, sort_keys=False))
    pack_name = 'runtime-packs/native-mujoco-macos-arm64.runtime.tar.gz'
    archive(stage, payload/pack_name)
    config = yaml.safe_load((sources/'Semantic-Framework/configs/semantic-server.yaml').read_text())
    write(payload/'defaults/server.json', config)
    for name in ('installer.py', 'install_support.py', 'uninstall.py'):
        copy(HERE.parent/'runtime'/name, payload/name)
    for name in ('ios.png', 'banner.json'):
        copy(HERE.parent/'assets'/name, payload/'assets'/name)
    copy(ROOT/'LICENSE', payload/'LICENSE')
    copy(HERE/'install.command', payload/'install.command'); (payload/'install.command').chmod(0o755)
    copy(HERE/'PACKAGE-README.txt', payload/'README.txt')
    skills = []
    for p in sorted((payload/'robot-skills').glob('*.zip')):
        with zipfile.ZipFile(p) as z:
            meta = yaml.safe_load(z.read('SKILL.md').decode().split('---',2)[1])
        skills.append({'name': meta['name'], 'version': str(meta['version']), 'path':'robot-skills/'+p.name})
    defaults = yaml.safe_load((bundle/'templates/robot-deployment.yaml.tmpl').read_text().split('\nrobot_skills:\n',1)[1])
    if {item['name']:item['version'] for item in skills} != {item['name']:str(item['version']) for item in defaults}:
        raise ValueError('Skill versions differ from the deployment template')
    write(payload/'native-linkage.json', native_report(payload))
    write(payload/'repo-versions.json', {'native_sources':pins, 'component_releases':{k:{f:v for f,v in r.items() if f != 'directory'} for k,r in records.items()}})
    write(payload/'release.json', dict(schema_version=1, component='semantic-installer', version=a.version,
        platform='macos-arm64', minimum_macos='15.5', robot_python='3.13.15', runtime_python='3.13.15',
        bundle_name=bundle_name, runtime_pack=pack_name, robot_skills=skills,
        source_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        validation_scope='Native offline installation, API, robot math and physics. Physical Mac CGL graphics qualification pending.',
        workflow_run=f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"))
    write(payload/'files.json', {p.relative_to(payload).as_posix():digest(p) for p in sorted(payload.rglob('*')) if p.is_file()})
    target = output/f'semantic-{a.version}-macos-arm64.tar.gz'
    archive(payload, target)
    for name in ('release.json', 'repo-versions.json', 'native-linkage.json'):
        copy(payload/name, output/name)
    (output/'install-macos.sh').write_text((HERE/'bootstrap.sh').read_text().replace("release_tag='macos-v0.1.0-rc.1'", f"release_tag='macos-v{a.version}'"))
    write(output/'manifest.json', {'version':a.version, 'platform':'macos-arm64', 'archive':target.name,
                                  'sha256':digest(target), 'size':target.stat().st_size})
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
    print(target)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--binaries', type=Path, required=True)
    build(p.parse_args())
