#!/usr/bin/env python3
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

"""Publish an allowlisted release to Alibaba OSS; credentials and tickets stay outside Git."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile
import urllib.parse

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = Path.home()/'.config/semantic-artifacts/oss.env'
LOG_FILE = None


def emit(*values):
    message = ' '.join(map(str, values))
    print(message, flush=True)
    if LOG_FILE:
        with LOG_FILE.open('a') as log:
            log.write(message+'\n')


def root_error(error):
    seen = set()
    while callable(getattr(error, 'unwrap', None)) and id(error) not in seen:
        seen.add(id(error))
        inner = error.unwrap()
        if inner is None:
            break
        error = inner
    return error


def read_config(path):
    path = Path(path).expanduser()
    resolved = path.resolve(strict=True)
    if path.is_symlink() or HERE.parent == resolved or HERE.parent in resolved.parents:
        raise ValueError('OSS 凭据必须保存在仓库外，且不能通过符号链接读取')
    if resolved.stat().st_mode & 0o077 or resolved.stat().st_uid != os.geteuid():
        raise ValueError('OSS 配置必须属于当前用户，权限为 600')
    values = {}
    for line in resolved.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'OSS_[A-Z_]+', key):
            raise ValueError('OSS 配置格式无效；使用 KEY=value，不执行 shell')
        values[key] = value.strip()
    for key in ('OSS_REGION', 'OSS_ENDPOINT', 'OSS_BUCKET', 'OSS_PREFIX',
                'OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET', 'OSS_DOWNLOAD_BASE'):
        if not values.get(key):
            raise ValueError('缺少配置项 '+key)
    if not re.fullmatch(r'[a-z0-9-]+', values['OSS_BUCKET']):
        raise ValueError('Bucket 名称无效')
    prefix = values['OSS_PREFIX']
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', prefix):
        raise ValueError('对象前缀无效')
    for key in ('OSS_ENDPOINT', 'OSS_DOWNLOAD_BASE'):
        parsed = urllib.parse.urlsplit(values[key])
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError(key+' 必须是无凭据的 HTTPS 地址')
    if values.get('OSS_ACCESS_MODE', 'private') not in ('private', 'public-read'):
        raise ValueError('OSS_ACCESS_MODE 必须是 private 或 public-read')
    return values


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024*1024):
            h.update(block)
    return h.hexdigest()


def release_files(version):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('非法发布版本')
    folder = HERE/'releases'/version/'linux-x86_64'
    manifest = json.loads((folder/'manifest.json').read_text())
    archive = folder/f'semantic-{version}-linux-x86_64.tar.gz'
    relative = archive.relative_to(HERE).as_posix()
    if manifest.get('archive') != relative or manifest.get('version') != version or manifest.get('platform') != 'linux-x86_64':
        raise ValueError('版本清单与归档路径不一致')
    if digest(archive) != manifest['sha256'] or archive.stat().st_size != manifest['size']:
        raise ValueError('本地制品校验失败')
    files = [archive, Path(str(archive)+'.sha256'), folder/'release.json', folder/'manifest.json']
    if any(p.is_symlink() or not p.is_file() or HERE.resolve() not in p.resolve().parents for p in files):
        raise ValueError('发布文件必须是 artifacts 内的普通文件')
    return manifest, files


class Store:
    def __init__(self, config):
        import alibabacloud_oss_v2 as oss
        self.oss = oss
        self.values = config
        cfg = oss.config.load_default()
        cfg.region = config['OSS_REGION']
        cfg.endpoint = config['OSS_ENDPOINT']
        cfg.readwrite_timeout = 120
        cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
            config['OSS_ACCESS_KEY_ID'], config['OSS_ACCESS_KEY_SECRET'])
        self.client = oss.Client(cfg)
        self.bucket = config['OSS_BUCKET']
        self.acl = config.get('OSS_ACCESS_MODE', 'private')

    def key(self, relative):
        return self.values['OSS_PREFIX']+'/'+relative

    def bucket_acl(self):
        return self.client.get_bucket_acl(self.oss.GetBucketAclRequest(bucket=self.bucket)).acl

    def head(self, key):
        try:
            return self.client.head_object(self.oss.HeadObjectRequest(bucket=self.bucket, key=key))
        except Exception as error:
            if getattr(root_error(error), 'status_code', None) == 404:
                return None
            raise

    def verify(self, key, checksum, size):
        head = self.head(key)
        metadata = {k.lower(): v for k, v in (head.metadata or {}).items()} if head else {}
        if not head or metadata.get('sha256') != checksum or head.content_length != size:
            raise RuntimeError('OSS 上传后的长度/校验元数据不匹配: '+key)
        acl = self.client.get_object_acl(self.oss.GetObjectAclRequest(bucket=self.bucket, key=key)).acl
        if acl != self.acl:
            raise RuntimeError('对象 ACL 与要求不符: '+key)

    def upload(self, path, relative, mutable=False):
        path = Path(path)
        if mutable and relative not in ('install.sh', 'channels/stable.json'):
            raise ValueError('只允许更新安装入口和默认版本清单')
        key, checksum = self.key(relative), digest(path)
        head = self.head(key)
        if head:
            meta = {k.lower(): v for k, v in (head.metadata or {}).items()}
            if meta.get('sha256') == checksum:
                self.verify(key, checksum, path.stat().st_size)
                emit('已校验，跳过:', key)
                return
            if not mutable or meta.get('semantic-managed') != '1':
                raise RuntimeError('拒绝覆盖已有不同内容/非本客户端管理的对象: '+key)
        kind = ('application/gzip' if path.name.endswith('.tar.gz') else
                {'.json': 'application/json', '.mp4': 'video/mp4'}.get(path.suffix, 'text/plain; charset=utf-8'))
        request = self.oss.PutObjectRequest(bucket=self.bucket, key=key, acl=self.acl,
            metadata={'sha256': checksum, 'semantic-managed': '1'},
            content_type=kind, cache_control='no-cache' if mutable else 'max-age=31536000, immutable',
            forbid_overwrite=not mutable)
        if mutable and head:
            if not head.etag:
                raise RuntimeError('已有对象缺少 ETag，拒绝无条件覆盖: '+key)
            self.backup_mutable(key, head)
            current = self.head(key)
            if not current or current.etag != head.etag:
                raise RuntimeError('更新前对象发生变化，停止发布: '+key)
            # OSS PutObject rejects If-Match (400 NotImplemented). Preserve a
            # verified backup + recheck, and serialize local publishers below.
            # This is NOT a cross-machine atomic compare-and-swap.
        elif mutable:
            request.forbid_overwrite = True
        emit('上传:', key, f'({path.stat().st_size} bytes, {self.acl})')
        self.client.put_object_from_file(request, str(path))
        self.verify(key, checksum, path.stat().st_size)
        emit('上传校验通过:', key)

    def sign(self, relative, ttl):
        result = self.client.presign(self.oss.GetObjectRequest(bucket=self.bucket, key=self.key(relative)),
                                     expires=datetime.timedelta(seconds=ttl))
        return result.url

    def backup_mutable(self, key, head):
        if not 0 <= head.content_length <= 2*1024*1024:
            raise RuntimeError('旧入口大小异常，停止发布: '+key)
        response = self.client.get_object(self.oss.GetObjectRequest(
            bucket=self.bucket, key=key, if_match=head.etag))
        try:
            if response.content_length != head.content_length:
                raise RuntimeError('旧入口长度发生变化，停止发布: '+key)
            # SDK response bodies expose read() without a size argument.
            data = response.body.read()
        finally:
            response.body.close()
        checksum = hashlib.sha256(data).hexdigest()
        if len(data) > 2*1024*1024 or checksum != (head.metadata or {}).get('sha256') or len(data) != head.content_length:
            raise RuntimeError('旧入口备份校验失败，停止发布: '+key)
        output = DEFAULT_CONFIG.parent/'backups'/(key.replace('/', '_')+'.'+checksum)
        save_private(output, data.decode('utf-8'))
        emit('已备份旧入口:', output)


def save_private(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('拒绝覆盖符号链接输出文件')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.oss-', dir=path.parent)
    with os.fdopen(fd, 'w') as f:
        f.write(data)
    os.replace(temporary, path)


def ticket(store, manifest, output):
    ttl = int(store.values.get('OSS_SIGNED_URL_TTL', '3600'))
    if not 60 <= ttl <= 604800:
        raise ValueError('签名链接有效期应为 60～604800 秒')
    archive_key = store.key(manifest['archive'])
    store.verify(archive_key, manifest['sha256'], manifest['size'])
    bootstrap_head = store.head(store.key('install.sh'))
    if not bootstrap_head:
        raise ValueError('请先上传 install.sh')
    bootstrap_sha = (bootstrap_head.metadata or {}).get('sha256')
    if not bootstrap_sha or not re.fullmatch('[0-9a-f]{64}', bootstrap_sha):
        raise ValueError('远端 install.sh 缺少校验元数据')
    grant = {**manifest, 'base_url': store.values['OSS_DOWNLOAD_BASE'],
             'archive_url': store.sign(manifest['archive'], ttl),
             'bootstrap_url': store.sign('install.sh', ttl), 'bootstrap_sha256': bootstrap_sha,
             'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=ttl)).isoformat()}
    output = Path(output).expanduser().resolve()
    if HERE.parent in output.parents:
        raise ValueError('签名下载票据必须保存到仓库外')
    grant_file = output/'download.json'
    save_private(grant_file, json.dumps(grant, indent=2)+'\n')
    # The launcher contains only a path to the private ticket; never credentials or URLs.
    launcher = '''#!/usr/bin/env bash
set -euo pipefail
python3 - TICKET "$@" <<'PY'
import hashlib, json, pathlib, subprocess, sys, tempfile, urllib.request
ticket = pathlib.Path(sys.argv[1])
m = json.loads(ticket.read_text())
try:
    with urllib.request.urlopen(m['bootstrap_url'], timeout=60) as response:
        code = response.read(1024*1024)
except Exception:
    raise SystemExit('安装入口下载失败；签名可能过期，请重新生成下载票据。')
if hashlib.sha256(code).hexdigest() != m['bootstrap_sha256']:
    raise SystemExit('安装入口 SHA256 校验失败')
with tempfile.TemporaryDirectory(prefix='semantic-bootstrap-') as directory:
    script = pathlib.Path(directory)/'install.sh'
    script.write_bytes(code)
    subprocess.run(['bash', str(script), '--ticket', str(ticket), *sys.argv[2:]], check=True)
PY
'''.replace('TICKET', shlex.quote(str(grant_file)), 1)
    save_private(output/'install-current.sh', launcher)
    emit('限时下载票据及入口已写入仓库外:', output)
    emit('有效期（秒）:', ttl)
    emit('安装命令: bash '+shlex.quote(str(output/'install-current.sh'))+' --yes')


def main():
    global LOG_FILE
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    p.add_argument('action', choices=['check', 'publish', 'ticket'])
    p.add_argument('--version')
    p.add_argument('--skip-bootstrap', action='store_true')
    p.add_argument('--allow-public-internal-assets', action='store_true')
    p.add_argument('--ticket-dir', type=Path, default=DEFAULT_CONFIG.parent/'download')
    a = p.parse_args()
    logdir = DEFAULT_CONFIG.parent/'logs'
    logdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix='oss-', suffix='.log', dir=logdir)
    os.close(fd)
    LOG_FILE = Path(filename)
    emit('OSS 客户端日志:', LOG_FILE)
    config = read_config(a.config)
    store = Store(config)
    emit('Bucket:', store.bucket, 'ACL:', store.bucket_acl(), '本次对象 ACL:', store.acl)
    if a.action == 'check':
        return
    if not a.version:
        raise ValueError('必须指定 --version')
    manifest, files = release_files(a.version)
    if store.acl == 'public-read' and manifest.get('distribution') == 'internal-only' and not a.allow_public_internal_assets:
        raise ValueError('资产标记为 internal-only；公开上传需要明确的资产分发确认参数')
    if a.action == 'publish':
        for path in files:
            store.upload(path, path.relative_to(HERE).as_posix())
        if not a.skip_bootstrap:
            store.upload(HERE/'install.sh', 'install.sh', mutable=True)
        # Promote only after every immutable release object (and bootstrap when requested) verifies.
        with tempfile.TemporaryDirectory(prefix='semantic-oss-channel-') as directory:
            channel = Path(directory)/'stable.json'
            channel.write_text(json.dumps(manifest, indent=2)+'\n')
            store.upload(channel, 'channels/stable.json', mutable=True)
        emit('已发布版本:', a.version)
    if not a.skip_bootstrap and (store.acl == 'private' or a.action == 'ticket'):
        ticket(store, manifest, a.ticket_dir)
    elif not a.skip_bootstrap:
        emit('公开安装（无需票据）: curl -fsSL '+
             shlex.quote(config['OSS_DOWNLOAD_BASE'].rstrip('/')+'/install.sh')+' | bash -s -- --yes')


if __name__ == '__main__':
    try:
        DEFAULT_CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (DEFAULT_CONFIG.parent/'publish.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            main()
    except Exception as error:
        error = root_error(error)
        # SDK exception strings can contain signed URLs/credentials. Never dump their repr/traceback.
        if isinstance(error, (ValueError, RuntimeError)):
            emit('OSS 客户端失败:', str(error))
        else:
            emit('OSS 客户端失败:', type(error).__name__, 'status=', getattr(error, 'status_code', None),
                 'code=', getattr(error, 'code', None))
        sys.exit(1)
