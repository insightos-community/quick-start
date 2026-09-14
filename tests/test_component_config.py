# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/runtime'))
import installer
import install_support as support


class ComponentConfigTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()/'instance with spaces'
        self.root.mkdir()

    def fixture(self):
        state = dict(support.component_values(), version='test', ready=True)
        for name in ('run', 'configs', 'logs', 'runtimes.d', 'releases/test/bin', 'releases/test/assets'):
            (self.root/name).mkdir(parents=True, exist_ok=True)
        (self.root/'.semantic-install-root').touch()
        (self.root/'install.json').write_text(json.dumps(state))
        (self.root/'releases/test/bin/semantic-server').touch()
        (self.root/'configs/semantic-server.yaml').write_text(json.dumps(dict(server={}, robot_runtime={})))
        (self.root/'runtimes.d/local-native-mujoco.yaml').write_text('installation_id: local-native-mujoco\nendpoint: http://127.0.0.1:8036\n')
        return state

    def args(self, **changes):
        return SimpleNamespace(dir=str(self.root), payload=self.root/'current', yes=True,
                               no_start=True, desktop='never', **changes)

    def test_yaml_round_trip_validation_and_cli_precedence(self):
        path = self.root/'components.yaml'
        values = support.component_values()
        support.export_components(path, values)
        self.assertEqual(support.read_component_config(path), values)
        self.assertEqual(installer.apply_component_options(self.args(config=path, web_port=43000), values)['web_port'], 43000)
        with self.assertRaises(FileExistsError):
            support.export_components(path, values)
        for text in ('schema_version: 1\nweb_port: 3000\nweb_port: 4000',
                     'schema_version: 1\nwrong: 3000', 'schema_version: 1\nweb_port: !!python/object:evil',
                     'schema_version: 1\nweb_port: $(touch bad)', 'web_port: 3000'):
            path.write_text(text)
            with self.assertRaises(ValueError): support.read_component_config(path)
        for changes in (dict(http_port=3000), dict(web_port=18101), dict(runtime_port=80), dict(ability_port_last=18000)):
            with self.assertRaises(ValueError): support.validate_components(dict(values, **changes))

    def test_both_bootstraps_export_without_network_and_reject_bad_yaml(self):
        for script in ('install.sh', 'install-en.sh'):
            command = ['bash', str(ROOT/script), '--dir', str(self.root), '--export-config', '-']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('http_port: 8034', result.stdout)
            self.assertIn('ws_port: 8035', result.stdout)
            self.assertIn('web_port: 3000', result.stdout)
            self.assertIn('runtime_port: 8036', result.stdout)
            bad = self.root/'bad.yaml'; bad.write_text('schema_version: 1\nhttp_port: $(touch SHOULD_NOT_EXIST)\n')
            result = subprocess.run(['bash', str(ROOT/script), '-f', str(bad)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Invalid flat component YAML', result.stderr)
            self.assertNotIn('Downloading', result.stderr)

    def test_reconfigure_updates_all_connections_and_retains_credentials(self):
        self.fixture()
        robot = self.root/'robots/r1/instance/robot-deployment.yaml'
        robot.parent.mkdir(parents=True)
        robot.write_text('server: http://127.0.0.1:8034\nwebsocket: ws://127.0.0.1:8035/ws/pilot\nsdk: http://127.0.0.1:8036/robot\ntoken: keep-secret\n')
        with patch('uninstall.uninstall_managed', return_value={}), patch('uninstall.uninstall_processes', return_value=[]), \
             patch.object(installer, 'install_manager'), patch.object(installer, 'stop_owned'), patch.object(installer, 'check_port'), \
             patch.object(installer, 'desktop_shortcuts'), patch.object(installer, 'welcome'), patch('sys.stdout', new=io.StringIO()):
            installer.configure_existing(self.args(http_port=28034, ws_port=28035, web_port=23000, runtime_port=28036))
        cfg = json.loads((self.root/'configs/semantic-server.yaml').read_text())
        self.assertEqual(cfg['server']['http_addr'], '127.0.0.1:28034')
        self.assertEqual(cfg['robot_runtime']['server_websocket_url'], 'ws://127.0.0.1:28035/ws/pilot')
        self.assertIn('endpoint: http://127.0.0.1:28036', (self.root/'runtimes.d/local-native-mujoco.yaml').read_text())
        self.assertIn('server: http://127.0.0.1:28034', robot.read_text())
        self.assertIn('websocket: ws://127.0.0.1:28035/ws/pilot', robot.read_text())
        self.assertIn('sdk: http://127.0.0.1:28036/robot', robot.read_text())
        self.assertIn('token: keep-secret', robot.read_text())
        self.assertEqual(support.read_component_config(self.root/'configs/components.yaml')['web_port'], 23000)
        self.assertEqual(len(list((self.root/'configs').glob('reconfigure-backup-*'))), 1)

    def test_reconfigure_rolls_back_files_when_restart_fails(self):
        state = self.fixture()
        original = (self.root/'configs/semantic-server.yaml').read_bytes()
        args = self.args(http_port=28034); args.no_start=False
        with patch('uninstall.uninstall_managed', return_value={}), patch('uninstall.uninstall_processes', return_value=[]), \
             patch.object(installer, 'install_manager'), patch.object(installer, 'stop_owned'), patch.object(installer, 'check_port'), \
             patch.object(installer, 'start', side_effect=RuntimeError('health failed')), patch('sys.stdout', new=io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'health failed'): installer.configure_existing(args)
        self.assertEqual(json.loads((self.root/'install.json').read_text()), state)
        self.assertEqual((self.root/'configs/semantic-server.yaml').read_bytes(), original)

    def test_active_robot_refuses_change_before_stopping_server(self):
        self.fixture()
        with patch('uninstall.uninstall_managed', return_value={}), patch('uninstall.uninstall_processes', return_value=[dict(pid=123)]), \
             patch.object(installer, 'stop_owned') as stop:
            with self.assertRaisesRegex(ValueError, 'Stop all scenes'):
                installer.configure_existing(self.args(http_port=28034))
            stop.assert_not_called()
