"""Publish a Windows release only after the complete offline project smoke passes."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root=Path('output')
tag=os.environ['GITHUB_REF_NAME']
repo=os.environ['GITHUB_REPOSITORY']
if not re.fullmatch(r'windows-v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',tag):
    raise ValueError('Invalid Windows installer tag')
version=tag.removeprefix('windows-v')
load=lambda name:json.loads((root/name).read_text())
release=load('release.json'); manifest=load('manifest.json'); report=load('windows-installation.json')
assert release['version']==manifest['version']==version
assert release['platform']==manifest['platform']=='windows-amd64'
assert release['source_commit']==os.environ['GITHUB_SHA']
for key in ('port_preflight','offline_install_and_retry','installed_math_unicode_paths',
            'project_abilities_skills_pilot','reconfigured_project','local_management_restart',
            'offline_uninstall_preserves_data'):
    assert report.get(key),key
assert report['shared_base_python']
assert len(report['shared_python_environments']) >= 5
for name in ('windows-project-first.json','windows-project-reconfigured.json'):
    project=load(name)
    assert project['success'] and project['released'],name
math=load('windows-installed-math.json')
assert math['fk_rnea'] and math['urdf_mesh_collision']
def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
for line in (root/'SHA256SUMS').read_text().splitlines():
    expected,name=line.split('  ',1)
    assert name==Path(name).name and checksum(root/name)==expected,name
assert manifest['archive']==Path(manifest['archive']).name
assert checksum(root/manifest['archive'])==manifest['sha256']
# Include the post-assembly validation reports in the published checksum set.
(root/'SHA256SUMS').write_text(''.join(checksum(path)+'  '+path.name+'\n' for path in sorted(root.iterdir())
                                    if path.is_file() and path.name!='SHA256SUMS'))
existing=subprocess.run(['gh','release','view',tag,'--repo',repo,'--json','isDraft'],capture_output=True)
if existing.returncode==0 and not json.loads(existing.stdout)['isDraft']:
    subprocess.run(['gh','release','download',tag,'--repo',repo,'--pattern','release.json','--dir','existing-release'],check=True)
    old=json.loads(Path('existing-release/release.json').read_text())
    assert all(old[key]==release[key] for key in ('version','platform','source_commit'))
    print('Matching published release already exists; original assets preserved')
    raise SystemExit(0)
if existing.returncode!=0:
    notes=Path('windows-release-notes.md')
    notes.write_text('''Native Windows x64 offline installer preview. Extract the ZIP and run `install.cmd` from Command Prompt. Use `install.cmd --export-config components.yaml` and `-f components.yaml` to customize ports. Installed `bin\\semanticctl.cmd` supports start, stop, reconfigure and local uninstall.

Validated on Windows Server 2022 runners: offline installation/retry, one bundled CPython 3.13.15 base with NumPy 2.3.5, native math/URDF/collision in Unicode paths, real project startup with seven healthy Abilities, three Skills and an online Pilot, port reconfiguration, normal scene release, restart and uninstall preserving data.

Physical Windows desktop GPU rendering has not been qualified. This is a preview; see the JSON validation reports for the exact tested scope. The executables are currently unsigned.
''')
    subprocess.run(['gh','release','create',tag,'--repo',repo,'--target',os.environ['GITHUB_SHA'],'--draft','--prerelease',
                    '--title','Semantic Windows x64 '+version,'--notes-file',str(notes)],check=True)
subprocess.run(['gh','release','upload',tag,'--repo',repo,'--clobber',*map(str,sorted(root.iterdir()))],check=True)
# Verify GitHub's received assets before making the draft public.
# GitHub's tag lookup omits drafts. The CLI resolves the draft's release ID.
release_url=json.loads(subprocess.check_output(['gh','release','view',tag,'--repo',repo,'--json','apiUrl']))['apiUrl']
published=json.loads(subprocess.check_output(['gh','api',release_url]))
assets={asset['name']:asset for asset in published['assets']}
for path in sorted(root.iterdir()):
    if not path.is_file():
        continue
    asset=assets[path.name]
    assert asset['size']==path.stat().st_size,path.name
    assert asset['digest']=='sha256:'+checksum(path),path.name
subprocess.run(['gh','release','edit',tag,'--repo',repo,'--draft=false'],check=True)
