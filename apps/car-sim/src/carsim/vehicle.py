"""The drawn car: the example's GLB meshes placed by the FMU's poses.

The meshes (examples/cars/meshes, written by examples/cars/design/make_scenes.py) are those of
the bg-sim scenes: the body in the chassis frame (x forward, y left, z up, the origin at the sprung
CG), the wheel and the hub in the carrier frame of each corner (x forward, y down, z the axle).
The FMU gives the chassis pose and, per corner, the carrier pose (steer and suspension travel
included) and the wheel's spin angle about the carrier z: wheel = carrier * Rz(spin).

The suspension rods (wishbones, push rods or dampers, tie rods, drive shafts) join the chassis to
a carrier, so they are in neither mesh: ``<vehicle>_suspension.json`` gives each rod's inner end in
the chassis frame and its outer end in the carrier frame, and every frame each rod is laid from
one end to the other (a unit cylinder, scaled to the length), so it stays attached through the
suspension travel and the steering.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path

import numpy as np
from panda3d.core import LMatrix4f, NodePath

from .fmu import CORNERS, quat_matrix

MESHES = Path(__file__).resolve().parents[4] / "examples" / "cars" / "meshes"
# the eye of the cockpit camera in the chassis frame (x forward, y left, z up), m
EYES = {"racecar": (0.34, 0.0, 0.47), "buggy": (-0.20, 0.30, 0.60)}


def load_glb(path: Path) -> NodePath:
    import gltf

    with contextlib.redirect_stdout(io.StringIO()):   # the loader prints a warning per untextured primitive
        node = gltf.load_model(str(path), gltf_settings=gltf.GltfSettings(skip_axis_conversion=True))
    return NodePath(node)


def pose_matrix(R: np.ndarray, p) -> LMatrix4f:
    """The node transform (local -> world) as a Panda row-vector matrix."""
    return LMatrix4f(R[0, 0], R[1, 0], R[2, 0], 0.0,
                     R[0, 1], R[1, 1], R[2, 1], 0.0,
                     R[0, 2], R[1, 2], R[2, 2], 0.0,
                     p[0], p[1], p[2], 1.0)


def rod_mesh(name: str, rgb, sections: int = 10) -> NodePath:
    """A closed cylinder of radius 1 from z = 0 to z = 1 in the colour rgb (0..255)."""
    from .world import mesh

    ang = np.linspace(0.0, 2.0 * math.pi, sections, endpoint=False)
    ring = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(sections)])
    side_n = ring.copy()
    v = [ring, ring + [0, 0, 1], np.zeros((1, 3)), ring, [[0, 0, 1]], ring + [0, 0, 1]]
    n = [side_n, side_n, [[0, 0, -1]], np.tile([0, 0, -1.0], (sections, 1)), [[0, 0, 1]], np.tile([0, 0, 1.0], (sections, 1))]
    tris = []
    for i in range(sections):
        j = (i + 1) % sections
        tris += [[i, j, sections + j], [i, sections + j, sections + i]]
        c0, b0 = 2 * sections, 2 * sections + 1           # bottom cap: centre, ring
        tris.append([c0, b0 + j, b0 + i])
        c1, t1 = 3 * sections + 1, 3 * sections + 2       # top cap: centre, ring
        tris.append([c1, t1 + i, t1 + j])
    col = (*(np.asarray(rgb, float) / 255.0), 1.0)
    return mesh(name, np.vstack(v), np.vstack(n), col, np.asarray(tris))


def segment_matrix(a: np.ndarray, b: np.ndarray, r: float) -> np.ndarray:
    """The 3x3 map of the unit rod (radius 1, z from 0 to 1) onto the rod of radius r from a to b
    (its columns: the two radial axes times r, then b - a)."""
    d = b - a
    length = float(np.linalg.norm(d))
    u = d / length if length > 1e-9 else np.array([0.0, 0.0, 1.0])
    e1 = np.cross(u, [1.0, 0.0, 0.0] if abs(u[0]) < 0.9 else [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)
    return np.column_stack([e1 * r, e2 * r, d])


def load_rods(vehicle: str) -> list[dict]:
    path = MESHES / f"{vehicle}_suspension.json"
    return json.loads(path.read_text(encoding="utf-8"))["rods"]


def rz(th: float) -> np.ndarray:
    c, s = math.cos(th), math.sin(th)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if float(np.dot(a, b)) < 0.0:
        b = -b
    q = a + (b - a) * t
    return q / np.linalg.norm(q)


class Car:
    def __init__(self, parent: NodePath, vehicle: str, index: dict[str, int]):
        self.root = parent.attach_new_node(vehicle)
        self.ix = index
        self.body = load_glb(MESHES / f"{vehicle}_body.glb")
        self.body.reparent_to(self.root)
        self.eye = self.body.attach_new_node("eye")
        self.eye.set_pos(*EYES[vehicle])
        self.eye.set_h(-90.0)                 # the camera looks along +y: turn it to +x (forward)
        wheel = load_glb(MESHES / f"{vehicle}_wheel.glb")
        hub = load_glb(MESHES / f"{vehicle}_hub.glb")
        self.wheels, self.hubs = {}, {}
        for c in CORNERS:
            self.wheels[c] = wheel.copy_to(self.root)
            self.hubs[c] = hub.copy_to(self.root)
        self.rods = load_rods(vehicle)
        unit = {}
        self.rod_nodes = []
        for rod in self.rods:
            key = tuple(rod["rgb"])
            if key not in unit:
                unit[key] = rod_mesh(f"rod{len(unit)}", rod["rgb"])
            self.rod_nodes.append(unit[key].copy_to(self.root))
        self.rod_inner = np.array([rod["inner"] for rod in self.rods], float)
        self.rod_outer = np.array([rod["outer"] for rod in self.rods], float)
        self.rod_corner = [rod["corner"].lower() for rod in self.rods]

    def _pose(self, y0, y1, a, prefix):
        ix = self.ix
        p = [y0[ix[f"{prefix}_p{k}"]] + (y1[ix[f"{prefix}_p{k}"]] - y0[ix[f"{prefix}_p{k}"]]) * a for k in "xyz"]
        qk = [ix[f"{prefix}_q{k}"] for k in "wxyz"]
        q = nlerp(y0[qk], y1[qk], a)
        return quat_matrix(*q), p

    def update(self, y0: np.ndarray, y1: np.ndarray, a: float) -> tuple[np.ndarray, list[float]]:
        """Draw the state a of the way from the outputs y0 to y1; returns the chassis pose."""
        R, p = self._pose(y0, y1, a, "chassis")
        self.body.set_mat(pose_matrix(R, p))
        carriers = {}
        for c in CORNERS:
            Rc, pc = self._pose(y0, y1, a, c)
            carriers[c] = (Rc, np.asarray(pc))
            self.hubs[c].set_mat(pose_matrix(Rc, pc))
            k = self.ix[f"{c}_spin"]
            th = y0[k] + (y1[k] - y0[k]) * a
            self.wheels[c].set_mat(pose_matrix(Rc @ rz(th), pc))
        self.lay_rods(R, np.asarray(p), carriers)
        return R, p

    def lay_rods(self, R: np.ndarray, p: np.ndarray, carriers: dict) -> list[tuple[np.ndarray, np.ndarray]]:
        """Lay every rod from its inner end (on the chassis at pose R, p) to its outer end (on its
        corner's carrier, carriers[c] = (Rc, pc)); returns the world end points."""
        inner = self.rod_inner @ R.T + p
        ends = []
        for i, node in enumerate(self.rod_nodes):
            Rc, pc = carriers[self.rod_corner[i]]
            a, b = inner[i], Rc @ self.rod_outer[i] + pc
            node.set_mat(pose_matrix(segment_matrix(a, b, self.rods[i]["r"]), a))
            ends.append((a, b))
        return ends
