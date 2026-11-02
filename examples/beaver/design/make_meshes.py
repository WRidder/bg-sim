# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "networkx>=3", "trimesh>=4.4", "shapely>=2.0", "mapbox-earcut>=1.0"]
# ///
"""The DHC-2 Beaver meshes of the 3D scenes (`meshes/*.glb`), built from simple solids.

    uv run examples/beaver/design/make_meshes.py

Body frame: x forward, y left, z up, metres, origin at the centre of gravity. The real aircraft
is 9.22 m long with a 14.63 m span and a 1.59 m constant chord [REP Table C.1]; the shapes here
are a sketch of it: a boxy lofted fuselage behind a radial-engine cowling, the high rectangular
wing on top of the cabin with one strut per side, the tailplane and fin, and two floats on
struts (decoration: the model has no water or ground contact).

The moving parts are separate meshes with their origin on their hinge line (`PIVOTS`, the same
numbers as in build_model.py), so the scene turns them with revolute joints: the elevator (both
halves), the ailerons (left, right), the flaps (left, right), the rudder and the two-blade
propeller (about the x axis).

Body paint schemes tell the aircraft of one model apart; the moving parts are one shared mesh
each (trim colour).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).resolve().parent.parent / "meshes"

# Geometry (m, body frame)
WING_LE, WING_TE = 0.55, -1.04      # wing leading/trailing edge x (chord 1.59 m)
WING_Z = 0.95                        # wing plane
SEMI = 7.315                         # semi-span
FLAP_Y = (0.75, 4.2)                 # flap span (left wing)
AIL_Y = (4.25, 7.2)                  # aileron span
SURF_CHORD = 0.42                    # chord of flaps and ailerons
HT_LE, HT_TE, HT_SEMI, HT_Z = -5.15, -6.35, 2.45, 0.42   # tailplane incl. the elevator
ELEV_CHORD = 0.45
FIN = [(-5.0, 0.55), (-5.75, 2.25), (-6.15, 2.25), (-6.05, 0.55)]   # fin + rudder outline (x, z)
RUDDER_HINGE_X = -6.05 + 0.42
PROP_X = 2.78
PIVOTS = {  # hinge point and axis of each moving part (build_model.PIVOTS)
    "elevator": ((HT_TE + ELEV_CHORD, 0.0, HT_Z), (0.0, 1.0, 0.0)),
    "aileron_l": ((WING_TE + SURF_CHORD, AIL_Y[0], WING_Z), (0.0, 1.0, 0.0)),
    "aileron_r": ((WING_TE + SURF_CHORD, -AIL_Y[0], WING_Z), (0.0, 1.0, 0.0)),
    "flap_l": ((WING_TE + SURF_CHORD, FLAP_Y[0], WING_Z), (0.0, 1.0, 0.0)),
    "flap_r": ((WING_TE + SURF_CHORD, -FLAP_Y[0], WING_Z), (0.0, 1.0, 0.0)),
    "rudder": ((RUDDER_HINGE_X, 0.0, 0.55), (0.0, 0.0, 1.0)),
    "prop": ((PROP_X, 0.0, 0.18), (1.0, 0.0, 0.0)),
}

SCHEMES = {
    "yellow": (232, 190, 40),
    "red": (196, 52, 44),
    "blue": (64, 104, 172),
    "white": (228, 228, 222),
    "green": (70, 128, 82),
    "orange": (226, 120, 40),
}
TRIM = (52, 56, 62)
GLASS = (40, 58, 74)
METAL = (150, 152, 156)
BLACK = (28, 28, 30)
FLOAT = (210, 210, 205)


def coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1)))
    return mesh


def loft(stations, segments=24, power=2.6) -> trimesh.Trimesh:
    """Body of super-elliptic sections (boxy for power > 2): (x, half-width, half-height, z-centre)."""
    rings = []
    ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    c, s = np.cos(ang), np.sin(ang)
    e = 2.0 / power
    cs = np.sign(c) * np.abs(c) ** e
    ss = np.sign(s) * np.abs(s) ** e
    for x, a, b, zc in stations:
        rings.append(np.column_stack([np.full(segments, x), a * cs, zc + b * ss]))
    verts = np.vstack(rings + [[[stations[0][0], 0, stations[0][3]]], [[stations[-1][0], 0, stations[-1][3]]]])
    nose, tail = len(verts) - 2, len(verts) - 1
    faces = []
    for r in range(len(rings) - 1):
        for k in range(segments):
            a = r * segments + k
            b = r * segments + (k + 1) % segments
            faces += [[a, a + segments, b + segments], [a, b + segments, b]]
    last = (len(rings) - 1) * segments
    for k in range(segments):
        faces.append([nose, (k + 1) % segments, k])
        faces.append([tail, last + k, last + (k + 1) % segments])
    mesh = trimesh.Trimesh(verts, np.array(faces), process=True)
    mesh.fix_normals()
    return mesh


def box(x0, x1, y0, y1, z0, z1) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=[abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


def cylinder_x(x0, x1, r, y=0.0, z=0.0, sections=28) -> trimesh.Trimesh:
    c = trimesh.creation.cylinder(radius=r, height=abs(x1 - x0), sections=sections)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0 + x1) / 2, y, z])
    return c


def rod(p0, p1, r) -> trimesh.Trimesh:
    """A cylinder between two points."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    return trimesh.creation.cylinder(radius=r, segment=[p0, p1], sections=10)


def plate(points, thickness, plane="xy") -> trimesh.Trimesh:
    """A flat plate of a polygon, centred on its plane (shapely + earcut)."""
    from shapely.geometry import Polygon
    m = trimesh.creation.extrude_polygon(Polygon(points), thickness)
    m.apply_translation([0.0, 0.0, -thickness / 2.0])
    if plane == "xz":   # local (x, y, z) -> (x, -z, y)
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.fix_normals()
    return m


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    m.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
    m.invert()
    m.fix_normals()
    return m


def wing_half(z, thick) -> trimesh.Trimesh:
    """Left wing without the flap and aileron cut-outs (a rectangle with the trailing-edge notches)."""
    hx = WING_TE + SURF_CHORD
    pts = [(WING_LE, 0.0), (WING_LE, SEMI), (WING_TE, SEMI), (WING_TE, AIL_Y[1]), (hx, AIL_Y[1]), (hx, AIL_Y[0]),
           (WING_TE, AIL_Y[0]), (WING_TE, FLAP_Y[1]), (hx, FLAP_Y[1]), (hx, FLAP_Y[0]), (WING_TE, FLAP_Y[0]),
           (WING_TE, 0.0)]
    m = plate(pts, thick, "xy")
    m.apply_translation([0.0, 0.0, z])
    return m


def body(rgb) -> trimesh.Scene:
    parts = []
    fus = loft([
        (2.62, 0.62, 0.62, 0.18), (2.0, 0.66, 0.66, 0.18), (1.2, 0.66, 0.78, 0.15), (0.0, 0.64, 0.82, 0.12),
        (-1.2, 0.58, 0.74, 0.12), (-2.6, 0.44, 0.58, 0.18), (-4.2, 0.28, 0.40, 0.28), (-5.6, 0.16, 0.24, 0.36),
        (-6.55, 0.06, 0.10, 0.42),
    ])
    parts.append(coloured(fus, rgb))
    # radial-engine cowling and the cylinder heads behind the propeller
    parts.append(coloured(cylinder_x(2.0, 2.68, 0.68, z=0.18), rgb))
    parts.append(coloured(cylinder_x(2.66, 2.70, 0.52, z=0.18), BLACK))
    for k in range(9):
        a = 2 * math.pi * k / 9
        parts.append(coloured(cylinder_x(2.52, 2.69, 0.07, y=0.42 * math.cos(a), z=0.18 + 0.42 * math.sin(a), sections=10),
                              METAL))
    # cabin windows (windscreen and side windows)
    parts.append(coloured(box(0.95, 1.25, -0.5, 0.5, 0.45, 0.88), GLASS))
    for sgn in (1.0, -1.0):
        parts.append(coloured(box(-0.9, 0.9, sgn * 0.645, sgn * 0.67, 0.38, 0.82), GLASS))
    # high wing on top of the cabin, both halves
    w = wing_half(WING_Z, 0.16)
    parts += [coloured(w, rgb), coloured(mirror_y(w), rgb)]
    # struts: from the lower fuselage to 2.9 m out under the wing
    for sgn in (1.0, -1.0):
        parts.append(coloured(rod((0.2, sgn * 0.55, -0.55), (0.1, sgn * 2.9, WING_Z - 0.08), 0.045), METAL))
    # tailplane without the elevator
    ht = plate([(HT_LE, -HT_SEMI), (HT_LE, HT_SEMI), (HT_TE + ELEV_CHORD, HT_SEMI), (HT_TE + ELEV_CHORD, -HT_SEMI)], 0.08)
    ht.apply_translation([0.0, 0.0, HT_Z])
    parts.append(coloured(ht, rgb))
    # fin without the rudder
    fin = plate([FIN[0], FIN[1], (RUDDER_HINGE_X - 0.12, FIN[1][1]), (RUDDER_HINGE_X, FIN[3][1])], 0.08, "xz")
    parts.append(coloured(fin, rgb))
    # floats (decoration) on struts
    for sgn in (1.0, -1.0):
        fl = loft([(3.0, 0.05, 0.05, -2.15), (2.4, 0.3, 0.26, -2.2), (0.8, 0.38, 0.32, -2.25), (-1.4, 0.36, 0.3, -2.25),
                   (-3.2, 0.2, 0.18, -2.18), (-4.4, 0.04, 0.04, -2.05)], power=2.2)
        fl.apply_translation([0.0, sgn * 1.35, 0.0])
        parts.append(coloured(fl, FLOAT))
        for x in (1.4, -0.9):
            parts.append(coloured(rod((x, sgn * 0.45, -0.7), (x, sgn * 1.35, -1.95), 0.04), METAL))
    scene = trimesh.Scene()
    for k, p in enumerate(parts):
        scene.add_geometry(p, node_name=f"part{k}")
    return scene


def moving_parts() -> dict[str, trimesh.Scene]:
    """Each moving part with its origin on its hinge point (PIVOTS)."""
    out = {}
    c = SURF_CHORD

    def at_pivot(mesh, name):
        (px, py, pz), _ = PIVOTS[name]
        mesh.apply_translation([-px, -py, -pz])
        sc = trimesh.Scene()
        sc.add_geometry(coloured(mesh, TRIM), node_name=name)
        out[name] = sc

    el = plate([(HT_TE + ELEV_CHORD, -HT_SEMI), (HT_TE + ELEV_CHORD, HT_SEMI), (HT_TE, HT_SEMI - 0.2), (HT_TE, -HT_SEMI + 0.2)], 0.06)
    el.apply_translation([0.0, 0.0, HT_Z])
    at_pivot(el, "elevator")
    for side, sgn in (("l", 1.0), ("r", -1.0)):
        for nm, (y0, y1) in (("aileron", AIL_Y), ("flap", FLAP_Y)):
            pts = [(WING_TE + c, sgn * y0), (WING_TE + c, sgn * y1), (WING_TE, sgn * y1), (WING_TE, sgn * y0)]
            m = plate(pts if sgn > 0 else pts[::-1], 0.08)
            m.apply_translation([0.0, 0.0, WING_Z])
            at_pivot(m, f"{nm}_{side}")
    rud = plate([(RUDDER_HINGE_X, 0.55), (RUDDER_HINGE_X - 0.12, FIN[1][1]), FIN[2], (FIN[3][0] - 0.25, 0.3),
                 (RUDDER_HINGE_X, 0.3)], 0.07, "xz")
    at_pivot(rud, "rudder")
    # two-blade propeller (2.59 m) and spinner
    blades = []
    for sgn in (1.0, -1.0):
        b = plate([(0.0, sgn * 0.12), (0.06, sgn * 1.295), (-0.06, sgn * 1.295), (-0.1, sgn * 0.12)], 0.035, "xy")
        b.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))   # blade in the y-z plane
        b.apply_translation([PROP_X, 0.0, 0.18])
        blades.append(b)
    spinner = trimesh.creation.cone(radius=0.2, height=0.32, sections=24)
    spinner.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    spinner.apply_translation([PROP_X, 0.0, 0.18])
    prop = trimesh.util.concatenate([coloured(blades[0], BLACK), coloured(blades[1], BLACK), coloured(spinner, METAL)])
    (px, py, pz), _ = PIVOTS["prop"]
    prop.apply_translation([-px, -py, -pz])
    sc = trimesh.Scene()
    sc.add_geometry(prop, node_name="prop")
    out["prop"] = sc
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for name, rgb in SCHEMES.items():
        path = OUT / f"beaver_body_{name}.glb"
        data = body(rgb).export(file_type="glb")
        path.write_bytes(data)
        print(f"wrote {path.name}: {len(data) / 1024:.1f} KiB")
    for name, scene in moving_parts().items():
        path = OUT / f"beaver_{name}.glb"
        data = scene.export(file_type="glb")
        path.write_bytes(data)
        print(f"wrote {path.name}: {len(data) / 1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
