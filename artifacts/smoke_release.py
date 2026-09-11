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

"""Opt-in real install test. Uses a separate directory/ports; never starts Robot tasks."""
import argparse
import functools
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.request

HERE = Path(__file__).resolve().parent


def request(base, path, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    req = urllib.request.Request(base+path, headers=headers, data=json.dumps(data).encode() if data else None)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=20) as response:
        return json.load(response)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--musl', action='store_true', help='Exercise the explicitly selected musl variant')
    p.add_argument('--offline', action='store_true', help='Test loopback only in a container without a network interface')
    p.add_argument('--dir', type=Path, help='New or previously managed smoke-test directory')
    p.add_argument('--port-base', type=int, default=28080)
    p.add_argument('--install-system-deps', action='store_true', help='Opt-in, intended for disposable containers')
    p.add_argument('--configure-package', type=Path, help='After install, test management-only update from this newer package')
    a = p.parse_args()
    root = a.dir.resolve() if a.dir else Path(tempfile.mkdtemp(prefix='smoke-', dir=HERE/'.build'))
    ports = [a.port_base+i for i in range(4)]
    options = ['--dir', str(root), '--yes', '--http-port', str(ports[0]), '--ws-port', str(ports[1]),
               '--web-port', str(ports[2]), '--runtime-port', str(ports[3])]
    if a.musl:
        options.append('--musl')
    if a.install_system_deps:
        options.append('--install-system-deps')
    report = {'directory': str(root), 'package': str(a.package.resolve()), 'checks': []}
    ctl = root/'bin/semanticctl'
    try:
        subprocess.run(['bash', str(HERE/'install.sh'), '--package', str(a.package.resolve()), *options], check=True)
        base = f'http://127.0.0.1:{ports[2]}'
        password = json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD']
        token = request(base, '/api/v1/auth/login', {'username': 'admin', 'password': password})['token']
        with urllib.request.urlopen(base+'/projects/test-spa-route') as r:
            assert b'<html' in r.read().lower()
        report['checks'].append('Web SPA routing and same-origin authenticated API')
        state = json.loads((root/'install.json').read_text())
        if state.get('web_host') == '0.0.0.0' and not a.offline:
            with __import__('socket').socket(__import__('socket').AF_INET, __import__('socket').SOCK_DGRAM) as sock:
                sock.connect(('192.0.2.1', 9))
                lan_ip = sock.getsockname()[0]
            assert request(f'http://{lan_ip}:{ports[2]}', '/api/v1/system/healthz')
            report['checks'].append('Default install serves both loopback and LAN without --lan')
        release = json.loads((root/'current/release.json').read_text())
        for skill in release['robot_skills']:
            result = request(base, f"/api/v1/robot-skills/{skill['name']}/{skill['version']}", token=token)
            assert result
        report['checks'].append('Three exact Robot Skill versions published')
        runtime = subprocess.check_output([str(root/'current/bin/semantic'), 'runtime', 'list',
                                          '-c', str(root/'configs/semantic-server.yaml')], text=True)
        assert 'native-mujoco' in runtime
        report['checks'].append('Native MuJoCo profile registered after real CLI scene smoke')
        # Exercise the actual curl | bash path using a loopback HTTP mirror, then idempotence.
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(HERE)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        mirror = f'http://127.0.0.1:{server.server_port}'
        try:
            curl = subprocess.Popen(['curl', '-fsSL', mirror+'/install.sh'], stdout=subprocess.PIPE)
            with curl.stdout:
                result = subprocess.run(['bash', '-s', '--', '--base-url', mirror, '--allow-http',
                    '--version', release['version'], *options], stdin=curl.stdout)
            assert curl.wait() == 0 and result.returncode == 0
        finally:
            server.shutdown()
            server.server_close()
        assert json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD'] == password
        report['checks'].append('HTTP mirror curl pipe, archive SHA256 and same-version password preservation')
        # Management-only configuration must also work for older installed releases.
        config_package = a.configure_package or a.package
        old_version = release['version']
        signature = (root/'current/files.json').read_bytes()
        server_identity = json.loads((root/'run/services.json').read_text())['server']
        for host, web_port in [('0.0.0.0', ports[2]), ('127.0.0.1', ports[2]), ('0.0.0.0', ports[2]+10)]:
            subprocess.run(['bash', str(HERE/'install.sh'), '--package', str(config_package.resolve()),
                            '--configure-existing', '--dir', str(root), '--yes', '--web-host', host,
                            '--web-port', str(web_port), '--no-desktop-shortcut'], check=True)
            assert json.loads((root/'install.json').read_text())['version'] == old_version
            assert json.loads((root/'install.json').read_text())['web_port'] == web_port
            assert request(f'http://127.0.0.1:{web_port}', '/api/v1/system/healthz')
            assert (root/'current/files.json').read_bytes() == signature
            assert json.loads((root/'configs/secrets.json').read_text())['SEMANTIC_ADMIN_PASSWORD'] == password
            assert json.loads((root/'run/services.json').read_text())['server'] == server_identity
            if host == '0.0.0.0' and not a.offline:
                with __import__('socket').socket(__import__('socket').AF_INET, __import__('socket').SOCK_DGRAM) as sock:
                    sock.connect(('192.0.2.1', 9))  # Routing lookup only; no packet sent.
                    lan_ip = sock.getsockname()[0]
                assert request(f'http://{lan_ip}:{web_port}', '/api/v1/system/healthz')
        report['checks'].append(('Loopback verification of Web listen settings' if a.offline else 'LAN Web interface') + ' and proxied API; management-only update preserves app version, payload and password')
        assert (root/'configs/secrets.json').stat().st_mode & 0o777 == 0o600
        report['success'] = True
    finally:
        if ctl.exists():
            subprocess.run([str(ctl), 'stop'], check=True)
        report_path = root/'smoke-report.json' if root.exists() else root.parent/'smoke-report.json'
        report_path.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
