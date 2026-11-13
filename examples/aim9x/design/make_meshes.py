# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "trimesh>=4.4", "shapely>=2.0", "mapbox-earcut>=1.0"]
# ///
"""The meshes of the AIM-9X 3D scene (`meshes/*.glb`).

Body frame: x forward, y left, z up, metres, origin at the centre of mass. The missile is 3.02 m
long with the nose at x = +1.50 and the nozzle at x = -1.52; the four canards are separate
meshes with their origin on the hinge (x = +1.12, radius 0.0635) so the scene turns them with
the servo deflection. The target is a generic red aggressor drone, 8 m long and 9.6 m span.

    uv run examples/aim9x/design/make_meshes.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

OUT = Path(__file__).resolve().parent.parent / "meshes"

GREY = (0.76, 0.78, 0.80)
DARK = (0.16, 0.18, 0.21)
OLIVE = (0.55, 0.48, 0.24)
RED = (0.52, 0.14, 0.11)
RED2 = (0.36, 0.10, 0.09)
GLASS = (0.08, 0.14, 0.20)
ORANGE = (1.0, 0.48, 0.10)
CYAN = (0.15, 0.85, 0.95)


def coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1)))
    return mesh


def loft_x(stations, segments: int = 40, rgb=GREY) -> trimesh.Trimesh:
    """A surface of revolution about x: stations are (x, radius) pairs."""
    verts = []
    faces = []
    for x, r in stations:
        for k in range(segments):
            a = 2.0 * math.pi * k / segments
            verts.append([x, r * math.cos(a), r * math.sin(a)])
    n = len(stations)
    for i in range(n - 1):
        for k in range(segments):
            a = i * segments + k
            b = i * segments + (k + 1) % segments
            c = (i + 1) * segments + (k + 1) % segments
            d = (i + 1) * segments + k
            faces.append([a, b, c])
            faces.append([a, c, d])
    # close the ends with a fan
    for i, x in ((0, stations[0][0]), (n - 1, stations[-1][0])):
        pass
    mesh = trimesh.Trimesh(np.array(verts), np.array(faces), process=True)
    return coloured(mesh, rgb)


def plate(points, thickness: float, plane: str = "xz", rgb=GREY) -> trimesh.Trimesh:
    poly = Polygon(points)
    mesh = trimesh.creation.extrude_polygon(poly, height=thickness)
    mesh.apply_translation([0.0, 0.0, -thickness / 2.0])
    if plane == "xz":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0]))
    elif plane == "yz":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
    return coloured(mesh, rgb)


def add(meshes):
    return trimesh.util.concatenate([m for m in meshes if m is not None])


def missile_body() -> trimesh.Trimesh:
    body = loft_x([
        (1.340, 0.046), (1.250, 0.056), (1.150, 0.062), (1.050, 0.0635),
        (0.000, 0.0635), (-0.900, 0.0635), (-1.050, 0.060), (-1.300, 0.052),
        (-1.470, 0.046), (-1.520, 0.042),
    ])
    # the dark imaging seeker dome at the tip
    window = loft_x([(1.500, 0.000), (1.485, 0.014), (1.450, 0.030), (1.395, 0.041), (1.340, 0.046)], rgb=GLASS)
    band = trimesh.creation.cylinder(radius=0.0645, height=0.055, sections=40)
    band.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
    band.apply_translation([0.58, 0.0, 0.0])
    coloured(band, OLIVE)
    # a thin panel ring aft of the wing
    ring = trimesh.creation.cylinder(radius=0.0642, height=0.008, sections=40)
    ring.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
    ring.apply_translation([-0.62, 0.0, 0.0])
    coloured(ring, DARK)
    # four fixed tail fins at 45, 135, 225, 315 deg
    fins = []
    for phi in (45.0, 135.0, 225.0, 315.0):
        p = math.radians(phi - 90.0)
        fin = plate([(-0.14, 0.0), (0.14, 0.0), (0.07, 0.16), (-0.06, 0.16)], 0.006, "xz", GREY)
        fin.apply_transform(trimesh.transformations.rotation_matrix(p, [1, 0, 0]))
        fin.apply_translation([-1.12, 0.0635 * math.cos(math.radians(phi)), 0.0635 * math.sin(math.radians(phi))])
        fins.append(fin)
    nozzle = trimesh.creation.cylinder(radius=0.042, height=0.05, sections=32)
    nozzle.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0]))
    nozzle.apply_translation([-1.50, 0.0, 0.0])
    coloured(nozzle, DARK)
    return add([body, window, band, ring, nozzle, *fins])


def canard() -> trimesh.Trimesh:
    return plate([(-0.085, 0.0), (0.085, 0.0), (0.045, 0.19), (-0.035, 0.19)], 0.008, "xz", (0.30, 0.32, 0.35))


def plume() -> trimesh.Trimesh:
    # a cone from the nozzle (x = 0) backwards to x = -1, scaled by View/plume
    c = trimesh.creation.cone(radius=0.072, height=1.0, sections=28)
    c.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2.0, [0, 1, 0]))
    c.apply_translation([-0.5, 0.0, 0.0])
    return coloured(c, ORANGE)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "aim9x_missile.glb": missile_body(),
        "aim9x_canard.glb": canard(),
        "aim9x_plume.glb": plume(),
    }
    for name, mesh in files.items():
        path = OUT / name
        trimesh.Scene([mesh]).export(path)
        print(f"wrote {path} ({path.stat().st_size / 1024:.1f} kB, {len(mesh.faces)} faces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
