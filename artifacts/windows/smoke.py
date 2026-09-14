"""Exercise the extracted payload on native Windows without dependency downloads."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent))
from manager import Manager, shared
from install_support import component_values, export_components
from macos.project_smoke import check_project


def free_values():
    sockets = [socket.socket() for _ in range(4)]
    try:
        for sock in sockets:
            sock.bind(('127.0.0.1',0))
        return dict(component_values(), **dict(zip(('http_port','ws_port','web_port','runtime_port'),
                   (sock.getsockname()[1] for sock in sockets))))
    finally:
        for sock in sockets:
            sock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    payload=args.payload.resolve(); root=args.root.resolve()
    assert not root.exists()
    report={'platform':'windows-amd64','physical_gpu_verified':False}
    values=free_values()
    config=root.parent/(root.name+' components.yaml')
    export_components(config,values)
    # Remove build tools, Conda and developer Python from the target environment.
    env=dict(os.environ,PATH=os.pathsep.join([os.environ['SystemRoot']+'/System32',os.environ['SystemRoot']]),
             UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX','UV_PYTHON_INSTALL_DIR'):
        env.pop(key,None)
    command=[str(payload/'python/python.exe'),'-I','-B',str(payload/'install.py'),
             '--payload',str(payload),'--dir',str(root),'--yes','--no-start','-f',str(config)]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',values['http_port'])); listener.listen(1)
        failed=subprocess.run(command,env=env,capture_output=True)
        assert failed.returncode != 0 and not root.exists(), 'Port preflight must precede installation'
    report['port_preflight']=True
    subprocess.run(command,env=env,check=True)
    subprocess.run(command,env=env,check=True)
    report['offline_install_and_retry']=True
    native_shortcuts = shared.load(root/'install.json')['native_shortcuts']
    assert len(native_shortcuts) == 4 and all(Path(p).is_file() for p in native_shortcuts)
    report['native_application_entries']=True
    manager=Manager(root)
    python=manager.release/'python/python.exe'
    def verify_shared_python(minimum):
        venvs = list(root.rglob('pyvenv.cfg'))
        assert len(venvs) >= minimum, 'Missing Robot, Runtime or Skill environments'
        for config_path in venvs:
            interpreter = config_path.parent/'Scripts/python.exe'
            actual = json.loads(subprocess.check_output([str(interpreter),'-I','-B','-c',
                'import json,sys; print(json.dumps(sys.base_prefix))'],env=env))
            assert Path(actual).resolve() == python.parent.resolve(), actual
        report['shared_python_environments'] = [str(path.parent.relative_to(root)) for path in venvs]
    verify_shared_python(2)
    report['shared_base_python'] = str(python.parent)
    manifest = shared.load(manager.release/'release.json')
    robot_python = manager.release/'robot-bundles'/manifest['bundle_name']/'python/venv/Scripts/python.exe'
    pin_source = json.loads((HERE/'sources.json').read_text())['pinocchio']
    math_env = manager.environment()
    math_env.update(PATH=os.pathsep.join([str(python.parent),str(manager.release/'bin'),env['PATH']]),
        SEMANTIC_PINOCCHIO_SOURCE_COMMIT=pin_source.get('build_commit',pin_source['commit']),
        SEMANTIC_PINOCCHIO_VERIFICATION_COMMIT=pin_source['commit'])
    subprocess.run([str(robot_python),'-I','-B',str(HERE.parents[1]/'sources/pinocchio/ci/windows/verify.py'),
                    str(args.report.with_name('windows-installed-math.json'))],env=math_env,check=True)
    report['installed_math_unicode_paths']=True
    ctl=[str(python),'-I','-B',str(manager.release/'manager.py'),'--dir',str(root)]
    def control(*arguments):
        subprocess.run(ctl+list(arguments),env=env,check=True)
        manager.reload()
    try:
        control('start')
        def project(label):
            base=f"http://127.0.0.1:{manager.values['web_port']}"
            password=shared.load(root/'configs/secrets.json')['SEMANTIC_ADMIN_PASSWORD']
            token=shared.request(base+'/api/v1/auth/login',data=json.dumps({'username':'admin','password':password}).encode())['token']
            check_project(root,base,token,args.report.with_name(label+'.json'),release_dir=manager.release,readiness_timeout=360)
        project('windows-project-first')
        report['project_abilities_skills_pilot']=True
        skill_envs = list((root/'runtime-envs/skills').glob('*/pyvenv.cfg'))
        assert len(skill_envs) >= 3, 'Skills must use the short installation-owned environment root'
        assert not list((root/'robots').glob('**/skills/environments/**/.semantic-ready'))
        report['offline_uv_skill_environments']=True
        changed=free_values()
        config=root.parent/(root.name+' reconfigured components.yaml')
        export_components(config,changed)
        control('reconfigure','-f',str(config))
        project('windows-project-reconfigured')
        report['reconfigured_project']=True
        # Include dynamically installed Skill venvs in the single-base assertion.
        verify_shared_python(5)
        control('stop')
        assert manager.status()=={'server':False,'web':False}
        control('start')
        control('stop')
        report['local_management_restart']=True
        cleanup=subprocess.run(ctl+['uninstall','--yes'],env=env,check=True,capture_output=True)
        result=Path(cleanup.stdout.decode('utf-8').strip().split('Result: ',1)[1])
        deadline=time.monotonic()+120
        while not result.exists() and time.monotonic()<deadline:
            time.sleep(0.2)
        evidence=json.loads(result.read_text(encoding='utf-8'))
        assert evidence['success'],evidence
        assert not (root/'releases').exists() and (root/'data/semantic.db').is_file()
        assert all(not Path(p).exists() for p in native_shortcuts)
        report['offline_uninstall_preserves_data']=True
    finally:
        # Keep the originating project error if conservative cleanup refuses an
        # unconfirmed Robot; never replace it with a secondary stop exception.
        failed = sys.exc_info()[0] is not None
        # The manager preserves any scene whose normal release was not confirmed.
        try:
            if not report.get('offline_uninstall_preserves_data'):
                control('stop')
        except Exception as error:
            report['cleanup_error'] = str(error)
            if not failed:
                raise
        finally:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
