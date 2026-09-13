# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('github_bootstrap',ROOT/'artifacts/github_bootstrap.py')
github=importlib.util.module_from_spec(spec)
spec.loader.exec_module(github)


class GithubBootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work=Path(temporary.name)

    def release(self, corrupt=False):
        body=b'archive'
        metadata=json.dumps(dict(tag='v0.1.0',version='0.1.0',component='semantic-installer',platform='linux-x86_64',source_commit=github.GITHUB_BASELINE_COMMIT)).encode()
        name='semantic-0.1.0-linux-x86_64.tar.gz'
        files={'release.json':metadata,name:body}
        files['SHA256SUMS']=''.join(f'{hashlib.sha256(data).hexdigest()}  {key}\n' for key,data in files.items()).encode()
        if corrupt:files[name]=b'corrupted'
        urls=[]
        def download(url,target,limit):
            urls.append(url)
            target.write_bytes(files[url.rsplit('/',1)[1]])
        return download,urls

    def test_default_release_uses_only_github_and_verifies_identity(self):
        download,urls=self.release()
        archive,expected=github.github_archive(self.work,'stable',download)
        self.assertEqual(github.github_digest(archive),expected)
        self.assertTrue(all(url.startswith('https://github.com/insightos-community/quick-start/releases/download/v0.1.0/') for url in urls))
        with self.assertRaises(ValueError):github.github_archive(self.work,'../bad',download)
        with self.assertRaises(ValueError):github.github_archive(self.work,'0.1.0',download,'0'*64)

    def test_corrupt_release_does_not_reach_installation(self):
        download,_=self.release(corrupt=True)
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            github.github_archive(self.work,'v0.1.0',download)

    def payload(self, pointer=False):
        payload=self.work/'payload'
        target=payload/'assets/mujoco/robot/model.stl'
        target.parent.mkdir(parents=True)
        content=b'verified mesh'
        digest=hashlib.sha256(content).hexdigest()
        lfs=f'version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize {len(content)}\n'.encode()
        if pointer:target.write_bytes(lfs)
        (payload/'files.json').write_text(json.dumps({'assets/mujoco/robot/model.stl':digest}))
        (payload/'release-lock.json').write_text(json.dumps({'semantic-scene/mujoco-asset':dict(repository=github.GITHUB_ASSET_REPO,source_commit='a'*40)}))
        return payload,target,content,digest,lfs

    def test_missing_and_pointer_assets_use_lfs_and_preserve_inventory(self):
        payload,target,content,digest,pointer=self.payload(pointer=True)
        inventory=(payload/'files.json').read_bytes()
        def download(url,destination,limit):
            self.assertIn('/'+'a'*40+'/robot/model.stl',url)
            destination.write_bytes(pointer)
        calls=[]
        def request(req):
            calls.append(req)
            if req.data:
                body=json.loads(req.data)
                self.assertEqual(body['objects'],[dict(oid=digest,size=len(content))])
                return io.BytesIO(json.dumps({'objects':[dict(oid=digest,size=len(content),actions={'download':{'href':'https://objects.githubusercontent.com/model'}})]}).encode())
            return io.BytesIO(content)
        with patch.object(github,'github_open',side_effect=request):
            self.assertEqual(github.hydrate_github_assets(payload,download),1)
            self.assertEqual(target.read_bytes(),content)
            target.unlink()
            self.assertEqual(github.hydrate_github_assets(payload,download),1)
        self.assertEqual((payload/'files.json').read_bytes(),inventory)
        self.assertEqual(len(calls),4)
        with patch.object(github,'github_open',side_effect=AssertionError('Unexpected network')):
            self.assertEqual(github.hydrate_github_assets(payload,download),0)

    def test_wrong_lfs_oid_and_response_bytes_are_rejected(self):
        payload,target,content,digest,pointer=self.payload()
        with patch.object(github,'github_open',side_effect=AssertionError('Must reject before networking')):
            with self.assertRaises(ValueError):github.github_lfs_object(pointer,target,'0'*64)
        replies=[io.BytesIO(json.dumps({'objects':[dict(oid=digest,size=len(content),actions={'download':{'href':'https://objects.githubusercontent.com/model'}})]}).encode()),io.BytesIO(b'X'*len(content))]
        with patch.object(github,'github_open',side_effect=replies):
            with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):github.github_lfs_object(pointer,target,digest)

    def test_asset_path_traversal_is_rejected(self):
        payload,*_=self.payload()
        (payload/'files.json').write_text(json.dumps({'assets/mujoco/../../../escape':'a'*64}))
        with self.assertRaises(ValueError):github.hydrate_github_assets(payload,lambda *args: None)

    def test_english_environment_preserves_user_package_sources(self):
        spec=importlib.util.spec_from_file_location('english_generator',ROOT/'artifacts/build_english_installer.py')
        generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
        tree=ast.parse(generator.manager_sources()['installer.py'])
        environment=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='environment')
        namespace={'os':os,'platform':__import__('platform'),'load':lambda path:{}}
        exec(compile(ast.Module(body=[environment],type_ignores=[]),'<environment>','exec'),namespace)
        with patch.dict(os.environ,{'UV_INDEX_URL':'https://user.example/simple','PIP_CONFIG_FILE':'/user/pip.conf','UV_CONFIG_FILE':'/user/uv.toml'},clear=True):
            env=namespace['environment'](self.work,self.work/'release')
        self.assertNotIn('UV_NO_CONFIG',env)
        self.assertEqual(env['UV_INDEX_URL'],'https://user.example/simple')
        self.assertEqual(env['PIP_CONFIG_FILE'],'/user/pip.conf')
        self.assertEqual(env['UV_CONFIG_FILE'],'/user/uv.toml')
