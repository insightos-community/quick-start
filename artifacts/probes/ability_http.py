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

"""Start a static AbilityFramework with empty state and probe its read-only APIs."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('binary', type=Path)
a = p.parse_args()
with tempfile.TemporaryDirectory(prefix='semantic-af-probe-') as temporary:
    root = Path(temporary)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    (root/'log').mkdir()
    config = root/'config.yaml'
    config.write_text(json.dumps({'framework_name': 'static-portability-smoke',
        'http_ip': '127.0.0.1', 'http_port': port,
        'log': {'glog': {'log_dir': str(root/'log'), 'also_log_to_stderr': True}}}))
    with (root/'output.log').open('w+') as log:
        process = subprocess.Popen([str(a.binary.resolve()), '-c', str(config)], cwd=root,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+20
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/crs', timeout=1) as response:
                        json.load(response)
                    break
                except (OSError, ValueError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    time.sleep(.1)
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/ui/', timeout=5) as response:
                assert b'html' in response.read().lower()
            print('PASS: static AbilityFramework startup, resource API, embedded Web UI')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
