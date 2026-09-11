#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Assemble the opt-in musl installer from hash-pinned releases, inside Alpine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from email.parser import BytesParser

import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_releases import digest, download

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PYTHON = '3.13.15'
EXCLUDED = {'pin', 'libpinocchio', 'eigenpy', 'coal', 'libcoal', 'ruckig'}


def run(args, **kwargs):
    print('Run:', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2)+'\n')


def verified(url, sha, target):
    if not re.fullmatch('[0-9a-f]{64}', sha):
        raise ValueError('Invalid SHA256')
    if not target.exists() or digest(target) != sha:
        download(url, target, 4*1024**3)
    if digest(target) != sha:
        raise ValueError('Checksum mismatch: '+url)
    return target


def extract(path, target):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    # Python's data filter rejects escaping links and special files. Upstream
    # prefixes legitimately contain internal SONAME links, unlike our final payload.
    with tarfile.open(path) as archive:
        if sum(m.size for m in archive) > 10*1024**3:
            raise ValueError('Oversized archive')
        archive.extractall(target, filter='data')
    return target


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('Corrupt wheel: '+path.name)
        names = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise ValueError('Ambiguous wheel metadata')
        metadata = BytesParser().parsebytes(archive.read(names[0]))
    return re.sub('[-_.]+', '-', metadata['Name']).lower(), metadata['Version']


def replace_wheels(house, released, requirements, cache):
    house.mkdir(parents=True, exist_ok=True)
    for wheel in released:
        shutil.copy2(wheel, house/wheel.name)
    locked = json.loads((HERE/'python-wheels.json').read_text())
    for requirement in requirements:
        name, version = requirement.split('==')
        matches = [(filename, pin) for filename, pin in locked.items()
                   if pin['name'] == name and pin['version'] == version]
        if len(matches) != 1:
            raise ValueError('Missing unique musl wheel pin: '+requirement)
        filename, pin = matches[0]
        source = verified(pin['url'], pin['sha256'], cache/'python-wheels'/filename)
        shutil.copy2(source, house/filename)
    for wheel in house.glob('*.whl'):
        if 'manylinux' in wheel.name or not (re.search(r'musllinux_1_[12]_x86_64', wheel.name) or 'none-any' in wheel.name):
            raise ValueError('Non-musl wheel: '+wheel.name)


def merge_prefix(source, target, name):
    for path in sorted((source/'prefix/lib').rglob('*')):
        relative = path.relative_to(source/'prefix/lib')
        if not path.is_file():
            continue
        # Mesa's Iris/Crocus drivers use libdrm directly, not libdrm_intel's
        # optional PCI convenience API. Keep that unused dependency out of the bundle.
        if name == 'libdrm' and path.name.startswith('libdrm_intel.'):
            continue
        if '.so' not in path.name and relative.parts[0] != 'python3.13':
            continue
        dest = target/'lib'/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and digest(path) != digest(dest):
            raise ValueError('Conflicting runtime library: '+str(relative))
        shutil.copy2(path, dest)  # Dereference only validated internal archive links.
    if (source/'licenses').is_dir():
        shutil.copytree(source/'licenses', target/'licenses'/name, dirs_exist_ok=True)
    shutil.copy2(source/'build-manifest.json', target/'manifests'/f'{name}.json')


def assemble(args):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-musl\.[1-9][0-9]*', args.version):
        raise ValueError('Expected MAJOR.MINOR.PATCH-musl.REVISION')
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output must be a new or empty directory')
    work, cache = args.work.resolve(), args.cache.resolve()
    work.mkdir(parents=True, exist_ok=True)
    upstream = json.loads((HERE/'upstream.json').read_text())
    pins = json.loads((HERE/'releases.json').read_text())
    expected = {'pinocchio','ruckig','assimp','qhull','tinyxml2','zlib','libdrm','libexpat',
                'libffi','xz','libxml2','elfutils','llvm-project','SPIRV-Tools','zstd','mujoco','mesa'}
    if set(pins) != expected:
        raise ValueError('Incomplete musl release lock')
    downloaded = {}
    for name, pin in pins.items():
        directory = cache/name/pin['tag']
        for filename, sha in pin['assets'].items():
            verified(f"https://github.com/{pin['repository']}/releases/download/{pin['tag']}/{filename}", sha, directory/filename)
        manifest = json.loads((directory/'build-manifest.json').read_text())
        if manifest['source_commit'] != pin['source_commit'] or manifest['platform'] != ('musllinux_1_2_x86_64' if name == 'ruckig' else 'linux-musl-x86_64'):
            raise ValueError('Release source/platform mismatch: '+name)
        downloaded[name] = directory
    fetched = {}
    for name, pin in upstream.items():
        if 'url' in pin:
            filename = pin['url'].rsplit('/',1)[1].replace('%2B','+')
            fetched[name] = verified(pin['url'], pin['sha256'], cache/'upstream'/filename)
    payload = extract(fetched['installer'], work/'payload')
    old = json.loads((payload/'release.json').read_text())
    if old['version'] != '0.1.0' or old['source_commit'] != upstream['installer']['source_commit']:
        raise ValueError('Unexpected base installer')
    (payload/'files.json').unlink()
    prefix = payload/'musl'
    (prefix/'manifests').mkdir(parents=True)
    for name, directory in downloaded.items():
        archives = list(directory.glob('*-prefix.tar.gz'))
        if name == 'ruckig':
            shutil.copy2(directory/'build-manifest.json', prefix/'manifests/ruckig.json')
            continue
        if len(archives) != 1:
            raise ValueError('Missing unique prefix: '+name)
        unpacked = extract(archives[0], work/'prefixes'/name)
        # MuJoCo uses its self-contained audited wheel; installing a second native
        # libmujoco here would make it possible to load two independent cores.
        if name != 'mujoco':
            merge_prefix(unpacked, prefix, name)
        else:
            shutil.copytree(unpacked/'licenses', prefix/'licenses'/name)
            shutil.copy2(unpacked/'build-manifest.json', prefix/'manifests'/f'{name}.json')
        if name == 'mesa':
            shutil.copytree(unpacked/'prefix/share/insightos-mesa', prefix/'share/insightos-mesa')
    # Unmodified GCC runtimes come from the pinned Alpine distribution packages.
    compiler = upstream['compiler_runtime']
    for library in ('libgcc_s.so.1', 'libstdc++.so.6', 'libgomp.so.1'):
        shutil.copy2(Path('/usr/lib')/library, prefix/'lib'/library)
    runtime_notice = prefix/'licenses/gcc-runtime'
    runtime_notice.mkdir(parents=True)
    for name in ('COPYING3','COPYING.RUNTIME'):
        pin = compiler['licenses'][name]
        shutil.copy2(verified(pin['url'], pin['sha256'], cache/'licenses'/name), runtime_notice/name)
    actual = [p for p in subprocess.check_output(['apk','info','-v'], text=True).splitlines() if re.fullmatch(r'(libgcc|libstdc\+\+|libgomp)-[0-9].*', p)]
    if sorted(actual) != sorted(compiler['packages']):
        raise ValueError('Alpine compiler runtime changed: '+repr(actual))
    write_json(prefix/'manifests/compiler-runtime.json', {**compiler, 'actual_packages':actual})
    python_tree = extract(fetched['python'], work/'cpython')/'python'
    shutil.copytree(python_tree, payload/'python', symlinks=False)
    uv_tree = extract(fetched['uv'], work/'uv')/'uv-x86_64-unknown-linux-musl'
    shutil.copy2(uv_tree/'uv', payload/'bin/uv')
    # Build the application wheels from the committed Python 3.13 adaptation.
    runtime = work/'mujoco-runtime'
    if runtime.exists():
        shutil.rmtree(runtime)
    source = upstream['mujoco_runtime']
    run(['git','init',runtime])
    run(['git','-C',runtime,'fetch','--depth=1',source['repository'],source['commit']])
    run(['git','-C',runtime,'checkout','--detach','FETCH_HEAD'])
    wheels = work/'application-wheels'
    wheels.mkdir(exist_ok=True)
    for project in (runtime, runtime/'packages/mujoco-visuals'):
        run([payload/'bin/uv','build','--wheel','--project',project,'--out-dir',wheels])
    pack = work/'runtime-pack'
    pack.mkdir(exist_ok=True)
    run(['tar','--zstd','-xf',payload/old['runtime_pack'],'-C',pack])
    manifest = yaml.safe_load((pack/'runtime-pack.yaml').read_text())
    runtime_requirements = []
    for wheel in (pack/'wheelhouse').glob('*.whl'):
        name, version = wheel_metadata(wheel)
        if name in {'mujoco','glfw','semantic-mujoco-visuals'}:
            continue
        runtime_requirements.append(f"{name}=={'2.3.5' if name == 'numpy' else version}")
    for folder in ('wheels','wheelhouse'):
        shutil.rmtree(pack/folder)
        (pack/folder).mkdir()
    mujoco_wheels = list(downloaded['mujoco'].glob('*.whl'))
    replace_wheels(pack/'wheelhouse', mujoco_wheels, runtime_requirements, cache)
    for wheel in wheels.glob('*.whl'):
        name,_ = wheel_metadata(wheel)
        shutil.copy2(wheel, pack/('wheels' if name == 'semantic-plugin-mujoco' else 'wheelhouse')/wheel.name)
    record = lambda p: {'path':p.relative_to(pack).as_posix(),'sha256':digest(p)}
    lock = pack/'locks/requirements.lock'
    lock.write_text(''.join(f'{name}=={version}\n' for name,version in sorted(wheel_metadata(w) for w in (pack/'wheelhouse').glob('*.whl'))))
    manifest.update(python_version=PYTHON, requirements_lock=record(lock),
                    wheels=[record(w) for w in sorted((pack/'wheels').glob('*.whl'))],
                    wheelhouse=[record(w) for w in sorted((pack/'wheelhouse').glob('*.whl'))])
    (pack/'runtime-pack.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False))
    (payload/old['runtime_pack']).unlink()
    pack_name = 'runtime-packs/native-mujoco-0.4.0-dev.0-musl.runtime.tar.zst'
    run(['tar','--zstd','-cf',payload/pack_name,'-C',pack,'runtime-pack.yaml','wheels','wheelhouse','locks','catalog','licenses','verification','smoke'])
    bundle = payload/'robot-bundles'/old['bundle_name']
    requirements = []
    for wheel in list((bundle/'wheels').glob('*.whl')):
        name,version = wheel_metadata(wheel)
        if name in EXCLUDED or name.startswith('cmeel'):
            wheel.unlink()
        elif 'none-any' not in wheel.name:
            requirements.append(f'{name}=={version}')
            wheel.unlink()
    # The robot environment also supplies the isolated EGL probe. Only these
    # rendering dependencies are shared; FastAPI/Pydantic remain environment-local.
    extras = {'mujoco','glfw','absl-py','etils','fsspec','importlib-resources','zipp','pyopengl'}
    rendering_wheels = [p for p in (pack/'wheelhouse').glob('*.whl') if wheel_metadata(p)[0] in extras]
    replace_wheels(bundle/'wheels', [*downloaded['ruckig'].glob('*.whl'), *rendering_wheels], requirements, cache)
    spec = yaml.safe_load((bundle/'bundle.yaml').read_text())
    spec['spec']['artifacts']['pythonWheels'] = [f'wheels/{p.name}' for p in sorted((bundle/'wheels').glob('*.whl'))]
    (bundle/'bundle.yaml').write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    for filename in ('installer.py','install_support.py','uninstall.py'):
        shutil.copy2(ROOT/'artifacts/runtime'/filename, payload/filename)
    meta = {**old, 'tag':args.tag, 'version':args.version, 'platform':'linux-musl-x86_64',
            'libc':'musl','minimum_musl':'1.2','robot_python':PYTHON,'runtime_python':PYTHON,
            'runtime_pack':pack_name,'native_linkage':'static applications; musl shared Python and libraries',
            'distribution':'optional-musl-component-releases',
            'base_installer':upstream['installer'],
            'musl_runtime_source':upstream['mujoco_runtime'],
            'workflow_run':f"https://github.com/{os.environ.get('GITHUB_REPOSITORY','insightos-community/quick-start')}/actions/runs/{os.environ.get('GITHUB_RUN_ID','local')}",
            'source_commit':subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True).strip(),
            'validation_scope':'Offline musl install, robot library operations, native scene smoke and software EGL RGB/depth; GPU hardware validation is separate.'}
    meta.pop('minimum_glibc',None)
    meta['build_recipe_commit'] = meta['source_commit']
    meta['source_revisions'] = dict(meta['source_revisions'])
    meta['source_revisions']['semantic-simulation/mujoco-runtime'] = dict(source_commit=source['commit'], repository=source['repository'], distribution='source wheel for optional musl runtime')
    write_json(payload/'release.json',meta)
    (payload/'release-lock.json').rename(payload/'base-release-lock.json')
    write_json(payload/'release-lock.json',meta['source_revisions'])
    write_json(payload/'musl-releases.json',pins)
    write_json(payload/'musl-upstream.json',upstream)
    shutil.copy2(HERE/'python-wheels.json',payload/'musl-python-wheels.json')
    # Audit the whole payload including ELF objects hidden inside Python wheels.
    audit = []
    audit_temp = work/'audit-elf'
    audit_files = [(p, str(p.relative_to(payload))) for p in sorted(payload.rglob('*'))]
    audit_files += [(p, pack_name+'!'+str(p.relative_to(pack))) for p in sorted(pack.rglob('*.whl'))]
    for path, audit_name in audit_files:
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Final payload must not contain links')
        if path.suffix == '.whl':
            with zipfile.ZipFile(path) as wheel:
                for entry in wheel.infolist():
                    with wheel.open(entry) as stream:
                        if stream.read(4) != b'\x7fELF':
                            continue
                    audit_temp.write_bytes(wheel.read(entry))
                    audit.append(elf_record(audit_temp, audit_name+'!'+entry.filename))
        elif path.open('rb').read(4) == b'\x7fELF':
            audit.append(elf_record(path,audit_name))
    provided = {Path(item['path'].split('!')[-1]).name for item in audit}
    host = {'libc.musl-x86_64.so.1', 'libc.so'}
    missing = sorted({needed for item in audit for needed in item['needed']} - provided - host)
    if missing:
        raise ValueError('Unbundled ELF dependencies: '+', '.join(missing))
    write_json(payload/'native-linkage.json',audit)
    write_json(payload/'files.json',{p.relative_to(payload).as_posix():digest(p) for p in sorted(payload.rglob('*')) if p.is_file() and p != payload/'files.json'})
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    archive = output/f'semantic-{args.version}-linux-musl-x86_64.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
        for path in sorted(payload.rglob('*')):
            if path.is_file():
                tar.add(path,arcname=path.relative_to(payload).as_posix(),recursive=False)
    for filename in ('release.json','musl-releases.json','musl-upstream.json','musl-python-wheels.json','native-linkage.json'):
        shutil.copy2(payload/filename,output/filename)
    for filename in ('install.sh','install-en.sh'):
        shutil.copy2(ROOT/filename,output/filename)
    shutil.copy2(payload/pack_name,output/Path(pack_name).name)
    Path(str(archive)+'.sha256').write_text(f'{digest(archive)}  {archive.name}\n')
    write_json(output/'manifest.json',dict(version=args.version,platform='linux-musl-x86_64',
              archive=f'releases/{args.version}/linux-musl-x86_64/{archive.name}',sha256=digest(archive),size=archive.stat().st_size))
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file() and p.name not in ('SHA256SUMS','RELEASE_NOTES.md')))
    print('Assembled:',archive)


def elf_record(path, name):
    header = subprocess.check_output(['readelf','-h',path],text=True)
    if 'Advanced Micro Devices X86-64' not in header:
        raise ValueError('Non-x86_64 ELF: '+name)
    versions = subprocess.check_output(['readelf','--version-info',path],text=True)
    if re.search(r'\bGLIBC_[0-9]',versions):
        raise ValueError('glibc dependency: '+name)
    dynamic = subprocess.check_output(['readelf','-d',path],text=True)
    headers = subprocess.check_output(['readelf','-l',path],text=True)
    interpreters = re.findall(r'Requesting program interpreter: (.*?)\]',headers)
    if any('ld-musl-x86_64' not in p for p in interpreters):
        raise ValueError('Non-musl interpreter: '+name)
    needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]',dynamic)
    if any(n in ('libc.so.6','libpthread.so.0','libdl.so.2','librt.so.1') for n in needed):
        raise ValueError('glibc SONAME: '+name)
    return {'path':name,'needed':needed,'interpreters':interpreters}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--tag',required=True)
    assemble(parser.parse_args())
