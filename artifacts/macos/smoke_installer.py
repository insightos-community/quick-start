#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Exercise the distributed bootstrap and offline installer on macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

HERE=Path(__file__).resolve().parent


def run(*args, **kwargs):
    return subprocess.run(list(map(str,args)), check=True, **kwargs)


def request(url, data=None):
    req=urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                               headers={'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=20) as r:
        return json.load(r)


def main(a):
    root=a.root.resolve()
    package=a.package.resolve()
    checksum=hashlib.file_digest(package.open('rb'),'sha256').hexdigest()
    options=['--package',package,'--sha256',checksum,'--dir',root,'--yes','--no-desktop-shortcut',
             '--web-host','127.0.0.1','--http-port','28080','--ws-port','28081','--web-port','28082','--runtime-port','28083']
    ctl=root/'bin/semanticctl'
    report={'checks':[], 'graphics':'not-qualified: physical Mac CGL validation required'}
    try:
        run('bash',HERE/'bootstrap.sh',*options)
        report['checks'].append('Downloaded-format archive SHA256, bootstrap, offline install and native scene startup smoke')
        state=json.loads((root/'install.json').read_text())
        password=json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD']
        response=request('http://127.0.0.1:28082/api/v1/auth/login',{'username':'admin','password':password})
        assert response['token']
        request('http://127.0.0.1:28082/api/v1/system/healthz')
        report['checks'].append('Web gateway, Server health and authenticated login')
        release=root/'releases'/state['version']
        metadata=json.loads((release/'release.json').read_text())
        robot=release/'robot-bundles'/metadata['bundle_name']/'python/venv/bin/python'
        env={**os.environ, 'PYTHONPATH':'', 'PYTHONNOUSERSITE':'1', 'MUJOCO_GL':'cgl'}
        run(robot,HERE/'smoke.py',env=env)
        run(robot,'-c',"import runpy,tempfile,inspect; from pathlib import Path; checks=runpy.run_path("+repr(str(HERE.parent/'musl/robot_checks.py'))+");\nwith tempfile.TemporaryDirectory() as tmp:\n for name, fn in checks.items():\n  if name.startswith('test_'): fn(Path(tmp)) if inspect.signature(fn).parameters else fn()",env=env)
        run(release/'bin/uv','pip','check','--python',robot,env=env)
        report['checks'].append('Shared Python/NumPy: Pinocchio, Ruckig, MuJoCo and actual Robot math checks; dependency consistency')
        runtime_pythons=list((root/'runtime-envs').rglob('bin/python'))
        assert runtime_pythons, 'Missing runtime venv'
        for python in [robot,*runtime_pythons]:
            prefix=subprocess.check_output([str(python),'-c','import sys,numpy; assert numpy.__version__=="2.3.5"; print(sys.base_prefix)'],text=True).strip()
            assert Path(prefix).resolve()==(release/'python').resolve(),prefix
        report['checks'].append('Robot and simulation use the same bundled Python base and NumPy version')
        run(ctl,'status')
        run(ctl,'stop')
        run(ctl,'start')
        run('bash',HERE/'bootstrap.sh',*options)
        assert json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD']==password
        report['checks'].append('Process identity, stop/start and repeat installation preserve credentials')
        run(ctl,'uninstall','--dry-run')
        run(ctl,'uninstall','--yes')
        assert (root/'configs/secrets.json').is_file() and not (root/'releases').exists()
        report['checks'].append('Uninstall preserves user configuration and removes installed programs')
        report['success']=True
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2)+'\n')
        if ctl.exists():
            subprocess.run([str(ctl),'stop'],check=False)
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    main(p.parse_args())
