# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Extension scene manifest: parse, verify and list what an extension needs.

An extension scene (LIBERO today, Isaac later) is an optional side-payload installed
*after* the base environment. It is never folded into the immutable base release:
the base payload is an exact verified file set, and the extension artifacts are an
order of magnitude larger (LIBERO is about 10.4 GB against 345 MiB).

See docs/extensions.md for the full design.

The manifest carries one role per artifact. A role decides where an artifact lands:

    runtime        local ``semantic install runtime --pack`` execution
    scene_catalog  Server component install
    robot_base     Server component install
    robot_ability  Server component install
    model          Server component install
    robot_skill    Server component install

Runtime goes first and the components follow in a fixed order: the Bundle is the
base that ability, model and skill are inserted into.

This module is deliberately dependency-free apart from the standard library and
``install_support``, and it must not import ``installer``: ``installer`` imports it.
"""

import hashlib
import json
import shlex
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_support import Progress

SCHEMA_VERSION = 1

# One artifact may legitimately be huge; keep a ceiling so a bad manifest cannot
# fill the disk before the digest check runs.
ARTIFACT_LIMIT = 12 * 1024**3

COMPONENT_ORDER = ('scene_catalog', 'robot_base', 'robot_ability', 'model', 'robot_skill')
ROLES = ('runtime', *COMPONENT_ORDER)
# Roles whose bundle is the base the remaining components are inserted into.
BASE_ROLES = ('robot_base',)
PREREQUISITE_KINDS = ('probe', 'user_action')

MANIFEST_NAME = 'extension.json'
STABLE_POINTER = 'stable.json'

# Two channels carry the same immutable artifacts. The manifest and its stable
# pointer always come from the OSS base; a relative artifact URL is resolved
# against the selected channel so one manifest serves both.
SOURCES = ('oss', 'github')
DEFAULT_OSS_BASE = 'https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic'
DEFAULT_GITHUB_REPO = 'insightos-community/quick-start'
GITHUB_DOWNLOAD = 'https://github.com/{repo}/releases/download/{tag}/'
# GitHub rejects a single release asset at or above 2 GiB. Artifacts over the
# limit are marked ``hosts: ["oss"]`` and fall back to OSS on the GitHub channel.
GITHUB_ASSET_LIMIT = 2 * 1024**3


class ManifestError(ValueError):
    """A manifest is unusable; the message names the offending field."""


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f'{field} 必须是非空字符串')
    return value


def _checksum(record, field):
    if not isinstance(record, dict):
        raise ManifestError(f'{field} 必须是对象')
    value = _text(record.get('sha256'), f'{field}.sha256').lower()
    if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ManifestError(f'{field}.sha256 格式不正确')
    size = record.get('size')
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ManifestError(f'{field}.size 必须是非零整数')
    if size > ARTIFACT_LIMIT:
        raise ManifestError(f'{field}.size 超出上限')
    return value, size


def _artifact(record, field):
    source = _text(record.get('url'), f'{field}.url')
    scheme = urllib.parse.urlsplit(source).scheme
    if scheme and scheme not in ('https', 'http'):
        raise ManifestError(f'{field}.url 只支持 http(s) 或相对路径')
    checksum, size = _checksum(record, field)
    artifact = {'url': source, 'sha256': checksum, 'size': size}
    if 'license' in record:
        artifact['license'] = _text(record['license'], f'{field}.license')
    hosts = _hosts(record, field)
    if hosts:
        artifact['hosts'] = hosts
    return artifact


def _hosts(record, field):
    """An artifact's allowed channels; ``None`` means every channel serves it.

    ``hosts: ["oss"]`` (or the shorthand ``github: false``) marks an artifact the
    GitHub mirror must not carry, so the installer falls back to OSS.
    """
    value = record.get('hosts')
    if value is None:
        github = record.get('github')
        if github is None:
            return None
        if not isinstance(github, bool):
            raise ManifestError(f'{field}.github 必须是布尔值')
        return None if github else ['oss']
    if not isinstance(value, list) or not value:
        raise ManifestError(f'{field}.hosts 必须是非空数组')
    hosts = []
    for item in value:
        name = _text(item, f'{field}.hosts')
        if name not in SOURCES:
            raise ManifestError(f'{field}.hosts 只能是 oss 或 github')
        if name not in hosts:
            hosts.append(name)
    return hosts


def parse(text, source=None, base=None, repo=None):
    """Validate a manifest and return it with the install order applied.

    ``source``/``base`` are optional: when given, each artifact URL is bound to
    the requested channel (``resolve_sources``); absolute URLs are preserved.
    """
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as error:
        raise ManifestError(f'清单不是合法 JSON: {error}') from None
    if not isinstance(manifest, dict):
        raise ManifestError('清单必须是 JSON 对象')

    version = manifest.get('schema_version')
    if version != SCHEMA_VERSION:
        raise ManifestError(f'清单 schema_version 必须是 {SCHEMA_VERSION}')

    identifier = _text(manifest.get('id'), 'id')
    title = _text(manifest.get('title'), 'title')
    if not all(c.islower() or c.isdigit() or c == '-' for c in identifier) or identifier.startswith('-'):
        raise ManifestError('id 只能是小写字母、数字与连字符')
    compatible = manifest.get('compatible_base')
    if not isinstance(compatible, str) or not compatible.strip():
        raise ManifestError('compatible_base 必须是非空字符串')

    runtime = manifest.get('runtime')
    if not isinstance(runtime, dict):
        raise ManifestError('runtime 段缺失')
    endpoints = runtime.get('endpoint')
    if not isinstance(endpoints, str) or not endpoints.startswith(('http://', 'https://')):
        raise ManifestError('runtime.endpoint 必须是 http(s) 地址')
    pack = _artifact(runtime.get('pack') or {}, 'runtime.pack')
    installation_id = _text(runtime.get('installation_id'), 'runtime.installation_id')
    if installation_id in ('native-mujoco', 'base'):
        raise ManifestError('runtime.installation_id 不能占用基础 Runtime 的标识')
    content = _content(runtime.get('content'))

    components, seen, roles = [], set(), set()
    raw_components = manifest.get('components')
    if not isinstance(raw_components, list) or not raw_components:
        raise ManifestError('components 必须是非空数组')
    for index, record in enumerate(raw_components):
        field = f'components[{index}]'
        role = _text(record.get('role'), f'{field}.role')
        if role not in ROLES or role == 'runtime':
            raise ManifestError(f'{field}.role 不在允许的取值内: {" ".join(ROLES)}')
        identifier_text = _text(record.get('id'), f'{field}.id')
        component = dict(_artifact(record, field), role=role, id=identifier_text,
                         previews=_previews(record.get('previews'), f'{field}.previews'),
                         project_default=_flag(record.get('project_default'), f'{field}.project_default'),
                         robot_required=_flag(record.get('robot_required'), f'{field}.robot_required'))
        key = (role, identifier_text)
        if key in seen:
            raise ManifestError(f'{field} 重复声明 {role}/{identifier_text}')
        seen.add(key)
        roles.add(role)
        components.append(component)
    missing = [role for role in BASE_ROLES if role not in roles]
    if missing:
        raise ManifestError('components 缺少基座产物: ' + ', '.join(missing))
    components.sort(key=lambda item: COMPONENT_ORDER.index(item['role']))

    requirements = manifest.get('host_requirements') or {}
    if not isinstance(requirements, dict):
        raise ManifestError('host_requirements 必须是对象')
    gpu = requirements.get('gpu', 'optional')
    if gpu not in ('required', 'optional', 'forbidden'):
        raise ManifestError('host_requirements.gpu 只能是 required/optional/forbidden')
    disk_gib = requirements.get('disk_gib')
    if disk_gib is not None and (not isinstance(disk_gib, int) or isinstance(disk_gib, bool) or disk_gib <= 0):
        raise ManifestError('host_requirements.disk_gib 必须是正整数')

    prerequisites = _steps(manifest.get('prerequisites'), 'prerequisites', probes=True)
    post_install = _steps(manifest.get('post_install'), 'post_install')

    ports = manifest.get('ports') or []
    if not isinstance(ports, list) or any(
            not isinstance(item, list) or len(item) != 2
            or any(not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535 for port in item)
            or item[1] < item[0] for item in ports):
        raise ManifestError('端口段必须是 [起始, 结束] 整数对，且范围合法')

    license_text = manifest.get('license')
    if license_text is not None:
        license_text = _text(license_text, 'license')

    normalized = dict(manifest,
                id=identifier, title=title, license=license_text,
                runtime=dict(runtime, pack=pack, installation_id=installation_id,
                             endpoint=endpoints, content=content),
                components=components, prerequisites=prerequisites, post_install=post_install,
                ports=ports, host_requirements=dict(requirements, gpu=gpu))
    if source is None and base is None:
        return normalized
    return resolve_sources(normalized, source=source or 'oss', base=base, repo=repo)


def _steps(value, field, probes=False):
    """Normalize a ``prerequisites``-shaped list of ``{kind, text}`` steps."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError(f'{field} 必须是数组')
    steps = []
    for index, record in enumerate(value):
        label = f'{field}[{index}]'
        if not isinstance(record, dict):
            raise ManifestError(f'{label} 必须是对象')
        kind = _text(record.get('kind'), f'{label}.kind')
        if kind not in PREREQUISITE_KINDS:
            raise ManifestError(f'{label}.kind 只能是 {" ".join(PREREQUISITE_KINDS)}')
        step = {'kind': kind, 'text': _text(record.get('text'), f'{label}.text')}
        if probes and 'check' in record:
            step['check'] = _text(record['check'], f'{label}.check')
        steps.append(step)
    return steps


def _flag(value, field):
    """A component's boolean marker (``project_default`` / ``robot_required``)."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ManifestError(f'{field} 必须是布尔值')
    return value


def _content(value):
    """The Runtime's external content requirement (``--asset-root`` today)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError('runtime.content 必须是对象')
    content = {'name': _text(value.get('name'), 'runtime.content.name')}
    for key in ('option', 'requires', 'note'):
        if key in value:
            content[key] = _text(value[key], f'runtime.content.{key}')
    return content


def _previews(value, field):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManifestError(f'{field} 必须是对象')
    scenes = value.get('default_scenes', [])
    if not isinstance(scenes, list) or any(not isinstance(item, str) or not item for item in scenes):
        raise ManifestError(f'{field}.default_scenes 必须是字符串数组')
    return dict(value, default_scenes=scenes)


def channel_url(base, *parts):
    """Join a channel base URL with path segments, keeping the query string."""
    base = base.rstrip('/') + '/'
    return urllib.parse.urljoin(base, '/'.join(urllib.parse.quote(p, safe='') for p in parts))


def github_tag(identifier, version):
    """The GitHub Release tag that mirrors one extension version."""
    return f'ext-{identifier}-v{version}'


def github_download(repo, identifier, version):
    """The flat asset directory of a GitHub Release; GitHub has no subfolders."""
    return GITHUB_DOWNLOAD.format(repo=repo, tag=github_tag(identifier, version))


def artifact_base(source, base, identifier, version, repo=None):
    """Artifact directory for one channel: an OSS version prefix or a release."""
    if source == 'github':
        return github_download(repo or DEFAULT_GITHUB_REPO, identifier, version)
    return channel_url(base, 'extensions', identifier, version) + '/'


def resolve_artifact(artifact, source, base, identifier, version, repo=None):
    """Bind one artifact to the ``source`` channel, falling back to OSS.

    Absolute URLs (legacy manifests, offline bundles) are kept untouched; a
    relative URL is joined with the channel's artifact directory.
    """
    hosts = artifact.get('hosts') or list(SOURCES)
    chosen = source if source in hosts else ('oss' if 'oss' in hosts else hosts[0])
    url = artifact['url']
    if not urllib.parse.urlsplit(url).scheme:
        url = urllib.parse.urljoin(artifact_base(chosen, base, identifier, version, repo),
                                   urllib.parse.quote(url, safe='/'))
    return dict(artifact, url=url, channel=chosen)


def resolve_sources(manifest, source='oss', base=None, repo=None):
    """Return a copy of ``manifest`` with every artifact bound to ``source``."""
    if source not in SOURCES:
        raise ManifestError('未知的产物通道: ' + str(source))
    base = (base or DEFAULT_OSS_BASE).rstrip('/')
    identifier, version = manifest['id'], manifest['version']
    runtime = dict(manifest['runtime'])
    runtime['pack'] = resolve_artifact(manifest['runtime']['pack'], source, base,
                                       identifier, version, repo)
    components = [resolve_artifact(item, source, base, identifier, version, repo)
                  for item in manifest['components']]
    return dict(manifest, runtime=runtime, components=components, source=source)


def stable_pointer(base, identifier):
    """The mutable ``stable.json`` for an extension; ``None`` when unreachable."""
    url = channel_url(base, 'extensions', identifier, STABLE_POINTER)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/json'}), timeout=30) as response:
            pointer = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    version = (pointer or {}).get('version') if isinstance(pointer, dict) else None
    return version if isinstance(version, str) and version.strip() else None


def resolve_version(base, identifier, version=None):
    """Version to use: explicit request, else the channel pointer, else fail."""
    if version:
        return version
    version = stable_pointer(base, identifier)
    if not version:
        raise ManifestError('无法从通道解析 {} 的版本，请显式指定 version'.format(identifier))
    return version


def manifest_url(base, identifier, version):
    return channel_url(base, 'extensions', identifier, version, MANIFEST_NAME)


def load_manifest(base, identifier, version=None, source='oss', repo=None):
    """Download and parse an extension manifest. Download only; no artifacts yet."""
    version = resolve_version(base, identifier, version)
    url = manifest_url(base, identifier, version)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/json'}), timeout=30) as response:
            text = response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ManifestError('通道上没有 {} {} 的清单'.format(identifier, version)) from None
        raise ManifestError('下载清单失败: HTTP {}'.format(error.code)) from None
    except (urllib.error.URLError, OSError) as error:
        raise ManifestError('连接通道失败: {}'.format(error)) from None
    manifest = parse(text, source=source, base=base, repo=repo)
    if manifest['id'] != identifier:
        raise ManifestError('清单 id({}) 与请求的 ({}) 不一致'.format(manifest['id'], identifier))
    return manifest


def render(manifest, base=None):
    """Human-readable summary; ``base`` adds the resolved download URL per artifact."""
    rows = [('扩展', manifest['title']), ('标识', manifest['id']),
            ('版本', manifest['version']), ('兼容基础版本', manifest['compatible_base']),
            ('Runtime', manifest['runtime']['installation_id']), ('Runtime 入口', manifest['runtime']['endpoint']),
            ('GPU', manifest['host_requirements']['gpu'])]
    content = manifest['runtime'].get('content') or {}
    if content:
        detail = content['name']
        if content.get('option'):
            detail += '  ' + content['option']
        if content.get('requires'):
            detail += '  需存在 ' + content['requires']
        rows.append(('Runtime 内容', detail))
    pack = manifest['runtime']['pack']
    rows.append(('Runtime 包', _describe(pack, base)))
    for component in manifest['components']:
        rows.append((component['role'], f"{component['id']}  {_describe(component, base)}"))
    if manifest['ports']:
        rows.append(('端口段', ', '.join(f'{first}-{last}' for first, last in manifest['ports'])))
    prerequisites = manifest['prerequisites']
    if prerequisites:
        rows.append(('前置条件', '; '.join(
            f"{item['kind']}: {item['text']}" + (f" [{item['check']}]" if item.get('check') else '')
            for item in prerequisites)))
    post_install = manifest.get('post_install') or []
    if post_install:
        rows.append(('安装后', '; '.join(item['text'] for item in post_install)))
    return rows


def probe_rows(manifest, runner=None):
    """Run the manifest's ``probe`` steps. Failures warn; nothing raises.

    The execution semantics are "skippable but reported": a probe that fails must
    not block the install, or a normal "install the base first, add the image
    later" order would be impossible.
    """
    runner = runner or run_probe
    rows = []
    for item in manifest.get('prerequisites', []):
        if item['kind'] != 'probe':
            continue
        command = item.get('check')
        if not command:
            rows.append((item['text'], 'skip', '清单未提供 check 命令'))
            continue
        try:
            code, output = runner(command)
        except OSError as error:
            rows.append((item['text'], 'warn', str(error)))
            continue
        detail = (output or '').strip().splitlines()
        detail = detail[-1] if detail else ''
        rows.append((item['text'], 'ok' if code == 0 else 'warn', detail or f'退出码 {code}'))
    return rows


def run_probe(command):
    """Run a probe command through the shell; returns ``(exit_code, output)``."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    return result.returncode, (result.stdout or '') + (result.stderr or '')


def _describe(artifact, base=None):
    text = f"{artifact['size'] / 1024**2:.1f} MiB  sha256={artifact['sha256'][:12]}…"
    return text + '  ' + artifact['url']


def verify(manifest, quiet=False):
    """Download every artifact and check its digest and size. Nothing is installed.

    Returns one ``(name, state, detail)`` row per artifact and raises on the first
    failure, so a caller can record the rows and still stop the install.
    """
    artifacts = [(manifest['runtime']['installation_id'], manifest['runtime']['pack'])]
    artifacts += [(f"{item['role']}/{item['id']}", item) for item in manifest['components']]
    rows, failures = [], []
    progress = None if quiet else Progress([name for name, _ in artifacts])
    try:
        for name, artifact in artifacts:
            if progress:
                progress.next(name)
            state, detail = _verify_one(artifact)
            rows.append((name, state, detail))
            if state != 'ok':
                failures.append(name)
    finally:
        if progress:
            progress.finish()
    if failures:
        raise ManifestError('存在校验失败的产物: ' + ', '.join(f'{name}: {state} ({detail})'
                           for (name, state, detail) in rows if name in failures))
    return rows


def _verify_one(artifact):
    url, expected, size = artifact['url'], artifact['sha256'], artifact['size']
    try:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/Path(urllib.parse.urlsplit(url).path).name
            _download(url, target)
            if target.stat().st_size != size:
                return 'size-mismatch', f'期望 {size} 实际 {target.stat().st_size}'
            actual = digest(target)
            if actual != expected:
                return 'sha256-mismatch', f'期望 {expected[:12]}… 实际 {actual[:12]}…'
            return 'ok', f'{size / 1024**2:.1f} MiB'
    except ManifestError as error:
        return 'download-failed', str(error)
    except (urllib.error.HTTPError, OSError) as error:
        return 'download-failed', str(error)


def _download(url, destination):
    """Stream ``url`` to ``destination``, stopping before a runaway manifest fills the disk."""
    received = 0
    with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as response, destination.open('wb') as target:
        while block := response.read(1024 * 1024):
            received += len(block)
            if received > ARTIFACT_LIMIT:
                raise ManifestError(f'下载体积超过上限 {ARTIFACT_LIMIT / 1024**3:.1f} GiB')
            target.write(block)
    return received


def artifact_name(artifact):
    """File name an artifact lands as, inside a package dir or the download workspace."""
    return Path(urllib.parse.urlsplit(artifact['url']).path).name


def artifact_paths(manifest, package_dir=None, workspace=None):
    """Where each artifact is expected: ``package_dir`` (offline) or the workspace."""
    directory = Path(package_dir) if package_dir else Path(workspace or '.')
    paths = {'runtime': directory/artifact_name(manifest['runtime']['pack'])}
    for component in manifest['components']:
        paths[(component['role'], component['id'])] = directory/artifact_name(component)
    return paths


def stage_artifact(artifact, path):
    """Verify a staged artifact before it is installed. Raises ``ManifestError``."""
    path = Path(path)
    name = path.name
    if not path.is_file():
        raise ManifestError(f'缺少产物: {path}')
    if path.stat().st_size != artifact['size']:
        raise ManifestError(f'{name} 大小不符: 期望 {artifact["size"]} 实际 {path.stat().st_size}')
    actual = digest(path)
    if actual != artifact['sha256']:
        raise ManifestError(f'{name} 摘要不符: 期望 {artifact["sha256"][:12]}… 实际 {actual[:12]}…')
    return path


def plan_commands(manifest, paths, cli, config, project=None, robot=None, asset_root=None,
                  accept_license=None, replace=False, previews=True, scenes=None):
    """The exact commands an install runs, in order. Pure; used by dry-run and tests."""
    plan = []
    command = [cli, 'runtime', 'install', '--pack', str(paths['runtime']),
               '--sha256', manifest['runtime']['pack']['sha256'],
               '--installation-id', manifest['runtime']['installation_id'],
               '--endpoint', manifest['runtime']['endpoint'], '-c', str(config)]
    content = manifest['runtime'].get('content') or {}
    if content:
        if not asset_root:
            raise ManifestError('Runtime 需要内容 {}: 请提供 --asset-root'.format(content['name']))
        command += ['--asset-root', str(asset_root)]
    declared = manifest['runtime']['pack'].get('license')
    if declared:
        command += ['--accept-license', accept_license or declared]
    if replace:
        command.append('--replace')
    plan.append(('runtime', command))
    for component in manifest['components']:
        command = [cli, 'install', str(paths[(component['role'], component['id'])]), '--project', str(project)]
        if component.get('project_default'):
            command.append('--project-default')
        if component.get('robot_required'):
            if not robot:
                raise ManifestError('组件 {} 需要 --robot'.format(component['id']))
            command += ['--robot', str(robot)]
        if component['role'] == 'scene_catalog':
            if not previews:
                command.append('--generate-previews=false')
            chosen = scenes if scenes is not None else (component.get('previews') or {}).get('default_scenes') or []
            for scene in chosen:
                command += ['--scene', scene]
        plan.append((f"{component['role']}/{component['id']}", command))
    return plan


def uninstall_plan(manifest, cli, config, project):
    """The commands that remove an installed extension, in reverse order."""
    plan = []
    for component in reversed(manifest['components']):
        plan.append((f"{component['role']}/{component['id']}",
                     [cli, 'uninstall', component['id'], '--project', str(project)]))
    plan.append(('runtime', [cli, 'uninstall', 'runtime', '--id',
                             manifest['runtime']['installation_id'], '-c', str(config)]))
    return plan


def port_warnings(manifest, host='127.0.0.1'):
    """Report declared ports already in use. A warning, never a failure."""
    rows = []
    for first, last in manifest.get('ports', []):
        for port in range(first, last + 1):
            if port_busy(port, host):
                rows.append((port, f'{host}:{port} 已被占用; 同机并存需为各环境分配不同端口段'))
    return rows


def port_busy(port, host='127.0.0.1', timeout=0.3):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def run_command(command):
    subprocess.run(command, check=True)


def install(manifest, root, project=None, robot=None, asset_root=None, accept_license=None,
            package_dir=None, workspace=None, replace=False, previews=True, scenes=None,
            dry_run=False, report=print, runner=None):
    """Install a parsed extension: verify every artifact, then run the plan.

    Offline installs take artifacts from ``package_dir``; otherwise they are
    expected in ``workspace`` (the caller downloads them there first).
    """
    runner = runner or run_command
    cli = str(Path(root)/'current/bin/semantic')
    config = Path(root)/'configs/semantic-server.yaml'
    paths = artifact_paths(manifest, package_dir, workspace)
    if dry_run:
        plan = plan_commands(manifest, paths, cli, config, project, robot, asset_root,
                             accept_license, replace, previews, scenes)
        for name, command in plan:
            report('dry-run', name, shell_line(command))
        return plan
    for key, path in paths.items():
        artifact = manifest['runtime']['pack'] if key == 'runtime' else next(
            item for item in manifest['components'] if (item['role'], item['id']) == key)
        if package_dir is None and not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            _download(artifact['url'], path)
        stage_artifact(artifact, path)
    plan = plan_commands(manifest, paths, cli, config, project, robot, asset_root,
                         accept_license, replace, previews, scenes)
    for name, command in plan:
        report('run', name, shell_line(command))
        runner(command)
    for item in manifest.get('post_install') or []:
        report('post', item['kind'], item['text'])
    return plan


def remove(manifest, root, project, dry_run=False, report=print, runner=None):
    """Uninstall an extension: components first, then the Runtime installation."""
    runner = runner or run_command
    cli = str(Path(root)/'current/bin/semantic')
    config = Path(root)/'configs/semantic-server.yaml'
    plan = uninstall_plan(manifest, cli, config, project)
    for name, command in plan:
        report('dry-run' if dry_run else 'run', name, shell_line(command))
        if not dry_run:
            runner(command)
    return plan


def shell_line(command):
    """Render an argv for display without losing quoting."""
    return ' '.join(shlex.quote(str(part)) for part in command)


def load_manifest_file(path, source='oss', base=None, repo=None):
    """Load a manifest from disk: the offline counterpart of ``load_manifest``."""
    return parse(Path(path).read_text(), source=source, base=base, repo=repo)


def entry(args):
    """``semanticctl extension`` dispatch."""
    action = args.extension_action
    if action not in ('list', 'show', 'verify', 'install', 'remove'):
        raise SystemExit(f'未知的 extension 动作: {action}')
    source = getattr(args, 'source', 'oss')
    if action == 'list':
        base = args.base_url.rstrip('/')
        try:
            with urllib.request.urlopen(urllib.request.Request(channel_url(base, 'extensions', 'index.json'),
                        headers={'Accept': 'application/json'}), timeout=30) as response:
                index = json.load(response)
        except (urllib.error.URLError, OSError, ValueError):
            index = None
        if not isinstance(index, dict) or not index:
            print(f'通道 {base} 没有可用的扩展目录 (extensions/index.json)')
            return 1
        for identifier, item in sorted(index.items()):
            version = (item or {}).get('version') if isinstance(item, dict) else None
            print(f"{identifier}\t{(item or {}).get('title', '')}\t{version if isinstance(version, str) else '?'}")
        return 0
    if not args.id:
        raise SystemExit(f'extension {action} 需要扩展 id，例如 isaac')
    manifest_file = getattr(args, 'manifest_file', None)
    manifest = (load_manifest_file(manifest_file, source=source, base=args.base_url)
                if manifest_file else load_manifest(args.base_url, args.id, args.version, source=source))
    if action == 'show':
        for label, value in render(manifest):
            print(f'{label}: {value}')
        return 0
    if action == 'verify':
        for name, state, detail in verify(manifest, quiet=args.quiet):
            print(f'{state}\t{name}\t{detail}')
        print(f'已校验 {len(manifest["components"]) + 1} 个产物。')
        return 0
    quiet = getattr(args, 'quiet', False)

    def emit(kind, name, detail):
        if not quiet:
            print(f'{kind}\t{name}\t{detail}')

    root = getattr(args, 'root', None)
    if not root:
        raise SystemExit(f'extension {action} 需要 --root <安装根目录>')
    project = getattr(args, 'project', None)
    if not project:
        raise SystemExit(f'extension {action} 需要 --project <项目ID>')
    dry_run = getattr(args, 'dry_run', False)
    if action == 'install':
        for name, state, detail in probe_rows(manifest):
            emit(state, name, detail)
        for port, detail in port_warnings(manifest):
            emit('warn', f'端口 {port}', detail)
        package_dir = getattr(args, 'extension_package_dir', None)
        workspace = Path(root)/'tmp'/f'extension-{manifest["id"]}'
        if not package_dir and not dry_run:
            workspace.mkdir(parents=True, exist_ok=True)
        install(manifest, root, project=project, robot=getattr(args, 'robot', None),
                asset_root=getattr(args, 'asset_root', None),
                accept_license=getattr(args, 'accept_license', None),
                package_dir=package_dir, workspace=workspace,
                replace=getattr(args, 'replace', False),
                previews=getattr(args, 'previews', True),
                scenes=getattr(args, 'scenes', None),
                dry_run=dry_run, report=emit)
        return 0
    if not dry_run and not getattr(args, 'yes', False):
        raise SystemExit('extension remove 会卸载该扩展的 Runtime 与组件；确认请加 --yes，或先 --dry-run')
    remove(manifest, root, project, dry_run=dry_run, report=emit)
    return 0


def register(parser):
    commands = parser.add_parser('extension', help='扩展场景: 清单查看、产物校验与安装')
    commands.add_argument('extension_action', choices=['list', 'show', 'verify', 'install', 'remove'])
    commands.add_argument('id', nargs='?', help='扩展标识，例如 libero / isaac')
    commands.add_argument('--base-url', dest='base_url', default=DEFAULT_OSS_BASE,
                          help='发布通道地址')
    commands.add_argument('--source', dest='source', choices=list(SOURCES), default='oss',
                          help='产物通道: oss 走 OSS, github 走 GitHub Releases (超限产物自动回退 OSS)')
    commands.add_argument('--version', help='覆盖 stable.json 指向的版本')
    commands.add_argument('--manifest-file', dest='manifest_file', type=Path,
                          help='离线清单文件；给出后不再联网解析版本')
    commands.add_argument('--extension-package-dir', dest='extension_package_dir', type=Path,
                          help='离线产物目录；六个产物齐备即完全离线')
    commands.add_argument('--root', type=Path, help='安装根目录（install/remove 必填）')
    commands.add_argument('--project', help='目标 Project ID')
    commands.add_argument('--robot', help='robot_required 组件要安装到的 Robot ID')
    commands.add_argument('--asset-root', dest='asset_root', help='Runtime 的原生资产目录')
    commands.add_argument('--accept-license', dest='accept_license', help='确认 Runtime 包声明的许可')
    commands.add_argument('--scene', dest='scenes', action='append', help='限定场景预览范围，可重复')
    commands.add_argument('--no-previews', dest='previews', action='store_false', default=True,
                          help='安装场景时不生成预览（低显存机器）')
    commands.add_argument('--replace', action='store_true', help='修复同一 installation_id 时替换已有 Runtime')
    commands.add_argument('--dry-run', dest='dry_run', action='store_true', help='只打印将执行的命令')
    commands.add_argument('--yes', action='store_true', help='remove: 跳过确认')
    commands.add_argument('--quiet', action='store_true')
    commands.set_defaults(extension=entry)
    return commands
