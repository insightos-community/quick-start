"""Fetch native CI inputs only after their exact revision passes validation."""
import json
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


fetch('AbilityFramework',34812148701,'AbilityFramework-windows-amd64-development',root/'ability')
archives = list((root/'ability').rglob('AbilityFramework-windows-amd64-development.zip'))
if len(archives) != 1:
    raise ValueError('Expected one native AbilityFramework archive')
with zipfile.ZipFile(archives[0]) as archive:
    for name in archive.namelist():
        if name != Path(name).name or ':' in name:
            raise ValueError('Unexpected native archive member')
    archive.extractall(root/'bin')
fetch('r1pro-ability',34812933585,'r1pro-abilities-windows-amd64',root/'abilities')
fetch('pinocchio',34813368953,'pinocchio-windows-cp313',root/'pin-inputs')

reports = list((root/'pin-inputs').rglob('windows-validation.json'))
if len(reports) != 1:
    raise ValueError('Expected one standalone Pinocchio validation report')
shutil.copytree(reports[0].parent, root/'pin')
