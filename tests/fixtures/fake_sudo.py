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

"""PTY-test fixture. Never executes commands or requests real privileges."""
import os
from pathlib import Path
import sys
import termios

marker = Path(os.environ['SEMANTIC_TEST_AUTH_MARKER'])
args = sys.argv[1:]
if args[:1] == ['-n']:
    if not marker.exists():
        sys.exit(1)
    if args[1:] != ['-v']:
        print('FAKE_DEPENDENCY_OK', flush=True)
    sys.exit(0)
if args[:1] != ['-v'] or not all(os.isatty(fd) for fd in (0, 1, 2)):
    sys.exit(2)
original = termios.tcgetattr(0)
hidden = termios.tcgetattr(0)
hidden[3] &= ~termios.ECHO
try:
    termios.tcsetattr(0, termios.TCSANOW, hidden)
    print('[Semantic sudo] TEST PASSWORD [y/N] ', end='', flush=True)
    password = sys.stdin.readline().strip()
finally:
    termios.tcsetattr(0, termios.TCSANOW, original)
    print(flush=True)
if password != 'fake-secret-for-pty':
    sys.exit(1)
marker.touch()
