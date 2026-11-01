"""The 3D scenes of the suction-cup example (``scenes/suction-cup.sdf`` with one cup,
``scenes/suction-cup-compare.sdf`` with the nonlinear and the linear cup side by side), written by
``build_model.py`` from the numbers in ``params.py``.

Z up, metres; the table top is the plane z = 0 of the model's ``Table`` contact surface. Links
whose poses are bound to signals:

* ``tool``       the cup mount frame T (``Tool/g``): flange, wrist and the cup fittings;
* ``box_<k>``    the payload of cup k at its centre of mass (``Pose<s>/qw..pz``); the box is offset
  by -(cx, cy, cz).

The cup itself lives in the static link ``cups``: its visuals are placed every frame by segment
bindings from ``Mon<s>/bel``, ``ring1``, ``ring2`` and ``lip`` (world end points), so the
see-through bellows body stretches, compresses and tilts with the cup, the two fold rings ride
on it, and the lip disc sits on the box (coloured by the cup utilisation U).
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


#: box colours per cup: the nonlinear cup's payload blue-grey, the linear cup's sand
BOX_RGBA = {1: (0.36, 0.47, 0.62, 1), 2: (0.78, 0.62, 0.36, 1)}


def scene_sdf(mounts: list[tuple[float, float]]) -> str:
    """``mounts``: the cup mount (x, y) in the tool frame, cup 1 first."""
    b, c = P.BOX, P.CUP
    L, W, H = b["L_p"], b["W_p"], b["H_p"]
    L0, D = c["L0"], c["D_lip"]
    steel = (0.55, 0.58, 0.62, 1)
    dark = (0.18, 0.19, 0.21, 1)
    alu = (0.74, 0.76, 0.79, 1)
    leg_z = -0.3      # a compact bench centred under the cup, so a camera fit frames the cup

    # ---------------------------------------------------------------- world (fixed)
    w = [
        _visual("table_top", (0, 0, -0.015, 0, 0, 0), _box(1.3, 0.5, 0.03), (0.42, 0.44, 0.47, 1)),
        _visual("table_mat", (0, 0, 0.0005, 0, 0, 0), _box(1.24, 0.44, 0.001), (0.25, 0.27, 0.3, 1)),
    ]
    for k, (xl, yl) in enumerate(((-0.6, 0.2), (-0.6, -0.2), (0.6, 0.2), (0.6, -0.2))):
        w.append(_visual(f"table_leg_{k}", (xl, yl, (leg_z - 0.03) / 2, 0, 0, 0), _box(0.04, 0.04, -leg_z - 0.03), steel))
    # pick mark: the box footprint under each cup
    t = 0.006
    for n, (mx, my) in enumerate(mounts, start=1):
        for k, (dx, dy, sx, sy) in enumerate(((0, W / 2 + t, L + 2 * t, t), (0, -W / 2 - t, L + 2 * t, t),
                                              (L / 2 + t, 0, t, W), (-L / 2 - t, 0, t, W))):
            w.append(_visual(f"pick_mark_{n}_{k}", (mx + dx, my + dy, 0.0012, 0, 0, 0), _box(sx, sy, 0.001), (0.95, 0.78, 0.1, 1)))

    # ---------------------------------------------------------------- tool (cup mount frame, z up)
    span = max(abs(my) for _, my in mounts) * 2 + 0.06
    tl = [
        _visual("flange", (0, 0, 0.012, 0, 0, 0), _box(0.07, span, 0.012), (0.82, 0.84, 0.86, 1)),
        _visual("wrist", (0, 0, 0.05, 0, 0, 0), _cyl(0.032, 0.06), dark),
        _visual("arm", (0, 0, 0.18, 0, 0, 0), _box(0.06, 0.06, 0.2), (0.95, 0.55, 0.12, 1)),
        _visual("axis_mark", (0.036, 0, 0.05, 0, 0, 0), _box(0.004, 0.02, 0.05), (0.9, 0.9, 0.9, 1)),
    ]
    for n, (mx, my) in enumerate(mounts, start=1):
        tl.append(_visual(f"fitting_{n}", (mx, my, 0.002, 0, 0, 0), _cyl(0.009, 0.008), alu))
        tl.append(_visual(f"hose_{n}", (mx + 0.02, my, 0.012, 0, 1.5708, 0), _cyl(0.003, 0.03), (0.2, 0.42, 0.78, 1)))

    # ---------------------------------------------------------------- the cups (segment bindings)
    cups = []
    for n, (mx, my) in enumerate(mounts, start=1):
        z = H + L0 / 2
        cups.append(_visual(f"bellows_{n}", (mx, my, z, 0, 0, 0), _cyl(D * 0.40, L0), (0.25, 0.27, 0.32, 0.35)))
        cups.append(_visual(f"ring1_{n}", (mx, my, z, 0, 0, 0), _cyl(D * 0.46, 0.004), (0.12, 0.13, 0.15, 1)))
        cups.append(_visual(f"ring2_{n}", (mx, my, z, 0, 0, 0), _cyl(D * 0.46, 0.004), (0.12, 0.13, 0.15, 1)))
        cups.append(_visual(f"lip_{n}", (mx, my, H + 0.0015, 0, 0, 0), _cyl(D / 2, 0.003), (0.1, 0.1, 0.12, 1)))

    def link(name, visuals, pose=(0, 0, 0, 0, 0, 0)):
        return (f'    <link name="{name}">\n      <pose>{" ".join(_f(v) for v in pose)}</pose>\n'
                + "".join(visuals) + "    </link>\n")

    boxes = ""
    for n, (mx, my) in enumerate(mounts, start=1):
        bx, by, bz = -b["cx"], -b["cy"], -b["cz"]
        bv = [
            _visual(f"box_body_{n}", (bx, by, bz, 0, 0, 0), _box(L, W, H), BOX_RGBA.get(n, BOX_RGBA[1])),
            _visual(f"box_top_{n}", (bx, by, bz + H / 2 + 0.0004, 0, 0, 0), _box(L - 0.02, W - 0.02, 0.0008), (0.9, 0.9, 0.88, 1)),
            _visual(f"box_stripe_{n}", (bx + L / 2 + 0.0004, by, bz, 0, 0, 0), _box(0.0008, W * 0.6, H * 0.4), (0.95, 0.95, 0.95, 1)),
        ]
        boxes += link(f"box_{n}", bv, (mx + b["cx"], my + b["cy"], H / 2 + b["cz"], 0, 0, 0))

    return ("<?xml version=\"1.0\"?>\n<!--\n" + __doc__.strip().replace("--", "-") + "\n-->\n"
            '<sdf version="1.9">\n  <model name="suction-cup">\n'
            + link("world_fixed", w)
            + link("tool", tl, (0, 0, H + L0, 0, 0, 0))
            + link("cups", cups)
            + boxes
            + "  </model>\n</sdf>\n")
