# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Write ``scenes/bicycle.sdf`` and ``scenes/bicycle-turn.sdf``, the 3D scenes of the `bicycle` example.

    uv run examples/bicycle/design/build_scene.py

Every visual is written in world coordinates of the upright bicycle at the start (rear contact
at the origin, x forward, y to the left, z up) and stored in its link's frame; the link frames
are the bond graph's body frames, so the pose bindings of the models move them directly:

* ``rear_frame``: frame tubes, saddle, cranks and the rider (the paper's rear body B includes
  the rider). Bound to the rear frame pose ``PoseB`` (principal axes at the centre of mass).
* ``fork``: steerer, crown, fork blades, stem, handlebar and the rider's forearms. Bound to
  ``PoseH/g``.
* ``rear_wheel`` and ``front_wheel``: tyre, rim, spokes and hub, bound to ``PoseR/g`` and
  ``PoseF/g`` (z = axle).
* ``ground``: a floor of 2 m tiles: 28 m x 12 m for the straight runs of `whipple`
  (``bicycle.sdf``), 36 m x 24 m for the right turn of `balance` (``bicycle-turn.sdf``).

The bicycle is drawn to the benchmark's geometry: wheel base 1.02 m, wheel radii 0.30 m and
0.35 m, steer axis tilt 18 degrees, trail 0.08 m.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_model as bm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "scenes" / "bicycle.sdf"
P, GEO = bm.P, bm.GEO
LAM = P["lam"]

FRAME = (0.75, 0.12, 0.12, 1)
FORK = (0.82, 0.83, 0.86, 1)
RUBBER = (0.12, 0.12, 0.13, 1)
RIM = (0.78, 0.8, 0.83, 1)
SPOKE = (0.7, 0.72, 0.75, 1)
DARK = (0.15, 0.15, 0.17, 1)
SADDLE = (0.1, 0.1, 0.1, 1)
SHIRT = (0.18, 0.38, 0.7, 1)
TROUSERS = (0.2, 0.22, 0.28, 1)
SKIN = (0.93, 0.76, 0.62, 1)
HELMET = (0.95, 0.6, 0.1, 1)
TILE_A = (0.8, 0.82, 0.78, 1)
TILE_B = (0.72, 0.75, 0.7, 1)
LINE = (0.95, 0.95, 0.95, 1)


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


class Link:
    """Visuals given in world coordinates of the start pose, stored in the link frame."""

    def __init__(self, name, M):
        self.name, self.R, self.p = name, M[:3, :3], M[:3, 3]
        self.visuals: list[str] = []

    def _add(self, vname, R_loc, c, geometry, colour):
        Rv = self.R.T @ R_loc
        pv = self.R.T @ (np.asarray(c, float) - self.p)
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

    def tube(self, vname, a, b, radius, colour):
        a, b = np.asarray(a, float), np.asarray(b, float)
        self.cyl(vname, 0.5 * (a + b), b - a, radius, float(np.linalg.norm(b - a)), colour)

    def sphere(self, vname, c, radius, colour):
        self._add(vname, np.eye(3), c, f"<sphere><radius>{radius:.6g}</radius></sphere>", colour)

    def text(self) -> str:
        return (f'    <link name="{self.name}">\n      <pose>{pose_text(self.R, self.p)}</pose>\n'
                + "\n".join(self.visuals) + "\n    </link>")


def axis_point(t):
    """Point on the steer axis at distance t (m) up from where it meets the ground."""
    return np.array([P["w"] + P["c"] - t * np.sin(LAM), 0.0, t * np.cos(LAM)])


def wheel(L: Link, centre, r):
    n = 40
    centre = np.asarray(centre, float)
    for k in range(n):
        th = 2 * np.pi * k / n
        er = np.array([np.cos(th), 0.0, np.sin(th)])
        F = np.column_stack([er, [0.0, 1.0, 0.0], np.cross(er, [0.0, 1.0, 0.0])])
        L.box(f"tyre_{k:02d}", centre + (r - 0.016) * er, (0.032, 0.035, 2 * np.pi * r / n * 1.08), RUBBER, F)
        L.box(f"rim_{k:02d}", centre + (r - 0.045) * er, (0.022, 0.022, 2 * np.pi * (r - 0.045) / n * 1.08), RIM, F)
    for k in range(16):
        th = 2 * np.pi * k / 16
        side = 0.028 if k % 2 else -0.028
        hub = centre + np.array([0.0, side, 0.0])
        rim = centre + (r - 0.055) * np.array([np.cos(th), 0.0, np.sin(th)])
        L.tube(f"spoke_{k:02d}", hub, rim, 0.0018, SPOKE)
    L.cyl("hub", centre, (0, 1, 0), 0.022, 0.08, DARK)
    # a coloured marker on the rim makes the rolling visible
    L.box("valve", centre + (r - 0.06) * np.array([1.0, 0, 0]), (0.03, 0.03, 0.03), HELMET)


def rear_frame(L: Link):
    hub = np.array([0.0, 0.0, P["rR"]])
    bb = np.array([0.42, 0.0, 0.28])
    seat = np.array([0.30, 0.0, 0.80])
    ht_bot, ht_top = axis_point(0.66), axis_point(0.86)
    for side in (-1, 1):
        y = np.array([0.0, 0.035 * side, 0.0])
        L.tube(f"chainstay_{'left' if side > 0 else 'right'}", hub + 2 * y, bb + y, 0.011, FRAME)
        L.tube(f"seatstay_{'left' if side > 0 else 'right'}", hub + 2 * y, seat + 0.5 * y, 0.009, FRAME)
    L.tube("seat_tube", bb, seat, 0.016, FRAME)
    L.tube("top_tube", seat, ht_top + np.array([0, 0, -0.02]), 0.016, FRAME)
    L.tube("down_tube", bb, ht_bot + np.array([0, 0, 0.03]), 0.019, FRAME)
    L.tube("head_tube", ht_bot, ht_top, 0.022, FRAME)
    saddle = seat + np.array([-0.03, 0.0, 0.12])
    L.tube("seat_post", seat, saddle, 0.012, RIM)
    L.box("saddle", saddle + np.array([0.02, 0, 0.02]), (0.24, 0.13, 0.05), SADDLE)
    # cranks and pedals (fixed, horizontal)
    L.cyl("bottom_bracket", bb, (0, 1, 0), 0.025, 0.09, DARK)
    L.cyl("chainring", bb + np.array([0, -0.06, 0]), (0, 1, 0), 0.1, 0.006, RIM)
    for side in (-1, 1):
        arm_end = bb + np.array([0.17 * side, 0.08 * side, 0.0])
        L.tube(f"crank_{'left' if side > 0 else 'right'}", bb + np.array([0, 0.06 * side, 0]), arm_end, 0.011, RIM)
        L.box(f"pedal_{'left' if side > 0 else 'right'}", arm_end + np.array([0, 0.05 * side, 0]), (0.09, 0.09, 0.02), DARK)
    # the rider (rigid with the rear frame, as in the benchmark)
    hip = saddle + np.array([0.0, 0.0, 0.07])
    shoulder = np.array([0.58, 0.0, 1.42])
    L.tube("torso", hip, shoulder, 0.15, SHIRT)
    L.sphere("hips", hip, 0.16, TROUSERS)
    L.tube("neck", shoulder, shoulder + np.array([0.04, 0, 0.1]), 0.05, SKIN)
    L.sphere("head", shoulder + np.array([0.08, 0, 0.22]), 0.1, SKIN)
    L.sphere("helmet", shoulder + np.array([0.06, 0, 0.26]), 0.11, HELMET)
    for side in (-1, 1):
        s = shoulder + np.array([0.0, 0.19 * side, -0.02])
        L.sphere(f"shoulder_{'left' if side > 0 else 'right'}", s, 0.065, SHIRT)
        L.tube(f"upper_arm_{'left' if side > 0 else 'right'}", s, elbow(side), 0.045, SHIRT)
        h = hip + np.array([0.02, 0.1 * side, 0.0])
        knee = np.array([0.6, 0.15 * side, 0.68])
        foot = bb + np.array([0.17 * side, 0.13 * side, 0.03])
        L.tube(f"thigh_{'left' if side > 0 else 'right'}", h, knee, 0.07, TROUSERS)
        L.tube(f"shin_{'left' if side > 0 else 'right'}", knee, foot, 0.05, TROUSERS)
        L.box(f"shoe_{'left' if side > 0 else 'right'}", foot + np.array([0.03, 0, -0.01]), (0.26, 0.1, 0.07), DARK)


def elbow(side):
    return np.array([0.66, 0.25 * side, 1.15])


def fork(L: Link):
    hub = np.array([P["w"], 0.0, P["rF"]])
    crown = axis_point(0.63)
    L.tube("steerer", axis_point(0.6), axis_point(0.98), 0.013, FORK)
    L.box("crown", crown, (0.05, 0.13, 0.03), FORK)
    for side in (-1, 1):
        y = np.array([0.0, 0.05 * side, 0.0])
        L.tube(f"blade_{'left' if side > 0 else 'right'}", crown + y, hub + y, 0.012, FORK)
    top = axis_point(0.98)
    bar = np.array([0.73, 0.0, 0.98])
    L.tube("stem", top, bar, 0.014, DARK)
    L.cyl("handlebar", bar, (0, 1, 0), 0.012, 0.58, DARK)
    for side in (-1, 1):
        grip = bar + np.array([0.0, 0.25 * side, 0.0])
        L.cyl(f"grip_{'left' if side > 0 else 'right'}", grip, (0, 1, 0), 0.017, 0.1, SADDLE)
        L.tube(f"forearm_{'left' if side > 0 else 'right'}", elbow(side), grip, 0.04, SKIN)
        L.sphere(f"hand_{'left' if side > 0 else 'right'}", grip, 0.04, SKIN)


# floors of 2 m tiles (x and y ranges in tiles): the straight runs of `whipple`, the right turn of
# `balance`. Each floor is about centred on the bicycle at the docs' snapshot times, because the
# 3D view's fit frames the whole scene.
FLOORS = {"bicycle.sdf": ((-2, 12), (-4, 2)), "bicycle-turn.sdf": ((-2, 16), (-11, 1))}


def ground(L: Link, tiles):
    (i0, i1), (j0, j1) = tiles
    for i in range(i0, i1):
        for j in range(j0, j1):
            L.box(f"tile_{i - i0:02d}_{j - j0:02d}", (2 * i + 1.0, 2 * j + 1.0, -0.006), (2.0, 2.0, 0.01),
                  TILE_A if (i + j) % 2 == 0 else TILE_B)
    L.box("start_line", (0.0, 0.0, 0.0005), (0.05, 1.2, 0.002), LINE)


def main():
    for name, tiles in FLOORS.items():
        write(SCENE.parent / name, tiles)


def write(path: Path, tiles):
    links = [
        (Link("ground", np.eye(4)), lambda L: ground(L, tiles)),
        (Link("rear_frame", GEO["B"]), rear_frame),
        (Link("fork", GEO["H"]), fork),
        (Link("rear_wheel", GEO["R"]), lambda L: wheel(L, [0.0, 0.0, P["rR"]], P["rR"])),
        (Link("front_wheel", GEO["F"]), lambda L: wheel(L, [P["w"], 0.0, P["rF"]], P["rF"])),
    ]
    for L, fill in links:
        fill(L)
    (i0, i1), (j0, j1) = tiles
    header = f"""<?xml version="1.0"?>
<!--
  bicycle: the benchmark bicycle of Meijaard, Papadopoulos, Ruina and Schwab (Proc. R. Soc. A,
  2007). Generated by design/build_scene.py. Z-up, metres, the world frame of the 3D models
  (x forward, y to the left); the link poses are those of the upright bicycle at the start.

  "rear_frame" (frame, saddle, cranks and the rider; principal axes at the centre of mass of the
  paper's rear body B) follows PoseB; "fork" (fork, stem, handlebar, the rider's forearms)
  follows PoseH/g[1..7]; "rear_wheel" and "front_wheel" (z = axle) follow PoseR/g and PoseF/g.
  "ground": a floor of 2 m tiles, x {2 * i0} to {2 * i1} m, y {2 * j0} to {2 * j1} m.
-->
<sdf version="1.9">
  <model name="bicycle">
"""
    body = "\n\n".join(L.text() for L, _ in links)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body + "\n  </model>\n</sdf>\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
