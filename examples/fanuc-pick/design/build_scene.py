# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the scenes of the fanuc-pick example (`scenes/fanuc-pick-{box,sphere,cylinder}.sdf`).

    uv run examples/fanuc-pick/design/build_scene.py

Z-up, metres; the world frame is the robot base. The robot is the URDF tree of the LR Mate
200iD/7L (ros-industrial/fanuc, BSD-3-Clause, meshes/LICENSE): every link at its rest pose
(all joints zero; this URDF has no fixed rotations), every joint frame its child link frame
with the URDF axis, so the bound joint angle `Planner/qr[i]` turns link i exactly as the
planner's kinematics do. The gripper hangs from the flange (link_6, its x axis is the tool axis):
the gripper frame G has z_G = -x_flange (up when the tool points down). Each zone's rod is a
prismatic link moving along -z_G (bound to `Rod<k>/qout`); its bellows (`bellows_<k>`, coloured by
the cup utilisation U) and lip (`lip_<k>`, coloured by the vacuum) ride on it.

The carton is drawn semi-transparent (`<diffuse>` alpha) so that the centre-of-mass marker and,
in the loose-content scenes, the sphere or cylinder inside stay visible. The scene is drawn for
the default sizes of params.py (the carton, the gripper): a model with other sizes keeps the
default visuals.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fanuc as fz  # noqa: E402
import params as P  # noqa: E402

ROOT = HERE.parent
NL = "\n"
YELLOW = "0.96 0.76 0.13 1"


def f(x: float) -> str:
    v = round(float(x), 6)
    if v == 0:
        v = 0.0
    text = repr(v)
    return text[:-2] if text.endswith(".0") else text


def pose(xyz, rpy=(0.0, 0.0, 0.0)) -> str:
    return " ".join(f(v) for v in (*xyz, *rpy))


def rpy_of(r: np.ndarray) -> tuple[float, float, float]:
    """Roll-pitch-yaw (SDF: R = Rz(y) Ry(p) Rx(r)) of a rotation matrix."""
    pitch = math.asin(max(-1.0, min(1.0, -r[2, 0])))
    roll = math.atan2(r[2, 1], r[2, 2])
    yaw = math.atan2(r[1, 0], r[0, 0])
    return roll, pitch, yaw


def visual(name: str, xyz, geom: str, rgba: str, rpy=(0.0, 0.0, 0.0)) -> str:
    return (f'      <visual name="{name}">{NL}        <pose>{pose(xyz, rpy)}</pose>{NL}'
            f"        <geometry>{geom}</geometry>{NL}"
            f"        <material><diffuse>{rgba}</diffuse></material>{NL}      </visual>{NL}")


def box(sx, sy, sz) -> str:
    return f"<box><size>{f(sx)} {f(sy)} {f(sz)}</size></box>"


def cyl(r, length) -> str:
    return f"<cylinder><radius>{f(r)}</radius><length>{f(length)}</length></cylinder>"


def sphere(r) -> str:
    return f"<sphere><radius>{f(r)}</radius></sphere>"


def link(name: str, pose_text: str, body: str) -> str:
    return f'    <link name="{name}">{NL}      <pose>{pose_text}</pose>{NL}{body}    </link>{NL}'


def joint(name: str, kind: str, parent: str, child: str, axis=None, limits=None) -> str:
    text = f'    <joint name="{name}" type="{kind}">{NL}      <parent>{parent}</parent>{NL}      <child>{child}</child>{NL}'
    if axis is not None:
        lim = "" if limits is None else f"<limit><lower>{f(limits[0])}</lower><upper>{f(limits[1])}</upper></limit>"
        text += f"      <axis><xyz>{' '.join(f(v) for v in axis)}</xyz>{lim}</axis>{NL}"
    return text + f"    </joint>{NL}"


def scene(kind: str) -> str:
    g = P.global_values()
    out = []
    # ---- cell: floor, pedestal, conveyor (pick), place table; support surface z_s = 0
    z_floor = -0.60
    body = visual("floor_slab", (0.4, 0.0, z_floor - 0.006), box(2.4, 2.0, 0.012), "0.62 0.64 0.67 1")
    body += visual("pedestal", (0.0, 0.0, z_floor / 2), box(0.36, 0.36, -z_floor - 0.002), "0.30 0.31 0.33 1")
    xp, yp, xq, yq = g["xp"], g["yp"], g["xq"], g["yq"]
    zs = g["z_s"]
    body += visual("conveyor", (xp, yp, (zs + z_floor) / 2 - 0.01), box(1.4, 0.36, zs - z_floor - 0.02), "0.40 0.42 0.45 1")
    body += visual("belt", (xp, yp, zs - 0.005), box(1.4, 0.34, 0.01), "0.16 0.17 0.18 1")
    body += visual("place_table", (xq, yq, (zs + z_floor) / 2 - 0.005), box(0.5, 0.5, zs - z_floor - 0.01), "0.78 0.79 0.80 1")
    body += visual("place_mark", (xq, yq, zs - 0.004),
                   box(g["L_p"], g["W_p"], 0.002), "0.20 0.60 0.30 1", (0, 0, g["psiq_deg"] * fz.DEG))
    out.append(link("cell", pose((0, 0, 0)), body))
    # ---- robot links at the rest pose
    names = ["base_link"] + [f"link_{i}" for i in range(1, 7)]
    frames = [np.eye(4)] + fz.link_frames(np.zeros(6))
    for n, t in zip(names, frames, strict=True):
        out.append(link(n, pose(t[:3, 3]), f'      <visual name="{n}_mesh">{NL}        <geometry><mesh><uri>meshes/{n}.glb</uri></mesh></geometry>{NL}      </visual>{NL}'))
    # ---- gripper (fixed to the flange), G at the flange, z_G = -x_flange
    t6 = frames[-1]
    r_g = t6[:3, :3] @ fz.R_FLANGE_G
    gp = t6[:3, 3]
    rpy = rpy_of(r_g)
    hb, lc, dcyl, r0 = g["h_base"], g["L_cyl"], g["D_cyl"], g["rod0"]
    body = visual("adapter", (0, 0, -hb / 2), cyl(0.045, hb), "0.55 0.57 0.60 1")
    body += visual("manifold", (0, 0, -hb + 0.006), box(2 * g["r_p"] + dcyl + 0.01, 2 * g["r_p"] + dcyl + 0.01, 0.012), "0.70 0.72 0.75 1")
    zone_xy = []
    for dx, dy in P.ZONE_DIRS:
        la = g["lay_deg"] * fz.DEG
        zone_xy.append((g["r_p"] * (dx * math.cos(la) - dy * math.sin(la)), g["r_p"] * (dx * math.sin(la) + dy * math.cos(la))))
    for k, (x, y) in enumerate(zone_xy, start=1):
        body += visual(f"cylinder_{k}", (x, y, -hb - lc / 2), cyl(dcyl / 2, lc), "0.80 0.82 0.85 1")
    out.append(link("gripper", pose(gp, rpy), body))
    # ---- rods (prismatic along -z_G): rod link frame = G orientation at the retracted rod tip
    z_tip = -(hb + lc + r0)
    stroke, L0, dl = g["stroke"], g["L0"], g["D_lip"]
    for k, (x, y) in enumerate(zone_xy, start=1):
        tip = gp + r_g @ np.array([x, y, z_tip])
        body = visual(f"rod_{k}", (0, 0, (r0 + stroke) / 2), cyl(0.003, r0 + stroke), "0.85 0.86 0.88 1")
        body += visual(f"holder_{k}", (0, 0, -0.004), cyl(0.008, 0.008), "0.25 0.25 0.27 1")
        body += visual(f"bellows_{k}", (0, 0, -0.008 - (L0 - 0.012) / 2), cyl(dl / 2 - 0.003, L0 - 0.012), "0.10 0.10 0.11 1")
        body += visual(f"lip_{k}", (0, 0, -L0 + 0.002), cyl(dl / 2, 0.004), "0.15 0.15 0.16 1")
        out.append(link(f"rod_link_{k}", pose(tip, rpy), body))
    # ---- the parcel: box at the carton centre (bound to BoxPose), CoM marker (bound to Pose)
    pz = zs + g["H_p"] / 2
    alpha = "0.35" if kind != "box" else "0.55"
    body = visual("carton", (0, 0, 0), box(g["L_p"], g["W_p"], g["H_p"]), f"0.76 0.56 0.33 {alpha}")
    body += visual("tape", (0, 0, g["H_p"] / 2 + 0.0005), box(g["L_p"] * 0.995, 0.05, 0.001), "0.88 0.80 0.62 0.8")
    out.append(link("parcel", pose((xp, yp, pz), (0, 0, g["psip_deg"] * fz.DEG)), body))
    out.append(link("com", pose((xp, yp, pz), (0, 0, g["psip_deg"] * fz.DEG)),
                    visual("com_marker", (0, 0, 0), sphere(0.012), "0.85 0.10 0.10 1")))
    if kind == "sphere":
        r = g["r_s"]
        out.append(link("content", pose((xp, yp, zs + g["wall"] + r)),
                        visual("ball", (0, 0, 0), sphere(r), "0.15 0.35 0.80 1")
                        + visual("ball_mark", (0, 0, r * 0.75), sphere(r * 0.35), "0.95 0.95 0.95 1")))
    elif kind == "cylinder":
        r, length = g["r_c"], g["l_c"]
        out.append(link("content", pose((xp, yp, zs + g["wall"] + r), (0, math.pi / 2, 0)),
                        visual("roll", (0, 0, 0), cyl(r, length), "0.15 0.35 0.80 1")
                        + visual("roll_stripe", (0, 0, 0), box(2 * r + 0.002, 0.01, length * 0.98), "0.95 0.95 0.95 1")))
    # ---- joints
    out.append(joint("cell_base", "fixed", "cell", "base_link"))
    for i in range(6):
        out.append(joint(f"joint_{i + 1}", "revolute", names[i], names[i + 1], fz.JOINT_AXIS[i],
                         (float(fz.URDF_Q_MIN[i]), float(fz.URDF_Q_MAX[i]))))
    out.append(joint("flange_gripper", "fixed", "link_6", "gripper"))
    for k in range(1, 6):
        out.append(joint(f"rod_{k}", "prismatic", "gripper", f"rod_link_{k}", (0, 0, -1), (-0.002, stroke + 0.002)))
    head = f'''<?xml version="1.0"?>
<!--
  fanuc-pick ({kind}): written by design/build_scene.py. Z-up, metres; the world frame is the robot
  base. Robot: FANUC LR Mate 200iD/7L geometry (ros-industrial/fanuc d8f42bd7, BSD-3-Clause,
  meshes/LICENSE) standing in for the cell's LR-10iA/10; links at their rest poses, joint frames =
  child link frames with the URDF axes (bound to Planner/qr[i]). The gripper hangs from link_6
  (z_G = -x_flange); rod_<k> are prismatic along -z_G (Rod<k>/qout). The carton is semi-transparent
  (diffuse alpha {alpha}); `com` marks the centre of mass{"" if kind == "box" else ", `content` is the loose " + kind}.
-->
<sdf version="1.9">
  <model name="fanuc_pick">
'''
    return head + "".join(out) + "  </model>" + NL + "</sdf>" + NL


def main() -> int:
    for kind in ("box", "sphere", "cylinder"):
        path = ROOT / "scenes" / f"fanuc-pick-{kind}.sdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(scene(kind), encoding="utf-8", newline=NL)
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
