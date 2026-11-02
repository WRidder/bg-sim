"""The aircraft model: the example's GLB meshes with moving ailerons, flaps, elevator, rudder, the
propeller and the steered nose wheel.

The meshes (examples/cessna/meshes, written by examples/cessna/design/make_meshes.py) are in the
body frame of the bg-sim scene: x forward, y left, z up, metres, origin at the CG. The hinge points
and axes are make_meshes.PIVOTS; the gains follow the scene's bindings
(examples/cessna/scenes/cessna-sim.sdf): a positive surface angle (JSBSim: trailing edge down,
the rudder's trailing edge left) is a negative turn about the hinge axis.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from panda3d.core import LMatrix4f, NodePath, Quat, TransparencyAttrib, Vec3

from .world import cylinder

MESHES = Path(__file__).resolve().parents[4] / "examples" / "cessna" / "meshes"
PARTS = {  # name: (pivot, axis, gain per unit of its signal, signal)
    "aileron_l": ((-0.63, 4.09, 0.66), (0.0, 1.0, 0.0), -1.0, "aileron_deg"),
    "aileron_r": ((-0.63, -4.09, 0.66), (0.0, 1.0, 0.0), 1.0, "aileron_deg"),
    "flap_l": ((-0.59, 1.785, 0.63), (0.0, 1.0, 0.0), -1.0, "flap_deg"),
    "flap_r": ((-0.59, -1.785, 0.63), (0.0, 1.0, 0.0), -1.0, "flap_deg"),
    "elevator": ((-5.20, 0.0, 0.10), (0.0, 1.0, 0.0), -1.0, "elevator_deg"),
    "rudder": ((-5.55, 0.0, 0.10), (-0.074, 0.0, 0.997), -1.0, "rudder_deg"),
    "nosewheel": ((1.331, 0.0, -1.217), (0.0, 0.0, 1.0), -math.degrees(1.0), "steer_rad"),
}
HUB = (2.116, 0.0, -0.226)
EYE = (0.25, 0.28, 0.33)          # m, the pilot's eye (left seat) in the body frame
# the model's world (x north, y west, z up) -> Panda3D's (x east, y north, z up)
_W = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def load_glb(path: Path) -> NodePath:
    import contextlib
    import io

    import gltf

    with contextlib.redirect_stdout(io.StringIO()):   # the loader prints a warning per untextured primitive
        node = gltf.load_model(str(path), gltf_settings=gltf.GltfSettings(skip_axis_conversion=True))
    return NodePath(node)


def to_panda(north: float, west: float, up: float) -> tuple[float, float, float]:
    return -west, north, up


def world_matrix(R_world_body: np.ndarray, north: float, east: float, alt: float) -> LMatrix4f:
    """The node transform: mesh (FLU body) -> Panda world, as a Panda row-vector matrix."""
    M = _W @ R_world_body
    return LMatrix4f(M[0, 0], M[1, 0], M[2, 0], 0.0,
                     M[0, 1], M[1, 1], M[2, 1], 0.0,
                     M[0, 2], M[1, 2], M[2, 2], 0.0,
                     east, north, alt, 1.0)


class Aircraft:
    def __init__(self, parent: NodePath):
        self.root = parent.attach_new_node("aircraft")
        self.body = load_glb(MESHES / "c172_body.glb")
        self.body.reparent_to(self.root)
        self.parts = {}
        for name, (pivot, axis, gain, sig) in PARTS.items():
            hinge = self.root.attach_new_node(f"{name}_hinge")
            hinge.set_pos(*pivot)
            load_glb(MESHES / f"c172_{name}.glb").reparent_to(hinge)
            ax = Vec3(*axis)
            ax.normalize()
            self.parts[name] = (hinge, ax, gain, sig)
        self.prop = self.root.attach_new_node("prop_hinge")
        self.prop.set_pos(*HUB)
        self.blades = load_glb(MESHES / "c172_propeller.glb")
        self.blades.reparent_to(self.prop)
        # the blur disc of the turning propeller
        self.disc = cylinder("prop_disc", 0.95, 0.95, 0.02, (0.25, 0.25, 0.25, 0.22), 32)
        self.disc.reparent_to(self.prop)
        q = Quat()
        q.set_from_axis_angle(90.0, Vec3(0, 1, 0))     # the disc's axis (its local z) along the body x
        self.disc.set_quat(q)
        self.disc.set_pos(0.05, 0, 0)
        self.disc.set_transparency(TransparencyAttrib.M_alpha)
        self.disc.set_depth_write(False)
        self.disc.set_two_sided(True)
        self.disc.set_bin("transparent", 20)
        self.eye = self.root.attach_new_node("eye")
        self.eye.set_pos(*EYE)
        self.eye.set_h(-90.0)                 # the camera looks along +y: turn it to +x (forward)
        self._spin = 0.0

    def update(self, R: np.ndarray, north: float, east: float, alt: float, y: dict[str, float], dt: float) -> None:
        self.root.set_mat(world_matrix(R, north, east, alt))
        for hinge, ax, gain, sig in self.parts.values():
            q = Quat()
            q.set_from_axis_angle(gain * y[sig], ax)
            hinge.set_quat(q)
        rpm = y["rpm"]
        if rpm < 350.0:      # starting or stopping: the blades at their angle
            ang = math.degrees(y["prop_angle"]) % 360.0
            self.disc.hide()
        else:                # a stroboscopic slow turn and the disc
            self._spin = (self._spin + dt * 360.0 * 0.6 * min(1.0, rpm / 2400.0)) % 360.0
            ang = self._spin
            self.disc.show()
            self.disc.set_alpha_scale(min(1.0, rpm / 1500.0))
        q = Quat()
        q.set_from_axis_angle(-ang, Vec3(1, 0, 0))
        self.blades.set_quat(q)
