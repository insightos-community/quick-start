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

"""Opt-in disposable-container deployment smoke, with persistent local logs (no host services)."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
IMAGES = {
    'debian11': ('python:3.11-bullseye', ['python3', '/artifacts/probes/debian_https.py']),
    'debian12': ('python:3.11-bookworm', ['python3', '/artifacts/probes/debian_https.py']),
    'fedora': ('fedora:42', ['dnf', 'install', '-y', 'python3', 'curl']),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--distro', choices=IMAGES, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--configure-package', type=Path)
    a = p.parse_args()
    relative = a.package.resolve().relative_to(HERE)
    results = Path(tempfile.mkdtemp(prefix='container-'+a.distro+'-', dir=HERE/'.build'))
    image, bootstrap = IMAGES[a.distro]
    # No host network, privileged mode, devices, or daemon socket mounted.
    command = ['docker', 'run', '--rm', '-v', f'{HERE}:/artifacts:ro', '-v', f'{results}:/results',
               image, 'python3', '/artifacts/smoke_release.py', '--package', '/artifacts/'+str(relative),
               '--dir', '/results/semantic', '--install-system-deps']
    if a.configure_package:
        command += ['--configure-package', '/artifacts/'+str(a.configure_package.resolve().relative_to(HERE))]
    script = f"trap 'chown -R {os.getuid()}:{os.getgid()} /results' EXIT; "
    if bootstrap:
        script += ' '.join(bootstrap)+' && '
    script += '"$@"'
    command = command[:command.index(image)+1] + ['sh', '-c', script, 'sh', *command[command.index(image)+1:]]
    log = results/'container.log'
    log.touch(mode=0o600)
    print('容器测试日志:', log, flush=True)
    with log.open('a') as f:
        result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT)
    report = dict(image=image, returncode=result.returncode, log=str(log), command=command)
    (results/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
