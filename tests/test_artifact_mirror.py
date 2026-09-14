# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'artifacts'))
import mirror_release_to_oss as mirror


class MirrorTests(unittest.TestCase):
    def test_rejects_non_platform_tags(self):
        for tag in ('stable','../tag','macos-v../bad','musl-v0.1.0-0'):
            with self.assertRaises(ValueError):mirror.identity(tag)

    def test_verified_original_assets_and_separate_channels(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            for tag in ('v0.1.0','musl-v0.1.0-2','macos-v0.1.0-rc.4','windows-v0.1.0-rc.2'):
                version,platform=mirror.identity(tag)
                folder=output/tag;folder.mkdir()
                prefix=f'releases/{version}/{platform}'
                extension='zip' if platform=='windows-amd64' else 'tar.gz'
                archive=f'semantic-{version}-{platform}.{extension}'; content=b'verified fixture'
                manifest=dict(version=version,platform=platform,
                    archive=archive if platform=='macos-arm64' else prefix+'/'+archive,
                    sha256=hashlib.sha256(content).hexdigest(),size=len(content))
                data={archive:content,'manifest.json':json.dumps(manifest).encode(),'release.json':b'{}'}
                data['SHA256SUMS']=''.join(hashlib.sha256(value).hexdigest()+'  '+name+'\n' for name,value in data.items()).encode()
                assets=[]
                for name,value in data.items():
                    (folder/name).write_bytes(value)
                    assets.append(dict(name=name,size=len(value),digest='sha256:'+hashlib.sha256(value).hexdigest(),
                        browser_download_url=f'https://github.com/insightos-community/quick-start/releases/download/{tag}/{name}'))
                with patch.object(mirror.subprocess,'run') as network:
                    verified,files=mirror.stage(tag,output,dict(assets=assets))
                    network.assert_not_called()
                writes=[]
                store=Mock()
                store.upload.side_effect=lambda path,key,**kw:writes.append((key,Path(path).read_bytes(),kw))
                mirror.publish(store,tag,verified,files)
                immutable=[w for w in writes if not w[2].get('mutable')]
                self.assertEqual(immutable[-1][0],prefix+'/manifest.json')
                for key,body,_ in immutable:self.assertEqual(body,data[key.rsplit('/',1)[1]])
                channel=[w for w in writes if w[2].get('mutable')]
                if platform in ('macos-arm64','windows-amd64'):self.assertFalse(channel)
                else:
                    expected='musl-stable.json' if platform=='linux-musl-x86_64' else 'stable.json'
                    self.assertEqual(channel[0][0],'channels/'+expected)
                    self.assertEqual(json.loads(channel[0][1])['archive'],prefix+'/'+archive)
                (folder/'SHA256SUMS').write_text('0'*64+'  ../outside\n')
                bad_assets=[dict(a,digest='sha256:'+mirror.digest(folder/a['name']),size=(folder/a['name']).stat().st_size) for a in assets]
                with self.assertRaisesRegex(ValueError,'SHA256SUMS'):
                    mirror.stage(tag,output,dict(assets=bad_assets))
