"""The aircraft model: the example's GLB meshes with moving stabilators, flaperons and rudder.

The meshes (examples/f16/meshes, written by examples/f16/design/make_meshes.py) are in the body
frame of the bg-sim scene: x forward, y left, z up, metres. The hinge points and axes are those of
build_model.SIM_PIVOTS; the gains follow the scene's bindings (examples/f16/scenes/f16-sim.sdf).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from panda3d.core import LMatrix4f, NodePath, Quat, TransparencyAttrib, Vec3

from .world import cylinder

# The gear as drawn: the legs of examples/f16/design/gear.py (x forward, y left, z up, from the CG at
# xcg 0.35), a strut and a wheel per leg, folding up by `gear_pos`, and hidden when retracted.
GEAR_LEGS = {"nose": (2.797, 0.0, -1.699), "left": (-0.785, 1.219, -1.689), "right": (-0.785, -1.219, -1.689)}
GEAR_TOP = -0.55              # m, body z where a strut meets the fuselage
WHEEL_R = {"nose": 0.23, "left": 0.35, "right": 0.35}
MESHES = Path(__file__).resolve().parents[4] / "examples" / "f16" / "meshes"
SURFACES = {  # name: (mesh, pivot, axis, gain per deg of its signal, signal)
    "stab": ("f16_stab_grey.glb", (-5.0, 0.0, 0.05), (0.0, 1.0, 0.0), -1.0, "stab_deg"),
    "flap_l": ("f16sim_flap_l.glb", (-2.419, 1.25, 0.0), (0.153, 0.988, 0.0), 1.0, "ail_deg"),
    "flap_r": ("f16sim_flap_r.glb", (-2.419, -1.25, 0.0), (-0.153, 0.988, 0.0), -1.0, "ail_deg"),
    "rudder": ("f16sim_rudder.glb", (-5.75, 0.0, 0.9), (-0.0797, 0.0, 0.9968), -1.0, "rdr_deg"),
}
EYE = (4.2, 0.0, 1.30)          # m, the pilot's eye in the body frame (x fwd, y left, z up)

# body (FRD) -> NED rotation R; the world is ENU-like (x east, y north, z up) and the mesh is FLU
_NED_TO_WORLD = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
_FLU_TO_FRD = np.diag([1.0, -1.0, -1.0])


def load_glb(path: Path) -> NodePath:
    import contextlib
    import io

    import gltf

    with contextlib.redirect_stdout(io.StringIO()):   # the loader prints a warning per untextured primitive
        node = gltf.load_model(str(path), gltf_settings=gltf.GltfSettings(skip_axis_conversion=True))
    return NodePath(node)


def world_matrix(R_ned_body: np.ndarray, north: float, east: float, alt: float) -> LMatrix4f:
    """The node transform: mesh (FLU body) -> world, as a Panda row-vector matrix."""
    M = _NED_TO_WORLD @ R_ned_body @ _FLU_TO_FRD
    return LMatrix4f(M[0, 0], M[1, 0], M[2, 0], 0.0,
                     M[0, 1], M[1, 1], M[2, 1], 0.0,
                     M[0, 2], M[1, 2], M[2, 2], 0.0,
                     east, north, alt, 1.0)


class Aircraft:
    def __init__(self, parent: NodePath):
        self.root = parent.attach_new_node("aircraft")
        self.body = load_glb(MESHES / "f16sim_body.glb")
        self.body.reparent_to(self.root)
        self.surfaces = {}
        for name, (glb, pivot, axis, gain, sig) in SURFACES.items():
            hinge = self.root.attach_new_node(f"{name}_hinge")
            hinge.set_pos(*pivot)
            load_glb(MESHES / glb).reparent_to(hinge)
            ax = Vec3(*axis)
            ax.normalize()
            self.surfaces[name] = (hinge, ax, gain, sig)
        # afterburner plume: a cone behind the nozzle, scaled with the power above military
        self.plume = cylinder("plume", 0.45, 0.05, 1.0, (1.0, 0.55, 0.2, 0.75), 16)
        self.plume.reparent_to(self.root)
        self.plume.set_pos(-7.25, 0.0, 0.25)
        self.plume.set_transparency(TransparencyAttrib.M_alpha)
        self.plume.set_light_off()
        self.plume.set_depth_write(False)
        self.plume.set_two_sided(True)
        q = Quat()
        q.set_from_axis_angle(-90.0, Vec3(0, 1, 0))    # the cone's +z along -x (aft)
        self.plume.set_quat(q)
        self.gear = {}
        for name, (x, y, z) in GEAR_LEGS.items():
            hinge = self.root.attach_new_node(f"gear_{name}")
            hinge.set_pos(x, y, GEAR_TOP)
            r = WHEEL_R[name]
            strut = cylinder(f"strut_{name}", 0.07, 0.07, GEAR_TOP - z - r, (0.75, 0.75, 0.78, 1.0), 8)
            strut.reparent_to(hinge)
            strut.set_p(180.0)
            wheel = cylinder(f"wheel_{name}", r, r, 0.22, (0.08, 0.08, 0.09, 1.0), 16)
            wheel.reparent_to(hinge)
            wheel.set_pos(0.0, 0.11, z + r - GEAR_TOP)
            wheel.set_p(90.0)
            self.gear[name] = hinge
        self.eye = self.root.attach_new_node("eye")
        self.eye.set_pos(*EYE)
        self.eye.set_h(-90.0)                 # the camera looks along +y: turn it to +x (forward)

    def update(self, R_ned_body: np.ndarray, north: float, east: float, alt: float, y: dict[str, float]) -> None:
        self.root.set_mat(world_matrix(R_ned_body, north, east, alt))
        for hinge, ax, gain, sig in self.surfaces.values():
            q = Quat()
            q.set_from_axis_angle(gain * y[sig], ax)
            hinge.set_quat(q)
        for name, hinge in self.gear.items():
            pos = y["gear_pos"]
            if pos < 0.02:
                hinge.hide()
            else:
                hinge.show()
                hinge.set_hpr(-math.degrees(y["steer_rad"]) if name == "nose" else 0.0, 0.0, 100.0 * (1.0 - pos))
        pw = y["power_pct"]
        ab = max(0.0, (pw - 50.0) / 50.0)
        if ab > 0.01:
            self.plume.show()
            self.plume.set_scale(0.8 + 0.4 * ab, 0.8 + 0.4 * ab, 2.0 + 6.0 * ab)
            self.plume.set_alpha_scale(0.35 + 0.5 * ab)
        else:
            self.plume.hide()

