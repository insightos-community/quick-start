#!/usr/bin/env python3
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""Probe EGL in a disposable process, before the application imports MuJoCo."""
import ctypes
import json
from pathlib import Path
import sys


def probe(list_devices=False):
    import mujoco
    import numpy as np
    from mujoco.egl import egl_ext as egl

    if list_devices:
        return {"devices": len(egl.eglQueryDevicesEXT())}
    model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <light pos="0 0 3"/><camera name="top" pos="0 0 3"/>
      <geom type="sphere" size="0.3" rgba="1 0.1 0.1 1"/>
    </worldbody></mujoco>''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    with mujoco.Renderer(model, height=64, width=64) as renderer:
        renderer.update_scene(data, camera="top")
        rgb = renderer.render().copy()
        renderer.enable_depth_rendering()
        depth = renderer.render().copy()
        get_string = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_uint)(
            egl.eglGetProcAddress("glGetString"))
        info = {name: get_string(value).decode() for name, value in
                (("vendor", 0x1F00), ("renderer", 0x1F01), ("version", 0x1F02))}
    if rgb.std() < 1 or not np.isfinite(depth).all():
        raise RuntimeError("RGB/depth rendering failed")
    if abs(float(depth[32, 32]) - 2.7) > 0.03:
        raise RuntimeError(f"Unexpected sphere depth: {depth[32, 32]}")
    info["software"] = any(name in info["renderer"].lower() for name in
                           ("llvmpipe", "softpipe", "swrast", "software rasterizer"))
    info["libraries"] = sorted({line.split()[-1] for line in
                                Path("/proc/self/maps").read_text().splitlines()
                                if "/" in line and ".so" in line})
    info["depth_center"] = float(depth[32, 32])
    return info


if __name__ == "__main__":
    try:
        print(json.dumps(probe("--list" in sys.argv)))
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
