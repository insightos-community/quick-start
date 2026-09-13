#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Repair upstream Mach-O search paths after verifying original wheel hashes."""
import base64
import csv
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relocate(wheelhouse, lock_text):
    report = {}
    for wheel in sorted(wheelhouse.glob('*.whl')):
        original_hash = sha(wheel)
        replacements = {}
        changes = {}
        with tempfile.TemporaryDirectory(prefix='semantic-wheel-') as tmp, zipfile.ZipFile(wheel) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                data = archive.read(entry)
                if data[:4] not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
                    continue
                # Retain layout for calculating relative library paths, but do
                # not extract archive-provided paths outside this scratch root.
                relative = Path(entry.filename)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe wheel path: '+entry.filename)
                path = Path(tmp)/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod((entry.external_attr >> 16) & 0o777 or 0o644)
                load = subprocess.check_output(['otool', '-l', str(path)], text=True)
                rpaths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', load)
                identities = subprocess.check_output(['otool', '-D', str(path)], text=True).splitlines()[1:]
                commands = []
                for identity in set(x.strip() for x in identities):
                    if identity.startswith('/'):
                        commands += ['-id', '@rpath/'+path.name]
                removed = [r for r in dict.fromkeys(rpaths)
                           if (r.startswith('/') and not r.startswith(('/usr/lib/', '/System/Library/')))
                           or '$ORIGIN' in r]
                for rpath in removed:
                    commands += ['-delete_rpath', rpath]
                if relative.parts[0] == 'cmeel.prefix':
                    local = '@loader_path/'+os.path.relpath(Path(tmp)/'cmeel.prefix/lib', path.parent)
                    if local not in rpaths:
                        commands += ['-add_rpath', local]
                if not commands:
                    continue
                subprocess.run(['install_name_tool', *commands, str(path)], check=True)
                subprocess.run(['codesign', '--force', '--sign', '-', str(path)], check=True)
                subprocess.run(['codesign', '--verify', str(path)], check=True)
                replacements[entry.filename] = path.read_bytes()
                changes[entry.filename] = commands
            if not replacements:
                continue
            if original_hash not in lock_text:
                raise ValueError('Modified wheel is not pinned by the upstream lock: '+wheel.name)
            records = [n for n in archive.namelist() if n.endswith('.dist-info/RECORD')]
            if len(records) != 1 or any(n.endswith(('.dist-info/RECORD.jws', '.dist-info/RECORD.p7s')) for n in archive.namelist()):
                raise ValueError('Unsupported wheel RECORD/signature: '+wheel.name)
            record = records[0]
            output = io.StringIO(newline='')
            writer = csv.writer(output, lineterminator='\n')
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                if entry.filename == record:
                    writer.writerow([record, '', ''])
                    continue
                data = replacements.get(entry.filename)
                if data is None:
                    data = archive.read(entry)
                encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
                writer.writerow([entry.filename, 'sha256='+encoded, len(data)])
            replacements[record] = output.getvalue().encode()
            result = wheel.with_suffix('.relocated')
            with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED) as rebuilt:
                for entry in archive.infolist():
                    rebuilt.writestr(entry, replacements.get(entry.filename, archive.read(entry)))
        result.replace(wheel)
        relocated_hash = sha(wheel)
        lock_text = lock_text.replace(original_hash, relocated_hash)
        report[wheel.name] = {'upstream_sha256': original_hash, 'relocated_sha256': relocated_hash, 'changes': changes}
    return lock_text, report
