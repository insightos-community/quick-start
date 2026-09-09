# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PublicationBoundaryTests(unittest.TestCase):
    def test_packager_rejects_external_models(self):
        spec = importlib.util.spec_from_file_location('public_packager', ROOT / 'artifacts/build_release.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'yaml': SimpleNamespace()}), patch.object(sys, 'path', [str(ROOT / 'artifacts'), *sys.path]):
            spec.loader.exec_module(module)
        for name in ('robot/r1_pro/config/model.xml', 'robot/r1_pro_chassis/meshes/model.STL', 'robot/r1_pro_tote_gripper/config/model.xml'):
            with self.assertRaisesRegex(ValueError, 'Galaxea'):
                module.reject_external_models(name)
        for name in ('robot/franka_panda/model_bundle/LICENSE', 'assets/objects/box.xml', 'scene/r1_pro_001/scene_info.yaml'):
            module.reject_external_models(name)

    def test_bootstraps_do_not_select_old_binary_channel(self):
        for script in ('install.sh', 'install-en.sh'):
            result = subprocess.run(['bash', str(ROOT / 'artifacts' / script)],
                                    capture_output=True, text=True, timeout=20,
                                    env={'PATH': '/usr/bin:/bin'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--base-url', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_source_installer_checks_external_model_entry_files(self):
        import semantic_installer as installer
        app = SimpleNamespace(settings={'SEMANTIC': '/tmp/example workspace', 'BUNDLE_VER': '0.5.0-dev'})
        self.assertIn('check_external_models.py', installer._verify2_script(app)[0])

if __name__ == '__main__':
    unittest.main()
