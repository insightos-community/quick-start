#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual project -> scene -> AbilityFramework -> Pilot startup path."""
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def check_project(root, base, token, report):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, data=None):
        req = urllib.request.Request(base+'/api/v1'+path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json', 'Authorization':'Bearer '+token})
        try:
            with opener.open(req, timeout=240) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{path}: HTTP {error.code}: {error.read().decode()}') from error

    project = request('/projects', {'name':'Native macOS device startup regression'})['project']
    project_path = '/projects/'+project['id']+'/simulation'
    diagnostics = {}
    try:
        request(project_path+'/runtime/ensure', {})
        instance = request(project_path+'/scenes/palletizing_depalletizing_tote_v1/instances', {
            'request_id':'macos-ability-startup', 'runtime_profile_id':'native-mujoco',
            'layout':'layout001', 'seed':7, 'headless':True, 'render_backend':'auto'})['instance']
        diagnostics['instance'] = instance
        deadline = time.monotonic()+180
        while True:
            devices = request('/devices')['devices']
            diagnostics['devices'] = devices
            states = [json.loads(path.read_text()) for path in (root/'robots').glob('*/*/run/state.json')]
            diagnostics['supervisors'] = states
            failed = [state for state in states if state.get('status') == 'failed']
            assert not failed, failed
            if devices and states and all(state.get('status') == 'running' for state in states) and all(
                device.get('pilot', {}).get('status') == 'online' and
                device.get('ability_framework', {}).get('status') == 'ready' and
                device.get('ability_framework', {}).get('healthy_instances') == 7
                for device in devices):
                break
            if time.monotonic() >= deadline:
                raise AssertionError('Project devices did not become ready: '+json.dumps(diagnostics))
            time.sleep(1)
        assert len(devices) >= 2, 'Expected both scene robots'
        diagnostics['success'] = True
    finally:
        report.write_text(json.dumps(diagnostics, indent=2)+'\n')
        # The server performs the normal safe shutdown, including Pilot hold.
        request(project_path+'/runtime/release', {})
