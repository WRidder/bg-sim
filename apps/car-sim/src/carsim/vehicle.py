"""The drawn car: the example's GLB meshes placed by the FMU's poses.

The meshes (examples/cars/meshes, written by examples/cars/design/make_scenes.py) are those of
the bg-sim scenes: the body in the chassis frame (x forward, y left, z up, the origin at the sprung
CG), the wheel and the hub in the carrier frame of each corner (x forward, y down, z the axle).
The FMU gives the chassis pose and, per corner, the carrier pose (steer and suspension travel
included) and the wheel's spin angle about the carrier z: wheel = carrier * Rz(spin).
"""

from __future__ import annotations

import contextlib
import io
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
        for c in CORNERS:
            Rc, pc = self._pose(y0, y1, a, c)
            self.hubs[c].set_mat(pose_matrix(Rc, pc))
            k = self.ix[f"{c}_spin"]
            th = y0[k] + (y1[k] - y0[k]) * a
            self.wheels[c].set_mat(pose_matrix(Rc @ rz(th), pc))
        return R, p
