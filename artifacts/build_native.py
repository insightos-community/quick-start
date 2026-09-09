#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Build release-only native binaries without changing the source workspace builds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def elf_report(path):
    env = {**os.environ, 'LC_ALL': 'C'}
    headers = subprocess.check_output(['readelf', '-hW', str(path)], text=True, env=env)
    dynamic = subprocess.check_output(['readelf', '-dW', str(path)], text=True, env=env)
    program = subprocess.check_output(['readelf', '-lW', str(path)], text=True, env=env)
    symbols = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(path)], text=True, env=env)
    versions = re.findall(r'@GLIBC_([0-9.]+)', symbols)
    needed = re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic)
    interpreter = 'INTERP' in program
    return dict(sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                machine='x86_64' if 'Advanced Micro Devices X86-64' in headers else 'unknown',
                static=not needed and not interpreter, needed=needed, interpreter=interpreter,
                minimum_glibc=max(versions, key=lambda v: tuple(map(int, v.split('.')))) if versions else None)


def require_static(path):
    report = elf_report(path)
    if not report['static'] or report['machine'] != 'x86_64':
        raise ValueError(f'需要完整静态 x86_64 ELF: {path}: {report}')
    return report


def logged(command, cwd, log, env=None, accepted=(0,)):
    print('构建:', ' '.join(map(str, command)), flush=True)
    with log.open('a') as f:
        f.write('\n$ '+' '.join(map(str, command))+'\n')
        f.flush()
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        if result.returncode not in accepted:
            raise subprocess.CalledProcessError(result.returncode, command)


def ability(workspace, output, log):
    source = workspace/'ability-framework/abilityframework'
    # An independent clone keeps xmake configuration, generated headers and outputs isolated.
    stage = Path(tempfile.mkdtemp(prefix='ability-static-', dir=HERE/'.build'))
    logged(['git', 'clone', '--local', '--no-hardlinks', source, stage/'source'], workspace, log)
    tree = stage/'source'
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode().split('\0')
    for name in filter(None, tracked):
        src, dst = source/name, tree/name
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif dst.is_file():
            dst.unlink()
    # Source dependencies, never host .so discoveries, for this release-only configuration.
    project = tree/'xmake.lua'
    project.write_text('add_requireconfs("**", {system = false, configs = {shared = false}})\n'+project.read_text())
    env = {**os.environ, 'XMAKE_COLORTERM': 'nocolor'}
    logged(['xmake', 'f', '-y', '-m', 'release', '--fwk-static=y'], tree, log, env)
    logged(['xmake', 'build', '-y', '-j', '4', 'AbilityFramework'], tree, log, env)
    binary = tree/'build/linux/x86_64/release/AbilityFramework'
    report = require_static(binary)
    logged([binary, '--version'], tree, log)
    shutil.copy2(binary, output/'AbilityFramework')
    return {'AbilityFramework': report}


def server(workspace, output, log):
    source = workspace/'semantic-framework'
    env = {**os.environ, 'CGO_ENABLED': '1', 'CC': 'musl-gcc'}
    if not shutil.which('musl-gcc'):
        raise RuntimeError('静态 Go 构建需要 musl-gcc；在构建机安装 musl-tools 后重试')
    reports = {}
    for name in ('semantic-server', 'semantic', 'semantic-pilot'):
        binary = output/name
        logged(['go', 'build', '-trimpath', '-tags', 'musl,netgo,osusergo',
                '-ldflags', '-linkmode external -extldflags "-static"',
                '-o', binary, './cmd/'+name], source, log, env)
        reports[name] = require_static(binary)
        logged([binary, '--help'], source, log, accepted=(0, 2) if name == 'semantic' else (0,))
    binary = output/'semantic-robot-instance'
    logged(['go', 'build', '-trimpath', '-tags', 'musl,netgo,osusergo',
            '-ldflags', '-linkmode external -extldflags "-static"', '-o', binary,
            './cmd/semantic-robot-instance'], workspace/'semantic-robot-deployment', log, env)
    reports[binary.name] = require_static(binary)
    logged([binary, '--help'], source, log, accepted=(0, 2))
    probe = output/'pdf-probe'
    logged(['go', 'build', '-trimpath', '-tags', 'musl,netgo,osusergo',
            '-ldflags', '-linkmode external -extldflags "-static"', '-o', probe,
            HERE/'probes/pdf_static.go'], source, log, env)
    require_static(probe)
    logged([probe], source, log)
    return reports


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, default=HERE.parent)
    p.add_argument('--component', choices=['ability', 'server', 'all'], default='all')
    p.add_argument('--output', type=Path, default=HERE/'.build/native-static')
    a = p.parse_args()
    (HERE/'.build').mkdir(exist_ok=True)
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, function in [('ability', ability), ('server', server)]:
        if a.component not in (name, 'all'):
            continue
        log = output/(name+'-build.log')
        log.touch(mode=0o600)
        print('日志:', log, flush=True)
        report = function(a.workspace.resolve(), output, log)
        (output/(name+'-build.json')).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
