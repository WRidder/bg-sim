# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Extract the microduck rigid-body data from the microduck_rl MJCF into design/robot_data.json.

    uv run examples/microduck/design/extract_mjcf.py <microduck_rl>/src/mjlab_microduck/robot/microduck [<mesh dir>]

Reads (as data) `robot_groundcontact.xml` (onshape-to-robot export: bodies, joints, inertials,
the two sole collision geoms) and `assets/sole_left.stl`, `assets/sole_right.stl`, from
github.com/pollen-robotics/microduck_rl at 0daab160d3fb1c2cbaba16a4a19052f36709dd9e (Apache-2.0).
The sole meshes are reduced to four contact points per foot: the bottom vertices (in the STAND
pose) that are extreme along the four diagonals of the sole. The other collision meshes of the
trunk, the head and the shins (np_f970, top_head_shell, jaw, bottom_head_shell, leg; from the same
commit's `assets/`, given as <mesh dir> when the clone has only the soles) are reduced to bumper
points for falls (`BUMPER_BODIES`).
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = "github.com/pollen-robotics/microduck_rl@0daab160d3fb1c2cbaba16a4a19052f36709dd9e:src/mjlab_microduck/robot/microduck/robot_groundcontact.xml"


def floats(s: str) -> list[float]:
    return [float(v) for v in s.split()]


def quat_rot(q) -> np.ndarray:
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def read_stl(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    n = int(np.frombuffer(raw[80:84], "<u4")[0])
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = np.frombuffer(raw[84:84 + n * rec.itemsize], rec)
    return np.unique(tri["v"].reshape(-1, 3).astype(float), axis=0)


def walk(elem, parent, out):
    for body in elem.findall("body"):
        joint = body.find("joint")
        inertial = body.find("inertial")
        fi = floats(inertial.get("fullinertia"))
        rec = {
            "name": body.get("name"), "parent": parent,
            "pos": floats(body.get("pos", "0 0 0")), "quat": floats(body.get("quat", "1 0 0 0")),
            "mass": float(inertial.get("mass")), "com": floats(inertial.get("pos")),
            # MuJoCo fullinertia order: Ixx Iyy Izz Ixy Ixz Iyz
            "inertia": [[fi[0], fi[3], fi[4]], [fi[3], fi[1], fi[5]], [fi[4], fi[5], fi[2]]],
        }
        if joint is not None and joint.tag == "joint":
            rec["joint"] = joint.get("name")
            rec["axis"] = floats(joint.get("axis", "0 0 1"))
            rec["range"] = floats(joint.get("range"))
        for g in body.findall("geom"):
            if g.get("name", "").endswith("_foot_collision"):
                rec["sole"] = {"mesh": g.get("mesh"), "pos": floats(g.get("pos")), "quat": floats(g.get("quat"))}
            elif g.get("class") == "collision":
                rec.setdefault("collision", []).append(
                    {"mesh": g.get("mesh"), "pos": floats(g.get("pos")), "quat": floats(g.get("quat"))})
        out.append(rec)
        walk(body, rec["name"], out)


HOME = {  # microduck_rl HOME_FRAME = microduck DEFAULT_POSITION (STAND keyframe)
    "left_hip_yaw": 0.0, "left_hip_roll": -0.0873, "left_hip_pitch": -0.4579, "left_knee": -0.0049,
    "left_ankle": 0.4530, "neck_pitch": 0.3491, "head_pitch": 0.3491, "head_yaw": 0.0, "head_roll": 0.0,
    "right_hip_yaw": 0.0, "right_hip_roll": 0.0873, "right_hip_pitch": 0.4579, "right_knee": 0.0049,
    "right_ankle": -0.4530,
}


def stand_fk(bodies):
    """World (trunk frame) rotation and origin of every body at HOME, trunk at the origin."""
    out = {}
    for b in bodies:
        r = quat_rot(b["quat"])
        p = np.array(b["pos"])
        if "joint" in b:
            q = HOME[b["joint"]]
            c, s_ = np.cos(q), np.sin(q)
            r = r @ np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
        if b["parent"] is None:
            out[b["name"]] = (np.eye(3), np.zeros(3))
        else:
            rp, pp = out[b["parent"]]
            out[b["name"]] = (rp @ r, pp + rp @ p)
    return out


# Bumper points: the bodies other than the feet that the microduck_rl ground-contact model lets
# touch the floor (its collision geoms), each reduced to the vertices of its collision meshes that
# are extreme along the eight diagonals of the body frame (the trunk and the head) or along the
# trunk's forward and backward axis (the legs: the knee in front, the calf behind). Hip collision
# meshes are left out: they sit between the trunk and the legs, which reach the floor first.
BUMPER_BODIES = {"trunk_base": "corners", "jaw_soft": "corners", "leg": "front_back", "leg_2": "front_back"}


def bumper_points(local: np.ndarray, rw: np.ndarray, kind: str) -> list[list[float]]:
    """Extreme vertices of a body's collision meshes (`local`, body frame) for `kind`."""
    if kind == "corners":
        dirs = [np.array([sx, sy, sz], float) for sx in (1, -1) for sy in (1, -1) for sz in (1, -1)]
        # corners of the box the body spans in the stand pose, expressed in the trunk frame
        dirs = [rw.T @ d for d in dirs]
    else:
        dirs = [rw.T @ np.array([1.0, 0, 0]), rw.T @ np.array([-1.0, 0, 0])]
    pts = []
    for d in dirs:
        k = int(np.argmax(local @ d))
        if local[k].tolist() not in pts:
            pts.append(local[k].tolist())
    return pts


def main() -> int:
    src = Path(sys.argv[1])
    meshes = Path(sys.argv[2]) if len(sys.argv) > 2 else src / "assets"
    root = ET.parse(src / "robot_groundcontact.xml").getroot()
    bodies: list[dict] = []
    walk(root.find("worldbody"), None, bodies)
    world = stand_fk(bodies)
    for b in bodies:
        if "sole" in b:
            verts = read_stl(src / "assets" / f"{b['sole']['mesh']}.stl")
            r = quat_rot(b["sole"]["quat"])
            local = verts @ r.T + np.array(b["sole"]["pos"])  # in the ankle body frame
            rw, pw = world[b["name"]]
            wv = local @ rw.T + pw
            bottom = wv[:, 2] < wv[:, 2].min() + 0.5e-3
            pts = []
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
                k = int(np.argmax(np.where(bottom, sx * wv[:, 0] + sy * wv[:, 1], -np.inf)))
                pts.append(local[k].tolist())
            b["sole"]["points"] = pts
            b["sole"]["bottom_z_stand"] = float(wv[:, 2].min())
        if b["name"] in BUMPER_BODIES and b.get("collision"):
            local = np.concatenate([read_stl(meshes / f"{g['mesh']}.stl") @ quat_rot(g["quat"]).T + np.array(g["pos"])
                                    for g in b["collision"]])
            b["bumpers"] = bumper_points(local, world[b["name"]][0], BUMPER_BODIES[b["name"]])
    data = {"source": SOURCE, "bodies": bodies}
    (HERE / "robot_data.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(bodies)} bodies, total mass {sum(b['mass'] for b in bodies):.4f} kg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
