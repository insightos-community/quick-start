"""Fetch native CI inputs only after their exact revision passes validation."""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
pins = json.loads((HERE/'sources.json').read_text())
root = Path(sys.argv[1]).resolve()


def fetch(repo, run, name, destination):
    # CI may wait for the expensive source build; a failure prevents assembly.
    subprocess.run(['gh','run','watch',str(run),'--repo','insightos-community/'+repo,'--exit-status','--interval','30'],check=True)
    result = json.loads(subprocess.check_output(['gh','api',f'repos/insightos-community/{repo}/actions/runs/{run}']))
    if result['conclusion'] != 'success' or result['head_sha'] != pins[repo]['commit'] or result['event'] != 'push':
        raise ValueError('Native input run does not match the qualified source: '+repo)
    subprocess.run(['gh','run','download',str(run),'--repo','insightos-community/'+repo,'--name',name,'--dir',str(destination)],check=True)


def fetch_release(repo, destination):
    pinned = json.loads((HERE/'native-releases.json').read_text())[repo]
    subprocess.run(['gh','release','download',pinned['tag'],'--repo','insightos-community/'+repo,
                    '--dir',str(destination)],check=True)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(destination/'SHA256SUMS') != pinned['checksums_sha256']:
        raise ValueError('Native release checksum manifest changed: '+repo)
    for line in (destination/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ',1)
        if name != Path(name).name or ':' in name or digest(destination/name) != checksum:
            raise ValueError('Native release asset checksum mismatch: '+repo)
    metadata = json.loads((destination/'release.json').read_text())
    if metadata['source_commit'] != pins[repo]['commit'] or metadata['platform'] != 'windows-amd64':
        raise ValueError('Native release source identity mismatch: '+repo)


fetch_release('AbilityFramework',root/'ability')
archives = list((root/'ability').rglob('AbilityFramework-windows-amd64-development.zip'))
if len(archives) != 1:
    raise ValueError('Expected one native AbilityFramework archive')
with zipfile.ZipFile(archives[0]) as archive:
    for name in archive.namelist():
        if name != Path(name).name or ':' in name:
            raise ValueError('Unexpected native archive member')
    archive.extractall(root/'bin')
fetch_release('r1pro-ability',root/'abilities/windows')
fetch('pinocchio',34813368953,'pinocchio-windows-cp313',root/'pin-inputs')

reports = list((root/'pin-inputs').rglob('windows-validation.json'))
if len(reports) != 1:
    raise ValueError('Expected one standalone Pinocchio validation report')
shutil.copytree(reports[0].parent, root/'pin')
