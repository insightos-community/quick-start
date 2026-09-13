#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Inspect actual dyld images after loading the installed native dependency set."""
import ctypes
import json
from pathlib import Path
import sqlite3
import ssl
import sys

import charset_normalizer
import coal
import glfw
import httptools
import mujoco
import numpy
import PIL.Image
import pinocchio
import pydantic_core
import ruckig
import uvloop
import watchfiles
import yaml

root=Path(sys.argv[1]).resolve()
lib=ctypes.CDLL(None)
lib._dyld_image_count.restype=ctypes.c_uint32
lib._dyld_get_image_name.argtypes=[ctypes.c_uint32]
lib._dyld_get_image_name.restype=ctypes.c_char_p
local=[]
system=[]
for i in range(lib._dyld_image_count()):
    value=lib._dyld_get_image_name(i).decode()
    path=Path(value).resolve()
    if path.is_relative_to(root):
        local.append(path.relative_to(root).as_posix())
    elif value.startswith(('/usr/lib/', '/System/Library/', '/System/Volumes/Preboot/Cryptexes/OS/usr/lib/',
                           '/System/Volumes/Preboot/Cryptexes/OS/System/Library/')):
        system.append(value)
    else:
        raise RuntimeError('Loaded library outside the installation/system: '+value)
report={'bundled_images':sorted(set(local)), 'system_image_count':len(system), 'external_images':[]}
assert local
Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
