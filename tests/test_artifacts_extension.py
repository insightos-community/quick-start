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

import hashlib
import importlib.util
import json
import shutil

def digest_of(body):
    """Digest of an in-memory payload, so tests can build a self-consistent manifest."""
    return hashlib.sha256(body).hexdigest()

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('artifact_extension', ROOT/'artifacts/runtime/extension.py')
extension = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extension)

MANIFEST = {
    'schema_version': 1,
    'id': 'libero',
    'title': 'LIBERO 仿真场景',
    'version': '0.1.0',
    'compatible_base': '>=0.5.0',
    'runtime': {
        'installation_id': 'local-libero-robosuite-1.4',
        'endpoint': 'http://127.0.0.1:8092',
        'pack': {'url': 'https://example.invalid/libero.runtime.tar.zst', 'sha256': 'a'*64, 'size': 1932735283},
    },
    'components': [
        {'role': 'robot_skill', 'id': 'vla-manipulation',
         'url': 'https://example.invalid/vla-manipulation.zip', 'sha256': 'b'*64, 'size': 11264,
         'robot_required': True},
        {'role': 'scene_catalog', 'id': 'libero-scenes',
         'url': 'https://example.invalid/libero-scenes.zip', 'sha256': 'c'*64, 'size': 250609664,
         'previews': {'default_scenes': ['libero-spatial-0']}},
        {'role': 'robot_base', 'id': 'franka-libero-robot',
         'url': 'https://example.invalid/franka-libero-robot.zip', 'sha256': 'd'*64, 'size': 3113851289},
        {'role': 'robot_ability', 'id': 'franka-ability',
         'url': 'https://example.invalid/franka-ability.zip', 'sha256': 'e'*64, 'size': 2899102924},
        {'role': 'model', 'id': 'franka-smolvla-model',
         'url': 'https://example.invalid/franka-smolvla-model.zip', 'sha256': 'f'*64, 'size': 3435973836},
    ],
}


def manifest(**overrides):
    value = json.loads(json.dumps(MANIFEST))
    value.update(overrides)
    return json.dumps(value)


class ManifestParsingTests(unittest.TestCase):
    def test_valid_manifest_is_normalized_in_install_order(self):
        parsed = extension.parse(manifest())
        self.assertEqual(parsed['id'], 'libero')
        self.assertEqual([c['role'] for c in parsed['components']],
                         ['scene_catalog', 'robot_base', 'robot_ability', 'model', 'robot_skill'])
        self.assertEqual(parsed['runtime']['pack']['size'], 1932735283)

    def test_runtime_is_listed_before_components(self):
        parsed = extension.parse(manifest())
        labels = [label for label, _ in extension.render(parsed)]
        self.assertLess(labels.index('Runtime 包'), labels.index('scene_catalog'))
        self.assertLess(labels.index('scene_catalog'), labels.index('robot_skill'))

    def test_missing_schema_version_is_rejected(self):
        value = json.loads(manifest())
        del value['schema_version']
        with self.assertRaisesRegex(extension.ManifestError, 'schema_version'):
            extension.parse(json.dumps(value))

    def test_wrong_schema_version_is_rejected(self):
        with self.assertRaisesRegex(extension.ManifestError, 'schema_version'):
            extension.parse(manifest(schema_version=2))

    def test_unknown_component_role_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['role'] = 'unknown'
        with self.assertRaisesRegex(extension.ManifestError, 'role 不在允许'):
            extension.parse(json.dumps(value))

    def test_base_role_is_required(self):
        value = json.loads(manifest())
        value['components'] = [c for c in value['components'] if c['role'] != 'robot_base']
        with self.assertRaisesRegex(extension.ManifestError, '基座产物'):
            extension.parse(json.dumps(value))

    def test_duplicate_component_is_rejected(self):
        value = json.loads(manifest())
        value['components'].append(dict(value['components'][0]))
        with self.assertRaisesRegex(extension.ManifestError, '重复声明'):
            extension.parse(json.dumps(value))

    def test_artifact_without_digest_is_rejected(self):
        value = json.loads(manifest())
        del value['runtime']['pack']['sha256']
        with self.assertRaisesRegex(extension.ManifestError, 'sha256'):
            extension.parse(json.dumps(value))

    def test_artifact_without_size_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['size'] = 0
        with self.assertRaisesRegex(extension.ManifestError, 'size'):
            extension.parse(json.dumps(value))

    def test_invalid_digest_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['sha256'] = 'nothex'
        with self.assertRaisesRegex(extension.ManifestError, 'sha256 格式'):
            extension.parse(json.dumps(value))

    def test_non_http_artifact_url_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['url'] = 'ftp://example.invalid/x.zip'
        with self.assertRaisesRegex(extension.ManifestError, 'http'):
            extension.parse(json.dumps(value))

    def test_runtime_installation_id_cannot_collide_with_base(self):
        for identifier in ('native-mujoco', 'base'):
            value = json.loads(manifest())
            value['runtime']['installation_id'] = identifier
            with self.subTest(identifier=identifier), self.assertRaisesRegex(extension.ManifestError, '标识'):
                extension.parse(json.dumps(value))

    def test_oversized_artifact_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['size'] = 13 * 1024**3
        with self.assertRaisesRegex(extension.ManifestError, '超出上限'):
            extension.parse(json.dumps(value))

    def test_bad_prerequisite_kind_is_rejected(self):
        value = json.loads(manifest())
        value['prerequisites'] = [{'kind': 'magic', 'text': '扫码安装'}]
        with self.assertRaisesRegex(extension.ManifestError, 'prerequisites'):
            extension.parse(json.dumps(value))

    def test_bad_port_range_is_rejected(self):
        for ports in ([[0, 18199]], [[18200, 18199]], [['a', 'b']]):
            with self.subTest(ports=ports), self.assertRaisesRegex(extension.ManifestError, '整数对'):
                extension.parse(manifest(ports=ports))

    def test_valid_ports_and_prerequisites_are_accepted(self):
        parsed = extension.parse(manifest(ports=[[18100, 18199]],
            prerequisites=[{'kind': 'probe', 'text': '本机已导入引擎镜像', 'check': 'docker image inspect x'},
                           {'kind': 'user_action', 'text': '数据集需单独取得'}]))
        self.assertEqual(parsed['ports'], [[18100, 18199]])
        self.assertEqual(len(parsed['prerequisites']), 2)

    def test_invalid_gpu_requirement_is_rejected(self):
        with self.assertRaisesRegex(extension.ManifestError, 'gpu'):
            extension.parse(manifest(host_requirements={'gpu': 'sometimes'}))

    def test_invalid_json_is_rejected(self):
        with self.assertRaisesRegex(extension.ManifestError, 'JSON'):
            extension.parse('{not json')

    def test_non_object_manifest_is_rejected(self):
        with self.assertRaisesRegex(extension.ManifestError, '必须是 JSON 对象'):
            extension.parse('[]')

    def test_manifest_id_must_match_request(self):
        parsed = extension.parse(manifest())
        self.assertEqual(parsed['id'], 'libero')

    def test_component_flags_are_preserved_for_the_install_plan(self):
        value = json.loads(manifest())
        value['components'][0]['robot_required'] = True
        value['components'][1]['project_default'] = True
        parsed = extension.parse(json.dumps(value))
        flags = {(c['role'], c['id']): (c['project_default'], c['robot_required'])
                 for c in parsed['components']}
        self.assertEqual(flags[('robot_skill', 'vla-manipulation')], (False, True))
        self.assertEqual(flags[('scene_catalog', 'libero-scenes')], (True, False))

    def test_non_boolean_component_flag_is_rejected(self):
        value = json.loads(manifest())
        value['components'][0]['project_default'] = 'yes'
        with self.assertRaisesRegex(extension.ManifestError, '布尔值'):
            extension.parse(json.dumps(value))


class ChannelTests(unittest.TestCase):
    def test_channel_url_encodes_and_preserves_slash(self):
        self.assertEqual(extension.channel_url('https://oss.invalid/semantic/', 'extensions', 'libero'),
                         'https://oss.invalid/semantic/extensions/libero')

    def test_manifest_url_shape(self):
        self.assertEqual(
            extension.manifest_url('https://oss.invalid/semantic', 'libero', '0.1.0'),
            'https://oss.invalid/semantic/extensions/libero/0.1.0/extension.json')

    def test_explicit_version_wins_over_pointer(self):
        with patch.object(extension, 'stable_pointer', return_value='9.9.9') as pointer:
            self.assertEqual(extension.resolve_version('https://oss.invalid', 'libero', '0.1.0'), '0.1.0')
            pointer.assert_not_called()

    def test_unreachable_pointer_is_reported(self):
        with patch.object(extension, 'stable_pointer', return_value=None):
            with self.assertRaisesRegex(extension.ManifestError, '无法从通道解析'):
                extension.resolve_version('https://oss.invalid', 'libero')

    def test_unreachable_pointer_returns_none(self):
        with patch.object(extension.urllib.request, 'urlopen', side_effect=OSError('no network')):
            self.assertIsNone(extension.stable_pointer('https://oss.invalid', 'libero'))

    def test_blank_pointer_is_rejected(self):
        with patch.object(extension.urllib.request, 'urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = FakeResponse(json.dumps({'version': '  '}))
            self.assertIsNone(extension.stable_pointer('https://oss.invalid', 'libero'))

    def test_manifest_download_404_names_the_version(self):
        error = extension.urllib.error.HTTPError('url', 404, 'Not Found', {}, None)
        with patch.object(extension.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaisesRegex(extension.ManifestError, '通道上没有'):
                extension.load_manifest('https://oss.invalid', 'libero', '0.1.0')

    def test_manifest_id_mismatch_is_rejected(self):
        with patch.object(extension, 'resolve_version', return_value='0.1.0'), \
             patch.object(extension.urllib.request, 'urlopen',
                          return_value=FakeResponse(json.dumps({**json.loads(manifest()), 'id': 'isaac'})
                                       .encode())):
            with self.assertRaisesRegex(extension.ManifestError, '不一致'):
                extension.load_manifest('https://oss.invalid', 'libero')


class FakeResponse:
    """Minimal context-manager stream: ``read()`` drains a fixed body, like a socket."""

    def __init__(self, body=b''):
        self.body = body if isinstance(body, bytes) else body.encode()
        self.offset = 0

    def read(self, amount=-1):
        if amount is None or amount < 0:
            amount = len(self.body)
        block, self.offset = self.body[self.offset:self.offset + amount], self.offset + max(amount, 0)
        return block

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


class Runaway(FakeResponse):
    """A stream that always has one more block, to prove the size ceiling engages."""

    def read(self, amount=-1):
        return b'x' * (1024 * 1024)


class VerifyTests(unittest.TestCase):
    """The digest that is checked must be the one the manifest declares."""

    def parsed(self, declared=b'payload'):
        """Build a manifest whose declared digests and sizes match ``declared``."""
        value = json.loads(manifest())
        for artifact in [value['runtime']['pack'], *value['components']]:
            artifact['size'] = len(declared)
            artifact['sha256'] = digest_of(declared)
        return extension.parse(json.dumps(value))

    def test_verify_reports_one_row_per_artifact(self):
        with patch.object(extension, '_download', side_effect=write(b'payload')), \
             patch.object(extension, 'Progress'):
            rows = extension.verify(self.parsed(), quiet=True)
        self.assertEqual(len(rows), 6)
        self.assertEqual({row[0] for row in rows},
                         {'local-libero-robosuite-1.4', 'scene_catalog/libero-scenes',
                          'robot_base/franka-libero-robot', 'robot_ability/franka-ability',
                          'model/franka-smolvla-model', 'robot_skill/vla-manipulation'})
        self.assertTrue(all(row[1] == 'ok' for row in rows))

    def test_verify_truncated_artifact_is_rejected(self):
        with patch.object(extension, '_download', side_effect=write(b'paylo')), \
             patch.object(extension, 'Progress'):
            with self.assertRaisesRegex(extension.ManifestError, 'size-mismatch'):
                extension.verify(self.parsed(), quiet=True)

    def test_verify_substituted_artifact_of_equal_size_is_rejected(self):
        with patch.object(extension, '_download', side_effect=write(b'payloaz')), \
             patch.object(extension, 'Progress'):
            with self.assertRaisesRegex(extension.ManifestError, 'sha256-mismatch'):
                extension.verify(self.parsed(), quiet=True)

    def test_verify_download_failure_names_the_artifact(self):
        with patch.object(extension, '_download', side_effect=OSError('connection reset')), \
             patch.object(extension, 'Progress'):
            with self.assertRaisesRegex(extension.ManifestError, 'connection reset'):
                extension.verify(self.parsed(), quiet=True)

    def test_one_artifact_result_names_expected_and_actual_size(self):
        parsed = self.parsed()
        with patch.object(extension, '_download', side_effect=write(b'paylo')):
            state, detail = extension._verify_one(parsed['runtime']['pack'])
        self.assertEqual(state, 'size-mismatch')
        self.assertIn('期望 7', detail)
        self.assertIn('实际 5', detail)


def write(body):
    """A ``_download`` stand-in that stages ``body`` at the destination."""
    def download(url, destination):
        destination.write_bytes(body)
        return len(body)
    return download


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = __import__('tempfile').TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.target = Path(self.temporary.name)/'pack.zip'

    def test_download_refuses_runaway_size(self):
        with patch.object(extension.urllib.request, 'urlopen', return_value=Runaway()), \
             patch.object(extension, 'ARTIFACT_LIMIT', 1024):
            with self.assertRaisesRegex(extension.ManifestError, '上限'):
                extension._download('https://example.invalid/x.zip', self.target)

    def test_download_writes_streamed_bytes(self):
        with patch.object(extension.urllib.request, 'urlopen', return_value=FakeResponse(b'hello')):
            self.assertEqual(extension._download('https://example.invalid/x.zip', self.target), 5)
        self.assertEqual(self.target.read_bytes(), b'hello')


class EntryTests(unittest.TestCase):
    def test_list_without_index_reports_unavailable(self):
        args = __import__('types').SimpleNamespace(extension_action='list', id=None, base_url='https://oss.invalid',
                                                   version=None, quiet=False)
        with patch.object(extension.urllib.request, 'urlopen', side_effect=OSError('no network')):
            self.assertEqual(extension.entry(args), 1)

    def test_show_prints_summary(self):
        args = __import__('types').SimpleNamespace(extension_action='show', id='libero',
                                                   base_url='https://oss.invalid', version='0.1.0', quiet=False)
        with patch.object(extension, 'load_manifest', return_value=extension.parse(manifest())), \
             patch('builtins.print') as show:
            self.assertEqual(extension.entry(args), 0)
        self.assertTrue(any('LIBERO 仿真场景' in str(call) for call in show.call_args_list))

    def test_install_requires_root_and_project(self):
        """install/remove are supported now, but they refuse to run half-specified."""
        for action in ('install', 'remove'):
            args = __import__('types').SimpleNamespace(
                extension_action=action, id='libero', base_url='https://oss.invalid',
                version='0.1.0', quiet=True, manifest_file=None, root=None, project=None,
                dry_run=True, yes=True, robot=None, asset_root=None, accept_license=None,
                extension_package_dir=None, previews=True, scenes=None, replace=False)
            with self.subTest(action=action), \
                 patch.object(extension, 'load_manifest', return_value=extension.parse(manifest())):
                with self.assertRaises(SystemExit):
                    extension.entry(args)

    def test_unknown_action_is_rejected(self):
        args = __import__('types').SimpleNamespace(extension_action='bogus', id='libero',
                                                   base_url='https://oss.invalid', version=None, quiet=False)
        with self.assertRaises(SystemExit):
            extension.entry(args)

    def test_show_uses_an_offline_manifest_file(self):
        directory = __import__('tempfile').mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = Path(directory)/'extension.json'
        path.write_text(manifest(), encoding='utf-8')
        args = __import__('types').SimpleNamespace(extension_action='show', id='libero',
                                                   base_url='https://oss.invalid', version=None,
                                                   quiet=False, manifest_file=path)
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
             patch.object(extension, 'load_manifest', side_effect=AssertionError('must not use the network')):
            self.assertEqual(extension.entry(args), 0)
        self.assertIn('LIBERO', out.getvalue())


class ProbeTests(unittest.TestCase):
    """Probes are "skippable but reported": a failure warns, it never raises."""

    def parsed(self, prerequisites):
        value = json.loads(manifest())
        value['prerequisites'] = prerequisites
        return extension.parse(json.dumps(value))

    def test_failed_probe_warns_and_keeps_going(self):
        parsed = self.parsed([
            {'kind': 'probe', 'text': '引擎镜像', 'check': 'docker image inspect x'},
            {'kind': 'user_action', 'text': '数据集需另行取得'},
            {'kind': 'probe', 'text': '缺少 check 的探测'},
        ])
        rows = extension.probe_rows(parsed, runner=lambda command: (1, 'no such image'))
        self.assertEqual([row[1] for row in rows], ['warn', 'skip'])
        self.assertIn('no such image', rows[0][2])

    def test_successful_probe_reports_ok(self):
        parsed = self.parsed([{'kind': 'probe', 'text': '磁盘', 'check': 'df -h .'}])
        rows = extension.probe_rows(parsed, runner=lambda command: (0, 'avail\n120G'))
        self.assertEqual(rows, [('磁盘', 'ok', '120G')])

    def test_probe_runner_error_is_not_fatal(self):
        parsed = self.parsed([{'kind': 'probe', 'text': 'docker', 'check': 'docker ps'}])
        def broken(command):
            raise OSError('docker 未安装')
        rows = extension.probe_rows(parsed, runner=broken)
        self.assertEqual(rows[0][1], 'warn')
        self.assertIn('docker 未安装', rows[0][2])


class PortWarningTests(unittest.TestCase):
    """Port collisions are a warning, never a failed install."""

    def test_busy_port_is_reported(self):
        value = json.loads(manifest())
        value['ports'] = [[18100, 18102]]
        parsed = extension.parse(json.dumps(value))
        busy = lambda port, host='127.0.0.1', timeout=0.3: port == 18101
        with patch.object(extension, 'port_busy', side_effect=busy):
            rows = extension.port_warnings(parsed)
        self.assertEqual([row[0] for row in rows], [18101])
        self.assertIn('同机并存', rows[0][1])


class PlanTests(unittest.TestCase):
    """The install plan is pure and pins every documented flag."""

    def isaac_like(self):
        value = json.loads(manifest())
        value['runtime']['content'] = {'name': 'behavior_data', 'option': '--asset-root'}
        value['runtime']['pack']['license'] = 'behavior-assets'
        return extension.parse(json.dumps(value))

    def test_runtime_content_requires_asset_root_and_carries_the_license(self):
        parsed = self.isaac_like()
        paths = extension.artifact_paths(parsed, package_dir='/tmp/packages')
        with self.assertRaisesRegex(extension.ManifestError, 'asset-root'):
            extension.plan_commands(parsed, paths, 'semantic', 'cfg', project='proj')
        plan = extension.plan_commands(parsed, paths, 'semantic', 'cfg', project='proj',
                                       asset_root='/data/behavior', robot='robot_r1')
        runtime = plan[0][1]
        self.assertEqual(runtime[1:3], ['runtime', 'install'])
        self.assertIn('--asset-root', runtime)
        self.assertIn('--accept-license', runtime)
        self.assertIn('behavior-assets', runtime)

    def test_scene_previews_and_robot_requirement(self):
        parsed = extension.parse(manifest())
        paths = extension.artifact_paths(parsed)
        plan = extension.plan_commands(parsed, paths, 'semantic', 'cfg', project='proj',
                                       robot='robot_r1', previews=False)
        scene = next(command for name, command in plan if 'libero-scenes' in name)
        self.assertIn('--generate-previews=false', scene)
        self.assertIn('--scene', scene)
        skill = next(command for name, command in plan if 'vla-manipulation' in name)
        self.assertEqual(skill[-2:], ['--robot', 'robot_r1'])
        with self.assertRaisesRegex(extension.ManifestError, '--robot'):
            extension.plan_commands(parsed, paths, 'semantic', 'cfg', project='proj')

    def test_components_install_after_the_runtime(self):
        parsed = extension.parse(manifest())
        plan = extension.plan_commands(parsed, extension.artifact_paths(parsed), 'semantic', 'cfg',
                                       project='proj', robot='robot_r1')
        self.assertEqual(plan[0][0], 'runtime')
        self.assertEqual([name for name, _ in plan[1:]], [
            'scene_catalog/libero-scenes', 'robot_base/franka-libero-robot',
            'robot_ability/franka-ability', 'model/franka-smolvla-model',
            'robot_skill/vla-manipulation'])

    def test_uninstall_plan_reverses_the_components_then_the_runtime(self):
        parsed = extension.parse(manifest())
        plan = extension.uninstall_plan(parsed, 'semantic', 'cfg', 'proj')
        self.assertEqual(plan[0][0], 'robot_skill/vla-manipulation')
        self.assertEqual(plan[-1][1][1:4], ['uninstall', 'runtime', '--id'])


class OfflineInstallTests(unittest.TestCase):
    """An offline directory must be verified by digest before anything runs."""

    def setUp(self):
        temp = __import__('tempfile').TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pkg = Path(temp.name)/'packages'
        self.pkg.mkdir()
        value = json.loads(manifest())
        value['post_install'] = [{'kind': 'user_action', 'text': '绑定 Ability 与模型'}]
        bodies = {}
        for artifact, name in [(value['runtime']['pack'], 'libero.runtime.tar.zst'),
                               *[(c, c['url'].rsplit('/', 1)[1]) for c in value['components']]]:
            body = ('payload:'+name).encode()
            bodies[name] = body
            artifact['size'] = len(body)
            artifact['sha256'] = digest_of(body)
        for name, body in bodies.items():
            (self.pkg/name).write_bytes(body)
        self.parsed = extension.parse(json.dumps(value))

    def test_offline_install_verifies_then_runs_every_command(self):
        ran, rows = [], []
        plan = extension.install(self.parsed, self.pkg/'instance', project='proj-1', robot='robot_r1',
                                 package_dir=self.pkg, report=lambda *row: rows.append(row),
                                 runner=lambda command: ran.append(command))
        self.assertEqual(len(plan), 6)
        self.assertEqual(len(ran), 6)
        self.assertEqual(ran[0][1:3], ['runtime', 'install'])
        self.assertEqual(ran[1][1], 'install')
        self.assertIn('--project', ran[1])
        self.assertTrue(any(row[0] == 'post' for row in rows))

    def test_offline_install_rejects_a_corrupted_artifact_before_running(self):
        (self.pkg/'vla-manipulation.zip').write_bytes(b'tampered')
        ran = []
        with self.assertRaisesRegex(extension.ManifestError, '不符'):
            extension.install(self.parsed, self.pkg/'instance', project='proj-1',
                              package_dir=self.pkg, runner=lambda command: ran.append(command))
        self.assertEqual(ran, [])

    def test_offline_install_rejects_a_missing_artifact(self):
        (self.pkg/'franka-ability.zip').unlink()
        with self.assertRaisesRegex(extension.ManifestError, '缺少产物'):
            extension.install(self.parsed, self.pkg/'instance', project='proj-1',
                              package_dir=self.pkg, runner=lambda command: None)


class CheckedInManifestTests(unittest.TestCase):
    """The committed template must keep parsing as the validator tightens."""

    def test_libero_manifest_parses(self):
        parsed = extension.parse((ROOT/'extensions/libero/extension.json').read_text())
        self.assertEqual(parsed['id'], 'libero')
        self.assertEqual(parsed['runtime']['installation_id'], 'local-libero-robosuite-1.4')

    def test_libero_manifest_order_is_runtime_then_components(self):
        parsed = extension.parse((ROOT/'extensions/libero/extension.json').read_text())
        self.assertEqual([c['role'] for c in parsed['components']],
                         ['scene_catalog', 'robot_base', 'robot_ability', 'model', 'robot_skill'])

    def test_libero_manifest_carries_a_license_to_accept(self):
        parsed = extension.parse((ROOT/'extensions/libero/extension.json').read_text())
        self.assertTrue(parsed['license'].strip())

    def test_libero_manifest_declares_no_gpu_requirement(self):
        parsed = extension.parse((ROOT/'extensions/libero/extension.json').read_text())
        self.assertEqual(parsed['host_requirements']['gpu'], 'optional')

    def test_isaac_manifest_parses(self):
        parsed = extension.parse((ROOT/'extensions/isaac/extension.json').read_text())
        self.assertEqual(parsed['id'], 'isaac')
        self.assertEqual(parsed['runtime']['installation_id'], 'local-behavior-omnigibson')
        self.assertEqual(parsed['runtime']['endpoint'], 'http://127.0.0.1:18090')
        self.assertEqual(parsed['host_requirements']['gpu'], 'required')

    def test_isaac_manifest_keeps_the_documented_install_order(self):
        parsed = extension.parse((ROOT/'extensions/isaac/extension.json').read_text())
        self.assertEqual([c['role'] for c in parsed['components']],
                         ['scene_catalog', 'robot_base', 'robot_ability', 'model', 'robot_skill'])

    def test_isaac_manifest_ports_cover_runtime_ability_and_policy(self):
        parsed = extension.parse((ROOT/'extensions/isaac/extension.json').read_text())
        self.assertIn([18090, 18090], parsed['ports'])
        self.assertIn([18100, 18199], parsed['ports'])
        self.assertIn([20080, 20080], parsed['ports'])

    def test_isaac_manifest_declares_probes_and_a_license_placeholder(self):
        parsed = extension.parse((ROOT/'extensions/isaac/extension.json').read_text())
        probes = [item for item in parsed['prerequisites'] if item['kind'] == 'probe']
        self.assertTrue(probes)
        self.assertTrue(all(item.get('check') for item in probes))
        self.assertTrue(parsed['license'].strip())

    def test_isaac_manifest_requires_asset_root_content(self):
        parsed = extension.parse((ROOT/'extensions/isaac/extension.json').read_text())
        self.assertEqual(parsed['runtime']['content']['option'], '--asset-root')
        self.assertEqual(parsed['runtime']['pack']['license'], 'behavior-assets')


class ChannelResolutionTests(unittest.TestCase):
    """One relative-URL manifest must serve both the OSS prefix and GitHub."""

    def relative(self):
        value = json.loads(manifest())
        for artifact in [value['runtime']['pack'], *value['components']]:
            artifact['url'] = artifact['url'].rsplit('/', 1)[1]
        return json.dumps(value)

    def test_parse_without_a_source_keeps_relative_urls(self):
        parsed = extension.parse(self.relative())
        self.assertEqual(parsed['runtime']['pack']['url'], 'libero.runtime.tar.zst')

    def test_oss_channel_joins_the_version_prefix(self):
        parsed = extension.parse(self.relative(), source='oss', base='https://oss.invalid/semantic')
        self.assertEqual(parsed['runtime']['pack']['url'],
                         'https://oss.invalid/semantic/extensions/libero/0.1.0/libero.runtime.tar.zst')
        self.assertEqual(parsed['source'], 'oss')

    def test_github_channel_joins_the_release_tag(self):
        parsed = extension.parse(self.relative(), source='github', base='https://oss.invalid/semantic')
        self.assertEqual(parsed['runtime']['pack']['url'],
                         'https://github.com/insightos-community/quick-start/releases/download/'
                         'ext-libero-v0.1.0/libero.runtime.tar.zst')

    def test_oversized_artifacts_fall_back_to_oss_on_the_github_channel(self):
        value = json.loads(self.relative())
        base = next(item for item in value['components'] if item['role'] == 'robot_base')
        base['hosts'] = ['oss']
        parsed = extension.parse(json.dumps(value), source='github', base='https://oss.invalid/semantic')
        base_role = next(item for item in parsed['components'] if item['role'] == 'robot_base')
        self.assertEqual(base_role['channel'], 'oss')
        self.assertTrue(base_role['url'].startswith('https://oss.invalid/'))
        skill = next(item for item in parsed['components'] if item['role'] == 'robot_skill')
        self.assertEqual(skill['channel'], 'github')

    def test_absolute_urls_survive_resolution(self):
        parsed = extension.parse(manifest(), source='github', base='https://oss.invalid/semantic')
        self.assertEqual(parsed['runtime']['pack']['url'], 'https://example.invalid/libero.runtime.tar.zst')

    def test_github_false_is_the_oss_only_shorthand(self):
        value = json.loads(self.relative())
        value['components'][0]['github'] = False
        parsed = extension.parse(json.dumps(value), source='github', base='https://oss.invalid/semantic')
        skill = next(item for item in parsed['components'] if item['role'] == 'robot_skill')
        self.assertEqual(skill['hosts'], ['oss'])
        self.assertEqual(skill['channel'], 'oss')

    def test_unknown_host_is_rejected(self):
        value = json.loads(self.relative())
        value['components'][0]['hosts'] = ['floppy']
        with self.assertRaisesRegex(extension.ManifestError, 'hosts'):
            extension.parse(json.dumps(value))

    def test_non_boolean_github_marker_is_rejected(self):
        value = json.loads(self.relative())
        value['components'][0]['github'] = 'no'
        with self.assertRaisesRegex(extension.ManifestError, 'github'):
            extension.parse(json.dumps(value))

    def test_unknown_source_is_rejected(self):
        with self.assertRaisesRegex(extension.ManifestError, '通道'):
            extension.resolve_sources(extension.parse(self.relative()), source='ftp')

    def test_default_base_is_the_real_oss_prefix(self):
        self.assertEqual(extension.DEFAULT_OSS_BASE,
                         'https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic')
        parsed = extension.parse(self.relative(), source='oss')
        self.assertTrue(parsed['runtime']['pack']['url'].startswith(extension.DEFAULT_OSS_BASE))

    def test_github_tag_and_download_shapes(self):
        self.assertEqual(extension.github_tag('isaac', '0.1.0'), 'ext-isaac-v0.1.0')
        self.assertEqual(extension.github_download('org/repo', 'isaac', '0.1.0'),
                         'https://github.com/org/repo/releases/download/ext-isaac-v0.1.0/')

    def test_installed_manifest_file_resolves_relative_urls(self):
        directory = __import__('tempfile').mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = Path(directory)/'extension.json'
        path.write_text(self.relative(), encoding='utf-8')
        parsed = extension.load_manifest_file(path, source='oss', base='https://oss.invalid/semantic')
        self.assertEqual(parsed['runtime']['pack']['url'],
                         'https://oss.invalid/semantic/extensions/libero/0.1.0/libero.runtime.tar.zst')

    def test_cli_default_base_and_source_are_the_real_channel(self):
        import argparse
        parser = argparse.ArgumentParser()
        commands = parser.add_subparsers()
        extension.register(commands)
        parsed = parser.parse_args(['extension', 'show', 'libero'])
        self.assertEqual(parsed.base_url, extension.DEFAULT_OSS_BASE)
        self.assertEqual(parsed.source, 'oss')


class CheckedInManifestChannelTests(unittest.TestCase):
    """The committed templates must use relative URLs and mark the OSS-only tail."""

    def parse(self, name):
        return extension.parse((ROOT/'extensions'/name/'extension.json').read_text())

    def test_libero_template_uses_relative_urls(self):
        parsed = self.parse('libero')
        for artifact in [parsed['runtime']['pack'], *parsed['components']]:
            self.assertNotIn('://', artifact['url'], artifact['url'])

    def test_isaac_template_uses_relative_urls(self):
        parsed = self.parse('isaac')
        for artifact in [parsed['runtime']['pack'], *parsed['components']]:
            self.assertNotIn('://', artifact['url'], artifact['url'])

    def test_libero_marks_the_three_oversized_artifacts_oss_only(self):
        parsed = self.parse('libero')
        oss_only = {item['id'] for item in parsed['components']
                    if item.get('hosts') == ['oss']}
        self.assertEqual(oss_only, {'franka-libero-robot', 'franka-ability', 'franka-smolvla-model'})
        for item in parsed['components']:
            if item['id'] in oss_only:
                self.assertGreater(item['size'], extension.GITHUB_ASSET_LIMIT)

    def test_isaac_fits_under_the_github_asset_limit(self):
        parsed = self.parse('isaac')
        sizes = [parsed['runtime']['pack']['size']] + [item['size'] for item in parsed['components']]
        self.assertTrue(all(size <= extension.GITHUB_ASSET_LIMIT for size in sizes))
        self.assertTrue(all('hosts' not in item for item in parsed['components']))

    def test_libero_runtime_declares_the_license_to_accept(self):
        parsed = self.parse('libero')
        self.assertEqual(parsed['runtime']['pack']['license'], 'LIBERO')

    def test_both_templates_carry_a_real_license(self):
        for name in ('libero', 'isaac'):
            with self.subTest(name=name):
                parsed = self.parse(name)
                self.assertTrue(parsed['license'].strip())
                self.assertNotIn('TO_BE_FILLED', parsed['license'])


class InstallerChannelWiringTests(unittest.TestCase):
    """``install.sh`` must expose the channel selector and forward it to the loader."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('runtime_installer', ROOT/'artifacts/runtime/installer.py')
        cls.runtime_installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runtime_installer)

    def args(self, **overrides):
        values = dict(extension='libero', extension_source='oss', extension_manifest=None,
                      extension_base_url=None, extension_dry_run=True, extension_package_dir=None,
                      no_start=True, extension_project='proj', extension_robot=None,
                      extension_asset_root=None, accept_license=None)
        values.update(overrides)
        return __import__('types').SimpleNamespace(**values)

    def test_channel_source_is_forwarded_to_the_manifest_loader(self):
        seen = {}

        def fake_load(base, identifier, version=None, source='oss', repo=None):
            seen.update(base=base, source=source)
            return extension.parse(manifest())

        with patch.object(self.runtime_installer.extension, 'load_manifest', side_effect=fake_load), \
             patch.object(self.runtime_installer.extension, 'install', return_value=[]), \
             patch.object(self.runtime_installer, 'DEFAULT_EXTENSION_BASE', 'https://oss.invalid/semantic'):
            self.runtime_installer.install_extension(Path('/tmp/root'), self.args(extension_source='github'))
        self.assertEqual(seen['source'], 'github')
        self.assertEqual(seen['base'], 'https://oss.invalid/semantic')

    def test_default_channel_is_oss(self):
        seen = {}

        def fake_load(base, identifier, version=None, source='oss', repo=None):
            seen['source'] = source
            return extension.parse(manifest())

        with patch.object(self.runtime_installer.extension, 'load_manifest', side_effect=fake_load), \
             patch.object(self.runtime_installer.extension, 'install', return_value=[]):
            self.runtime_installer.install_extension(Path('/tmp/root'), self.args(extension_source=None))
        self.assertEqual(seen['source'], 'oss')

    def test_offline_manifest_keeps_the_requested_channel(self):
        seen = {}
        with patch.object(self.runtime_installer.extension, 'load_manifest_file',
                          side_effect=lambda path, source='oss', base=None, repo=None:
                          seen.update(source=source) or extension.parse(manifest())), \
             patch.object(self.runtime_installer.extension, 'install', return_value=[]):
            self.runtime_installer.install_extension(Path('/tmp/root'), self.args(
                extension_source='github', extension_manifest=Path('/tmp/extension.json')))
        self.assertEqual(seen['source'], 'github')

    def test_generated_installers_expose_the_channel_selector(self):
        for name in ('install.sh', 'install-en.sh'):
            text = (ROOT/name).read_text()
            with self.subTest(name=name):
                self.assertIn('--extension-source', text)
                self.assertIn("choices=['oss', 'github']", text)
                self.assertIn("source = getattr(a, 'extension_source', None) or 'oss'", text)


if __name__ == '__main__':
    unittest.main()
