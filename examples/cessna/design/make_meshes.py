# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "networkx>=3", "trimesh>=4.4", "shapely>=2.0", "mapbox-earcut>=1.0"]
# ///
"""The Cessna 172 meshes of the 3D scenes (`meshes/*.glb`), built from simple solids.

    uv run examples/cessna/design/make_meshes.py

Body frame: x forward, y left, z up, metres, origin at the centre of gravity of the model's
loading (station 45.6 in, 35.5 in above the datum's waterline; `c172_si.py`). The proportions
are the 172's (8.28 m long, 11 m span, 2.7 m high): a lofted fuselage with the cowling and the
cabin, the strut-braced high wing, the horizontal and the swept vertical tail, the fixed
tricycle gear (spring-steel main legs, the nose oleo), and a two-blade propeller.

The moving parts are separate meshes with their origin on their hinge line (`PIVOTS`; the same
numbers are in build_model.py), so the scene turns them with revolute joints: the ailerons, the
flaps, the elevator, the rudder, the propeller (about the shaft) and the nose wheel (steering).
The gear contact points of the model are the bottoms of the tyres.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).resolve().parent.parent / "meshes"

# ---- geometry (body frame, m)
HUB = (2.116, 0.0, -0.226)        # propeller hub (JSBSim thruster location)
Z_WING = 0.66                     # wing chord plane (underside of the cabin roof)
X_LE, CHORD = 0.50, 1.49          # leading edge (the MAC's, 25.9 in aft of the datum) and chord
HALF_SPAN = 5.50
Y_FLAP = (0.62, 2.95)             # flap span (left wing)
Y_AIL = (2.98, 5.20)              # aileron span
C_FLAP, C_AIL = 0.40, 0.36
X_TE = X_LE - CHORD
TAIL_X = (-4.55, -5.62)           # horizontal tail leading/trailing edge at the root
C_ELEV = 0.42
FIN = [(-4.0, 0.18), (-5.25, 1.62), (-5.70, 1.62), (-5.62, 0.18)]   # (x, z)
RUDDER = [(-5.55, 0.10), (-5.66, 1.58), (-6.05, 1.50), (-6.10, 0.10)]
GEAR = {"nose": (1.331, 0.0, -1.397), "left": (-0.320, 1.092, -1.295), "right": (-0.320, -1.092, -1.295)}
R_NOSE, R_MAIN = 0.18, 0.22
PIVOTS = {   # name: (hinge point, axis), body frame
    "aileron_l": ((X_TE + C_AIL, 0.5 * (Y_AIL[0] + Y_AIL[1]), Z_WING), (0.0, 1.0, 0.0)),
    "aileron_r": ((X_TE + C_AIL, -0.5 * (Y_AIL[0] + Y_AIL[1]), Z_WING), (0.0, 1.0, 0.0)),
    "flap_l": ((X_TE + C_FLAP, 0.5 * (Y_FLAP[0] + Y_FLAP[1]), Z_WING - 0.03), (0.0, 1.0, 0.0)),
    "flap_r": ((X_TE + C_FLAP, -0.5 * (Y_FLAP[0] + Y_FLAP[1]), Z_WING - 0.03), (0.0, 1.0, 0.0)),
    "elevator": ((TAIL_X[1] + C_ELEV, 0.0, 0.10), (0.0, 1.0, 0.0)),
    "rudder": ((-5.55, 0.0, 0.10), (-0.074, 0.0, 0.997)),
    "propeller": (HUB, (1.0, 0.0, 0.0)),
    "nosewheel": ((GEAR["nose"][0], 0.0, GEAR["nose"][2] + R_NOSE), (0.0, 0.0, 1.0)),
}

WHITE = (236, 236, 232)
STRIPE = (178, 34, 40)
DARK = (55, 58, 64)
GLASS = (60, 80, 100)
TYRE = (30, 30, 32)
METAL = (170, 172, 176)
SPINNER = (200, 40, 40)


def coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1)))
    return mesh


def loft(stations, segments=28) -> trimesh.Trimesh:
    """Body of super-elliptic sections: stations (x, half-width, half-height, z-centre), nose first."""
    rings = []
    for x, a, b, zc in stations:
        ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        c, s = np.cos(ang), np.sin(ang)
        # exponent 0.6 squares the sections a little (the 172's boxy cabin)
        cx = np.sign(c) * np.abs(c) ** 0.7
        sz = np.sign(s) * np.abs(s) ** 0.7
        rings.append(np.column_stack([np.full(segments, x), a * cx, zc + b * sz]))
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


def plate(points, thickness, plane="xy") -> trimesh.Trimesh:
    """A flat plate of any polygon, centred on its plane (shapely + earcut)."""
    from shapely.geometry import Polygon
    m = trimesh.creation.extrude_polygon(Polygon(points), thickness)
    m.apply_translation([0.0, 0.0, -thickness / 2.0])
    if plane == "xz":   # local (x, y, z) -> (x, -z, y)
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.fix_normals()
    return m


def rod(p0, p1, r, sections=12) -> trimesh.Trimesh:
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    m = trimesh.creation.cylinder(radius=r, segment=[p0, p1], sections=sections)
    return m


def wheel(centre, r, width) -> trimesh.Trimesh:
    c = np.asarray(centre, float)
    m = trimesh.creation.cylinder(radius=r, height=width, sections=24)
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
    m.apply_translation(c)
    return m


def wing_half() -> trimesh.Trimesh:
    """Left wing panel without the flap and the aileron (a slab with the cut-outs)."""
    pts = [(X_LE, 0.55), (X_LE, HALF_SPAN), (X_TE + 0.12, HALF_SPAN), (X_TE + 0.12, Y_AIL[1]),
           (X_TE + C_AIL, Y_AIL[1]), (X_TE + C_AIL, Y_AIL[0]), (X_TE + C_FLAP, Y_FLAP[1]),
           (X_TE + C_FLAP, Y_FLAP[0]), (X_TE, Y_FLAP[0]), (X_TE, 0.55)]
    m = plate(pts, 0.14, "xy")
    m.apply_translation([0.0, 0.0, Z_WING])
    return m


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    m.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
    m.invert()
    m.fix_normals()
    return m


def body() -> trimesh.Scene:
    parts = []
    fus = loft([
        (2.02, 0.16, 0.16, -0.20), (1.85, 0.46, 0.40, -0.15), (1.30, 0.55, 0.50, -0.06), (0.75, 0.56, 0.66, 0.06),
        (0.20, 0.56, 0.70, 0.04), (-0.60, 0.55, 0.68, 0.02), (-1.30, 0.48, 0.58, 0.05), (-2.40, 0.36, 0.42, 0.10),
        (-3.60, 0.24, 0.30, 0.10), (-4.80, 0.15, 0.22, 0.10), (-5.70, 0.08, 0.15, 0.10),
    ])
    parts.append(coloured(fus, WHITE))
    # cheat line and the windows (thin boxes on the sides) and the windshield
    for sgn in (1.0, -1.0):
        stripe = trimesh.creation.box(extents=[5.6, 0.02, 0.08])
        stripe.apply_translation([-1.6, sgn * 0.47, -0.08])
        parts.append(coloured(stripe, STRIPE))
        win = trimesh.creation.box(extents=[1.55, 0.02, 0.40])
        win.apply_translation([0.05, sgn * 0.565, 0.38])
        parts.append(coloured(win, GLASS))
    ws = trimesh.creation.box(extents=[0.02, 0.9, 0.45])
    ws.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-55), [0, 1, 0]))
    ws.apply_translation([0.86, 0.0, 0.52])
    parts.append(coloured(ws, GLASS))
    # wing panels (with the cut-outs for the moving surfaces) and the struts
    w = wing_half()
    parts += [coloured(w, WHITE), coloured(mirror_y(w), WHITE)]
    for sgn in (1.0, -1.0):
        parts.append(coloured(rod((0.15, sgn * 0.50, -0.38), (0.10, sgn * 2.70, Z_WING - 0.06), 0.035), WHITE))
    # horizontal tail (without the elevator) and the fin (without the rudder)
    ht = plate([(TAIL_X[0], 0.0), (TAIL_X[0] - 0.35, 1.72), (TAIL_X[1] + C_ELEV, 1.72), (TAIL_X[1] + C_ELEV, 0.0)], 0.07, "xy")
    ht.apply_translation([0.0, 0.0, 0.10])
    parts += [coloured(ht, WHITE), coloured(mirror_y(ht), WHITE)]
    fin = plate(FIN, 0.07, "xz")
    parts.append(coloured(fin, WHITE))
    # gear: spring-steel main legs, the nose oleo, wheel fairings left out
    for name in ("left", "right"):
        x, y, z = GEAR[name]
        sgn = 1.0 if y > 0 else -1.0
        hub = (x, y, z + R_MAIN)
        parts.append(coloured(rod((x + 0.05, sgn * 0.42, -0.50), hub, 0.035), METAL))
        parts.append(coloured(wheel(hub, R_MAIN, 0.16), TYRE))
    nx, _, nz = GEAR["nose"]
    parts.append(coloured(rod((nx, 0.0, -0.45), (nx, 0.0, nz + R_NOSE + 0.12), 0.04), METAL))
    # exhaust and the cowling's air inlets
    for sgn in (1.0, -1.0):
        inlet = trimesh.creation.box(extents=[0.04, 0.16, 0.10])
        inlet.apply_translation([2.0, sgn * 0.18, -0.05])
        parts.append(coloured(inlet, DARK))
    scene = trimesh.Scene()
    for k, p in enumerate(parts):
        scene.add_geometry(p, node_name=f"part{k}")
    return scene


def local(points_xy, pivot_xy):
    return [(x - pivot_xy[0], y - pivot_xy[1]) for x, y in points_xy]


def surfaces() -> dict[str, trimesh.Scene]:
    out = {}

    def scene_of(mesh, rgb, name):
        sc = trimesh.Scene()
        sc.add_geometry(coloured(mesh, rgb), node_name=name)
        return sc

    for side, sgn in (("l", 1.0), ("r", -1.0)):
        (px, py, pz), _ = PIVOTS[f"aileron_{side}"]
        y0, y1 = Y_AIL
        ail = plate([(0.0, sgn * y0 - py), (0.0, sgn * y1 - py), (-C_AIL, sgn * y1 - py), (-C_AIL, sgn * y0 - py)], 0.06)
        out[f"aileron_{side}"] = scene_of(ail, WHITE, f"aileron_{side}")
        (px, py, pz), _ = PIVOTS[f"flap_{side}"]
        y0, y1 = Y_FLAP
        flp = plate([(0.0, sgn * y0 - py), (0.0, sgn * y1 - py), (-C_FLAP, sgn * y1 - py), (-C_FLAP, sgn * y0 - py)], 0.06)
        out[f"flap_{side}"] = scene_of(flp, WHITE, f"flap_{side}")
    elev = plate([(0.0, -1.72), (0.0, 1.72), (-C_ELEV, 1.72), (-C_ELEV, -1.72)], 0.05)
    out["elevator"] = scene_of(elev, WHITE, "elevator")
    (rx, _, rz), _ = PIVOTS["rudder"]
    rud = plate([(x - rx, z - rz) for x, z in RUDDER], 0.06, "xz")
    sc = trimesh.Scene()
    sc.add_geometry(coloured(rud, WHITE), node_name="rudder")
    stripe = plate([(x - rx, z - rz) for x, z in [(-5.60, 0.9), (-5.62, 1.1), (-6.07, 1.04), (-6.08, 0.84)]], 0.065, "xz")
    sc.add_geometry(coloured(stripe, STRIPE), node_name="rudder_stripe")
    out["rudder"] = sc
    # propeller: two blades and the spinner, origin on the hub, spinning about x
    prop = trimesh.Scene()
    for k, sgn in enumerate((1.0, -1.0)):
        blade = trimesh.creation.box(extents=[0.03, 0.12, 0.90])
        blade.apply_transform(trimesh.transformations.rotation_matrix(math.radians(15) * sgn, [0, 0, 1]))
        blade.apply_translation([0.10, 0.0, sgn * 0.50])
        prop.add_geometry(coloured(blade, DARK), node_name=f"blade{k}")
    spinner = trimesh.creation.cone(radius=0.16, height=0.32, sections=20)
    spinner.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    spinner.apply_translation([0.0, 0.0, 0.0])
    prop.add_geometry(coloured(spinner, SPINNER), node_name="spinner")
    out["propeller"] = prop
    # nose wheel and fork, origin on the steering axis at the axle
    nw = trimesh.Scene()
    nw.add_geometry(coloured(wheel((0.0, 0.0, 0.0), R_NOSE, 0.13), TYRE), node_name="tyre")
    for sgn in (1.0, -1.0):
        nw.add_geometry(coloured(rod((0.0, sgn * 0.09, 0.0), (0.0, sgn * 0.09, 0.26), 0.02), METAL), node_name=f"fork{sgn:+.0f}")
    out["nosewheel"] = nw
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for name, scene in [("body", body()), *surfaces().items()]:
        path = OUT / f"c172_{name}.glb"
        data = scene.export(file_type="glb")
        path.write_bytes(data)
        print(f"wrote {path.name}: {len(data) / 1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
