# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Write ``scenes/gyrover.sdf`` and ``scenes/gyrover-close.sdf``, the 3D scenes of the `gyrover` example.

Run ``uv run examples/gyrover/design/build_scene.py``. The link poses are those of the
showcase start (``build_model.START``, upright and at rest), so the scene matches the start of
every run; the simulation moves the links through the pose bindings of the models.

Links and what moves them:

* ``wheel``: tyre (48 segments with tread lugs), rim, five spokes per side and translucent side
  covers. Bound to the wheel pose ``Pose/q*, Pose/p*`` (body z = axle).
* ``pendulum``: the drive unit hanging from the axle (side plates, hub drive motor, battery and
  electronics box, the fork that carries the tilt bearings, the tilt motor). Bound to
  ``PoseP/g[1..7]``.
* ``gimbal``: the tilt frame (ring, tilt pins, bridges with the spin bearings). Bound to
  ``PoseG/g[1..7]`` (carrier frame, z = spin axis).
* ``flywheel``: the rotor, child of the joint ``flywheel_spin`` (about the gimbal z axis),
  bound to ``Sense/spin_vis``, the flywheel angle slowed down 200 times so that the turning
  disc stays readable (15 000 rpm would alias on screen).
* ``ground``: a 10 m x 10 m floor of 1 m tiles under the viewer's grid, and markers along the
  path of the showcase run (from ``path.json``, every 0.5 m of the reference model's path).

``uv run examples/gyrover/design/build_scene.py <run.json>`` first rewrites ``path.json`` from
a run of ``gyrover-ref`` (a JSON object with the columns ``time``, ``Gyrover/xc`` and
``Gyrover/yc``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_model as bm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "scenes" / "gyrover.sdf"
SCENE_CLOSE = ROOT / "scenes" / "gyrover-close.sdf"
PATH_FILE = Path(__file__).resolve().parent / "path.json"

RUBBER = (0.17, 0.17, 0.19, 1)
LUG = (0.09, 0.09, 0.1, 1)
RIM = (0.78, 0.8, 0.83, 1)
SPOKE = (0.95, 0.55, 0.1, 1)
COVER = (0.62, 0.8, 1.0, 0.16)
FRAME = (0.32, 0.33, 0.36, 1)
MOTOR = (0.22, 0.23, 0.26, 1)
ACCENT = (0.95, 0.55, 0.1, 1)
BATTERY = (0.16, 0.27, 0.52, 1)
PCB = (0.1, 0.5, 0.27, 1)
TILT_MOTOR = (0.8, 0.16, 0.16, 1)
GIMBAL = (0.56, 0.66, 0.8, 1)
BRASS = (0.86, 0.66, 0.26, 1)
DARK = (0.12, 0.12, 0.13, 1)
WHITE = (0.95, 0.95, 0.95, 1)
TILE_A = (0.8, 0.82, 0.78, 1)
TILE_B = (0.72, 0.75, 0.7, 1)
MARK = (0.95, 0.45, 0.1, 1)
START_MARK = (0.15, 0.65, 0.3, 1)


def rpy(R):
    """SDF roll-pitch-yaw (R = Rz(yaw) Ry(pitch) Rx(roll)) of a rotation matrix."""
    pitch = float(np.arcsin(np.clip(-R[2, 0], -1.0, 1.0)))
    if abs(np.cos(pitch)) < 1e-9:
        return 0.0, pitch, float(np.arctan2(-R[0, 1], R[1, 1]))
    return float(np.arctan2(R[2, 1], R[2, 2])), pitch, float(np.arctan2(R[1, 0], R[0, 0]))


def fmt(v) -> str:
    return " ".join(f"{float(x):.6g}" if abs(float(x)) > 1e-12 else "0" for x in v)


def pose_text(R, p) -> str:
    return fmt(list(p) + list(rpy(R)))


def z_to(axis):
    """A rotation that takes the z axis to `axis` (cylinders are drawn along z)."""
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    z = np.array([0.0, 0, 1])
    v = np.cross(z, a)
    c = float(z @ a)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def ring_frame(theta):
    """Box frame on a ring about the y axis (in the x-z plane): x radial, y axial, z tangential."""
    er = np.array([np.cos(theta), 0.0, np.sin(theta)])
    ey = np.array([0.0, 1.0, 0.0])
    return np.column_stack([er, ey, np.cross(er, ey)]), er


class Link:
    """Visuals written in a design frame F (world-aligned at the start) and stored in the link frame."""

    def __init__(self, name, R_link, p_link, F_origin):
        self.name, self.R, self.p, self.o = name, R_link, np.asarray(p_link, float), np.asarray(F_origin, float)
        self.visuals: list[str] = []

    def _add(self, vname, R_loc, c_loc, geometry, colour):
        Rv = self.R.T @ R_loc
        pv = self.R.T @ (self.o + np.asarray(c_loc, float) - self.p)
        self.visuals.append(
            f'      <visual name="{vname}">\n'
            f"        <pose>{pose_text(Rv, pv)}</pose>\n"
            f"        <geometry>{geometry}</geometry>\n"
            f"        <material><diffuse>{fmt(colour)}</diffuse></material>\n"
            f"      </visual>")

    def box(self, vname, c, size, colour, R=np.eye(3)):
        self._add(vname, R, c, f"<box><size>{fmt(size)}</size></box>", colour)

    def cyl(self, vname, c, axis, radius, length, colour):
        self._add(vname, z_to(axis), c,
                  f"<cylinder><radius>{radius:.6g}</radius><length>{length:.6g}</length></cylinder>", colour)

    def sphere(self, vname, c, radius, colour):
        self._add(vname, np.eye(3), c, f"<sphere><radius>{radius:.6g}</radius></sphere>", colour)

    def text(self) -> str:
        return (f'    <link name="{self.name}">\n      <pose>{pose_text(self.R, self.p)}</pose>\n'
                + "\n".join(self.visuals) + "\n    </link>")


def wheel(link: Link):
    R = bm.P["R"]
    n = 48
    width = 0.10
    for k in range(n):
        th = 2 * np.pi * k / n
        F, er = ring_frame(th)
        link.box(f"tyre_{k:02d}", 0.18 * er, (0.028, width, 2 * np.pi * 0.194 / n * 1.06), RUBBER, F)
        link.box(f"lug_{k:02d}", 0.1955 * er + np.array([0, 0.022 if k % 2 else -0.022, 0]),
                 (0.005, 0.042, 0.011), LUG, F)
        link.box(f"rim_{k:02d}", 0.16 * er, (0.012, width - 0.008, 2 * np.pi * 0.166 / n * 1.06), RIM, F)
    for side, y in (("l", 0.046), ("r", -0.046)):
        link.cyl(f"cover_{side}", (0, y, 0), (0, 1, 0), 0.166, 0.003, COVER)
        link.cyl(f"hub_{side}", (0, y, 0), (0, 1, 0), 0.03, 0.008, RIM)
        for k in range(5):
            th = 2 * np.pi * k / 5 + (0.0 if side == "l" else np.pi / 5)
            F, er = ring_frame(th)
            link.box(f"spoke_{side}{k}", 0.095 * er + np.array([0, y, 0]), (0.13, 0.004, 0.012), SPOKE, F)
    assert R > 0.195


def pendulum(link: Link):
    for side, y in (("l", 0.04), ("r", -0.04)):
        link.cyl(f"bearing_{side}", (0, y, 0), (0, 1, 0), 0.018, 0.012, FRAME)
        link.box(f"plate_{side}", (0, y, -0.0575), (0.026, 0.005, 0.115), FRAME)
        link.box(f"beam_{side}", (0, y, 0), (0.2, 0.005, 0.016), FRAME)
    for side, x in (("f", 0.096), ("b", -0.096)):
        link.box(f"fork_{side}", (x, 0, 0), (0.012, 0.085, 0.016), FRAME)
    link.cyl("drive_motor", (0, -0.03, 0), (0, 1, 0), 0.022, 0.018, MOTOR)
    link.cyl("drive_cap", (0, -0.0195, 0), (0, 1, 0), 0.016, 0.003, ACCENT)
    link.box("battery", (0, 0, -0.132), (0.12, 0.085, 0.042), BATTERY)
    link.box("electronics", (0, 0, -0.1085), (0.1, 0.07, 0.005), PCB)
    link.cyl("tilt_motor", (0.112, 0, 0), (1, 0, 0), 0.014, 0.022, TILT_MOTOR)


def gimbal(link: Link):
    n = 32
    for k in range(n):
        th = 2 * np.pi * k / n
        F, er = ring_frame(th)
        link.box(f"ring_{k:02d}", 0.082 * er, (0.006, 0.012, 2 * np.pi * 0.082 / n * 1.08), GIMBAL, F)
    for side, x in (("f", 0.088), ("b", -0.088)):
        link.cyl(f"pin_{side}", (x, 0, 0), (1, 0, 0), 0.005, 0.014, RIM)
    for side, y in (("l", 0.011), ("r", -0.011)):
        link.box(f"bridge_{side}", (0, y, 0), (0.012, 0.003, 0.164), GIMBAL)
        link.cyl(f"spin_bearing_{side}", (0, y, 0), (0, 1, 0), 0.009, 0.005, RIM)


def flywheel(link: Link):
    link.cyl("disc", (0, 0, 0), (0, 1, 0), 0.071, 0.01, BRASS)
    link.cyl("hub", (0, 0, 0), (0, 1, 0), 0.013, 0.016, RIM)
    for side, y in (("l", 0.0055), ("r", -0.0055)):
        F, er = ring_frame(0.0)
        link.box(f"stripe_{side}", 0.043 * er + np.array([0, y, 0]), (0.044, 0.002, 0.012), DARK, F)
        F, er = ring_frame(np.pi)
        link.box(f"stripe2_{side}", 0.043 * er + np.array([0, y, 0]), (0.044, 0.002, 0.012), WHITE, F)


def ground(link: Link, path):
    for i in range(-5, 5):
        for j in range(-5, 5):
            link.box(f"tile_{i + 5}{j + 5}", (i + 0.5, j + 0.5, -0.008), (1.0, 1.0, 0.01),
                     TILE_A if (i + j) % 2 == 0 else TILE_B)
    for k, (x, y) in enumerate(path):
        link.cyl(f"path_{k:02d}", (x, y, 0.001), (0, 0, 1), 0.03, 0.004, MARK)
    sx, sy = bm.START
    link.box("start_line", (sx, sy, 0.0015), (0.03, 0.5, 0.005), START_MARK)


def path_from_run(run_file: Path, spacing=0.5):
    r = json.loads(run_file.read_text())
    x, y = np.asarray(r["Gyrover/xc"], float), np.asarray(r["Gyrover/yc"], float)
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    targets = np.arange(spacing, s[-1], spacing)
    pts: list[list[float]] = []
    for t in targets:
        p = [round(float(np.interp(t, s, x)), 4), round(float(np.interp(t, s, y)), 4)]
        # the run ends past its start: skip the markers of the second pass over the first leg
        if all(np.hypot(p[0] - q[0], p[1] - q[1]) > 0.25 for q in pts):
            pts.append(p)
    PATH_FILE.write_text(json.dumps({
        "$comment": "Path of the wheel centre in the showcase run (model gyrover-ref), one point every 0.5 m; "
                    "written by build_scene.py <run.json>, drawn as markers on the ground of scenes/gyrover.sdf.",
        "points": pts}, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", PATH_FILE.name, len(pts), "points")


def small_ground(link: Link):
    """A 1 m x 1 m floor of 0.125 m tiles around the origin (the close-up scene)."""
    n = 8
    for i in range(n):
        for j in range(n):
            link.box(f"tile_{i}{j}", (-0.5 + 0.125 * (i + 0.5), -0.5 + 0.125 * (j + 0.5), -0.008), (0.125, 0.125, 0.01),
                     TILE_A if (i + j) % 2 == 0 else TILE_B)


SHOWCASE_TEXT = f"""Link poses are those of the showcase start (upright, at rest at x = {bm.START[0]}, y = {bm.START[1]}).
  The ground is a 10 m floor of 1 m tiles under the viewer's grid; the orange discs mark the
  path of the showcase run, every 0.5 m, and the green bar its start."""

CLOSE_TEXT = """Close-up variant for the bond graphs that start at the origin and stay near it (spin, no-spin,
  fig3): a 1 m floor of 0.125 m tiles, so that fitting the view frames the robot.
  Link poses are those of the upright robot at rest at the origin."""


def write_scene(file: Path, start, fill_ground, text):
    x0 = bm.x_init(x0=start[0], y0=start[1])
    s = bm.bg_state(x0)
    O = s["O"]
    links = [
        (Link("ground", np.eye(3), np.zeros(3), np.zeros(3)), fill_ground),
        (Link("wheel", s["Rw"], O, O), wheel),
        (Link("pendulum", s["Rp"], s["pP"], O), pendulum),
        (Link("gimbal", s["Rg"], s["pG"], s["pG"]), gimbal),
        (Link("flywheel", s["Rg"], s["pG"], s["pG"]), flywheel),
    ]
    for L, fill in links:
        fill(L)
    header = f"""<?xml version="1.0"?>
<!--
  gyrover: a single-wheel, gyroscopically stabilised robot after Tsai, Ferreira and Paredis
  (IROS 1999). Generated by design/build_scene.py. Z-up, metres, the world frame of the model.

  "wheel" (frame at the wheel centre, z = axle) follows the wheel pose Pose/q*, Pose/p*;
  "pendulum" (the drive unit: hub motor, side plates, battery, fork with the tilt motor) follows
  PoseP/g[1..7]; "gimbal" (tilt ring with the spin bearings, z = spin axis) follows PoseG/g[1..7];
  "flywheel" turns on the joint "flywheel_spin" about the gimbal z axis, bound to Sense/spin_vis
  (the flywheel angle slowed down 200 times). The side covers of the tyre are translucent so that
  the flywheel and the gimbal are visible.
  {text}
-->
<sdf version="1.9">
  <model name="gyrover">
"""
    joint = """    <joint name="flywheel_spin" type="continuous">
      <parent>gimbal</parent>
      <child>flywheel</child>
      <axis><xyz>0 0 1</xyz></axis>
    </joint>"""
    body = "\n\n".join(L.text() for L, _ in links)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(header + body + "\n\n" + joint + "\n  </model>\n</sdf>\n", encoding="utf-8", newline="\n")
    print("wrote", file.relative_to(ROOT))


def main():
    if len(sys.argv) > 1:
        path_from_run(Path(sys.argv[1]))
    path = json.loads(PATH_FILE.read_text())["points"]
    write_scene(SCENE, bm.START, lambda L: ground(L, path), SHOWCASE_TEXT)
    write_scene(SCENE_CLOSE, (0.0, 0.0), small_ground, CLOSE_TEXT)


if __name__ == "__main__":
    main()
