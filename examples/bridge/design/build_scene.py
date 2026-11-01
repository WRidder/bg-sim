# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Writes the 3D scenes of the `bridge` example and the model bindings (imported by build_model.py).

    uv run examples/bridge/design/build_scene.py

The model is planar: its (x, y) plane is the world x-z plane (z up). The two main trusses
stand at the world y = +/-HALF_WIDTH and both follow the one simulated truss (each carries half
the deck and half the lorry). Every bar is a cylinder visual stretched between its two nodes by
a `segment` binding (planar end points, depth = the truss's y) and coloured by its utilisation
(coolwarm: blue compression, red tension, the full colour at the failure load); a failed bar
is drawn snapped. The deck slabs are boxes stretched between the bottom-chord nodes. The lorry
is one link posed by `Truck/q` with four wheels turning on `Truck/wheel`.

``scenes/bridge.sdf`` has the lorry, ``scenes/bridge-load.sdf`` (the point-load models) not.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
D = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
C = D["constants"]

HALF_WIDTH = 3.6          # the trusses stand at y = +/-HALF_WIDTH
LANE = 1.75               # the lorry drives at y = -LANE (the right-hand lane seen from the start)
DECK_THICK = 0.12
TRUCK_START = (-25.0, 1.5)


def _f(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _pose(x, y, z, roll=0.0, pitch=0.0, yaw=0.0) -> str:
    return " ".join(_f(v) for v in (x, y, z, roll, pitch, yaw))


def _visual(name, pose, geometry, rgba, extra="") -> str:
    color = " ".join(_f(c) for c in rgba)
    return (f'      <visual name="{name}">\n        <pose>{pose}</pose>\n        <geometry>{geometry}</geometry>\n'
            f"        <material><diffuse>{color}</diffuse>{extra}</material>\n      </visual>\n")


def _box(sx, sy, sz) -> str:
    return f"<box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box>"


def _cyl(r, length) -> str:
    return f"<cylinder><radius>{_f(r)}</radius><length>{_f(length)}</length></cylinder>"


def bar_radius(k: int) -> float:
    """Visual radius of bar k (1-based) from its area (not to scale: thin bars stay visible)."""
    return 0.06 + 18.0 * float(D["A"][k - 1])


def _ground() -> str:
    xy = np.array(D["xy"])
    out = []
    # meadow on both banks and the river between the abutments
    out.append(_visual("bank_left", _pose(-35.0, 0, -3.05), _box(70, 40, 6), (0.42, 0.55, 0.32, 1)))
    out.append(_visual("bank_right", _pose(65.0, 0, -3.05), _box(70, 40, 6), (0.42, 0.55, 0.32, 1)))
    out.append(_visual("river", _pose(15.0, 0, -5.2), _box(31.0, 40, 0.4), (0.24, 0.42, 0.58, 1)))
    out.append(_visual("riverbed", _pose(15.0, 0, -6.2), _box(31.0, 40, 1.6), (0.36, 0.33, 0.27, 1)))
    # abutments under the bearings
    for name, x in (("abutment_left", -1.0), ("abutment_right", 31.0)):
        out.append(_visual(name, _pose(x, 0, -3.1), _box(2.0, 2 * HALF_WIDTH + 1.4, 6.0), (0.66, 0.65, 0.62, 1)))
    # bearings (small plinths under the end nodes of the bottom chords)
    for x in (0.0, 30.0):
        for side in (1, -1):
            out.append(_visual(f"bearing_{'l' if x == 0 else 'r'}{'p' if side > 0 else 'm'}",
                               _pose(x, side * HALF_WIDTH, -0.22), _box(0.6, 0.6, 0.3), (0.3, 0.3, 0.32, 1)))
    # approach slabs: the far slab, the settled ramp at the left abutment, the right slab
    for name, (a, b) in (("approach_left", (0, 1)), ("ramp_left", (1, 2)), ("approach_right", (8, 9))):
        pa, pb = xy[a], xy[b]
        d = pb - pa
        L = float(np.hypot(*d))
        pitch = -float(np.arctan2(d[1], d[0]))
        mid = (pa + pb) / 2
        out.append(_visual(name, _pose(mid[0], 0, mid[1] - DECK_THICK / 2, 0, pitch, 0),
                           _box(L, 2 * HALF_WIDTH - 0.3, DECK_THICK), (0.45, 0.45, 0.47, 1)))
    # lane markings on the approaches
    for name, x0, x1 in (("mark_left", -39.0, -2.0), ("mark_right", 31.0, 69.0)):
        out.append(_visual(name, _pose((x0 + x1) / 2, 0, 0.004), _box(x1 - x0, 0.15, 0.01), (0.95, 0.95, 0.9, 1)))
    return "".join(out)


def _node(n: int) -> np.ndarray:
    """Rest position (model x, y) of truss node n (1-based, as in Truss/x[n])."""
    return np.array(D["xy"][n - 1], dtype=float)


def _truss() -> str:
    # Every bar and deck slab is written at its rest place (the undeformed truss), so the bridge shows
    # before a run and in any model whose results are not loaded yet; a segment binding then moves it
    # to the simulated nodes (|AB| / length is 1 at rest: no jump at t = 0).
    out = []
    for side, depth in (("l", HALF_WIDTH), ("r", -HALF_WIDTH)):
        for k, (a, b) in enumerate(D["bars"], start=1):
            pa, pb = _node(a), _node(b)
            d = pb - pa
            L = float(np.hypot(*d))
            mid = (pa + pb) / 2
            pitch = float(np.arctan2(d[0], d[1]))   # turns the cylinder's +z onto (dx, 0, dz)
            out.append(_visual(f"bar_{side}_{k:02d}", _pose(mid[0], depth, mid[1], 0, pitch, 0),
                               _cyl(bar_radius(k), L), (0.55, 0.57, 0.6, 1)))
    for p in range(6):
        pa, pb = _node(3 + p), _node(4 + p)
        d = pb - pa
        L = float(np.hypot(*d))
        mid = (pa + pb) / 2
        pitch = -float(np.arctan2(d[1], d[0]))      # turns the box's +x onto (dx, 0, dz)
        out.append(_visual(f"deck_{p + 1}", _pose(mid[0], 0, mid[1], 0, pitch, 0),
                           _box(L, 2 * HALF_WIDTH - 0.3, DECK_THICK), (0.5, 0.5, 0.52, 1)))
    return "".join(out)


def _truck() -> str:
    x0, z0 = TRUCK_START
    out = ['    <link name="truck">\n', f"      <pose>{_pose(x0, -LANE, z0)}</pose>\n"]
    # body frame at the centre of mass; the wheel centres are 1 m below it, axles at +/-2 m
    out.append(_visual("chassis", _pose(0, 0, -0.55), _box(7.4, 2.3, 0.3), (0.18, 0.18, 0.2, 1)))
    out.append(_visual("cargo", _pose(-0.9, 0, 0.75), _box(5.4, 2.45, 2.3), (0.86, 0.62, 0.16, 1)))
    out.append(_visual("cab", _pose(2.85, 0, 0.35), _box(1.7, 2.4, 1.5), (0.2, 0.36, 0.62, 1)))
    out.append(_visual("windscreen", _pose(3.71, 0, 0.6), _box(0.04, 2.1, 0.7), (0.65, 0.8, 0.9, 1)))
    out.append("    </link>\n")
    joints = []
    for axle, ax in (("f", 2.0), ("r", -2.0)):
        for side, sy in (("l", 1.1), ("r", -1.1)):
            name = f"wheel_{axle}{side}"
            out.append(f'    <link name="{name}">\n      <pose>{_pose(x0 + ax, -LANE + sy, z0 - 1.0)}</pose>\n')
            out.append(_visual(f"{name}_tyre", _pose(0, 0, 0, np.pi / 2, 0, 0), _cyl(0.5, 0.38), (0.08, 0.08, 0.08, 1)))
            out.append(_visual(f"{name}_hub", _pose(0, 0.2 * np.sign(sy), 0, np.pi / 2, 0, 0), _cyl(0.24, 0.02),
                               (0.75, 0.75, 0.78, 1)))
            out.append(_visual(f"{name}_spoke", _pose(0.12, 0.21 * np.sign(sy), 0, 0, 0, 0), _box(0.24, 0.02, 0.06),
                               (0.2, 0.2, 0.22, 1)))
            out.append("    </link>\n")
            joints.append(f'    <joint name="axle_{axle}{side}" type="continuous">\n      <parent>truck</parent>\n'
                          f"      <child>{name}</child>\n      <axis><xyz>0 1 0</xyz></axis>\n    </joint>\n")
    return "".join(out) + "".join(joints)


HEADER = """<?xml version="1.0"?>
<!--
  bridge: a 30 m Warren truss road bridge (six 5 m panels, 4 m deep) over a river.
  Generated by design/build_scene.py. Z-up, metres; the planar model's (x, y) is the world (x, z).

  The two main trusses stand at y = +/-{hw}; both follow the simulated truss. Each bar is the
  cylinder "bar_<l|r>_<k>" (k = Truss2D bar number), stretched between its nodes by a segment
  binding and coloured by Truss/util[k] (coolwarm, -1 = buckling load, +1 = tensile strength);
  a failed bar is drawn snapped. "deck_<p>" are the deck slabs of the six panels.{truck}
  The approach slab on the left has settled 6 cm at the abutment: a short ramp up onto the bridge.
-->
"""


def write(path: Path, with_truck: bool) -> None:
    truck_note = ("\n  \"truck\" is the lorry (centre of mass, posed by Truck/q[1..7]); its wheels turn on the\n"
                  "  joints \"axle_*\" bound to Truck/wheel.") if with_truck else ""
    text = HEADER.format(hw=HALF_WIDTH, truck=truck_note)
    text += f'<sdf version="1.9">\n  <model name="{path.stem}">\n'
    text += '    <link name="ground">\n      <pose>0 0 0 0 0 0</pose>\n' + _ground() + "    </link>\n"
    text += '    <link name="bridge">\n      <pose>0 0 0 0 0 0</pose>\n' + _truss() + "    </link>\n"
    if with_truck:
        text += _truck()
    text += "  </model>\n</sdf>\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


def bindings(truck: str | None = None, load: str | None = None, broken: bool = True) -> list[dict]:
    """The bindings of a model whose truss node is `Truss` (and lorry node `truck`)."""
    out = []
    for side, depth in (("l", HALF_WIDTH), ("r", -HALF_WIDTH)):
        for k, (a, b) in enumerate(D["bars"], start=1):
            seg = {"target": f"visual:bar_{side}_{k:02d}", "property": "segment",
                   "signal": [f"Truss/x[{a}]", f"Truss/y[{a}]", f"Truss/x[{b}]", f"Truss/y[{b}]"],
                   "plane": "xz", "depth": depth}
            if broken:
                seg["broken"] = f"Truss/failed[{k}]"
                seg["brokenStyle"] = "snapped"
            out.append(seg)
            out.append({"target": f"visual:bar_{side}_{k:02d}", "property": "color", "signal": f"Truss/util[{k}]",
                        "colormap": "coolwarm", "range": [-1.0, 1.0]})
    for p in range(6):
        a, b = 3 + p, 4 + p
        out.append({"target": f"visual:deck_{p + 1}", "property": "segment",
                    "signal": [f"Truss/x[{a}]", f"Truss/y[{a}]", f"Truss/x[{b}]", f"Truss/y[{b}]"],
                    "plane": "xz", "depth": 0.0, "axis": "+x"})
    if truck:
        out.append({"target": "link:truck", "property": "pose", "signal": [f"{truck}/q[{i}]" for i in range(1, 8)]})
        for axle in "fr":
            for side in "lr":
                out.append({"target": f"joint:axle_{axle}{side}", "property": "position", "signal": f"{truck}/wheel"})
    return out


def main() -> None:
    (ROOT / "scenes").mkdir(exist_ok=True)
    write(ROOT / "scenes" / "bridge.sdf", True)
    write(ROOT / "scenes" / "bridge-load.sdf", False)


if __name__ == "__main__":
    main()
