"""The 3D scene of the excavator example (``scenes/excavator.sdf``), written by
``build_model.py`` from the geometry in ``exc_geom.py``. Simple solids only.

Z up, metres. The model is planar in its x-y plane; the scene uses the SDF X-Z plane (model x
is SDF X, model y is SDF Z, the depth is SDF Y), and the model's counter-clockwise joint angles
are rotations about -Y, as in robot-arm-2d. The boom foot pin O is the world origin; the
ground (the soil surface of the model) is at Z = Y_GROUND.

Links: ``base`` (upper structure, undercarriage, ground, and every bar that is drawn between
two moving points: the cylinder barrels and rods, the rocker and the H-link, bound with
``segment`` bindings), ``boom``, ``arm`` and ``bucket`` (bound through the joints ``boom_joint``,
``arm_joint`` and ``bucket_joint`` to the joint angles). ``soil_load`` in the bucket is scaled with the
bucket fill.
"""

from __future__ import annotations

import math

import exc_geom as G


def _f(x: float) -> str:
    s = f"{x:.6g}"
    return "0" if s in ("-0", "0") else s


def _visual(name: str, pose, geom: str, rgba) -> str:
    return (f'      <visual name="{name}">\n'
            f'        <pose>{" ".join(_f(v) for v in pose)}</pose>\n'
            f'        <geometry>{geom}</geometry>\n'
            f'        <material><diffuse>{" ".join(_f(v) for v in rgba)}</diffuse></material>\n'
            f'      </visual>\n')


def _box(sx, sy, sz) -> str:
    return f"<box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box>"


def _cyl(r, length) -> str:
    return f"<cylinder><radius>{_f(r)}</radius><length>{_f(length)}</length></cylinder>"


def _bar(name, a, b, width, height, rgba, y=0.0) -> str:
    """A box from planar point a to b (model x-y -> SDF X-Z), `height` across in the plane."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    th = math.atan2(dy, dx)
    return _visual(name, ((a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2, 0, -th, 0), _box(length, width, height), rgba)


def _pin(name, p, r, length, rgba) -> str:
    return _visual(name, (p[0], 0, p[1], math.pi / 2, 0, 0), _cyl(r, length), rgba)


YELLOW = (0.96, 0.72, 0.08, 1)
DARK = (0.16, 0.16, 0.17, 1)
STEEL = (0.62, 0.64, 0.67, 1)
CHROME = (0.85, 0.87, 0.9, 1)
SOIL = (0.47, 0.36, 0.24, 1)
GLASS = (0.35, 0.55, 0.7, 0.6)

#: segment visuals: name -> (radius, depth y)
CYL_VISUALS = {
    "boom": [("boom_barrel_l", "boom_rod_l", 0.42), ("boom_barrel_r", "boom_rod_r", -0.42)],
    "arm": [("arm_barrel", "arm_rod", 0.0)],
    "bucket": [("bucket_barrel", "bucket_rod", 0.0)],
}
LINK_VISUALS = [("rocker_l", 0.3), ("rocker_r", -0.3), ("hlink_l", 0.3), ("hlink_r", -0.3)]
BORE = {"boom": 0.12, "arm": 0.14, "bucket": 0.12}
ROD = {"boom": 0.085, "arm": 0.10, "bucket": 0.085}


def scene_sdf() -> str:
    g = G.GEOM
    yg = G.Y_GROUND
    w = []
    # ---------------------------------------------------------------- ground and machine
    w.append(_visual("ground", (3.0, 0, yg - 0.1, 0, 0, 0), _box(15.0, 6.0, 0.2), (0.55, 0.47, 0.36, 1)))
    w.append(_visual("dig_zone", (4.6, 0, yg + 0.002, 0, 0, 0), _box(3.6, 1.6, 0.004), (0.36, 0.27, 0.18, 1)))
    # undercarriage: two tracks and the car body (the swing centre 1.0 m behind the boom foot)
    xs = -1.0
    for side, y in (("l", 1.2), ("r", -1.2)):
        w.append(_visual(f"track_{side}", (xs, y, yg + 0.45, 0, 0, 0), _box(4.45, 0.6, 0.9), DARK))
        for k, xi in enumerate((-1.75, 1.75)):
            w.append(_visual(f"idler_{side}{k}", (xs + xi, y, yg + 0.45, math.pi / 2, 0, 0), _cyl(0.42, 0.62), STEEL))
    w.append(_visual("car_body", (xs, 0, yg + 0.75, 0, 0, 0), _box(2.4, 1.9, 0.5), DARK))
    w.append(_visual("swing_ring", (xs, 0, yg + 1.05, 0, 0, 0), _cyl(0.9, 0.12), STEEL))
    # upper structure: frame, engine hood, counterweight, cab
    z0 = yg + 1.12
    w.append(_visual("upper_frame", (-1.25, 0, z0 + 0.15, 0, 0, 0), _box(3.6, 2.6, 0.3), YELLOW))
    w.append(_visual("engine_hood", (-2.0, -0.25, z0 + 0.65, 0, 0, 0), _box(1.7, 2.1, 0.7), YELLOW))
    w.append(_visual("counterweight", (-3.0, 0, z0 + 0.55, 0, 0, 0), _box(0.6, 2.6, 0.9), (0.2, 0.2, 0.21, 1)))
    w.append(_visual("cab", (-0.45, 0.85, z0 + 1.1, 0, 0, 0), _box(1.5, 0.9, 1.6), YELLOW))
    w.append(_visual("cab_glass", (0.31, 0.85, z0 + 1.2, 0, 0, 0), _box(0.02, 0.8, 1.2), GLASS))
    w.append(_visual("boom_foot", (0.0, 0, (z0 + 0.3) / 2, 0, 0, 0), _box(0.7, 0.9, -z0 + 0.3 + 0.2), YELLOW))
    w.append(_visual("boom_cyl_foot", (g["A1"][0], 0, (g["A1"][1] + z0 + 0.3) / 2, 0, 0, 0),
                     _box(0.35, 1.05, abs(g["A1"][1] - z0 - 0.3) + 0.2), YELLOW))
    w.append(_pin("pin_A1", g["A1"], 0.06, 1.1, STEEL))
    w.append(_pin("pin_O", (0.0, 0.0), 0.07, 0.95, STEEL))
    # cylinders, rocker and H-link: placed every frame by segment bindings (world points)
    for name, vis in CYL_VISUALS.items():
        rb, rr = BORE[name] / 2 + 0.035, ROD[name] / 2
        for barrel, rod, y in vis:
            w.append(_visual(barrel, (0, y, 0, 0, 0, 0), _cyl(rb, 1.0), YELLOW))
            w.append(_visual(rod, (0, y, 0, 0, 0, 0), _cyl(rr, 1.0), CHROME))
    for name, y in LINK_VISUALS:
        w.append(_visual(name, (0, y, 0, 0, 0, 0), _box(1.0, 0.06, 0.14), DARK))

    # ---------------------------------------------------------------- boom (frame O, x to C)
    L1, L2, L3 = G.L1, G.L2, G.L3
    K = (2.8, 0.45)
    b = []
    b.append(_bar("boom_lower", (0, 0), K, 0.55, 0.62, YELLOW))
    b.append(_bar("boom_upper", K, (L1, 0), 0.5, 0.55, YELLOW))
    b.append(_bar("boom_bracket_B1", (g["B1"][0], g["B1"][1]), (g["B1"][0], 0.35), 0.75, 0.3, YELLOW))
    b.append(_bar("boom_bracket_A2", (g["A2"][0], 0.55), (g["A2"][0], g["A2"][1]), 0.3, 0.3, YELLOW))
    b.append(_pin("pin_B1", g["B1"], 0.055, 1.05, STEEL))
    b.append(_pin("pin_A2", g["A2"], 0.06, 0.4, STEEL))
    b.append(_pin("pin_C", (L1, 0), 0.07, 0.6, STEEL))

    # ---------------------------------------------------------------- arm (frame C, x to Q)
    a = []
    a.append(_bar("arm_tail", g["B2"], (0.3, 0.12), 0.42, 0.42, YELLOW))
    a.append(_bar("arm_main", (0.3, 0.12), (L2, 0), 0.38, 0.4, YELLOW))
    a.append(_bar("arm_bracket_A3", (0.277, 0.12), g["A3"], 0.25, 0.25, YELLOW))
    a.append(_pin("pin_B2", g["B2"], 0.06, 0.5, STEEL))
    a.append(_pin("pin_A3", g["A3"], 0.055, 0.35, STEEL))
    a.append(_pin("pin_R", g["R"], 0.05, 0.75, STEEL))
    a.append(_pin("pin_Q", (L2, 0), 0.06, 0.75, STEEL))

    # ---------------------------------------------------------------- bucket (frame Q, x to T)
    k = []
    shell = [(0.0, 0.05), (0.12, 0.52), (0.72, 0.80), (1.28, 0.52), (L3, 0.0)]
    for i, (p, q) in enumerate(zip(shell, shell[1:])):
        k.append(_bar(f"bucket_shell_{i}", p, q, 1.2, 0.04, YELLOW))
    for side, y in (("l", 0.6), ("r", -0.6)):
        k.append(_visual(f"bucket_side_{side}", (0.72, y, 0.36, 0, 0, 0), _box(1.3, 0.03, 0.66), YELLOW))
    k.append(_bar("bucket_ears", (0.0, 0.0), g["P"], 0.5, 0.12, YELLOW))
    k.append(_pin("pin_P", g["P"], 0.05, 0.75, STEEL))
    for i in range(5):
        y = -0.48 + 0.24 * i
        k.append(_visual(f"tooth_{i}", (L3 + 0.06, y, 0.02, 0, 0.25, 0), _box(0.16, 0.07, 0.05), DARK))
    k.append(_visual("soil_load", (0.72, 0, 0.38, 0, 0, 0), _box(1.0, 1.12, 0.62), SOIL))

    def link(name, pose, visuals) -> str:
        return (f'    <link name="{name}">\n      <pose>{" ".join(_f(v) for v in pose)}</pose>\n'
                + "".join(visuals) + "    </link>\n")

    def joint(name, parent, child) -> str:
        return (f'    <joint name="{name}" type="revolute">\n      <parent>{parent}</parent>\n'
                f'      <child>{child}</child>\n      <axis><xyz>0 -1 0</xyz></axis>\n    </joint>\n')

    head = (
        '<?xml version="1.0"?>\n'
        "<!--\n"
        "  excavator: the front of a 20-t class hydraulic excavator (boom 5.70 m, arm 2.90 m,\n"
        "  bucket 1.50 m) in the vertical X-Z plane, written by design/build_model.py.\n"
        "  Model x is SDF X, model y is SDF Z (the boom foot pin is the origin, the soil surface is\n"
        f"  at Z = {G.Y_GROUND}); the joints turn about -Y with the model's joint angles. The cylinders,\n"
        "  the rocker and the H-link are bars between two moving points (segment bindings).\n"
        "-->\n"
        '<sdf version="1.9">\n  <model name="excavator">\n'
    )
    return (head
            + link("base", (0, 0, 0, 0, 0, 0), w)
            + link("boom", (0, 0, 0, 0, 0, 0), b)
            + link("arm", (L1, 0, 0, 0, 0, 0), a)
            + link("bucket", (L1 + L2, 0, 0, 0, 0, 0), k)
            + joint("boom_joint", "base", "boom") + joint("arm_joint", "boom", "arm") + joint("bucket_joint", "arm", "bucket")
            + "  </model>\n</sdf>\n")
