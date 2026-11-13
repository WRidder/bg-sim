# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "trimesh>=4.4", "shapely>=2.0", "mapbox-earcut>=1.0"]
# ///
"""The meshes of the T8X spider scene (`meshes/*.glb`).

Body frame: x forward, y left, z up, metres, origin at the body centre of mass. The body
mesh carries the cephalothorax, abdomen, eyes, fangs and the eight hip bosses. The three
leg meshes are in their link frames: x along the link from the joint, z the hinge axis
after the fixed `Rx90`, so the SDF joints turn them exactly as the model does.

    uv run examples/spider/design/make_meshes.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

OUT = Path(__file__).resolve().parent.parent / "meshes"

SHELL = (0.120, 0.130, 0.155)
SHELL2 = (0.220, 0.235, 0.265)
JOINT = (0.34, 0.35, 0.39)
ACCENT = (0.82, 0.34, 0.07)
EYE = (0.015, 0.025, 0.045)
PAD = (0.10, 0.085, 0.075)
CYAN = (0.10, 0.72, 0.82)

HIPS = [
    (0.072, 0.032, math.radians(35.0)),
    (0.024, 0.040, math.radians(65.0)),
    (-0.024, 0.040, math.radians(115.0)),
    (-0.072, 0.032, math.radians(145.0)),
    (0.072, -0.032, math.radians(-35.0)),
    (0.024, -0.040, math.radians(-65.0)),
    (-0.024, -0.040, math.radians(-115.0)),
    (-0.072, -0.032, math.radians(-145.0)),
]


def colour(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1))
    )
    return mesh


def ellipsoid(radii, centre=(0.0, 0.0, 0.0), sub=3, rgb=SHELL) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=sub)
    m.apply_scale(radii)
    m.apply_translation(centre)
    return colour(m, rgb)


def tapered_tube(length: float, r0: float, r1: float, sections: int = 16,
                 rgb=JOINT, split: int = 1) -> trimesh.Trimesh:
    """A closed frustum along +x from 0 to length, with `split` extra rings."""
    xs = np.linspace(0.0, length, split + 2)
    verts = []
    for x in xs:
        f = x / length
        r = r0 + (r1 - r0) * f
        for k in range(sections):
            a = 2.0 * math.pi * k / sections
            verts.append([x, r * math.cos(a), r * math.sin(a)])
    faces = []
    n = len(xs)
    for i in range(n - 1):
        for k in range(sections):
            a = i * sections + k
            b = i * sections + (k + 1) % sections
            c = (i + 1) * sections + (k + 1) % sections
            d = (i + 1) * sections + k
            faces += [[a, b, c], [a, c, d]]
    # end caps
    c0 = len(verts)
    verts.append([0.0, 0.0, 0.0])
    c1 = len(verts)
    verts.append([length, 0.0, 0.0])
    for k in range(sections):
        a = k
        b = (k + 1) % sections
        faces.append([c0, b, a])
        e = (n - 1) * sections + k
        f = (n - 1) * sections + (k + 1) % sections
        faces.append([c1, e, f])
    m = trimesh.Trimesh(np.array(verts), np.array(faces), process=True)
    return colour(m, rgb)


def cylinder(radius: float, length: float, axis="x", centre=(0.0, 0.0, 0.0),
             sections: int = 20, rgb=JOINT) -> trimesh.Trimesh:
    m = trimesh.creation.cylinder(radius=radius, height=length, sections=sections)
    if axis == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
    elif axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0]))
    m.apply_translation(centre)
    return colour(m, rgb)


def sphere(radius: float, centre, sub=2, rgb=JOINT) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=sub)
    m.apply_scale(radius)
    m.apply_translation(centre)
    return colour(m, rgb)


def body() -> trimesh.Trimesh:
    parts = []
    # cephalothorax and abdomen, joined by a narrow waist
    parts.append(ellipsoid([0.078, 0.055, 0.027], (0.018, 0.0, 0.006), rgb=SHELL))
    parts.append(ellipsoid([0.020, 0.028, 0.022], (-0.060, 0.0, 0.012), rgb=SHELL2))
    parts.append(ellipsoid([0.092, 0.062, 0.047], (-0.125, 0.0, 0.020), rgb=SHELL))
    parts.append(ellipsoid([0.075, 0.050, 0.035], (-0.135, 0.0, 0.032), rgb=SHELL2))
    # an orange hourglass on the abdomen: two slim triangular plates
    for s in (-1.0, 1.0):
        tri = trimesh.Trimesh(
            vertices=[[-0.175, 0.0, 0.061], [-0.085, 0.0, 0.061],
                      [-0.130, s * 0.040, 0.060]],
            faces=[[0, 1, 2]], process=False,
        )
        # give the thin plate some thickness by extruding a small prism
        plate = trimesh.creation.extrude_polygon(
            Polygon([(0.0, 0.0), (0.090, 0.0), (0.045, 0.040)]), 0.003
        )
        plate.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0]))
        plate.apply_translation([-0.175, s * 0.001, 0.055])
        parts.append(colour(plate, ACCENT))
    # head eyes: four pairs of glossy beads
    for x, y, z, r in ((0.082, 0.012, 0.020, 0.009), (0.082, -0.012, 0.020, 0.009),
                       (0.074, 0.026, 0.014, 0.006), (0.074, -0.026, 0.014, 0.006),
                       (0.060, 0.036, 0.018, 0.004), (0.060, -0.036, 0.018, 0.004),
                       (0.055, 0.018, 0.030, 0.004), (0.055, -0.018, 0.030, 0.004)):
        parts.append(sphere(r, (x, y, z), rgb=EYE))
    # a small cyan sensor line on the forehead
    parts.append(cylinder(0.0035, 0.038, axis="y", centre=(0.086, 0.0, 0.006),
                          sections=12, rgb=CYAN))
    # chelicerae / fangs
    for s in (-1.0, 1.0):
        fang = trimesh.creation.cone(radius=0.010, height=0.030, sections=12)
        fang.apply_transform(trimesh.transformations.rotation_matrix(1.2, [0, 1, 0]))
        fang.apply_translation([0.092, s * 0.013, -0.012])
        parts.append(colour(fang, SHELL2))
    # hip bosses and joint caps
    for hx, hy, yaw in HIPS:
        boss = cylinder(0.013, 0.024, axis="x", centre=(0.0, 0.0, 0.0), sections=18, rgb=JOINT)
        boss.apply_transform(trimesh.transformations.rotation_matrix(yaw, [0, 0, 1]))
        boss.apply_translation([hx, hy, 0.0])
        parts.append(boss)
    return trimesh.util.concatenate(parts)


def coxa() -> trimesh.Trimesh:
    parts = [sphere(0.014, (0.0, 0.0, 0.0), rgb=JOINT),
             tapered_tube(0.045, 0.011, 0.009, rgb=SHELL2),
             cylinder(0.010, 0.018, axis="z", centre=(0.0, 0.0, 0.0), sections=16, rgb=JOINT)]
    return trimesh.util.concatenate(parts)


def femur() -> trimesh.Trimesh:
    parts = [sphere(0.013, (0.0, 0.0, 0.0), rgb=JOINT),
             tapered_tube(0.110, 0.011, 0.007, rgb=SHELL2, split=2)]
    # orange band near the hip
    band = cylinder(0.0115, 0.010, axis="x", centre=(0.018, 0.0, 0.0), sections=16, rgb=ACCENT)
    parts.append(band)
    # two small dorsal spikes
    for x in (0.060, 0.085):
        spike = trimesh.creation.cone(radius=0.004, height=0.018, sections=10)
        spike.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
        spike.apply_translation([x, 0.0, 0.010])
        parts.append(colour(spike, SHELL))
    return trimesh.util.concatenate(parts)


def tibia() -> trimesh.Trimesh:
    parts = [sphere(0.011, (0.0, 0.0, 0.0), rgb=JOINT),
             tapered_tube(0.140, 0.009, 0.0033, rgb=SHELL2, split=2)]
    # the rubber foot pad at the tip
    pad = sphere(0.010, (0.140, 0.0, 0.0), rgb=PAD)
    parts.append(pad)
    # a few sensory hairs near the tip
    for y, z in ((0.0, 0.006), (0.006, 0.0), (-0.006, 0.0)):
        hair = trimesh.creation.cylinder(radius=0.0011, height=0.020, sections=6)
        hair.apply_transform(trimesh.transformations.rotation_matrix(0.8, [0, 1, 0]))
        hair.apply_translation([0.128, y, z])
        parts.append(colour(hair, SHELL))
    return trimesh.util.concatenate(parts)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "spider_body.glb": body(),
        "spider_coxa.glb": coxa(),
        "spider_femur.glb": femur(),
        "spider_tibia.glb": tibia(),
    }
    for name, mesh in files.items():
        path = OUT / name
        trimesh.Scene([mesh]).export(path)
        print(f"wrote {path} ({path.stat().st_size / 1024:.1f} kB, {len(mesh.faces)} faces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
