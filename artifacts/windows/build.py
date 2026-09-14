#!/usr/bin/env python3
"""Assemble a Windows x64 offline installer from pinned native inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from fetch_releases import digest, download, extract, fetch
from macos.build import run, copy, archive, validate_skill_wheels


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def native_images(root):
    result = {}
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            magic = stream.read(4)
            if magic in (b'\x7fELF', b'\xcf\xfa\xed\xfe'):
                raise ValueError('Foreign executable in Windows payload: '+str(path))
            if magic[:2] != b'MZ':
                continue
            stream.seek(60)
            offset = struct.unpack('<I', stream.read(4))[0]
            stream.seek(offset)
            if stream.read(4) != b'PE\0\0' or struct.unpack('<H',stream.read(2))[0] != 0x8664:
                raise ValueError('Executable is not Windows x64: '+str(path))
        result[path.relative_to(root).as_posix()] = digest(path)
    return result


def zip_payload(source, target):
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as out:
        for path in sorted(source.rglob('*')):
            if path.is_symlink() or path.is_junction():
                raise ValueError('Reparse point in payload: '+str(path))
            if path.is_file():
                out.write(path, path.relative_to(source).as_posix())


def copy_native_abilities(source, bundle):
    report = json.loads((source/'windows-packages.json').read_text(encoding='utf-8'))
    pins = json.loads((HERE/'sources.json').read_text(encoding='utf-8'))
    if report['platform'] != 'windows-amd64' or report['source_commit'] != pins['r1pro-ability']['commit']:
        raise ValueError('Unpinned Windows Ability artifacts')
    if len(report['abilities']) != 7:
        raise ValueError('Seven native Ability packages are required')
    for entry in report['abilities']:
        path = source/entry['file']
        if path.name != entry['file'] or digest(path) != entry['sha256']:
            raise ValueError('Ability archive checksum mismatch')
        with zipfile.ZipFile(path) as package:
            if package.read('bin/ability.exe')[:2] != b'MZ':
                raise ValueError('Missing native Ability launcher')
        copy(path, bundle/'abilities'/path.name)


def verify_native_abilities(bundle, entries):
    for entry in entries:
        with zipfile.ZipFile(bundle/entry['file']) as package:
            metadata = yaml.safe_load(package.read('package.yaml'))
            if metadata['arch'] != 'x86_64' or not package.read('bin/ability.exe').startswith(b'MZ'):
                raise ValueError('Ability metadata differs from bundle: '+str(entry))


def import_native_wheels(source, destination):
    pins = json.loads((HERE/'sources.json').read_text(encoding='utf-8'))
    report = json.loads((source/'windows-validation.json').read_text(encoding='utf-8'))
    if report['source_commit'] != pins['pinocchio']['commit']:
        raise ValueError('Unpinned Pinocchio native artifacts')
    hashes = {}
    for line in (source/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        checksum, name = line.split(maxsplit=1)
        hashes[name.strip().lstrip('*')] = checksum
    names = set()
    for path in source.glob('*.whl'):
        if hashes.get(path.name) != digest(path):
            raise ValueError('Native wheel checksum mismatch: '+path.name)
        if path.name.startswith('numpy-'):
            if not (destination/path.name).exists() or digest(destination/path.name) != digest(path):
                raise ValueError('Pinocchio and public NumPy wheels differ')
            continue
        names.add(path.name.split('-')[0])
        copy(path, destination/path.name)
    if names != {'pin','eigenpy','coal','semantic_windows_native'}:
        raise ValueError('Expected the four qualified native math wheels')


def wheel_lock(wheelhouse):
    rows = {}
    for path in sorted(wheelhouse.glob('*.whl')):
        name, version = path.name.split('-')[:2]
        if name in rows:
            raise ValueError('Multiple wheels for '+name)
        rows[name] = f'{name}=={version} --hash=sha256:{digest(path)}'
    return '\n'.join(rows.values())+'\n'


def build(a):
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Build on native Windows x64')
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
    manifest = json.loads((ROOT/'repo-versions.json').read_text(encoding='utf-8'))
    keys = ['semantic-web', 'semantic-scene/mujoco-asset', 'semantic-robot-deployment',
            'semantic-robotsdk/robot-sdk',
            'semantic-skill/robot-skill']
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
    for name in ('bin', 'wheels', 'python', 'abilities'):
        if (bundle/name).exists():
            shutil.rmtree(bundle/name)
    copy_native_abilities(a.abilities.resolve(), bundle)
    # The source archives were checked out at exact commits by Actions.
    sources = a.sources.resolve()
    pins = json.loads((HERE/'sources.json').read_text(encoding='utf-8'))
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
    for name in ('semantic-robot-instance.exe', 'semantic-pilot.exe', 'AbilityFramework.exe'):
        copy(payload/'bin'/name, bundle/'bin'/name)
    for dll in (payload/'bin').glob('*.dll'):
        copy(dll, bundle/'bin'/dll.name)
    uv = Path(shutil.which('uv')).resolve()
    if subprocess.check_output([str(uv), '--version'], text=True).split()[1] != '0.12.12':
        raise ValueError('Assembly requires uv 0.12.12')
    copy(uv, payload/'bin/uv.exe')
    for license in ('LICENSE-APACHE', 'LICENSE-MIT'):
        download(f'https://raw.githubusercontent.com/astral-sh/uv/0.12.12/{license}', payload/'notices/uv'/license, 1024**2)
    python = Path(subprocess.check_output(['uv', 'python', 'find', '--managed-python', '3.13.15'], text=True).strip())
    prefix = Path(subprocess.check_output([str(python), '-c', 'import sys; print(sys.base_prefix)'], text=True).strip())
    copy(prefix, payload/'python')
    run(payload/'python/python.exe', '-I', '-B', '-c',
        'import sys,ssl,sqlite3; from pathlib import Path; assert Path(sys.base_prefix).resolve()==Path(sys.argv[1]).resolve()', payload/'python')
    # Only installer dependencies are resolved here; the target installs offline.
    run('uv', 'run', '--no-project', '--isolated', '--python', '3.13.15', '--with', 'pip==25.2',
        'python', '-m', 'pip', 'download', '--only-binary=:all:', '--require-hashes',
        '-r', HERE/'public-requirements.lock', '-d', wheelhouse)
    import_native_wheels(a.pin_wheels.resolve(), wheelhouse)
    runtime = sources/'mujoco-runtime'
    for project in (runtime, runtime/'packages/mujoco-visuals', sources/'ability-scaffold',
                    sources/'Ability-SDK-Python', sources/'r1pro-ability'):
        run('uv', 'build', '--wheel', '--project', project, '--out-dir', wheelhouse)
    validate_skill_wheels(payload/'robot-skills', wheelhouse)
    installed_lock = work/'installer-requirements.lock'
    installed_lock.write_text(wheel_lock(wheelhouse), encoding='utf-8')
    for wheel in wheelhouse.glob('*.whl'):
        with zipfile.ZipFile(wheel) as z:
            if z.testzip():
                raise ValueError('Corrupt wheel '+wheel.name)
            if not wheel.name.endswith('-none-any.whl') and 'win_amd64' not in wheel.name:
                raise ValueError('Non-Windows wheel '+wheel.name)
        copy(wheel, bundle/'wheels'/wheel.name)
    spec = yaml.safe_load((bundle/'bundle.yaml').read_text(encoding='utf-8'))
    spec['spec']['platform'] = {'os': 'windows', 'arch': 'amd64'}
    spec['spec']['artifacts']['pythonWheels'] = ['wheels/'+p.name for p in sorted(wheelhouse.glob('*.whl'))]
    (bundle/'bundle.yaml').write_text(yaml.safe_dump(spec, sort_keys=False))
    for key in ('instanceLauncher', 'abilityFramework', 'pilot'):
        spec['spec']['artifacts'][key] += '.exe'
    spec['spec']['artifacts']['pythonExecutable'] = 'python/venv/Scripts/python.exe'
    (bundle/'bundle.yaml').write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    copy(installed_lock, bundle/'python-requirements.lock')
    for entry in spec['spec']['artifacts']['abilities']:
        if not (bundle/entry['file']).is_file():
            raise ValueError('Missing ability: '+str(entry))
    verify_native_abilities(bundle, spec['spec']['artifacts']['abilities'])
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
    document = yaml.safe_load((sources/'Semantic-Framework/configs/scenes.d/mujoco-platforms.yaml').read_text(encoding='utf-8'))
    document['entries'] = [entry for entry in document['entries'] if entry['compatible_runtime_profile']=='native-mujoco']
    asset_version = json.loads((payload/'assets/mujoco/asset-catalog.v1.json').read_text(encoding='utf-8'))['catalog_version']
    document['catalog_version'] = asset_version
    for entry in document['entries']:
        for version in entry['versions']:
            if 'authoring' in version:
                version['authoring']['asset_catalog_version'] = asset_version
    catalog.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    # Let the Runtime select its configured native GLFW backend.
    request = json.loads(smoke.read_text(encoding='utf-8')); request['render_backend'] = 'auto'; write(smoke, request)
    write(verification, {'source_commit': pins['mujoco-runtime']['commit'], 'python_version': '3.13.15', 'platform': 'windows-amd64'})
    local_runtime = []
    deps = []
    for wheel in wheelhouse.glob('*.whl'):
        if wheel.name.startswith(('semantic_plugin_mujoco-', 'semantic_mujoco_visuals-')):
            dest = stage/'wheels'/wheel.name; local_runtime.append(dest)
        else:
            dest = stage/'wheelhouse'/wheel.name; deps.append(dest)
        copy(wheel, dest)
    lock = stage/'locks/requirements.lock'
    copy(installed_lock, lock)
    record = lambda p: builder.file_record(stage, p)
    pack_meta = dict(schema_version=1, pack_id='native-mujoco', pack_version='0.4.0-dev.0',
        profile=profile.profile, runner=profile.runner, python_version='3.13.15', endpoint=profile.endpoint,
        hardware_requirements={'architecture':'amd64', 'renderer':'glfw', 'gpu':'optional'},
        requirements_lock=record(lock), wheels=list(map(record, local_runtime)), wheelhouse=list(map(record, deps)),
        scene_catalog=record(catalog), scene_resources=list(map(record, resources)),
        licenses=list(map(record, sorted((stage/'licenses').iterdir()))), verification_files=[record(verification)],
        smoke_scene_key='palletizing_depalletizing_tote_v1', smoke_request=record(smoke), content_requirements=profile.content_requirements)
    (stage/'runtime-pack.yaml').write_text(yaml.safe_dump(pack_meta, sort_keys=False))
    pack_name = 'runtime-packs/native-mujoco-windows-amd64.runtime.tar.gz'
    archive(stage, payload/pack_name)
    config = yaml.safe_load((sources/'Semantic-Framework/configs/semantic-server.yaml').read_text(encoding='utf-8'))
    write(payload/'defaults/server.json', config)
    for name in ('installer.py', 'install_support.py'):
        copy(HERE.parent/'runtime'/name, payload/name)
    for name in ('ios.png', 'banner.json'):
        copy(HERE.parent/'assets'/name, payload/'assets'/name)
    copy(ROOT/'LICENSE', payload/'LICENSE')
    for name in ('install.py', 'manager.py', 'windows_ports.py', 'uninstall.ps1', 'install.cmd'):
        copy(HERE/name, payload/name)
    copy(HERE/'PACKAGE-README.txt', payload/'README.txt')
    skills = []
    for p in sorted((payload/'robot-skills').glob('*.zip')):
        with zipfile.ZipFile(p) as z:
            meta = yaml.safe_load(z.read('SKILL.md').decode().split('---',2)[1])
        skills.append({'name': meta['name'], 'version': str(meta['version']), 'path':'robot-skills/'+p.name})
    defaults = yaml.safe_load((bundle/'templates/robot-deployment.yaml.tmpl').read_text(encoding='utf-8').split('\nrobot_skills:\n',1)[1])
    if {item['name']:item['version'] for item in skills} != {item['name']:str(item['version']) for item in defaults}:
        raise ValueError('Skill versions differ from the deployment template')
    write(payload/'native-images.json', native_images(payload))
    write(payload/'repo-versions.json', {'native_sources':pins, 'component_releases':{k:{f:v for f,v in r.items() if f != 'directory'} for k,r in records.items()}})
    write(payload/'release.json', dict(schema_version=1, component='semantic-installer', version=a.version,
        platform='windows-amd64', minimum_windows='Windows 10 1809 x64', robot_python='3.13.15', runtime_python='3.13.15',
        bundle_name=bundle_name, runtime_pack=pack_name, robot_skills=skills,
        source_commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        validation_scope='Native offline installation, API, robot math and physics. Physical Windows GLFW/OpenGL graphics qualification pending.',
        workflow_run=f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','')}"))
    write(payload/'files.json', {p.relative_to(payload).as_posix():digest(p) for p in sorted(payload.rglob('*')) if p.is_file()})
    target = output/f'semantic-{a.version}-windows-amd64.zip'
    zip_payload(payload, target)
    for name in ('release.json', 'repo-versions.json', 'native-images.json'):
        copy(payload/name, output/name)
    write(output/'manifest.json', {'version':a.version, 'platform':'windows-amd64', 'archive':target.name,
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
    p.add_argument('--abilities', type=Path, required=True)
    p.add_argument('--pin-wheels', type=Path, required=True)
    build(p.parse_args())
