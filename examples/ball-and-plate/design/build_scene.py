# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Writes ``scenes/ball-and-plate.sdf``, the 3D scene of the `ball-and-plate` example.

    uv run examples/ball-and-plate/design/build_scene.py

Simple solids only, Z-up, metres, the world frame of the models (gimbal centre at
(0, 0, H_PIVOT)). Link poses are those of the rig at rest (plate level, ball at the centre);
the runs move the links through the bindings of the models:

* ``plate`` follows ``PosePlate/g[1..7]`` (plate frame at the gimbal centre, z up): the acrylic
  plate with a 5 cm grid, the centre cross and the two rod lugs under the edges, plus the two
  reference paths (figure-8: orange dots, circle: blue dots) drawn on the surface;
* ``ball`` follows ``PoseBall/g[1..7]``: a steel ball with two painted bands, so that its rolling
  is visible;
* ``crank_x_link``/``crank_y_link`` turn on the revolute joints ``crank_x``/``crank_y`` (about -y and +x at the
  servo shafts), bound to the servo angles ``ThetaX/y`` and ``ThetaY/y``;
* ``rod_x``/``rod_y`` follow ``Viz/rodx``/``Viz/rody`` (library/RigViz.jl: from the crank tips to
  the lugs under the plate);
* ``target`` follows ``Viz/target`` (the reference position on the plate, a red ring);
* ``base`` is fixed: base plate, the gimbal post and the two servo bodies.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "scenes" / "ball-and-plate.sdf"

BASE = (0.20, 0.21, 0.23, 1)
POST = (0.55, 0.57, 0.6, 1)
SERVO = (0.12, 0.12, 0.14, 1)
LABEL = (0.95, 0.75, 0.15, 1)
METAL = (0.75, 0.77, 0.8, 1)
PLATE = (0.93, 0.94, 0.96, 1)
GRID = (0.45, 0.5, 0.58, 1)
CROSS = (0.2, 0.25, 0.32, 1)
STEEL = (0.7, 0.72, 0.76, 1)
BAND_A = (0.9, 0.2, 0.15, 1)
BAND_B = (0.15, 0.35, 0.85, 1)
FIG8 = (0.95, 0.55, 0.1, 1)
CIRCLE = (0.25, 0.55, 0.95, 1)
TARGET = (0.9, 0.1, 0.1, 1)

Z_SHAFT = rig.H_PIVOT - rig.L_ROD          # servo shaft height (RigViz z_s)
L_ATT = rig.L_ROD_X                        # rod lug distance from the centre
ROD_LEN = rig.H_PIVOT - rig.T_PLATE / 2 - Z_SHAFT


def fmt(v) -> str:
    return " ".join(f"{float(x):.6g}" if abs(float(x)) > 1e-12 else "0" for x in v)


def z_to_rpy(axis):
    """Roll-pitch-yaw of a rotation that takes z to the unit `axis` (x, y or z)."""
    a = tuple(np.round(axis, 9))
    return {(1, 0, 0): (0, math.pi / 2, 0), (0, 1, 0): (-math.pi / 2, 0, 0), (0, 0, 1): (0, 0, 0)}[a]


class Link:
    def __init__(self, name, pose=(0, 0, 0)):
        self.name, self.pose, self.vis = name, pose, []

    def _v(self, name, xyz, rpy, geom, colour):
        self.vis.append(f'      <visual name="{name}">\n        <pose>{fmt(list(xyz) + list(rpy))}</pose>\n'
                        f"        <geometry>{geom}</geometry>\n"
                        f"        <material><diffuse>{fmt(colour)}</diffuse></material>\n      </visual>")

    def box(self, name, c, size, colour, yaw=0.0):
        self._v(name, c, (0, 0, yaw), f"<box><size>{fmt(size)}</size></box>", colour)

    def cyl(self, name, c, axis, radius, length, colour):
        self._v(name, c, z_to_rpy(axis),
                f"<cylinder><radius>{radius:.6g}</radius><length>{length:.6g}</length></cylinder>", colour)

    def sphere(self, name, c, radius, colour):
        self._v(name, c, (0, 0, 0), f"<sphere><radius>{radius:.6g}</radius></sphere>", colour)

    def text(self):
        return (f'    <link name="{self.name}">\n      <pose>{fmt(list(self.pose) + [0, 0, 0])}</pose>\n'
                + "\n".join(self.vis) + "\n    </link>")


def base():
    L = Link("base")
    L.box("base_plate", (0, 0, 0.008), (0.46, 0.46, 0.016), BASE)
    post_h = rig.H_PIVOT - 0.016 - 0.012
    L.cyl("post", (0, 0, 0.016 + post_h / 2), (0, 0, 1), 0.012, post_h, POST)
    # gimbal: a block with the two pins
    L.box("gimbal_block", (0, 0, rig.H_PIVOT - 0.006), (0.024, 0.024, 0.014), METAL)
    L.cyl("pin_x", (0, 0, rig.H_PIVOT - 0.006), (1, 0, 0), 0.004, 0.04, POST)
    L.cyl("pin_y", (0, 0, rig.H_PIVOT - 0.006), (0, 1, 0), 0.004, 0.04, POST)
    # servos (SRV02-like bodies) beside their shafts; the cranks turn in the x-z / y-z planes
    xs = -L_ATT - rig.R_ARM
    L.box("servo_x", (xs, 0.045, Z_SHAFT - 0.012), (0.06, 0.06, 0.09), SERVO)
    L.box("servo_x_label", (xs, 0.0145, Z_SHAFT - 0.03), (0.04, 0.001, 0.02), LABEL)
    L.cyl("shaft_x", (xs, 0.01, Z_SHAFT), (0, 1, 0), 0.004, 0.02, METAL)
    L.box("servo_y", (0.045, xs, Z_SHAFT - 0.012), (0.06, 0.06, 0.09), SERVO)
    L.box("servo_y_label", (0.0145, xs, Z_SHAFT - 0.03), (0.001, 0.04, 0.02), LABEL)
    L.cyl("shaft_y", (0.01, xs, Z_SHAFT), (1, 0, 0), 0.004, 0.02, METAL)
    return L


def crank(axis_name):
    xs = -L_ATT - rig.R_ARM
    if axis_name == "x":
        L = Link("crank_x_link", (xs, 0, Z_SHAFT))
        L.box("arm", (rig.R_ARM / 2, 0, 0), (rig.R_ARM + 0.012, 0.006, 0.012), METAL)
        L.cyl("hub", (0, 0, 0), (0, 1, 0), 0.009, 0.01, METAL)
        L.cyl("pin", (rig.R_ARM, 0, 0), (0, 1, 0), 0.003, 0.012, POST)
    else:
        L = Link("crank_y_link", (0, xs, Z_SHAFT))
        L.box("arm", (0, rig.R_ARM / 2, 0), (0.006, rig.R_ARM + 0.012, 0.012), METAL)
        L.cyl("hub", (0, 0, 0), (1, 0, 0), 0.009, 0.01, METAL)
        L.cyl("pin", (0, rig.R_ARM, 0), (1, 0, 0), 0.003, 0.012, POST)
    return L


def rod(name, x, y):
    # at rest: from the crank tip (x, y, Z_SHAFT) straight up to the lug; origin at the middle
    L = Link(name, (x, y, Z_SHAFT + ROD_LEN / 2))
    L.cyl("rod", (0, 0, 0), (0, 0, 1), 0.0025, ROD_LEN, METAL)
    L.sphere("end_a", (0, 0, -ROD_LEN / 2), 0.0045, POST)
    L.sphere("end_b", (0, 0, ROD_LEN / 2), 0.0045, POST)
    return L


def plate():
    L = Link("plate", (0, 0, rig.H_PIVOT))
    a, t = rig.A_PLATE, rig.T_PLATE
    L.box("acrylic", (0, 0, 0), (a, a, t), PLATE)
    top = t / 2 + 0.0002
    for k in range(-3, 4):
        c = 0.05 * k
        w = 0.0012 if k else 0.002
        col = CROSS if k == 0 else GRID
        L.box(f"grid_x_{k + 3}", (c, 0, top), (w, a - 0.01, 0.0004), col)
        L.box(f"grid_y_{k + 3}", (0, c, top), (a - 0.01, w, 0.0004), col)
    # rim
    for name, c, size in (("rim_n", (0, a / 2 - 0.004, t / 2 + 0.004), (a, 0.008, 0.008)),
                          ("rim_s", (0, -a / 2 + 0.004, t / 2 + 0.004), (a, 0.008, 0.008)),
                          ("rim_e", (a / 2 - 0.004, 0, t / 2 + 0.004), (0.008, a, 0.008)),
                          ("rim_w", (-a / 2 + 0.004, 0, t / 2 + 0.004), (0.008, a, 0.008))):
        L.box(name, c, size, CROSS)
    # lugs of the push rods and the gimbal plate underneath
    L.box("lug_x", (-L_ATT, 0, -t / 2 - 0.006), (0.014, 0.01, 0.012), METAL)
    L.box("lug_y", (0, -L_ATT, -t / 2 - 0.006), (0.01, 0.014, 0.012), METAL)
    L.box("hub", (0, 0, -t / 2 - 0.002), (0.05, 0.05, 0.004), METAL)
    # reference paths (task 3 figure-8 and task 2 circle of PlateTask, at full size)
    z = top + 0.0001
    n8 = 48
    for k in range(n8):
        s = 2 * math.pi * k / n8
        L.cyl(f"fig8_{k:02d}", (0.10 * math.sin(s), 0.06 * math.sin(2 * s), z), (0, 0, 1), 0.0022, 0.0004, FIG8)
    nc = 36
    for k in range(nc):
        s = 2 * math.pi * k / nc
        L.cyl(f"circle_{k:02d}", (0.08 * math.cos(s), 0.08 * math.sin(s), z), (0, 0, 1), 0.0018, 0.0004, CIRCLE)
    return L


def ball():
    L = Link("ball", (0, 0, rig.H_PIVOT + rig.H_BALL))
    r = rig.R_BALL
    L.sphere("steel", (0, 0, 0), r, STEEL)
    L.cyl("band_a", (0, 0, 0), (0, 1, 0), r * 1.004, 0.0035, BAND_A)
    L.cyl("band_b", (0, 0, 0), (1, 0, 0), r * 1.002, 0.0035, BAND_B)
    return L


def target():
    L = Link("target", (0, 0, rig.H_PIVOT + rig.T_PLATE / 2 + 0.0005))
    L.cyl("ring", (0, 0, 0), (0, 0, 1), 0.006, 0.0008, TARGET)
    L.cyl("dot", (0, 0, 0.0002), (0, 0, 1), 0.0035, 0.0008, PLATE)
    return L


def main():
    xs = -L_ATT - rig.R_ARM
    links = [base(), crank("x"), crank("y"), rod("rod_x", xs + rig.R_ARM, 0.0), rod("rod_y", 0.0, xs + rig.R_ARM),
             plate(), ball(), target()]
    header = f"""<?xml version="1.0"?>
<!--
  ball-and-plate: a 2 DOF ball-and-plate rig (Quanser 2 DOF Ball Balancer type). Generated by
  design/build_scene.py. Z-up, metres, the world frame of the models; gimbal centre at
  (0, 0, {rig.H_PIVOT}).
  "plate" follows PosePlate/g[1..7], "ball" PoseBall/g[1..7], "rod_x"/"rod_y" Viz/rodx and
  Viz/rody, "target" Viz/target (the reference). "crank_x_link" and "crank_y_link" turn on the revolute
  joints "crank_x" and "crank_y", bound to the servo angles ThetaX/y and ThetaY/y. Dots on the plate:
  the figure-8 (orange) and circle (blue) of the tracking tasks.
-->
<sdf version="1.9">
  <model name="ball-and-plate">
"""
    joints = """    <joint name="crank_x" type="revolute">
      <parent>base</parent>
      <child>crank_x_link</child>
      <axis><xyz>0 -1 0</xyz></axis>
    </joint>

    <joint name="crank_y" type="revolute">
      <parent>base</parent>
      <child>crank_y_link</child>
      <axis><xyz>1 0 0</xyz></axis>
    </joint>"""
    body = "\n\n".join(L.text() for L in links)
    SCENE.parent.mkdir(parents=True, exist_ok=True)
    SCENE.write_text(header + body + "\n\n" + joints + "\n  </model>\n</sdf>\n", encoding="utf-8", newline="\n")
    print("wrote", SCENE.relative_to(ROOT))


if __name__ == "__main__":
    main()
