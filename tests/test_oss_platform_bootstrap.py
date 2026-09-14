# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OSSPlatformTests(unittest.TestCase):
    def test_macos_language_and_explicit_sources_download_expected_mirror(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root/'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                body = b'#!/bin/bash\nexit 23\n'
                entry = tarfile.TarInfo('python/bin/python3.13'); entry.size=len(body); entry.mode=0o755
                tar.addfile(entry, io.BytesIO(body))
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            tools = root/'tools'; tools.mkdir()
            scripts = {'uname':'#!/bin/sh\nif [ "$1" = -s ]; then echo Darwin; else echo arm64; fi\n',
                       'lsof':'#!/bin/sh\nexit 1\n'}
            log = root/'requests'
            scripts['curl'] = f'''#!{sys.executable}
import pathlib,sys
args=sys.argv[1:]; url=next(a for a in args if a.startswith('https://')); target=pathlib.Path(args[args.index('-o')+1])
with pathlib.Path({str(log)!r}).open('a') as out:out.write(url+'\\n')
if url.endswith('SHA256SUMS'):target.write_text({(checksum+'  semantic-0.1.0-rc.4-macos-arm64.tar.gz'+chr(10))!r})
else:target.write_bytes(pathlib.Path({str(archive)!r}).read_bytes())
'''
            for name,code in scripts.items():
                path=tools/name;path.write_text(code);path.chmod(0o755)
            env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH']}
            oss='https://insightos-artifacts.oss-cn-shanghai.aliyuncs.com/semantic/releases/0.1.0-rc.4/macos-arm64'
            github='https://github.com/insightos-community/quick-start/releases/download/macos-v0.1.0-rc.4'
            cases=[('install.sh',[],oss),('install-en.sh',[],github),
                   ('install-en.sh',['--source','oss'],oss),('install.sh',['--source','github'],github),
                   ('install.sh',['--base-url','https://mirror.example.test/semantic'],'https://mirror.example.test/semantic/releases/0.1.0-rc.4/macos-arm64')]
            for index,(script,args,base) in enumerate(cases):
                with self.subTest(script=script,args=args):
                    log.write_text('')
                    result=subprocess.run(['bash',str(ROOT/script),'--tag','macos-v0.1.0-rc.4',
                        '--dir',str(root/'instance'),'--cache-dir',str(root/f'cache{index}'),'--no-start',*args],
                        env=env,capture_output=True,text=True)
                    self.assertEqual(result.returncode,23,result.stderr)
                    self.assertEqual(log.read_text().splitlines(),[base+'/SHA256SUMS',base+'/semantic-0.1.0-rc.4-macos-arm64.tar.gz'])

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux bootstrap integration')
    def test_musl_tag_resolves_oss_release_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); archive=root/'fixture.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                body=b'raise SystemExit(23)\n'; entry=tarfile.TarInfo('installer.py');entry.size=len(body)
                tar.addfile(entry,io.BytesIO(body))
            content=archive.read_bytes(); checksum=hashlib.sha256(content).hexdigest()
            prefix='/releases/0.1.0-musl.2/linux-musl-x86_64/'
            manifest=json.dumps(dict(version='0.1.0-musl.2',platform='linux-musl-x86_64',archive=prefix[1:]+'package.tar.gz',sha256=checksum,size=len(content))).encode()
            requests=[]
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append(self.path)
                    body=content if self.path==prefix+'package.tar.gz' else manifest
                    self.send_response(200);self.end_headers();self.wfile.write(body)
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
                result=subprocess.run(['bash',str(ROOT/'install.sh'),'--source','oss','--tag','musl-v0.1.0-2',
                    '--base-url',f'http://127.0.0.1:{server.server_port}','--allow-http','--no-start','--runtime-port',str(port),
                    '--dir',str(root/'instance'),'--cache-dir',str(root/'cache')],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,result.stderr)
                self.assertEqual(requests,[prefix+'manifest.json',prefix+'package.tar.gz'])
            finally:
                server.shutdown();server.server_close()
