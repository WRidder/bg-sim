# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "networkx>=3", "trimesh>=4.4", "shapely>=2.0", "mapbox-earcut>=1.0"]
# ///
"""The F-16 meshes of the 3D scenes (`meshes/*.glb`), built from simple solids.

    uv run examples/f16/design/make_meshes.py

Body frame: x forward, y left, z up, metres, origin at the centre of gravity (about 8 m behind
the nose; the real aircraft is 15.0 m long with a 9.45 m span over the wingtip rails). The
shapes are the F-16's: a lofted fuselage with the chin (ventral) intake, the bubble canopy, the
cropped-delta wing (40 deg leading-edge sweep) blended into the fuselage by the leading-edge
extension, wingtip missile rails, the single vertical tail, the ventral fins and the nozzle.
The all-moving horizontal tails (stabilators) are a separate mesh with its origin on their
pivot axis (`STAB_PIVOT`), so the scene can turn them with a revolute joint.

Three paint schemes (grey, sand, blue) tell the aircraft of one model apart.

The f16-sim model (and the f16-sim host, apps/f16-sim) also moves the ailerons and the rudder:
`f16sim_body.glb` (grey) has the wing cut out for the flaperons and the fin cut out for the
rudder, and `f16sim_flap_l.glb`, `f16sim_flap_r.glb`, `f16sim_rudder.glb` are those surfaces with
their origin on their hinge line (`SIM_PIVOTS`, the same numbers as in build_model.py).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).resolve().parent.parent / "meshes"
STAB_PIVOT = (-5.0, 0.0, 0.05)   # m, body frame
# Movable surfaces of the f16-sim meshes: hinge point (body frame) of each (build_model.SIM_PIVOTS)
FLAP_IN, FLAP_OUT = 1.25, 3.6    # m, span of the flaperon (left wing, y > 0)
FLAP_CHORD = 0.55                # m
RUDDER = [(-5.75, 0.9), (-5.95, 3.4), (-6.34, 3.4), (-6.22, 0.9)]   # (x, z): hinge bottom, top, trailing edge
SIM_PIVOTS = {"flap_l": (-2.419, 1.25, 0.0), "flap_r": (-2.419, -1.25, 0.0), "rudder": (-5.75, 0.0, 0.9)}

SCHEMES = {
    "grey": {"skin": (150, 156, 164), "dark": (95, 100, 108)},
    "sand": {"skin": (196, 170, 120), "dark": (130, 108, 70)},
    "blue": {"skin": (110, 140, 190), "dark": (60, 80, 125)},
}
BLACK = (30, 30, 34)
CANOPY = (70, 60, 25)
RED = (190, 40, 40)
WHITE = (230, 230, 230)


def coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1)))
    return mesh


def slab(points, thickness, plane="xy", offset=0.0) -> trimesh.Trimesh:
    """A flat plate: the polygon `points` (2D, counter-clockwise or not) extruded symmetrically
    by `thickness` normal to the plane; triangulated as a fan around the centroid (all our
    planforms are star-shaped about it)."""
    p = np.asarray(points, dtype=float)
    c = p.mean(axis=0)
    n = len(p)
    ring = np.vstack([c, p])
    verts2 = ring
    h = thickness / 2.0

    def lift(v2, s):
        if plane == "xy":
            return np.column_stack([v2[:, 0], v2[:, 1], np.full(len(v2), offset + s)])
        if plane == "xz":
            return np.column_stack([v2[:, 0], np.full(len(v2), offset + s), v2[:, 1]])
        raise ValueError(plane)

    top = lift(verts2, h)
    bot = lift(verts2, -h)
    verts = np.vstack([top, bot])
    faces = []
    m = n + 1
    for k in range(n):
        a, b = 1 + k, 1 + (k + 1) % n
        faces.append([0, a, b])
        faces.append([m, m + b, m + a])
        faces.append([a, m + a, m + b])
        faces.append([a, m + b, b])
    mesh = trimesh.Trimesh(verts, np.array(faces), process=True)
    mesh.fix_normals()
    return mesh


def loft(stations, segments=28) -> trimesh.Trimesh:
    """Body of elliptic sections: stations (x, half-width, half-height, z-centre), nose first."""
    rings = []
    for x, a, b, zc in stations:
        ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        rings.append(np.column_stack([np.full(segments, x), a * np.cos(ang), zc + b * np.sin(ang)]))
    verts = np.vstack(rings + [[[stations[0][0], 0, stations[0][3]]], [[stations[-1][0], 0, stations[-1][3]]]])
    nose, tail = len(verts) - 2, len(verts) - 1
    faces = []
    for r in range(len(rings) - 1):
        for k in range(segments):
            a = r * segments + k
            b = r * segments + (k + 1) % segments
            c, d = a + segments, b + segments
            faces += [[a, c, d], [a, d, b]]
    for k in range(segments):
        faces.append([nose, (k + 1) % segments, k])
        last = (len(rings) - 1) * segments
        faces.append([tail, last + k, last + (k + 1) % segments])
    mesh = trimesh.Trimesh(verts, np.array(faces), process=True)
    mesh.fix_normals()
    return mesh


def cylinder_x(x0, x1, r, y=0.0, z=0.0, sections=20) -> trimesh.Trimesh:
    c = trimesh.creation.cylinder(radius=r, height=abs(x1 - x0), sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0 + x1) / 2, y, z])
    return c


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    m.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
    m.invert()          # mirroring flips the winding
    m.fix_normals()
    return m


def body(scheme, sim: bool = False) -> trimesh.Scene:
    skin, dark = scheme["skin"], scheme["dark"]
    parts = []
    fus = loft([
        (8.2, 0.03, 0.03, 0.05), (7.6, 0.22, 0.22, 0.08), (6.8, 0.38, 0.38, 0.12), (5.8, 0.52, 0.55, 0.14),
        (4.6, 0.62, 0.65, 0.1), (3.0, 0.72, 0.7, 0.05), (1.0, 0.78, 0.72, 0.0), (-1.5, 0.78, 0.7, 0.0),
        (-3.5, 0.72, 0.62, 0.02), (-5.2, 0.6, 0.55, 0.05), (-6.4, 0.52, 0.5, 0.05),
    ])
    parts.append(coloured(fus, skin))
    radome = loft([(8.25, 0.02, 0.02, 0.05), (7.9, 0.14, 0.14, 0.07), (7.55, 0.23, 0.23, 0.08)])
    parts.append(coloured(radome, dark))
    # chin intake: a box under the fuselage with a black mouth
    intake = trimesh.creation.box(extents=[5.2, 1.0, 0.62])
    intake.apply_translation([1.7, 0.0, -0.78])
    parts.append(coloured(intake, skin))
    mouth = trimesh.creation.box(extents=[0.06, 0.86, 0.5])
    mouth.apply_translation([4.32, 0.0, -0.78])
    parts.append(coloured(mouth, BLACK))
    # canopy
    can = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    can.apply_scale([1.55, 0.4, 0.42])
    can.apply_translation([4.9, 0.0, 0.62])
    parts.append(coloured(can, CANOPY))
    # wing with the leading-edge extension (half span, y > 0), mirrored
    if sim:   # the wing without the flaperon (the trailing edge between FLAP_IN and FLAP_OUT)
        hi, ho = flap_hinge()
        wing = plate([(5.4, 0.45), (2.4, 1.05), (-1.25, 4.6), (-2.45, 4.6), (te_x(FLAP_OUT), FLAP_OUT), ho, hi,
                      (te_x(FLAP_IN), FLAP_IN), (-3.0, 1.05), (-3.0, 0.45)], 0.12, "xy")
    else:
        wing = slab([(5.4, 0.45), (2.4, 1.05), (-1.25, 4.6), (-2.45, 4.6), (-3.0, 1.05), (-3.0, 0.45)], 0.12, "xy", 0.0)
    parts += [coloured(wing, skin), coloured(mirror_y(wing), skin)]
    # wingtip rails with missiles (red nose, white body)
    for sgn in (1.0, -1.0):
        parts.append(coloured(cylinder_x(-2.6, 0.4, 0.065, y=sgn * 4.72, z=0.0), WHITE))
        tip = trimesh.creation.cone(radius=0.065, height=0.3, sections=16)
        tip.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
        tip.apply_translation([0.4, sgn * 4.72, 0.0])
        parts.append(coloured(tip, RED))
    # vertical tail (x-z plane) and the rudder line
    if sim:   # the fin without the rudder
        r = RUDDER
        fin = plate([(-2.2, 0.55), (-5.0, 3.55), (-6.35, 3.55), r[2], r[1], r[0], r[3], (-6.2, 0.55)], 0.12, "xz")
        parts.append(coloured(fin, skin))
    else:
        fin = slab([(-2.2, 0.55), (-5.0, 3.55), (-6.35, 3.55), (-6.2, 0.55)], 0.12, "xz", 0.0)
        parts.append(coloured(fin, skin))
        rudder = slab([(-5.75, 0.9), (-5.95, 3.4), (-6.3, 3.4), (-6.2, 0.9)], 0.13, "xz", 0.0)
        parts.append(coloured(rudder, dark))
    # ventral fins, canted out
    for sgn in (1.0, -1.0):
        vf = slab([(-3.6, 0.0), (-4.6, -0.6), (-5.2, -0.6), (-5.0, 0.0)], 0.06, "xz", 0.0)
        vf.apply_transform(trimesh.transformations.rotation_matrix(sgn * math.radians(15), [1, 0, 0]))
        vf.apply_translation([0.0, sgn * 0.55, -0.35])
        parts.append(coloured(vf, dark))
    # nozzle
    parts.append(coloured(cylinder_x(-7.2, -6.35, 0.47), dark))
    parts.append(coloured(cylinder_x(-7.22, -7.15, 0.38), BLACK))
    scene = trimesh.Scene()
    for k, p in enumerate(parts):
        scene.add_geometry(p, node_name=f"part{k}")
    return scene


def stabilators(scheme) -> trimesh.Scene:
    """Both stabilators, origin on the pivot axis (they turn together in pitch)."""
    px, _, pz = STAB_PIVOT
    half = slab([(1.0, 0.62), (-0.95, 2.75), (-1.95, 2.75), (-2.1, 0.62)], 0.08, "xy", 0.0)
    scene = trimesh.Scene()
    for k, m in enumerate((half, mirror_y(half))):
        m = m.copy()
        scene.add_geometry(coloured(m, scheme["skin"]), node_name=f"stab{k}")
    return scene


def te_x(y):
    """x of the wing's trailing edge at span y (left wing)."""
    return -3.0 + (y - 1.05) / (4.6 - 1.05) * 0.55


def flap_hinge():
    """Inboard and outboard hinge points (x, y) of the left flaperon."""
    return (te_x(FLAP_IN) + FLAP_CHORD, FLAP_IN), (te_x(FLAP_OUT) + FLAP_CHORD, FLAP_OUT)


def plate(points, thickness, plane="xy") -> trimesh.Trimesh:
    """A flat plate of any (also concave) polygon, centred on its plane (shapely + earcut)."""
    from shapely.geometry import Polygon
    m = trimesh.creation.extrude_polygon(Polygon(points), thickness)
    m.apply_translation([0.0, 0.0, -thickness / 2.0])
    if plane == "xz":   # local (x, y, z) -> (x, -z, y)
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.fix_normals()
    return m


def surfaces(scheme) -> dict[str, trimesh.Scene]:
    """The flaperons and the rudder of the f16-sim meshes, each with its origin on its hinge."""
    hi, ho = flap_hinge()
    left = [hi, ho, (te_x(FLAP_OUT), FLAP_OUT), (te_x(FLAP_IN), FLAP_IN)]
    px, py, _ = SIM_PIVOTS["flap_l"]
    flap_l = plate([(x - px, y - py) for x, y in left], 0.07, "xy")
    flap_r = mirror_y(flap_l)
    rx, _, rz = SIM_PIVOTS["rudder"]
    rudder = plate([(x - rx, z - rz) for x, z in RUDDER], 0.1, "xz")
    out = {}
    for name, mesh in (("flap_l", flap_l), ("flap_r", flap_r), ("rudder", rudder)):
        sc = trimesh.Scene()
        sc.add_geometry(coloured(mesh, scheme["dark"]), node_name=name)
        out[name] = sc
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    grey = SCHEMES["grey"]
    for name, scene in [("body", body(grey, sim=True)), *surfaces(grey).items()]:
        path = OUT / f"f16sim_{name}.glb"
        data = scene.export(file_type="glb")
        path.write_bytes(data)
        print(f"wrote {path.name}: {len(data) / 1024:.1f} KiB")
    for name, scheme in SCHEMES.items():
        for kind, build in (("body", body), ("stab", stabilators)):
            path = OUT / f"f16_{kind}_{name}.glb"
            data = build(scheme).export(file_type="glb")
            path.write_bytes(data)
            print(f"wrote {path.name}: {len(data) / 1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
