"""The 3D scenes of the microduck robot models and their bindings (written by build_model.py).

    scenes/microduck.sdf        the robot on the floor (microduck-stand, microduck-policy, microduck-policy-backlash)
    scenes/microduck-hang.sdf   the robot held by the trunk 0.3 m above the floor (microduck-hang)

One SDF link per body of design/robot_data.json, named after the body, carrying the GLB of
`meshes/<body>.glb` (Pollen Robotics' CAD meshes in that body's frame, CC BY-NC-SA 4.0, written
by design/build_visuals.py) at the link origin. The link poses in the file are the STAND pose
(HOME) with the trunk where the model starts it; in a run every link follows the world pose of
its body frame, the pose band of design/robot.py: `<joint>_link/W/g` (W of the body's Link
instance, W_b = W_P o T_Pb o joint pose) and, for the trunk, `Free/pose` (floating) or
`TrunkPose/g` (held). Floor: 6 x 6 tiles of 0.1 m.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

import robot as rb

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "scenes"
FLOOR = "scenes/microduck.sdf"
HANG = "scenes/microduck-hang.sdf"
SCENE_OF = {  # model -> scene file
    "microduck-stand": FLOOR,
    "microduck-policy": FLOOR,
    "microduck-policy-backlash": FLOOR,
    "microduck-hang": HANG,
}
TILE = 0.1  # m
TILES = 6  # per side


def rpy_of(r: np.ndarray) -> tuple[float, float, float]:
    """SDF roll, pitch, yaw with R = Rz(yaw) Ry(pitch) Rx(roll)."""
    pitch = math.asin(max(-1.0, min(1.0, -r[2, 0])))
    if abs(math.cos(pitch)) > 1e-9:
        return math.atan2(r[2, 1], r[2, 2]), pitch, math.atan2(r[1, 0], r[0, 0])
    return 0.0, pitch, math.atan2(-r[0, 1], r[1, 1])


def pose_text(t: np.ndarray) -> str:
    vals = [*t[:3, 3], *rpy_of(t[:3, :3])]
    return " ".join(f"{0.0 if abs(v) < 1e-12 else v:.9g}" for v in vals)


def trunk_start(held: bool) -> np.ndarray:
    z = rb.HANG_HEIGHT if held else rb.stand_height(rb.HOME)
    return rb.hom(np.eye(3), [0.0, 0.0, z])


def sdf(held: bool) -> str:
    frames = rb.fk(rb.HOME, trunk_start(held))
    what = ("held by the trunk 0.3 m above the floor (microduck-hang)" if held
            else "on the floor (microduck-stand, microduck-policy, microduck-policy-backlash)")
    lines = [
        '<?xml version="1.0"?>',
        "<!--",
        f"  microduck, {what}. Written by design/build_model.py (design/scene.py).",
        "  Z-up, metres; x forward, y to the left. One link per body of design/robot_data.json at the STAND",
        "  pose; in a run each link follows the world pose of its body frame (bindings in the model).",
        "  Meshes: meshes/<body>.glb, Pollen Robotics' microduck CAD (microduck_rl 0daab16), decimated,",
        "  CC BY-NC-SA 4.0, non-commercial: see meshes/LICENSE and meshes/NOTICE.",
        "-->",
        '<sdf version="1.9">',
        '  <model name="microduck">',
        '    <link name="floor">',
        "      <pose>0 0 0 0 0 0</pose>",
    ]
    half = TILES * TILE / 2
    for i in range(TILES):
        for j in range(TILES):
            x = -half + (i + 0.5) * TILE + 0.05
            y = -half + (j + 0.5) * TILE
            shade = "0.82 0.83 0.80 1" if (i + j) % 2 == 0 else "0.70 0.72 0.69 1"
            lines += [
                f'      <visual name="tile_{i:02d}_{j:02d}">',
                f"        <pose>{x:.4g} {y:.4g} -0.003 0 0 0</pose>",
                f"        <geometry><box><size>{TILE} {TILE} 0.006</size></box></geometry>",
                f"        <material><diffuse>{shade}</diffuse></material>",
                "      </visual>",
            ]
    lines.append("    </link>")
    for b in rb.BODIES:
        lines += [
            f'    <link name="{b["name"]}">',
            f"      <pose>{pose_text(frames[b['name']])}</pose>",
            f'      <visual name="{b["name"]}_mesh">',
            f"        <geometry><mesh><uri>meshes/{b['name']}.glb</uri></mesh></geometry>",
            "      </visual>",
            "    </link>",
        ]
    lines += ["  </model>", "</sdf>", ""]
    return "\n".join(lines)


def bindings(held: bool) -> list[dict]:
    out = []
    for b in rb.BODIES:
        if b["parent"] is None:
            sig = "TrunkPose/g" if held else "Free/pose"
        else:
            sig = rb.node_names(b)["pose"]
        out.append({"target": f"link:{b['name']}", "property": "pose", "signal": [f"{sig}[{k}]" for k in range(1, 8)]})
    return out


def write_scenes() -> None:
    SCENES.mkdir(parents=True, exist_ok=True)
    for path, held in ((FLOOR, False), (HANG, True)):
        (ROOT / path).write_text(sdf(held), encoding="utf-8", newline="\n")


def with_scene(doc: dict) -> dict:
    """The model with its scene and the pose bindings of every link (robot models only)."""
    path = SCENE_OF.get(doc["name"])
    if path is None:
        return doc
    doc["scene"] = {"file": path}
    doc["bindings"] = bindings(path == HANG)
    return doc
