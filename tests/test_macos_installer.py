# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import json
import os
import subprocess
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

    def test_finder_metadata_does_not_hide_unlisted_program_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(installer.platform,'system',return_value='Darwin'):
            root=Path(directory).resolve()
            (root/'release.json').write_text('{"version":"0.1.0-rc.1"}')
            (root/'files.json').write_text(json.dumps({'release.json':installer.digest(root/'release.json')}))
            (root/'.DS_Store').write_bytes(b'Finder metadata')
            self.assertEqual(installer.verify_payload(root)['version'],'0.1.0-rc.1')
            (root/'unlisted.py').write_text('print(1)')
            with self.assertRaises(ValueError): installer.verify_payload(root)
            (root/'unlisted.py').unlink()
            (root/'.DS_Store').unlink()
            (root/'.DS_Store').symlink_to('release.json')
            with self.assertRaises(ValueError): installer.verify_payload(root)

    @unittest.skipUnless(sys.platform=='darwin','native macOS process API')
    def test_native_process_identity_matches_current_executable(self):
        identity, executable=uninstall.mac_process(os.getpid())
        self.assertTrue(identity)
        self.assertTrue(Path(executable).is_file())
        self.assertEqual(identity,uninstall.uninstall_identity(os.getpid()))
        child=subprocess.Popen(['/bin/sleep','30'])
        try:
            child_id, child_exe=uninstall.mac_process(child.pid)
            self.assertTrue(child_id)
            self.assertEqual(Path(child_exe).resolve(),Path('/bin/sleep').resolve())
        finally:
            child.terminate(); child.wait(timeout=10)
        self.assertIsNone(uninstall.uninstall_identity(child.pid))


class MacAbilityPackageTests(unittest.TestCase):
    def test_script_packages_keep_contents_and_permissions_with_native_metadata(self):
        import zipfile
        import yaml
        sys.path.insert(0, str(ROOT/'artifacts/macos'))
        from build import adapt_python_abilities
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'ability.zip'
            launcher = zipfile.ZipInfo('bin/ability')
            launcher.external_attr = 0o100755 << 16
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('package.yaml', 'name: test\nversion: 1.0\narch: x86_64\n')
                z.writestr(launcher, '#!/bin/bash\nexec "$SEMANTIC_ABILITY_PYTHON" main.py\n')
                z.writestr('main.py', 'import ability_py\n')
            original = path.read_bytes()
            adapt_python_abilities(root, [{'file':'ability.zip'}])
            with zipfile.ZipFile(path) as z:
                self.assertEqual(yaml.safe_load(z.read('package.yaml'))['arch'], 'arm64')
                self.assertEqual(z.read('main.py'), b'import ability_py\n')
                self.assertEqual(z.getinfo('bin/ability').external_attr, launcher.external_attr)
            path.write_bytes(original)
            with zipfile.ZipFile(path, 'a') as z:
                z.writestr('lib/native.so', b'\x7fELFwrong platform')
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'native Ability binary'):
                adapt_python_abilities(root, [{'file':'ability.zip'}])
            self.assertEqual(path.read_bytes(), original)


class MacSkillDependencyTests(unittest.TestCase):
    def test_rejects_skill_dependency_not_in_offline_wheelhouse(self):
        import zipfile
        sys.path.insert(0, str(ROOT/'artifacts/macos'))
        from build import validate_skill_wheels
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills = root/'skills'; skills.mkdir()
            wheels = root/'wheels'; wheels.mkdir()
            with zipfile.ZipFile(skills/'grasp.zip', 'w') as z:
                z.writestr('requirements.lock', 'pydantic==2.13.4\n')
            (wheels/'pydantic-2.11.5-py3-none-any.whl').touch()
            with self.assertRaisesRegex(ValueError, 'offline wheel missing for pydantic==2.13.4'):
                validate_skill_wheels(skills, wheels)
            (wheels/'pydantic-2.13.4-py3-none-any.whl').touch()
            validate_skill_wheels(skills, wheels)
