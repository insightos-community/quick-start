# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_downloads', Path(__file__).resolve().parents[1]/'artifacts/fetch_releases.py')
releases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(releases)


class ReleaseDownloadsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, members):
        path = self.root/'component.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            for name, kind in members:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = '../outside'
                member.mode = 0o755
                member.size = 2 if kind == tarfile.REGTYPE else 0
                tar.addfile(member, io.BytesIO(b'ok') if member.size else None)
        return path

    def test_extract_preserves_executable(self):
        archive = self.archive([('bin/tool',tarfile.REGTYPE)])
        target = self.root/'payload'
        releases.extract(archive,target)
        self.assertEqual((target/'bin/tool').read_bytes(),b'ok')
        self.assertEqual((target/'bin/tool').stat().st_mode & 0o777,0o755)

    def test_reject_escaping_links_and_duplicate_members_before_extracting(self):
        for members in ([('../outside',tarfile.REGTYPE)], [('/absolute',tarfile.REGTYPE)],
                        [('link',tarfile.SYMTYPE)], [('hard',tarfile.LNKTYPE)],
                        [('a',tarfile.REGTYPE),('a',tarfile.REGTYPE)]):
            with self.subTest(members=members):
                with self.assertRaises(ValueError):
                    releases.extract(self.archive(members),self.root/'payload')
                self.assertFalse((self.root/'payload').exists())

    def fixture(self, commit='a'*40, corrupt=False, extra=False):
        tag='v1.0.0'
        identity=json.dumps(dict(component='test',platform='any',tag=tag,source_commit=commit)).encode()
        files={'release.json':identity,'test-v1.0.0-any.tar.gz':b'archive'}
        sums=''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in files.items()).encode()
        files['SHA256SUMS']=sums
        if corrupt:files['test-v1.0.0-any.tar.gz']=b'tampered'
        if extra:files['unlisted.txt']=b'extra'
        assets=[dict(name=name,browser_download_url='https://github.com/assets/'+name) for name in files]
        api=json.dumps(dict(draft=False,tag_name=tag,assets=assets)).encode()
        manifest=self.root/'repo-versions.json'
        manifest.write_text(json.dumps({'repos':{'test':dict(url='https://github.com/org/test.git',ref=tag,commit='a'*40)}}))
        def download(url,target,*args):
            target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(api if 'api.github.com' in url else files[url.rsplit('/',1)[1]])
        return manifest,download

    def test_fetch_checks_manifest_identity_and_revalidates_cache(self):
        manifest,download=self.fixture()
        with patch.object(releases,'download',download):
            record=releases.fetch(manifest,self.root/'cache')['test']
            cached=Path(record['directory'])/'test-v1.0.0-any.tar.gz'
            cached.write_bytes(b'corrupted cache')
            releases.fetch(manifest,self.root/'cache')
            self.assertEqual(cached.read_bytes(),b'archive')

    def test_fetch_rejects_wrong_source_hash_and_unlisted_assets(self):
        for index, options in enumerate(({'commit':'b'*40},{'corrupt':True},{'extra':True})):
            with self.subTest(options=options):
                manifest,download=self.fixture(**options)
                with patch.object(releases,'download',download), self.assertRaises(ValueError):
                    releases.fetch(manifest,self.root/f'cache-{index}')
