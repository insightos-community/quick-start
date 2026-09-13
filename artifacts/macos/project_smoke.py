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
    release = json.loads((root/'current/release.json').read_text())
    expected_skills = {(skill['name'], skill['version']) for skill in release['robot_skills']}
    try:
        catalog = request('/simulation/scene-catalog?project_id='+project['id'])['scenes']
        scene = next(item for item in catalog if item['scene_id'] == 'depalletizing-r1pro')
        version = next(item for item in scene['versions'] if item['published'] and
                       item['runtime_scene_key'] == 'palletizing_depalletizing_tote_v1')
        reference = request(project_path+'/project-scenes', {
            'catalog_scene_id':scene['scene_id'], 'scene_version':version['version'],
            'default_variant_id':'layout001'})['project_scene']
        instance = request(project_path+'/project-scenes/'+reference['project_scene_id']+'/instances', {
            'request_id':'macos-ability-startup', 'variant_id':'layout001',
            'seed':7, 'headless':True, 'render_backend':'auto'})['instance']
        deadline = time.monotonic()+180
        while instance['state'] == 'starting':
            if time.monotonic() >= deadline:
                raise AssertionError('Scene stayed in starting: '+json.dumps(instance))
            time.sleep(1)
            instance = request(project_path+'/instances/'+instance['instance_id'])['instance']
        diagnostics['instance'] = instance
        assert instance['state'] == 'running', instance
        scene_robots = request(project_path+'/instances/'+instance['instance_id']+'/robots')['robots']
        expected_ids = {robot['robot_id'] for robot in scene_robots}
        assert expected_ids, 'Scene has no robots'
        deadline = time.monotonic()+180
        while True:
            devices = request('/devices')['devices']
            diagnostics['devices'] = devices
            states = [json.loads(path.read_text()) for path in (root/'robots').glob('*/*/run/state.json')]
            diagnostics['supervisors'] = states
            failed = [state for state in states if state.get('status') == 'failed']
            failed += [device.get('runtime_instance') for device in devices
                       if (device.get('runtime_instance') or {}).get('status') in ('failed', 'interrupted')]
            assert not failed, failed
            if devices and states and all(state.get('status') == 'running' for state in states) and all(
                (device.get('runtime_instance') or {}).get('status') == 'ready' and
                {(skill['name'], skill['version']) for skill in device.get('installed_skills', [])
                 if skill.get('status') == 'installed'} == expected_skills and
                device.get('pilot', {}).get('status') == 'online' and
                device.get('ability_framework', {}).get('status') == 'ready' and
                device.get('ability_framework', {}).get('healthy_instances') == 7
                for device in devices):
                break
            if time.monotonic() >= deadline:
                raise AssertionError('Project devices did not become ready: '+json.dumps(diagnostics))
            time.sleep(1)
        assert {device['robot_id'] for device in devices} == expected_ids
        assert len(states) == len(expected_ids)
        diagnostics['success'] = True
    finally:
        diagnostics['supervisors'] = [json.loads(path.read_text())
            for path in (root/'robots').glob('*/*/run/state.json')]
        try:
            # The server performs the normal safe shutdown, including Pilot hold.
            request(project_path+'/runtime/release', {})
            diagnostics['released'] = True
        except Exception as error:
            diagnostics['release_error'] = str(error)
            if diagnostics.get('success'):
                diagnostics['success'] = False
                raise
        finally:
            report.write_text(json.dumps(diagnostics, indent=2)+'\n')
