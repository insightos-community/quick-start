#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Run the real installer, then exercise all robot/render libraries in one process."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
parser.add_argument('--musl-runtime', choices=['bundled', 'system'], default='bundled')
parser.add_argument('--dir', type=Path, required=True)
args = parser.parse_args()
subprocess.run([sys.executable, HERE.parent/'smoke_release.py', '--musl', '--offline', '--package', args.package,
                '--dir', args.dir, '--port-base', '29080', '--musl-runtime', args.musl_runtime], check=True)
spec = importlib.util.spec_from_file_location('musl_installer', HERE.parent/'runtime/installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
release = (args.dir/'current').resolve()
metadata = json.loads((release/'release.json').read_text())
python = release/'robot-bundles'/metadata['bundle_name']/'python/venv/bin/python'
env = installer.environment(args.dir, release)
code = r'''
import ctypes, inspect, json, os, runpy, sys, tempfile
from pathlib import Path
import numpy as np, pinocchio as pin, coal, ruckig, mujoco, ability_py, websockets
assert sys.version_info[:2] == (3,13)
# Subprocesses and multiprocessing must follow the same prepared ELF interpreter.
import subprocess
child = subprocess.check_output([sys.executable, '-c', 'import sys,numpy; print(sys.base_prefix)'], text=True).strip()
assert Path(child).resolve() == Path(os.environ['EXPECTED_PYTHON']).resolve()
import multiprocessing
worker = multiprocessing.get_context('spawn').Process(target=os.getpid)
worker.start(); worker.join(20)
if worker.is_alive():
    worker.terminate(); worker.join()
    raise AssertionError('Spawned Python did not exit')
assert worker.exitcode == 0
# Host tools must remain usable without inheriting musl library search paths.
subprocess.run(['tar', '--version'], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['zstd', '--version'], check=True, stdout=subprocess.DEVNULL)
assert np.__version__ == '2.3.5'
assert Path(sys.base_prefix).resolve() == Path(os.environ['EXPECTED_PYTHON']).resolve()
checks = runpy.run_path(os.environ['ROBOT_CHECKS'])
for name, function in checks.items():
    if name.startswith('test_') and callable(function):
        with tempfile.TemporaryDirectory() as directory:
            kwargs = {'tmp_path': Path(directory)} if 'tmp_path' in inspect.signature(function).parameters else {}
            function(**kwargs)
model = pin.buildSampleModelManipulator()
data = model.createData()
q = pin.neutral(model)
tau = pin.rnea(model, data, q, np.zeros(model.nv), np.zeros(model.nv))
assert tau.shape == (model.nv,) and np.isfinite(tau).all()
result = coal.CollisionResult()
assert coal.collide(coal.Sphere(1), coal.Transform3s(), coal.Sphere(1), coal.Transform3s(), coal.CollisionRequest(), result) > 0
inp, out, otg = ruckig.InputParameter(1), ruckig.OutputParameter(1), ruckig.Ruckig(1, .01)
inp.current_position=[0]; inp.current_velocity=[0]; inp.current_acceleration=[0]
inp.target_position=[1]; inp.target_velocity=[0]; inp.target_acceleration=[0]
inp.max_velocity=[1]; inp.max_acceleration=[2]; inp.max_jerk=[4]
assert otg.update(inp,out) == ruckig.Result.Working and out.new_position[0] > 0
model = mujoco.MjModel.from_xml_string('<mujoco><worldbody><light pos="0 0 3"/><geom type="plane" size="3 3 .1"/><body pos="0 0 1"><freejoint/><geom type="sphere" size=".2" rgba="1 0 0 1"/></body></worldbody></mujoco>')
data = mujoco.MjData(model)
for _ in range(500): mujoco.mj_step(model,data)
assert data.qpos[2] < .3 and data.ncon > 0
with mujoco.Renderer(model,64,64) as renderer:
    renderer.update_scene(data)
    rgb = renderer.render()
    assert rgb.shape == (64,64,3) and rgb.max() > rgb.min()
    renderer.enable_depth_rendering()
    depth = renderer.render()
    assert np.isfinite(depth).all() and depth.min() > 0
maps = Path('/proc/self/maps').read_text()
assert 'ld-musl-x86_64' in maps or 'libc.musl-x86_64' in maps
assert 'libc.so.6' not in maps
loader = str(Path(os.environ['EXPECTED_PYTHON']).parent/'musl/lib/ld-musl-x86_64.so.1')
assert (loader in maps) == (os.environ['EXPECTED_MUSL_RUNTIME'] == 'bundled')
loaded = {line.split()[-1] for line in maps.splitlines() if '/' in line}
for library in ('libassimp.so.', 'libqhull_r.so.', 'libtinyxml2.so.', 'libz.so.', 'libLLVM.so.'):
    paths = [Path(path) for path in loaded if Path(path).name.startswith(library)]
    assert paths and all(path.is_relative_to(Path(os.environ['EXPECTED_PYTHON']).parent/'musl/lib') for path in paths), (library, paths)
print(json.dumps({'python':sys.version,'base_prefix':sys.base_prefix,'numpy':np.__version__, 'pinocchio':pin.__version__, 'mujoco':mujoco.__version__, 'robot_and_render':'passed'}))
'''
env.update(EXPECTED_MUSL_RUNTIME=args.musl_runtime, EXPECTED_PYTHON=str(release/'python'), ROBOT_CHECKS=str(HERE/'robot_checks.py'), PYTHONPATH='', PYTHONNOUSERSITE='1')
result = subprocess.check_output([python, '-c', code], env=env, text=True)
# The CLI-created native environment must resolve to the SAME bundled interpreter.
venvs = [p for p in args.dir.rglob('pyvenv.cfg') if p.parent != python.parent.parent]
if len(venvs) != 1:
    raise AssertionError(f'Expected one native runtime venv, got {venvs}')
runtime_python = venvs[0].parent/'bin/python'
base = subprocess.check_output([runtime_python,'-c','import sys,numpy; assert numpy.__version__ == "2.3.5"; print(sys.base_prefix)'],env=env,text=True).strip()
assert Path(base).resolve() == (release/'python').resolve()
report = {'combined_runtime':json.loads(result),'same_python_base':base,
          'render':json.loads((args.dir/'configs/musl-render.json').read_text())}
(args.dir/'musl-smoke-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
