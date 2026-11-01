# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Write the SDF scene of `humanoid-dual-arm` (`scenes/humanoid.sdf`).

    uv run examples/humanoid-dual-arm/design/build_scene.py

Z-up, metres; the robot faces +X and its left arm is on +Y (world = (page z, page x, page y + 1)).
Two torsos: the stacked-offset robot at the origin and the ideal SRS pair 1 m to its right
(world y - 1). Every arm is a URDF-style tree: link `<arm>_link<i>` is the child frame of joint
i at rest (all joints zero), revolute joint `<arm>_joint<i>` turns it about its own z (the bound
angle is the multibond joint angle, so the viewer composes the arm). Arms: `L`, `R` (stacked),
`GL`, `GR` (ideal). Free links bound by pose: `box` (the held object), `box_target` (the
commanded pose, translucent) and `ghost_box` (the commanded pose beside the ideal pair).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

import humanoid as dz
import srs

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "scenes"

COLORS = {"L": "0.37 0.78 1 1", "R": "1 0.70 0.37 1", "GL": "0.50 0.88 0.66 1", "GR": "0.50 0.88 0.66 1"}
HUB = "0.17 0.21 0.25 1"
TORSO = "0.24 0.28 0.33 1"


def rpy_of(r: np.ndarray) -> tuple[float, float, float]:
    """SDF roll, pitch, yaw with R = Rz(yaw) Ry(pitch) Rx(roll)."""
    pitch = math.asin(max(-1.0, min(1.0, -r[2, 0])))
    if abs(math.cos(pitch)) > 1e-9:
        roll = math.atan2(r[2, 1], r[2, 2])
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:
        roll = 0.0
        yaw = math.atan2(-r[0, 1], r[1, 1])
    return roll, pitch, yaw


def pose_text(t: np.ndarray) -> str:
    vals = [*t[:3, 3], *rpy_of(t[:3, :3])]
    return " ".join(f"{0.0 if abs(v) < 1e-12 else v:.9g}" for v in vals)


def z_to(v: np.ndarray) -> np.ndarray:
    """A rotation taking z to the direction of v."""
    z = v / np.linalg.norm(v)
    ref = np.array([1.0, 0.0, 0.0]) if abs(z[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = np.cross(ref, z)
    x /= np.linalg.norm(x)
    return np.column_stack([x, np.cross(z, x), z])


def visual(name, t, geometry, color) -> list[str]:
    return [
        f'      <visual name="{name}">',
        f"        <pose>{pose_text(t)}</pose>",
        f"        <geometry>{geometry}</geometry>",
        f"        <material><diffuse>{color}</diffuse></material>",
        "      </visual>",
    ]


def cyl(r, length) -> str:
    return f"<cylinder><radius>{r:.4g}</radius><length>{length:.6g}</length></cylinder>"


def box(sx, sy, sz) -> str:
    return f"<box><size>{sx:.4g} {sy:.4g} {sz:.4g}</size></box>"


def sphere(r) -> str:
    return f"<sphere><radius>{r:.4g}</radius></sphere>"


def torso(name: str, dy: float) -> list[str]:
    z0 = srs.Z0
    out = [f'    <link name="{name}">', f"      <pose>0 {dy:g} 0 0 0 0</pose>"]
    out += visual(f"{name}_pedestal", srs.tr([0, 0, (z0 - 0.3) / 2]), cyl(0.06, z0 - 0.3), HUB)
    out += visual(f"{name}_body", srs.tr([0, 0, z0 - 0.01]), box(0.18, 0.30, 0.58), TORSO)
    out += visual(f"{name}_shoulders", srs.hom(srs.rot("x", math.pi / 2), [0, 0, z0 + 0.25]), cyl(0.025, 0.40), TORSO)
    out += visual(f"{name}_neck", srs.tr([0, 0, z0 + 0.32]), cyl(0.015, 0.08), TORSO)
    out += visual(f"{name}_head", srs.tr([0, 0, z0 + 0.43]), sphere(0.075), "0.34 0.40 0.48 1")
    out += ["    </link>"]
    return out


def arm(prefix: str, s: int, ideal: bool, parent: str, dy: float) -> list[str]:
    f = dz.chain_frames(s, ideal, dy)
    fk = dz.chain_fk(np.zeros(srs.NJ), s, ideal, dy)
    color = COLORS[prefix]
    out = []
    for i in range(srs.NJ):
        k = i + 1
        out += [f'    <link name="{prefix}_link{k}">', f"      <pose>{pose_text(fk['W'][i])}</pose>"]
        r_hub, l_hub = (0.034, 0.075) if i < 4 else (0.027, 0.058)
        out += visual(f"{prefix}_hub{k}", np.eye(4), cyl(r_hub, l_hub), HUB)
        nxt = f["LN"][i + 1][:3, 3] if i < 6 else f["LH"][:3, 3]
        if np.linalg.norm(nxt) > 1e-9:
            seg = srs.hom(z_to(nxt), nxt / 2)
            out += visual(f"{prefix}_seg{k}", seg, cyl(0.02 if i < 4 else 0.017, float(np.linalg.norm(nxt))), color)
        if i == 6:  # the hand: a palm and two fingers in the hand frame (x up, z toward the box)
            h = f["LH"]
            out += visual(f"{prefix}_palm", h @ srs.tr([0, 0, -0.012]), box(0.07, 0.03, 0.024), color)
            for j, side in enumerate((1, -1)):
                out += visual(f"{prefix}_finger{j + 1}", h @ srs.tr([side * 0.028, 0, 0.012]), box(0.012, 0.03, 0.03), HUB)
        out += ["    </link>"]
    for i in range(srs.NJ):
        k = i + 1
        lo, hi = srs.LO[i] * srs.D, srs.HI[i] * srs.D
        out += [
            f'    <joint name="{prefix}_joint{k}" type="revolute">',
            f"      <parent>{parent if i == 0 else f'{prefix}_link{i}'}</parent>",
            f"      <child>{prefix}_link{k}</child>",
            f"      <axis><xyz>0 0 1</xyz><limit><lower>{lo:.9g}</lower><upper>{hi:.9g}</upper></limit></axis>",
            "    </joint>",
        ]
    return out


def object_link(name: str, t: np.ndarray, size, color) -> list[str]:
    out = [f'    <link name="{name}">', f"      <pose>{pose_text(t)}</pose>"]
    out += visual(f"{name}_shape", np.eye(4), box(*size), color)
    return out + ["    </link>"]


def scene() -> str:
    p0, r0 = dz.OBJ_START
    t_obj = dz.pw() @ srs.hom(srs.obj_rotation(r0), p0)
    shift = srs.tr([0.0, dz.GHOST_DY, 0.0])
    lines = [
        '<?xml version="1.0"?>',
        "<!--",
        "  humanoid-dual-arm: the humanoid torso with two stacked 7-DOF SRS arms (left, blue; right, orange)",
        "  and the ideal SRS pair (green) 1 m to its right. Written by design/build_scene.py. Z-up, metres,",
        "  the robot faces +X, its left arm on +Y. Link <arm>_link<i> is the child frame of joint i at rest",
        "  (all joints zero); joint <arm>_joint<i> turns it about its own z by the bound joint angle.",
        "-->",
        '<sdf version="1.9">',
        '  <model name="humanoid">',
        '    <link name="floor">',
        "      <pose>0 0 0 0 0 0</pose>",
    ]
    lines += visual("floor_slab", srs.tr([0.2, -0.5, -0.006]), box(2.0, 2.6, 0.012), "0.55 0.57 0.6 1")
    lines += ["    </link>"]
    lines += torso("torso", 0.0) + torso("ghost_torso", dz.GHOST_DY)
    for name in ("torso", "ghost_torso"):
        lines += [f'    <joint name="{name}_mount" type="fixed">', "      <parent>floor</parent>", f"      <child>{name}</child>", "    </joint>"]
    lines += arm("L", 1, False, "torso", 0.0) + arm("R", -1, False, "torso", 0.0)
    lines += arm("GL", 1, True, "ghost_torso", dz.GHOST_DY) + arm("GR", -1, True, "ghost_torso", dz.GHOST_DY)
    lines += object_link("box", t_obj, srs.BOX, "0.79 0.64 1 1")
    lines += object_link("box_target", t_obj, srs.BOX + 0.012, "0.79 0.64 1 0.22")
    lines += object_link("ghost_box", shift @ t_obj, srs.BOX, "0.79 0.64 1 0.85")
    lines += ["  </model>", "</sdf>", ""]
    return "\n".join(lines)


def main() -> None:
    SCENES.mkdir(parents=True, exist_ok=True)
    path = SCENES / "humanoid.sdf"
    path.write_text(scene(), encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
