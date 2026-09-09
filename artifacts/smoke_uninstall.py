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

"""Create a disposable instance; test uninstall, same-version restore, and pipe purge."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--port-base', type=int, default=29080)
    a = p.parse_args()
    results = Path(tempfile.mkdtemp(prefix='uninstall-smoke-', dir=HERE/'.build'))
    root = results/'instance'
    options = ['--dir', str(root), '--yes', '--http-port', str(a.port_base),
               '--ws-port', str(a.port_base+1), '--web-port', str(a.port_base+2), '--runtime-port', str(a.port_base+3)]
    install = ['bash', str(HERE/'install.sh'), '--package', str(a.package.resolve()), *options]
    uninstall = ['bash', str(HERE/'install.sh'), '--uninstall', '--dir', str(root)]
    log = results/'smoke.log'
    log.touch(mode=0o600)
    print('卸载集成测试日志:', log, flush=True)
    report = dict(instance=str(root), package=str(a.package.resolve()), success=False)
    try:
        with log.open('a') as f:
            subprocess.run(install, check=True, stdout=f, stderr=subprocess.STDOUT)
            sentinel = root/'data/uninstall-test.txt'
            sentinel.write_text('User data survives default uninstall')
            fingerprint = lambda: hashlib.sha256((root/'configs/secrets.json').read_bytes()).hexdigest()
            secret_hash = fingerprint()
            subprocess.run([*uninstall, '--dry-run'], check=True, stdout=f, stderr=subprocess.STDOUT)
            assert (root/'bin/semanticctl').is_file()
            subprocess.run([*uninstall, '--yes'], check=True, stdout=f, stderr=subprocess.STDOUT)
            assert not (root/'releases').exists() and not (root/'current').is_symlink()
            assert sentinel.exists() and (root/'data/semantic.db').exists() and fingerprint() == secret_hash
            subprocess.run(install, check=True, stdout=f, stderr=subprocess.STDOUT)
            assert sentinel.exists() and fingerprint() == secret_hash
            # stdin is the script itself; flags must still work without a controlling tty.
            subprocess.run(['bash', '-s', '--', '--uninstall', '--dir', str(root), '--purge', '--yes'],
                input=(HERE/'install.sh').read_text(), text=True, check=True, stdout=f, stderr=subprocess.STDOUT)
            assert not root.exists()
            report['success'] = True
    finally:
        if (root/'bin/semanticctl').exists():
            subprocess.run([str(root/'bin/semanticctl'), 'stop'], check=False)
        (results/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
