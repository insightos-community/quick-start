# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'artifacts/runtime'))
import installer
import uninstall


class MacInstallerTests(unittest.TestCase):
    def test_platform_gate_rejects_old_systems_and_wrong_architecture(self):
        manifest={'platform':'macos-arm64','minimum_macos':'15.5'}
        with patch.object(installer.platform,'system',return_value='Darwin'), \
             patch.object(installer.platform,'machine',return_value='arm64'), \
             patch.object(installer.platform,'mac_ver',return_value=('15.5',(),'')):
            installer.check_platform(manifest)
            with self.assertRaises(RuntimeError):
                installer.check_platform(manifest,musl=True)
            with patch.object(installer.platform,'machine',return_value='x86_64'):
                with self.assertRaises(RuntimeError): installer.check_platform(manifest)
            with patch.object(installer.platform,'mac_ver',return_value=('14.7',(),'')):
                with self.assertRaises(RuntimeError): installer.check_platform(manifest)

    def test_macos_uses_bundled_python_offline_and_cgl(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(installer.platform,'system',return_value='Darwin'):
            root=Path(directory); release=root/'release'
            with patch.dict(os.environ,{'PYTHONHOME':'/foreign','PYTHONPATH':'/foreign'},clear=False):
                env=installer.environment(root,release)
            self.assertEqual(env['MUJOCO_GL'],'cgl')
            self.assertTrue(env['PATH'].startswith(str(release/'python/bin')+os.pathsep))
            self.assertEqual(env['UV_PYTHON_DOWNLOADS'],'never')
            self.assertEqual(env['UV_OFFLINE'],'1')
            self.assertNotIn('PYTHONHOME',env)
            self.assertNotIn('PYTHONPATH',env)

    @unittest.skipUnless(sys.platform=='darwin','native macOS process API')
    def test_native_process_identity_matches_current_executable(self):
        identity, executable=uninstall.mac_process(os.getpid())
        self.assertTrue(identity)
        self.assertEqual(Path(executable).resolve(),Path(sys.executable).resolve())
        self.assertEqual(identity,uninstall.uninstall_identity(os.getpid()))
