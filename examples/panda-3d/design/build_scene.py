# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the SDF scenes of `panda-3d` (`scenes/panda.sdf`, `scenes/panda-free.sdf`).

    uv run examples/panda-3d/design/build_scene.py

The scene is the URDF tree of franka_description: link `panda_link<i>` at its rest pose (all
joints at zero; the pose of link frame i, which is the URDF/modified-DH frame), revolute joint
`panda_joint<i>` with its frame on the child link and the axis along the child z, and the GLB
of `meshes/link<i>.glb` (converted by `convert_meshes.py`) at the link origin. The models bind
`joint:panda_joint<i>` position to their joint angle, so the viewer composes the arm itself.

`panda.sdf` adds two pose-bound markers: `tcp_target` (an RGB axis triad, the trajectory
output `Traj/g`) and `tcp_actual` (an orange ball, the flange pose `Robot/TCP/g` of the
simulated arm). `panda-free.sdf` has the flange ball only (bound to `TCP/g`).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

import design as dz
import panda as pz

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "scenes"


def rpy_of(r: np.ndarray) -> tuple[float, float, float]:
    """SDF roll, pitch, yaw with R = Rz(yaw) Ry(pitch) Rx(roll)."""
    pitch = math.asin(max(-1.0, min(1.0, -r[2, 0])))
    if abs(math.cos(pitch)) > 1e-9:
        roll = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:  # gimbal lock: put everything into yaw
        roll = 0.0
        yaw = math.atan2(-r[0, 1], r[1, 1])
    return roll, pitch, yaw


def pose_text(t: np.ndarray) -> str:
    vals = [*t[:3, 3], *rpy_of(t[:3, :3])]
    return " ".join(f"{0.0 if abs(v) < 1e-12 else v:.9g}" for v in vals)


def marker_links(with_target: bool) -> list[str]:
    home = dz.target_pose(0.0)
    out = []
    if with_target:
        out += [
            '    <link name="tcp_target">',
            f"      <pose>{pose_text(home)}</pose>",
            '      <visual name="target_x">',
            "        <pose>0.03 0 0 0 0 0</pose>",
            "        <geometry><box><size>0.06 0.006 0.006</size></box></geometry>",
            "        <material><diffuse>0.9 0.15 0.15 1</diffuse></material>",
            "      </visual>",
            '      <visual name="target_y">',
            "        <pose>0 0.03 0 0 0 0</pose>",
            "        <geometry><box><size>0.006 0.06 0.006</size></box></geometry>",
            "        <material><diffuse>0.15 0.75 0.2 1</diffuse></material>",
            "      </visual>",
            '      <visual name="target_z">',
            "        <pose>0 0 0.03 0 0 0</pose>",
            "        <geometry><box><size>0.006 0.006 0.06</size></box></geometry>",
            "        <material><diffuse>0.2 0.35 0.95 1</diffuse></material>",
            "      </visual>",
            "    </link>",
        ]
    out += [
        '    <link name="tcp_actual">',
        f"      <pose>{pose_text(home)}</pose>",
        '      <visual name="actual_ball">',
        "        <geometry><sphere><radius>0.012</radius></sphere></geometry>",
        "        <material><diffuse>1.0 0.55 0.05 0.9</diffuse></material>",
        "      </visual>",
        "    </link>",
    ]
    return out


def scene(name: str, with_target: bool) -> str:
    rest = [np.eye(4), *pz.link_frames(np.zeros(pz.NJ))[:7]]
    lines = [
        '<?xml version="1.0"?>',
        "<!--",
        f"  panda-3d ({name}): the Franka Emika Panda of franka_description (Apache-2.0, meshes/LICENSE),",
        "  written by design/build_scene.py. Z-up, metres; the world frame is the robot base (panda_link0).",
        "  Link poses are the rest poses (all joints at zero) of the URDF / modified-DH link frames; every",
        "  joint frame is its child link frame and the axis is the child z, so the bound joint angle",
        "  J<i>/qout turns link i exactly as the multibond Revolute3D does. Visuals: meshes/link<i>.glb.",
        "-->",
        '<sdf version="1.9">',
        '  <model name="panda">',
        '    <link name="floor">',
        "      <pose>0 0 0 0 0 0</pose>",
        '      <visual name="floor_slab">',
        "        <pose>0.2 0 -0.006 0 0 0</pose>",
        "        <geometry><box><size>1.6 1.4 0.012</size></box></geometry>",
        "        <material><diffuse>0.62 0.64 0.67 1</diffuse></material>",
        "      </visual>",
        "    </link>",
    ]
    for i in range(8):
        lines += [
            f'    <link name="panda_link{i}">',
            f"      <pose>{pose_text(rest[i])}</pose>",
            f'      <visual name="link{i}_mesh">',
            f"        <geometry><mesh><uri>meshes/link{i}.glb</uri></mesh></geometry>",
            "      </visual>",
            "    </link>",
        ]
    lines += [
        '    <joint name="panda_base" type="fixed">',
        "      <parent>floor</parent>",
        "      <child>panda_link0</child>",
        "    </joint>",
    ]
    for i in range(1, 8):
        lines += [
            f'    <joint name="panda_joint{i}" type="revolute">',
            f"      <parent>panda_link{i - 1}</parent>",
            f"      <child>panda_link{i}</child>",
            f"      <axis><xyz>0 0 1</xyz><limit><lower>{pz.Q_MIN[i - 1]}</lower><upper>{pz.Q_MAX[i - 1]}</upper></limit></axis>",
            "    </joint>",
        ]
    lines += marker_links(with_target)
    lines += ["  </model>", "</sdf>", ""]
    return "\n".join(lines)


def main() -> None:
    SCENES.mkdir(parents=True, exist_ok=True)
    for name, target in (("panda", True), ("panda-free", False)):
        path = SCENES / f"{name}.sdf"
        path.write_text(scene(name, target), encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
