"""The 3D scene of the suction-gripper example (``scenes/suction-gripper.sdf``), written by
``build_model.py`` from the numbers in ``params.py``.

Z up, metres. The pick conveyor and the place table both have their top at z = 0 (the plane of
the model's ``Table`` contact surface); the parcel starts at x = 0 and is placed at
x = L_move. Links whose poses are bound to signals:

* ``parcel``   the parcel's centre of mass (``Pose/qw..pz``); the box is offset by -(cx, cy, cz);
* ``gripper``  the cup mount plane G (``Path/g``), z up; the bellows hang from it to z = -L0;
* ``zaxis``    the untilted flange above G (``Path/gfl``), the vertical axis tube;
* ``carriage`` the gantry carriage on the beam (``Path/gcar``).

The visuals ``bellows_<n>`` (coloured by the cup utilisation U) and ``lip_<n>`` (coloured by
the cup vacuum) belong to the gripper link.
"""

from __future__ import annotations

import params as P


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


def scene_sdf() -> str:
    pa, cup, mo = P.PARCEL, P.CUP, P.MOTION
    L, W, H = pa["L_p"], pa["W_p"], pa["H_p"]
    L0 = cup["L0"]
    x_place = mo["L_move"]
    steel = (0.55, 0.58, 0.62, 1)
    dark = (0.18, 0.19, 0.21, 1)
    alu = (0.74, 0.76, 0.79, 1)
    floor_z = -0.8

    # ---------------------------------------------------------------- world (fixed)
    w = []
    w.append(_visual("floor", (0.5, 0, floor_z - 0.01, 0, 0, 0), _box(3.4, 2.0, 0.02), (0.5, 0.52, 0.54, 1)))
    # pick conveyor: belt from x = -0.75 to 0.45, rollers at the ends, frame and legs
    x0c, x1c = -0.75, 0.45
    w.append(_visual("belt", ((x0c + x1c) / 2, 0, -0.01, 0, 0, 0), _box(x1c - x0c, 0.62, 0.02), (0.12, 0.13, 0.14, 1)))
    for k, xr in enumerate((x0c, x1c)):
        w.append(_visual(f"roller_{k}", (xr, 0, -0.03, 1.5708, 0, 0), _cyl(0.03, 0.64), alu))
    for s in (-1, 1):
        w.append(_visual(f"conv_side_{'l' if s > 0 else 'r'}", ((x0c + x1c) / 2, s * 0.34, -0.03, 0, 0, 0),
                         _box(x1c - x0c + 0.08, 0.04, 0.08), (0.2, 0.45, 0.75, 1)))
    for k, (xl, yl) in enumerate(((x0c + 0.05, 0.3), (x0c + 0.05, -0.3), (x1c - 0.05, 0.3), (x1c - 0.05, -0.3))):
        w.append(_visual(f"conv_leg_{k}", (xl, yl, (floor_z - 0.07) / 2, 0, 0, 0), _box(0.05, 0.05, -floor_z - 0.07), steel))
    # place table: steel top from x = 0.5 to 1.6 with a place mark at x = L_move
    x0t, x1t = 0.5, 1.6
    w.append(_visual("table_top", ((x0t + x1t) / 2, 0, -0.015, 0, 0, 0), _box(x1t - x0t, 0.8, 0.03), (0.42, 0.44, 0.47, 1)))
    for k, (xl, yl) in enumerate(((x0t + 0.05, 0.35), (x0t + 0.05, -0.35), (x1t - 0.05, 0.35), (x1t - 0.05, -0.35))):
        w.append(_visual(f"table_leg_{k}", (xl, yl, (floor_z - 0.03) / 2, 0, 0, 0), _box(0.05, 0.05, -floor_z - 0.03), steel))
    # place mark: the parcel footprint outlined in yellow
    t = 0.012
    for k, (dx, dy, sx, sy) in enumerate(((0, W / 2 + t, L + 2 * t, t), (0, -W / 2 - t, L + 2 * t, t),
                                          (L / 2 + t, 0, t, W), (-L / 2 - t, 0, t, W))):
        w.append(_visual(f"place_mark_{k}", (x_place + dx, dy, 0.0005, 0, 0, 0), _box(sx, sy, 0.001), (0.95, 0.78, 0.1, 1)))
    # gantry: two posts and the beam along x at the carriage height
    zb = 1.6
    for k, xp in enumerate((-0.95, 1.85)):
        w.append(_visual(f"post_{k}", (xp, 0.45, (floor_z + zb + 0.1) / 2, 0, 0, 0), _box(0.1, 0.1, zb + 0.1 - floor_z), (0.95, 0.55, 0.12, 1)))
    w.append(_visual("beam", (0.45, 0.45, zb + 0.1, 0, 0, 0), _box(2.9, 0.12, 0.14), (0.95, 0.55, 0.12, 1)))
    w.append(_visual("rail", (0.45, 0.375, zb + 0.1, 0, 0, 0), _box(2.9, 0.03, 0.04), alu))

    # ---------------------------------------------------------------- carriage and Z axis
    car = [
        _visual("carriage_plate", (0, 0.33, 0.1, 0, 0, 0), _box(0.26, 0.04, 0.26), (0.25, 0.27, 0.3, 1)),
        _visual("carriage_arm", (0, 0.16, 0.1, 0, 0, 0), _box(0.1, 0.3, 0.12), (0.25, 0.27, 0.3, 1)),
        _visual("z_guide", (0, 0, 0.1, 0, 0, 0), _box(0.12, 0.12, 0.3), (0.95, 0.55, 0.12, 1)),
    ]
    zax = [
        _visual("z_tube", (0, 0, 0.75, 0, 0, 0), _box(0.07, 0.07, 1.5), alu),
        _visual("z_flange", (0, 0, 0.0, 0, 0, 0), _cyl(0.06, 0.02), dark),
    ]

    # ---------------------------------------------------------------- gripper (G, z up)
    hf = 0.12
    gr = [
        _visual("wrist", (0, 0, hf / 2 + 0.01, 1.5708, 0, 0), _cyl(0.035, 0.08), dark),
        _visual("wrist_post", (0, 0, hf / 2 + 0.02, 0, 0, 0), _box(0.05, 0.05, hf - 0.02), dark),
        _visual("head_plate", (0, 0, 0.012, 0, 0, 0), _box(2 * P.PX + 0.1, 2 * P.PY + 0.08, 0.024), (0.82, 0.84, 0.86, 1)),
        _visual("manifold", (0, 0, 0.04, 0, 0, 0), _box(2 * P.PX, 0.05, 0.032), (0.2, 0.42, 0.78, 1)),
        _visual("generator", (0.03, 0.06, 0.05, 0, 0, 0), _box(0.09, 0.03, 0.03), (0.15, 0.6, 0.35, 1)),
    ]
    for n, (cx_, cy_) in enumerate(P.CUPS, start=1):
        gr.append(_visual(f"fitting_{n}", (cx_, cy_, -0.004, 0, 0, 0), _cyl(0.012, 0.008), alu))
        gr.append(_visual(f"bellows_{n}", (cx_, cy_, -0.008 - (L0 - 0.016) / 2, 0, 0, 0),
                          _cyl(cup["D_lip"] * 0.38, L0 - 0.016), (0.35, 0.35, 0.38, 1)))
        gr.append(_visual(f"lip_{n}", (cx_, cy_, -L0 + 0.004, 0, 0, 0), _cyl(cup["D_lip"] / 2, 0.008), (0.1, 0.1, 0.12, 1)))

    # ---------------------------------------------------------------- parcel (centre of mass)
    bx, by, bz = -pa["cx"], -pa["cy"], -pa["cz"]
    card = (0.72, 0.53, 0.32, 1)
    tape = (0.84, 0.7, 0.45, 1)
    pc = [
        _visual("carton", (bx, by, bz, 0, 0, 0), _box(L, W, H), card),
        _visual("tape_top", (bx, by, bz + H / 2 + 0.0005, 0, 0, 0), _box(L + 0.002, 0.05, 0.001), tape),
        _visual("tape_front", (bx + L / 2 + 0.0005, by, bz + H / 2 - 0.04, 0, 0, 0), _box(0.001, 0.05, 0.08), tape),
        _visual("tape_back", (bx - L / 2 - 0.0005, by, bz + H / 2 - 0.04, 0, 0, 0), _box(0.001, 0.05, 0.08), tape),
        _visual("flap_seam", (bx, by, bz + H / 2 + 0.0008, 0, 0, 0), _box(L + 0.002, 0.003, 0.0012), (0.55, 0.4, 0.22, 1)),
        _visual("label", (bx + L / 4, by - W / 2 - 0.0005, bz + 0.03, 0, 0, 0), _box(0.12, 0.001, 0.08), (0.96, 0.96, 0.94, 1)),
        _visual("label_bar", (bx + L / 4, by - W / 2 - 0.0012, bz + 0.045, 0, 0, 0), _box(0.09, 0.001, 0.02), (0.1, 0.1, 0.1, 1)),
        _visual("arrow_up", (bx - L / 4, by - W / 2 - 0.0005, bz + 0.05, 0, 0, 0), _box(0.012, 0.001, 0.07), (0.15, 0.15, 0.15, 1)),
    ]

    def link(name, visuals, pose=(0, 0, 0, 0, 0, 0)):
        return (f'    <link name="{name}">\n      <pose>{" ".join(_f(v) for v in pose)}</pose>\n'
                + "".join(visuals) + "    </link>\n")

    return ("<?xml version=\"1.0\"?>\n<!--\n" + __doc__.strip().replace("--", "-") + "\n-->\n"
            '<sdf version="1.9">\n  <model name="suction-gripper">\n'
            + link("world_fixed", w)
            + link("carriage", car, (0, 0, zb, 0, 0, 0))
            + link("zaxis", zax, (0, 0, 0.6, 0, 0, 0))
            + link("gripper", gr, (0, 0, H / 2 + L0, 0, 0, 0))
            + link("parcel", pc, (0, 0, H / 2, 0, 0, 0))
            + "  </model>\n</sdf>\n")
