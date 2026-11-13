"""The AIM-9X and target-drone visuals: the example's GLB meshes with moving canards and plume.

The missile body, canards and plume are the aim9x example's meshes. The body frame is x forward,
y left, z up; the FMU gives a launch-frame attitude and position, and ``missile_model`` turns it
into the world NED matrix the F-16 aircraft uses. The target is a red F-16 airframe, a stand-in
for the target drone.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from panda3d.core import NodePath, Quat, TransparencyAttrib, Vec3

from .aircraft import MESHES as F16_MESHES
from .aircraft import load_glb, world_matrix
from .fmu import euler_to_ned
from .missile_model import T_REF, Missile, attitude_world, local_to_world
from .world import cylinder, sphere

AIM9X_MESHES = Path(__file__).resolve().parents[4] / "examples" / "aim9x" / "meshes"
CANARDS = ((45.0, 0), (135.0, 1), (225.0, 2), (315.0, 3))
RADIUS = 0.0635


def nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if float(np.dot(a, b)) < 0.0:
        b = -b
    q = a + (b - a) * t
    return q / np.linalg.norm(q)


class MissileView:
    """One missile's Panda3D nodes: body, four canards, plume and the fuze flash."""

    def __init__(self, parent: NodePath):
        self.root = parent.attach_new_node("aim9x")
        self.body = load_glb(AIM9X_MESHES / "aim9x_missile.glb")
        self.body.reparent_to(self.root)
        self.fins: list[NodePath] = []
        for phi, _ in CANARDS:
            rad = math.radians(phi)
            hinge = self.root.attach_new_node(f"canard_{int(phi)}")
            hinge.set_pos(1.12, RADIUS * math.cos(rad), RADIUS * math.sin(rad))
            rest = Quat()
            rest.set_from_axis_angle(phi - 90.0, Vec3(1, 0, 0))
            hinge.set_quat(rest)
            fin = hinge.attach_new_node(f"fin_{int(phi)}")
            load_glb(AIM9X_MESHES / "aim9x_canard.glb").reparent_to(fin)
            self.fins.append(fin)
        self.plume = load_glb(AIM9X_MESHES / "aim9x_plume.glb")
        self.plume.reparent_to(self.root)
        self.plume.set_pos(-1.02, 0.0, 0.0)
        self.plume.set_light_off()
        self.plume.hide()
        self.flash = sphere("aim9x_flash", 3.0, (1.0, 0.55, 0.12, 1.0), 20, 10)
        self.flash.reparent_to(self.root)
        self.flash.set_light_off()
        self.flash.set_transparency(TransparencyAttrib.M_alpha)
        self.flash.set_depth_write(False)
        self.flash.hide()

    def update(self, m: Missile, alpha: float) -> None:
        a = m.y_prev + (m.y - m.y_prev) * alpha
        q = nlerp(m.y_prev[[3, 4, 5, 6]], m.y[[3, 4, 5, 6]], alpha)
        R = attitude_world(m.launch, *q)
        n, e, h = local_to_world(m.launch, a[0], a[1], a[2])
        self.root.set_mat(world_matrix(R, n, e, h))
        for k, fin in enumerate(self.fins):
            q = Quat()
            q.set_from_axis_angle(float(a[27 + k]), Vec3(0, 0, 1))
            fin.set_quat(q)
        thrust = max(0.0, float(a[26]))
        if thrust > 1.0 and not m.fuze_latched:
            self.plume.show()
            self.plume.set_scale(max(0.05, thrust / T_REF), 1.0, 1.0)
        else:
            self.plume.hide()
        if m.fuze_latched and m.done_at is not None:
            age = max(0.0, m.time + (alpha * m.model.step_size) - m.done_at)
            self.body.hide()
            for fin in self.fins:
                fin.hide()
            self.plume.hide()
            if age < 0.8:
                self.flash.show()
                s = 0.35 + 2.2 * age
                self.flash.set_scale(s)
                self.flash.set_alpha_scale(max(0.0, 1.0 - age / 0.8))
            else:
                self.flash.hide()
        else:
            self.body.show()
            for fin in self.fins:
                fin.show()
            self.flash.hide()

    def destroy(self) -> None:
        self.root.remove_node()


class DroneView:
    """A red F-16 airframe for a target drone (a stand-in; the FMU sees only the state)."""

    def __init__(self, parent: NodePath):
        self.root = parent.attach_new_node("target_drone")
        self.body = load_glb(F16_MESHES / "f16_body_grey.glb")
        self.body.reparent_to(self.root)
        self.body.set_scale(1.6)
        self.body.set_color_scale(1.0, 0.32, 0.30, 1.0)
        self.plume = cylinder("target_plume", 0.34, 0.05, 2.4, (1.0, 0.5, 0.15, 0.85), 12)
        self.plume.reparent_to(self.root)
        self.plume.set_pos(-7.2, 0.0, 0.15)
        q = Quat()
        q.set_from_axis_angle(-90.0, Vec3(0, 1, 0))
        self.plume.set_quat(q)
        self.plume.set_transparency(TransparencyAttrib.M_alpha)
        self.plume.set_light_off()
        self.flash = sphere("drone_flash", 7.0, (1.0, 0.5, 0.1, 1.0), 20, 10)
        self.flash.reparent_to(self.root)
        self.flash.set_light_off()
        self.flash.set_transparency(TransparencyAttrib.M_alpha)
        self.flash.set_depth_write(False)
        self.flash.hide()
        self.was_alive = True
        self.dead_at: float | None = None

    def update(self, drone, t: float) -> None:
        R = euler_to_ned(0.0, 0.0, math.radians(drone.heading_deg))
        self.root.set_mat(world_matrix(R, drone.north, drone.east, drone.alt))
        if drone.alive:
            self.body.show()
            self.plume.show()
            self.flash.hide()
            self.was_alive = True
            self.dead_at = None
        else:
            self.body.hide()
            self.plume.hide()
            if self.was_alive:
                self.flash.show()
                self.was_alive = False
                self.dead_at = t
            if self.dead_at is None or t - self.dead_at > 1.2:
                self.flash.hide()
            else:
                age = t - self.dead_at
                self.flash.set_scale(0.4 + 1.3 * age)
                self.flash.set_alpha_scale(max(0.0, 1.0 - age / 1.2))

    def destroy(self) -> None:
        self.root.remove_node()
