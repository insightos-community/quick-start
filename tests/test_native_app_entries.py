"""Exercise real desktop integration on the target OS, including ownership cleanup."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/runtime'))
import install_support as support
if sys.platform != 'win32':
    import uninstall


class NativeEntries(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='semantic-app-test-')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.root = self.home/'Semantic test 中文 $ space'
        self.root.mkdir()
        self.state = dict(version='0.1.0', web_host='127.0.0.1', web_port=19030)
        self.identity = hashlib.sha256(str(self.root).encode()).hexdigest()[:12]

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux desktop entries')
    def test_linux_entries_launch_current_instance_and_preserve_foreign_edits(self):
        with patch.object(Path, 'home', return_value=self.home), patch.dict(os.environ, {'XDG_DATA_HOME':str(self.home/'.local/share')}), patch.object(support.subprocess, 'check_output', return_value=str(self.home/'Desktop')):
            support.desktop_shortcuts(self.root, self.state, 'always')
            self.assertEqual(len(self.state['desktop_shortcuts']), 4)
            for name in self.state['desktop_shortcuts']:
                content = Path(name).read_text()
                self.assertIn('semanticctl', content)
                self.assertNotIn('19030', content)
                self.assertIn('Terminal=true', content)
                if shutil.which('desktop-file-validate'):
                    subprocess.run(['desktop-file-validate', name], check=True)
            changed = Path(next(iter(self.state['desktop_shortcuts'])))
            changed.write_text('my replacement')
            uninstall.uninstall_shortcuts(self.root, self.state, lambda _:None)
            self.assertTrue(changed.exists())
            self.assertEqual(sum(Path(n).exists() for n in self.state['desktop_shortcuts']), 1)

    @unittest.skipUnless(sys.platform == 'darwin', 'Native AppleScript apps and LaunchServices')
    def test_macos_bundle_launch_registration_and_cleanup(self):
        assets = self.root/'bin/semantic-manager/assets'
        assets.mkdir(parents=True)
        shutil.copyfile(ROOT/'artifacts/assets/ios.png', assets/'ios.png')
        control = self.root/'bin/semanticctl'
        control.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > "'+str(self.root/'launched')+'"\n')
        # Quote a deliberately unusual root in the test stub as well.
        import shlex
        control.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > '+shlex.quote(str(self.root/'launched'))+'\n')
        control.chmod(0o755)
        with patch.object(Path, 'home', return_value=self.home):
            support.macos_shortcuts(self.root, self.state)
            self.assertEqual(len(self.state['application_bundles']), 2)
            for name in self.state['application_bundles']:
                app = Path(name)
                info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
                self.assertTrue((app/'Contents/Resources'/info['CFBundleIconFile']).stat().st_size > 1000)
                subprocess.run(['/usr/bin/codesign', '--verify', '--deep', str(app)], check=True)
                if info['CFBundleName'] == 'Semantic':
                    subprocess.run([str(app/'Contents/MacOS'/info['CFBundleExecutable'])], check=True, timeout=45)
                    self.assertEqual((self.root/'launched').read_text().strip(), 'open')
            support.macos_shortcuts(self.root, self.state)  # owned entries can be refreshed
            uninstall.uninstall_shortcuts(self.root, self.state, lambda _:None)
            self.assertTrue(all(not Path(p).exists() for p in self.state['application_bundles']))

    @unittest.skipUnless(sys.platform == 'win32', 'Native COM shortcuts and registry')
    def test_windows_shortcuts_and_uninstall_registration(self):
        import winreg
        release = self.root/'releases/0.1.0'
        (release/'assets').mkdir(parents=True)
        (self.root/'bin').mkdir()
        shutil.copyfile(ROOT/'artifacts/assets/ios.png', release/'assets/ios.png')
        statefile = self.root/'install.json'
        statefile.write_text(json.dumps(self.state), encoding='utf-8')
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                   str(ROOT/'artifacts/windows/desktop.ps1'), '-Root', str(self.root), '-Version', '0.1.0']
        records = json.loads(subprocess.check_output(command).decode('utf-8-sig'))
        self.addCleanup(self.cleanup_windows, records)
        self.assertEqual(len(records['native_shortcuts']), 4)
        statefile.write_text(json.dumps(dict(self.state, **records)), encoding='utf-8')
        refreshed = json.loads(subprocess.check_output(command).decode('utf-8-sig'))
        self.assertEqual(set(records['native_shortcuts']), set(refreshed['native_shortcuts']))
        key = records['uninstall_registry'].removeprefix('HKCU:\\')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            self.assertEqual(winreg.QueryValueEx(handle, 'InstallLocation')[0], str(self.root))
            self.assertIn('--interactive', winreg.QueryValueEx(handle, 'UninstallString')[0])
        for name in records['native_shortcuts']:
            query = "$s=New-Object -ComObject WScript.Shell; $s.CreateShortcut($env:SEMANTIC_TEST_LINK) | Select-Object TargetPath,Arguments,IconLocation | ConvertTo-Json"
            link = json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-Command',query],
                              env=dict(os.environ, SEMANTIC_TEST_LINK=name)).decode(errors='replace'))
            self.assertTrue(link['TargetPath'].endswith('python.exe'))
            self.assertIn('--interactive', link['Arguments'])
            self.assertTrue(link['IconLocation'].endswith('Semantic.ico,0'))

    def cleanup_windows(self, records):
        import winreg
        for name in records['native_shortcuts']:
            Path(name).unlink(missing_ok=True)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, records['uninstall_registry'].removeprefix('HKCU:\\'))

if __name__ == '__main__':
    unittest.main()
