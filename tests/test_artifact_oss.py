# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_oss', ROOT/'artifacts/oss_client.py')
oss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oss)


class OSSTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def config(self):
        path = self.root/'oss.env'
        path.write_text('OSS_REGION=cn-shanghai\nOSS_ENDPOINT=https://oss-cn-shanghai.aliyuncs.com\n'
            'OSS_BUCKET=test-bucket\nOSS_PREFIX=semantic\nOSS_DOWNLOAD_BASE=https://test.example/semantic\n'
            'OSS_ACCESS_KEY_ID=test-id\nOSS_ACCESS_KEY_SECRET=test-secret\n')
        path.chmod(0o600)
        return path

    def test_config_permissions_and_symlink_protection(self):
        path = self.config()
        self.assertEqual(oss.read_config(path)['OSS_PREFIX'], 'semantic')
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '600'):
            oss.read_config(path)
        path.chmod(0o600)
        link = self.root/'link'
        link.symlink_to(path)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            oss.read_config(link)

    def test_config_prefix_traversal_is_rejected(self):
        path = self.config()
        path.write_text(path.read_text().replace('OSS_PREFIX=semantic', 'OSS_PREFIX=../other'))
        with self.assertRaisesRegex(ValueError, '前缀'):
            oss.read_config(path)

    def test_config_non_https_is_rejected(self):
        path = self.config()
        path.write_text(path.read_text().replace('https://', 'http://'))
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            oss.read_config(path)

    def test_config_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '仓库外'):
            oss.read_config(ROOT/'artifacts/README.md')

    def test_release_path_validation(self):
        for version in ('../escape', '/tmp', 'v1', '1.2.3/../../x'):
            with self.assertRaisesRegex(ValueError, '版本'):
                oss.release_files(version)

    def store(self, head):
        store = object.__new__(oss.Store)
        store.values = {'OSS_PREFIX': 'semantic'}
        store.bucket, store.acl = 'test-bucket', 'private'
        # Match the real SDK: headers does not exist unless explicitly supplied.
        store.oss = SimpleNamespace(PutObjectRequest=lambda **kw: SimpleNamespace(**kw))
        store.client = Mock()
        store.head = Mock(return_value=head)
        store.verify = Mock()
        store.backup_mutable = Mock()
        return store

    def test_immutable_version_and_foreign_object_are_not_overwritten(self):
        path = self.root/'artifact'
        path.write_bytes(b'package')
        for mutable, metadata in [(False, {'semantic-managed': '1'}), (True, {})]:
            store = self.store(SimpleNamespace(metadata=metadata))
            with self.assertRaisesRegex(RuntimeError, '拒绝覆盖'):
                store.upload(path, 'channels/stable.json' if mutable else 'releases/1/file', mutable=mutable)
            store.client.put_object_from_file.assert_not_called()

    def test_new_objects_are_explicitly_private_and_non_overwriting(self):
        path = self.root/'artifact'
        path.write_bytes(b'package')
        store = self.store(None)
        store.upload(path, 'releases/1/file')
        request = store.client.put_object_from_file.call_args.args[0]
        self.assertEqual(request.acl, 'private')
        self.assertTrue(request.forbid_overwrite)
        self.assertEqual(request.metadata['sha256'], oss.digest(path))

    def test_managed_mutable_object_backs_up_and_rechecks_etag(self):
        path = self.root/'artifact'
        path.write_bytes(b'package')
        store = self.store(SimpleNamespace(metadata={'semantic-managed': '1'}, etag='old-etag'))
        store.upload(path, 'channels/stable.json', mutable=True)
        request = store.client.put_object_from_file.call_args.args[0]
        self.assertFalse(hasattr(request, 'headers'))
        store.backup_mutable.assert_called_once()
        self.assertEqual(store.head.call_count, 2)

    def test_video_upload_uses_playable_mime_and_immutable_public_object(self):
        path = self.root/'demo.mp4'
        path.write_bytes(b'video fixture')
        store = self.store(None)
        store.acl = 'public-read'
        store.upload(path, 'media/demo-sha.mp4')
        request = store.client.put_object_from_file.call_args.args[0]
        self.assertEqual(request.content_type, 'video/mp4')
        self.assertEqual(request.acl, 'public-read')
        self.assertTrue(request.forbid_overwrite)
        self.assertEqual(request.cache_control, 'max-age=31536000, immutable')
        self.assertEqual(request.metadata['sha256'], oss.digest(path))

    def test_changed_mutable_object_is_not_overwritten(self):
        path = self.root/'artifact'
        path.write_bytes(b'package')
        store = self.store(None)
        store.head.side_effect = [SimpleNamespace(metadata={'semantic-managed': '1'}, etag='old'),
                                  SimpleNamespace(etag='changed')]
        with self.assertRaisesRegex(RuntimeError, '发生变化'):
            store.upload(path, 'channels/stable.json', mutable=True)
        store.client.put_object_from_file.assert_not_called()

    def test_mutable_backup_uses_sdk_read_without_size(self):
        import hashlib
        data = b'old script'
        checksum = hashlib.sha256(data).hexdigest()
        head = SimpleNamespace(etag='old', content_length=len(data), metadata={'sha256': checksum})
        store = self.store(head)
        body = SimpleNamespace(read=lambda: data, close=Mock())
        store.oss.GetObjectRequest = lambda **kw: SimpleNamespace(**kw)
        store.client.get_object.return_value = SimpleNamespace(body=body, content_length=len(data))
        with patch.object(oss, 'DEFAULT_CONFIG', self.root/'oss.env'):
            oss.Store.backup_mutable(store, 'semantic/install.sh', head)
        backup = self.root/'backups'/('semantic_install.sh.'+checksum)
        self.assertEqual(backup.read_bytes(), data)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(store.client.get_object.call_args.args[0].if_match, 'old')
        body.close.assert_called_once()

    def test_oversized_backup_is_rejected_before_download(self):
        store = self.store(None)
        with self.assertRaisesRegex(RuntimeError, '大小异常'):
            oss.Store.backup_mutable(store, 'semantic/install.sh', SimpleNamespace(content_length=3*1024*1024))
        store.client.get_object.assert_not_called()

    def test_private_output_permissions(self):
        path = self.root/'download.json'
        oss.save_private(path, '{}')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_mutable_object_without_etag_is_not_overwritten(self):
        path = self.root/'artifact'
        path.write_bytes(b'package')
        store = self.store(SimpleNamespace(metadata={'semantic-managed': '1'}, etag=None))
        with self.assertRaisesRegex(RuntimeError, 'ETag'):
            store.upload(path, 'channels/stable.json', mutable=True)
        store.client.put_object_from_file.assert_not_called()

    def ticket(self):
        path = self.root/'download.json'
        value = dict(version='1.2.3', platform='linux-x86_64', archive='releases/1.2.3/file.tar.gz',
                     sha256='0'*64, base_url='https://bucket.example/semantic',
                     archive_url='https://other.example/semantic/releases/1.2.3/file.tar.gz',
                     expires_at=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat())
        return path, value

    def bootstrap_ticket(self, path):
        return subprocess.run(['bash', str(ROOT/'artifacts/install.sh'), '--ticket', str(path), '--yes'],
                              capture_output=True, text=True)

    def test_ticket_cross_origin_is_rejected_before_download(self):
        path, value = self.ticket()
        path.write_text(json.dumps(value))
        result = self.bootstrap_ticket(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Bucket/制品路径不一致', result.stderr)

    def test_expired_ticket_is_rejected(self):
        path, value = self.ticket()
        value['expires_at'] = '2000-01-01T00:00:00+00:00'
        path.write_text(json.dumps(value))
        result = self.bootstrap_ticket(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('已过期', result.stderr)
