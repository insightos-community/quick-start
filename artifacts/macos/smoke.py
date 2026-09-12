"""Verify the shared native macOS Python environment with real computations."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from pathlib import Path


def main() -> None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("This probe requires native macOS arm64")
    import mujoco
    import numpy as np
    import pinocchio as pin
    from ruckig import InputParameter, OutputParameter, Result, Ruckig

    assert sys.version_info[:2] == (3, 13)
    assert np.__version__ == "2.3.5"
    model = pin.buildSampleModelManipulator()
    data = model.createData()
    q = pin.neutral(model)
    pin.forwardKinematics(model, data, q)
    mass = pin.crba(model, data, q)
    assert np.isfinite(mass).all() and np.linalg.eigvalsh(mass).min() > 0

    otg, inp, out = Ruckig(1, 0.01), InputParameter(1), OutputParameter(1)
    inp.current_position = [0.0]
    inp.current_velocity = [0.0]
    inp.current_acceleration = [0.0]
    inp.target_position = [1.0]
    inp.target_velocity = [0.0]
    inp.target_acceleration = [0.0]
    inp.max_velocity, inp.max_acceleration, inp.max_jerk = [1.0], [2.0], [4.0]
    for _ in range(2000):
        result = otg.update(inp, out)
        assert result in (Result.Working, Result.Finished)
        out.pass_to_input(inp)
        if result == Result.Finished:
            break
    assert result == Result.Finished and abs(out.new_position[0] - 1) < 1e-6

    mj_model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
      <body pos="0 0 1"><freejoint/><geom type="sphere" size=".1"/></body>
      </worldbody></mujoco>''')
    mj_data = mujoco.MjData(mj_model)
    for _ in range(100):
        mujoco.mj_step(mj_model, mj_data)
    assert np.isfinite(mj_data.qpos).all() and mj_data.qpos[2] < 1
    report = {
        "system": platform.system(), "machine": platform.machine(), "python": sys.version,
        "executable": sys.executable,
        "checks": {"pinocchio_dynamics": "passed", "ruckig_trajectory": "passed", "mujoco_physics": "passed"},
        "packages": {name: importlib.metadata.version(name) for name in ("numpy", "pin", "ruckig", "mujoco")},
        "scope": "Native dependency validation; not a complete installer or GPU qualification",
    }
    output = Path(".output/macos/dependencies.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
