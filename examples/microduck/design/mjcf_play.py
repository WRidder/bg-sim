# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "mujoco>=3.2"]
# ///
"""The play hinges of microduck_rl's backlash robot, as MuJoCo compiles them: design/play_data.json.

    uv run examples/microduck/design/mjcf_play.py <microduck_rl>/src/mjlab_microduck/robot/microduck

Reads (as data) `robot_allcollisions_backlash.xml` of github.com/pollen-robotics/microduck_rl at
0daab160d3fb1c2cbaba16a4a19052f36709dd9e, the robot of the VelStand backlash tasks (add_backlash.py:
a `passive_<joint>_backlash` hinge after every servo joint), sets the servo joints' armature to
BAM's XL330 value and zeroes their damping and frictionloss, as bam.mjlab.BamActuator.edit_spec
does before the model is compiled, and stores per joint the play hinge's `dof_invweight0` (the
diagonal approximation MuJoCo builds its constraint regulariser from), with the class values of
the play hinge (range, armature, damping, solreflimit, solimplimit) for the record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = ("github.com/pollen-robotics/microduck_rl@0daab160d3fb1c2cbaba16a4a19052f36709dd9e:"
          "src/mjlab_microduck/robot/microduck/robot_allcollisions_backlash.xml")
BAM_ARMATURE = 0.0018077432831600838  # xl330.BAM["armature"]


def main() -> int:
    spec = mujoco.MjSpec.from_file(str(Path(sys.argv[1]) / "robot_allcollisions_backlash.xml"))
    for j in spec.joints:
        if j.name and not j.name.startswith("passive_") and j.type == mujoco.mjtJoint.mjJNT_HINGE:
            j.armature = BAM_ARMATURE
            j.damping = np.zeros(3) if np.ndim(j.damping) else 0.0
            j.frictionloss = 0.0
    m = spec.compile()
    joints = {}
    for jid in range(m.njnt):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, jid)
        if not (name and name.startswith("passive_") and name.endswith("_backlash")):
            continue
        dof = int(m.jnt_dofadr[jid])
        joints[name[len("passive_"):-len("_backlash")]] = {
            "invweight0": float(m.dof_invweight0[dof]),
            "armature": float(m.dof_armature[dof]),
            "damping": float(m.dof_damping[dof]),
            "frictionloss": float(m.dof_frictionloss[dof]),
            "range": [float(v) for v in m.jnt_range[jid]],
            "solreflimit": [float(v) for v in m.jnt_solref[jid]],
            "solimplimit": [float(v) for v in m.jnt_solimp[jid]],
        }
    out = {"source": SOURCE, "mujoco": mujoco.__version__, "servo_armature": BAM_ARMATURE, "joints": joints}
    (HERE / "play_data.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    for k, v in joints.items():
        print(f"{k:16s} invweight0 {v['invweight0']:9.3f}  range {v['range']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
