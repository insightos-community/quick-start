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

"""Release tooling: backfill a manifest, stage a tree, publish it to both channels."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts'))

_spec = importlib.util.spec_from_file_location('release_build', ROOT/'artifacts/build_extension.py')
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)
_pub_spec = importlib.util.spec_from_file_location('release_publish', ROOT/'artifacts/publish_extension.py')
publish = importlib.util.module_from_spec(_pub_spec)
_pub_spec.loader.exec_module(publish)
extension = build.extension


def digest_of(body):
    return hashlib.sha256(body).hexdigest()


TEMPLATE = {
    'schema_version': 1,
    'id': 'demo',
    'title': 'Demo 场景',
    'version': '0.1.0',
    'compatible_base': '>=0.5.0',
    'runtime': {'installation_id': 'local-demo', 'endpoint': 'http://127.0.0.1:8099',
                'pack': {'url': 'demo-runtime.tar.zst', 'sha256': '0'*64, 'size': 1}},
    'components': [
        {'role': 'robot_base', 'id': 'demo-base', 'url': 'demo-base.zip',
         'sha256': '0'*64, 'size': 1},
        {'role': 'robot_skill', 'id': 'vla-manipulation', 'url': 'vla.zip',
         'sha256': '0'*64, 'size': 1, 'robot_required': True},
    ],
    'license': 'demo-license',
}


class ReleaseCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='semantic-release-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.packages = self.root/'packages'
        self.packages.mkdir()
        self.output = self.root/'staging'
        self.output.mkdir()
        self.template = self.root/'template.json'

    def template_file(self, value=None):
        self.template.write_text(json.dumps(value if value is not None else TEMPLATE))
        return self.template

    def packages_with(self, names=('demo-runtime.tar.zst', 'demo-base.zip', 'vla.zip')):
        bodies = {}
        for name in names:
            body = ('payload:'+name).encode()
            bodies[name] = body
            (self.packages/name).write_bytes(body)
        return bodies

    def build_staged(self):
        self.packages_with()
        return build.build('demo', '0.1.0', self.packages, self.output,
                           manifest_path=self.template_file(), report=lambda *row: None)


class BackfillTests(ReleaseCase):
    def test_backfill_fills_real_digests_and_sizes(self):
        bodies = self.packages_with()
        manifest = json.loads(json.dumps(TEMPLATE))
        inventory = build.backfill(manifest, self.packages, report=lambda *row: None)
        self.assertEqual(len(inventory), 3)
        self.assertEqual(manifest['runtime']['pack']['sha256'], digest_of(bodies['demo-runtime.tar.zst']))
        self.assertEqual(manifest['runtime']['pack']['size'], len(bodies['demo-runtime.tar.zst']))
        self.assertEqual(manifest['runtime']['pack']['url'], 'demo-runtime.tar.zst')

    def test_oversized_artifact_is_marked_oss_only(self):
        record = {'url': 'big.zip'}
        self.assertTrue(build.mark_oss_only(record, extension.GITHUB_ASSET_LIMIT + 1))
        self.assertEqual(record['hosts'], ['oss'])
        self.assertFalse(build.mark_oss_only({'url': 'small.zip'}, extension.GITHUB_ASSET_LIMIT))

    def test_missing_artifact_is_rejected(self):
        self.packages_with(names=('demo-runtime.tar.zst', 'demo-base.zip'))
        manifest = json.loads(json.dumps(TEMPLATE))
        with self.assertRaisesRegex(FileNotFoundError, 'vla.zip'):
            build.backfill(manifest, self.packages, report=lambda *row: None)

    def test_nested_artifact_name_is_rejected(self):
        manifest = json.loads(json.dumps(TEMPLATE))
        manifest['components'][0]['url'] = 'sub/demo-base.zip'
        self.packages_with()
        with self.assertRaisesRegex(ValueError, '平铺'):
            build.backfill(manifest, self.packages, report=lambda *row: None)

    def test_duplicate_artifact_name_is_rejected(self):
        manifest = json.loads(json.dumps(TEMPLATE))
        manifest['components'][0]['url'] = 'vla.zip'
        self.packages_with()
        with self.assertRaisesRegex(ValueError, '重复'):
            build.backfill(manifest, self.packages, report=lambda *row: None)


class StageTests(ReleaseCase):
    def test_stage_writes_the_tree_and_pointer(self):
        folder = self.build_staged()
        self.assertTrue((folder/'extension.json').is_file())
        self.assertTrue((folder/'demo-base.zip').is_file())
        pointer = json.loads((self.output/'extensions'/'demo'/'stable.json').read_text())
        self.assertEqual(pointer, {'id': 'demo', 'version': '0.1.0', 'tag': 'ext-demo-v0.1.0'})

    def test_staged_manifest_is_self_consistent(self):
        folder = self.build_staged()
        parsed = extension.parse((folder/'extension.json').read_text(), source='oss')
        for label, artifact in publish.manifest_artifacts(parsed):
            path = folder/extension.artifact_name(artifact)
            self.assertEqual(extension.digest(path), artifact['sha256'], label)

    def test_staging_output_inside_the_checkout_is_refused(self):
        parser_manifest = self.template_file()
        with self.assertRaisesRegex(ValueError, '仓库之外'):
            build.build('demo', '0.1.0', self.packages, ROOT/'artifacts/__staging_probe',
                        manifest_path=parser_manifest, report=lambda *row: None)

    def test_offline_install_from_staged_directory_verifies_every_artifact(self):
        folder = self.build_staged()
        parsed = extension.load_manifest_file(folder/'extension.json', source='oss')
        ran, rows = [], []
        plan = extension.install(parsed, self.root/'instance', project='proj-1', robot='robot_r1',
                                 package_dir=folder, report=lambda *row: rows.append(row),
                                 runner=lambda command: ran.append(command))
        self.assertEqual(len(plan), 3)
        self.assertEqual(len(ran), 3)
        self.assertEqual(ran[0][1:3], ['runtime', 'install'])
        self.assertEqual(ran[1][1], 'install')

    def test_tampered_staged_artifact_is_rejected_before_running(self):
        folder = self.build_staged()
        (folder/'vla.zip').write_bytes(b'tampered')
        parsed = extension.load_manifest_file(folder/'extension.json', source='oss')
        ran = []
        with self.assertRaises(extension.ManifestError):
            extension.install(parsed, self.root/'instance', project='proj-1', robot='robot_r1',
                              package_dir=folder, runner=lambda command: ran.append(command))
        self.assertEqual(ran, [])


class PublishTests(ReleaseCase):
    def setUp(self):
        super().setUp()
        self.folder = self.build_staged()

    def test_immutable_objects_use_the_version_prefix(self):
        keys = [key for key, _ in publish.immutable_objects(self.folder, 'demo', '0.1.0')]
        self.assertIn('extensions/demo/0.1.0/extension.json', keys)
        self.assertIn('extensions/demo/0.1.0/demo-base.zip', keys)

    def test_mirror_assets_exclude_oss_only_artifacts(self):
        folder, _, parsed = publish.load_staging(self.output, 'demo', '0.1.0')
        names = [Path(path).name for path in publish.mirror_assets(folder, parsed)]
        self.assertEqual(names, ['extension.json', 'demo-runtime.tar.zst', 'demo-base.zip', 'vla.zip'])

    def test_sha256sums_lists_digests_in_order(self):
        folder, _, parsed = publish.load_staging(self.output, 'demo', '0.1.0')
        assets = publish.mirror_assets(folder, parsed)
        lines = publish.sha256sums(assets).splitlines()
        self.assertEqual(len(lines), len(assets))
        self.assertEqual(lines[0].split('  ', 1)[1], 'extension.json')
        self.assertEqual(lines[1].split('  ')[0], extension.digest(folder/'demo-runtime.tar.zst'))

    def test_publish_oss_uploads_immutable_objects_then_the_pointer(self):
        folder, _, _ = publish.load_staging(self.output, 'demo', '0.1.0')
        uploads = []

        class Store:
            def upload(self, path, relative, mutable=False):
                uploads.append((relative, mutable))

        publish.publish_oss(Store(), folder, 'demo', '0.1.0', report=lambda *row: None)
        self.assertEqual(uploads[-1], ('extensions/demo/stable.json', True))
        self.assertTrue(all(mutable is False for _, mutable in uploads[:-1]))

    def test_github_release_command_is_flat_and_tagged(self):
        folder, _, parsed = publish.load_staging(self.output, 'demo', '0.1.0')
        assets = publish.mirror_assets(folder, parsed)
        command = publish.github_command('ext-demo-v0.1.0', assets)
        self.assertEqual(command[:4], ['gh', 'release', 'create', 'ext-demo-v0.1.0'])
        self.assertTrue(all('/' not in Path(item).name or not item.startswith('extensions')
                            for item in command[4:]))

    def test_publish_github_uploads_manifest_sums_and_metadata(self):
        folder, _, parsed = publish.load_staging(self.output, 'demo', '0.1.0')
        calls = []
        tag = publish.publish_github(folder, parsed, 'demo', '0.1.0',
                                     'insightos-community/quick-start',
                                     runner=lambda command: calls.append(command),
                                     report=lambda *row: None)
        self.assertEqual(tag, 'ext-demo-v0.1.0')
        names = [Path(item).name for item in calls[0][8:-2]]
        self.assertIn('extension.json', names)
        self.assertIn('SHA256SUMS', names)
        self.assertIn('release.json', names)
        self.assertEqual(calls[0][-2:], ['--repo', 'insightos-community/quick-start'])

    def test_unsafe_asset_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '不安全'):
            publish.github_asset_names([Path('/tmp/evil name.zip')])

    def test_illegal_release_tag_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'tag'):
            publish.publish_github(self.folder, publish.load_staging(self.output, 'demo', '0.1.0')[2],
                                   'demo', 'bad version', 'org/repo',
                                   runner=lambda command: None, report=lambda *row: None)


if __name__ == '__main__':
    unittest.main()
