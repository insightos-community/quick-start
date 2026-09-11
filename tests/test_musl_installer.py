# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value
installer=module('installer_musl_test','artifacts/runtime/installer.py')
github=module('github_musl_test','artifacts/github_bootstrap.py')

class MuslInstallerTests(unittest.TestCase):
    def test_platform_selection_is_explicit_and_does_not_accept_glibc(self):
        musl={'libc':'musl','platform':'linux-musl-x86_64'}
        glibc={'minimum_glibc':'2.28','platform':'linux-x86_64'}
        with patch.object(installer.platform,'system',return_value='Linux'), patch.object(installer.platform,'machine',return_value='x86_64'), patch.object(installer,'musl_host',return_value=True):
            installer.check_platform(musl,True)
            with self.assertRaisesRegex(RuntimeError,'requires --musl'):installer.check_platform(musl)
            with self.assertRaisesRegex(RuntimeError,'glibc package'):installer.check_platform(glibc,True)
        with patch.object(installer,'musl_host',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'musl host'):installer.check_platform(musl,True)
        with patch.object(installer.platform,'libc_ver',return_value=('glibc','2.28')):
            installer.check_platform(glibc)

    def test_optional_download_uses_separate_tag_and_requires_musl_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            tag=github.GITHUB_MUSL_TAG
            version='0.1.0-musl.1'
            archive=f'semantic-{version}-linux-musl-x86_64.tar.gz'
            metadata={'component':'semantic-installer','tag':tag,'version':version,'platform':'linux-musl-x86_64','libc':'musl'}
            def fixture():
                files={archive:b'valid archive','release.json':json.dumps(metadata).encode()}
                files['SHA256SUMS']=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in files.items()).encode()
                def download(url,target,limit):
                    self.assertIn('/releases/download/'+tag+'/',url)
                    target.write_bytes(files[url.rsplit('/',1)[1]])
                return download
            actual,_=github.github_archive(directory,'stable',fixture(),musl=True)
            self.assertEqual(actual.name,archive)
            metadata['libc']='glibc'
            with self.assertRaisesRegex(ValueError,'declare musl'):github.github_archive(directory,'stable',fixture(),musl=True)
            with self.assertRaises(ValueError):github.github_archive(directory,'0.1.0',fixture(),musl=True)

    def test_environment_reuses_bundled_python_and_preserves_user_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);release=root/'release';(release/'musl').mkdir(parents=True)
            (root/'configs').mkdir()
            (root/'configs/musl-render.json').write_text(json.dumps({'selected':'software','device':0}))
            with patch.dict(os.environ,{'UV_INDEX_URL':'https://user.example/simple','LD_LIBRARY_PATH':'/wrong-glibc','PYTHONPATH':'/wrong-python'},clear=True):
                env=installer.environment(root,release)
            self.assertEqual(env['UV_INDEX_URL'],'https://user.example/simple')
            self.assertEqual(env['UV_PYTHON_DOWNLOADS'],'never')
            self.assertEqual(env['LD_LIBRARY_PATH'],str(release/'musl/lib'))
            self.assertTrue(env['PATH'].startswith(str(release/'python/bin')))
            self.assertEqual(env['GALLIUM_DRIVER'],'llvmpipe')

    def test_apk_uses_machine_repositories_without_rewriting_or_upgrade(self):
        with patch.object(installer.shutil,'which',return_value='/sbin/apk'):
            self.assertEqual(installer.package_manager({'ID':'alpine'}),'apk')
        self.assertEqual(installer.dependency_commands('apk'),[['apk','add','--no-cache','ca-certificates','tar','zstd']])

if __name__=='__main__':unittest.main()
