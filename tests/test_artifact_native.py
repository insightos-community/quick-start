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

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('artifact_native', Path(__file__).resolve().parents[1]/'artifacts/build_native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeArtifactTests(unittest.TestCase):
    def test_only_complete_static_x86_64_is_accepted(self):
        for static, machine in [(True, 'x86_64'), (False, 'x86_64'), (True, 'unknown')]:
            with patch.object(native, 'elf_report', return_value={'static': static, 'machine': machine}):
                if static and machine == 'x86_64':
                    self.assertTrue(native.require_static('binary')['static'])
                else:
                    with self.assertRaises(ValueError):
                        native.require_static('binary')

    def test_elf_interpreter_without_needed_is_not_static(self):
        with tempfile.NamedTemporaryFile() as f:
            with patch.object(native.subprocess, 'check_output', side_effect=[
                'Machine: Advanced Micro Devices X86-64', '', 'INTERP', 'symbol@GLIBC_2.9 symbol@GLIBC_2.28']):
                report = native.elf_report(f.name)
                self.assertFalse(report['static'])
                self.assertEqual(report['minimum_glibc'], '2.28')
