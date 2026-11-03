"""The helicopter model: the solids of the example's 3D scene with the main rotor tilted by the
shaft and the flapping, and both rotors turning.

The example builds its A109 from simple solids (examples/a109/design/build_model.py, written to
examples/a109/scenes/a109-sim.sdf): cabin, nose, windscreen, tail cone, boom, engine fairing, fin,
ventral fin, tailplane, mast, the tricycle gear; the main rotor (four blades, the hub and a faint
disc) and the two-blade tail rotor. This module reads that SDF file and builds the same solids
in Panda3D, in the body frame of the bg-sim scene: x forward, y left, z up, metres, origin at the
CG. The link poses of the SDF (the helicopter at its view height, the rotors at their hubs) give
the rotors' places on the airframe. The main rotor is tilted forward with the shaft and further
by the flapping (a1 aft, b1 right; the FMU's outputs), as the example's HeliView does.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from panda3d.core import LMatrix4f, NodePath, Quat, TransparencyAttrib, Vec3

from .world import mesh

SDF = Path(__file__).resolve().parents[4] / "examples" / "a109" / "scenes" / "a109-sim.sdf"
EYE = (1.45, -0.38, 0.42)          # m, the pilot's eye (right seat) in the body frame
OMEGA0 = 40.31710572106901         # rad/s, the main rotor at 100 % (385 rpm)
N_TR = 5.402597402597402           # the tail-rotor gear ratio (2080/385)
SPIN = 0.1                         # the blades turn at a tenth of their speed (no strobing), as in the example
# the model's world (x north, y west, z up) -> Panda3D's (x east, y north, z up)
_W = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


@dataclass
class Visual:
    name: str
    pose: tuple[float, ...]        # x y z roll pitch yaw (SDF: fixed axes x, y, z)
    kind: str                      # box, cylinder, sphere
    size: tuple[float, ...]        # box (sx, sy, sz); cylinder (radius, length); sphere (radius,)
    color: tuple[float, float, float, float]


def read_scene(path: Path = SDF) -> dict[str, tuple[tuple[float, ...], list[Visual]]]:
    """The links of the SDF scene: name -> (link pose, visuals)."""
    root = ET.parse(path).getroot()
    out = {}
    for link in root.iter("link"):
        pose = tuple(float(v) for v in (link.findtext("pose") or "0 0 0 0 0 0").split())
        vis = []
        for v in link.findall("visual"):
            p = tuple(float(x) for x in (v.findtext("pose") or "0 0 0 0 0 0").split())
            g = v.find("geometry")
            color = tuple(float(c) for c in (v.findtext("material/diffuse") or "0.7 0.7 0.7 1").split())
            if g.find("box") is not None:
                kind, size = "box", tuple(float(s) for s in g.findtext("box/size").split())
            elif g.find("cylinder") is not None:
                kind, size = "cylinder", (float(g.findtext("cylinder/radius")), float(g.findtext("cylinder/length")))
            elif g.find("sphere") is not None:
                kind, size = "sphere", (float(g.findtext("sphere/radius")),)
            else:
                continue
            vis.append(Visual(v.get("name"), p, kind, size, color))
        out[link.get("name")] = (pose, vis)
    return out


def rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """SDF's rotation: roll about x, then pitch about y, then yaw about z (fixed axes)."""
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def panda_matrix(R: np.ndarray, t) -> LMatrix4f:
    """A column-vector transform (R, t) as Panda3D's row-vector matrix."""
    return LMatrix4f(R[0, 0], R[1, 0], R[2, 0], 0.0, R[0, 1], R[1, 1], R[2, 1], 0.0,
                     R[0, 2], R[1, 2], R[2, 2], 0.0, float(t[0]), float(t[1]), float(t[2]), 1.0)


def world_matrix(R_world_body: np.ndarray, north: float, east: float, alt: float) -> LMatrix4f:
    """The node transform: body (FLU) -> Panda world, as a Panda row-vector matrix."""
    return panda_matrix(_W @ R_world_body, (east, north, alt))


def _box(name, sx, sy, sz, color) -> NodePath:
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
             ((0, 0, -1), [(-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz)]),
             ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
             ((1, 0, 0), [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
             ((0, 1, 0), [(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)]),
             ((-1, 0, 0), [(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)])]
    v, n, t = [], [], []
    for nrm, quad in faces:
        b = len(v)
        v += quad
        n += [nrm] * 4
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return mesh(name, np.array(v, float), np.array(n, float), np.tile(color, (len(v), 1)), np.array(t))


def _cylinder(name, r, length, color, seg=28) -> NodePath:
    """A closed cylinder along z, centred."""
    a = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    c, s = np.cos(a), np.sin(a)
    h = length / 2
    v = np.vstack([np.stack([r * c, r * s, -h * np.ones(seg)], -1), np.stack([r * c, r * s, h * np.ones(seg)], -1),
                   [[0, 0, -h], [0, 0, h]], np.stack([r * c, r * s, -h * np.ones(seg)], -1),
                   np.stack([r * c, r * s, h * np.ones(seg)], -1)])
    n = np.vstack([np.stack([c, s, 0 * c], -1), np.stack([c, s, 0 * c], -1), [[0, 0, -1], [0, 0, 1]],
                   np.tile([0, 0, -1.0], (seg, 1)), np.tile([0, 0, 1.0], (seg, 1))])
    t = []
    bot, top, cb, ct = 2 * seg + 2, 3 * seg + 2, 2 * seg, 2 * seg + 1
    for k in range(seg):
        j = (k + 1) % seg
        t += [(k, j, seg + j), (k, seg + j, seg + k), (cb, bot + j, bot + k), (ct, top + k, top + j)]
    return mesh(name, v, n, np.tile(color, (len(v), 1)), np.array(t))


def _sphere(name, r, color, rings=12, seg=24) -> NodePath:
    th = np.linspace(0, math.pi, rings + 1)
    ph = np.linspace(0, 2 * math.pi, seg + 1)
    T, P = np.meshgrid(th, ph, indexing="ij")
    nrm = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], -1).reshape(-1, 3)
    t = []
    for i in range(rings):
        for j in range(seg):
            a, b = i * (seg + 1) + j, (i + 1) * (seg + 1) + j
            t += [(a, b, b + 1), (a, b + 1, a + 1)]
    return mesh(name, r * nrm, nrm, np.tile(color, (len(nrm), 1)), np.array(t))


def solid(v: Visual) -> NodePath:
    if v.kind == "box":
        np_ = _box(v.name, *v.size, v.color)
    elif v.kind == "cylinder":
        np_ = _cylinder(v.name, *v.size, v.color)
    else:
        np_ = _sphere(v.name, v.size[0], v.color)
    x, y, z, r, p, yw = v.pose
    np_.set_mat(panda_matrix(rpy_matrix(r, p, yw), (x, y, z)))
    if v.color[3] < 0.99:
        np_.set_transparency(TransparencyAttrib.M_alpha)
        np_.set_depth_write(False)
        np_.set_two_sided(True)
        np_.set_bin("transparent", 20)
    return np_


class Helicopter:
    """``root`` carries the airframe (``body``), the main rotor (``tilt`` -> ``spin``) and the tail
    rotor (``tail``); ``eye`` is the cockpit camera's mount."""

    def __init__(self, parent: NodePath, sdf: Path = SDF, tag: str = "heli"):
        links = read_scene(sdf)
        (bx, by, bz, *_), body = links[f"heli_{tag}"]
        rpose, rotor = links[f"rotor_{tag}"]
        tpose, tail = links[f"tailrotor_{tag}"]
        self.root = parent.attach_new_node("helicopter")
        self.body = self.root.attach_new_node("airframe")
        for v in body:
            solid(v).reparent_to(self.body)
        self.body.flatten_strong()
        # the main rotor: the hub (from the link poses), the shaft tilt (the link's pitch) and the flapping
        self.hub = self.root.attach_new_node("hub")
        self.hub.set_pos(rpose[0] - bx, rpose[1] - by, rpose[2] - bz)
        self.shaft_tilt = rpose[4]
        self.tilt = self.hub.attach_new_node("tilt")
        self.spin = self.tilt.attach_new_node("spin")
        self.blades = self.spin.attach_new_node("blades")
        self.disc = None
        for v in rotor:
            node = solid(v)
            if v.name.startswith("disc"):
                node.reparent_to(self.tilt)
                self.disc = node
            else:
                node.reparent_to(self.blades)
        self.tail = self.root.attach_new_node("tail_hub")
        self.tail.set_pos(tpose[0] - bx, tpose[1] - by, tpose[2] - bz)
        self.tail_spin = self.tail.attach_new_node("tail_spin")
        self.tail_disc = None
        for v in tail:
            node = solid(v)
            if v.name.startswith("trdisc"):
                node.reparent_to(self.tail)
                self.tail_disc = node
            else:
                node.reparent_to(self.tail_spin)
        self.eye = self.root.attach_new_node("eye")
        self.eye.set_pos(*EYE)
        self.eye.set_h(-90.0)                 # the camera looks along +y: turn it to +x (forward)
        self.az = 0.0

    def update(self, R: np.ndarray, north: float, east: float, alt: float, y: dict[str, float], dt: float) -> None:
        self.root.set_mat(world_matrix(R, north, east, alt))
        # the tip-path plane: the shaft tilt less the aft flapping (about y), the lateral flapping
        # (about x), then the azimuth about the plane's normal (the A109's rotor turns anticlockwise
        # seen from above)
        a1, b1 = math.radians(y["a1_deg"]), math.radians(y["b1_deg"])
        q = Quat()
        q.set_from_axis_angle_rad(self.shaft_tilt - a1, Vec3(0, 1, 0))
        qx = Quat()
        qx.set_from_axis_angle_rad(b1, Vec3(1, 0, 0))
        self.tilt.set_quat(qx * q)
        om = OMEGA0 * y["rotor_pct"] / 100.0
        self.az = (self.az + SPIN * om * dt) % (2 * math.pi)
        self.spin.set_h(math.degrees(self.az))
        self.tail_spin.set_r(math.degrees(self.az * N_TR) % 360.0)
        if self.disc is not None:
            self.disc.set_alpha_scale(min(1.0, max(0.0, (y["rotor_pct"] - 20.0) / 60.0)) * 1.6)
