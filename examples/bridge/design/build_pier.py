# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Writes the two-span bridge on a centre pier: its 3D scenes and its models, from ``design_pier.json``.

    uv run examples/bridge/design/design_pier.py     # the independent numbers first
    uv run examples/bridge/design/build_pier.py

Models:

* ``bridge-pier``: a lorry crossing the two spans, with a dashboard (global strength factor,
  the slender diagonal's buckling capacity, lorry mass and speed). By default an overloaded
  40 t lorry buckles the slender diagonal next to the pier, and the redundant truss carries on.
* ``bridge-pier-static``: dead load plus 100 kN in the middle of the left span, against the
  stiffness method of ``design_pier.py``;
* ``bridge-pier-modes``: free vibration in the first mode, against the eigenvalue problem.

Scenes: ``scenes/bridge-pier.sdf`` (with the lorry) and ``scenes/bridge-pier-load.sdf``. The
model plane (x, y) is the world x-z plane, as in ``build_scene.py`` (whose lorry and helpers
this file reuses); the two main trusses stand at y = +/-HALF_WIDTH.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import build_model as bm  # noqa: E402
import build_scene as sc  # noqa: E402

P = json.loads((HERE / "design_pier.json").read_text(encoding="utf-8"))
C = P["constants"]
T = P["truck"]
NN, NB, ND = len(P["xy"]), len(P["bars"]), int(C["nd"])
LOAD = int(C["load_node"])                 # middle of the left span (x = 15)
PIER = int(C["pier_node"])                 # bottom node on the pier (x = 30)
RIGHT = int(C["right_node"])               # middle of the right span
ROLLER = int(C["roller_node"])             # the roller bearing (right end), on a seat of finite length
BEARING = int(C["left_bearing"])           # the pinned bearing (left end)
FOOT = int(C["foot_node"])
PIER_BAR = int(C["pier_bar"])
WEAK, PARTNER = int(C["weak_bar"]), int(C["partner_bar"])
PIER_POST = int(C["pier_post_bar"])
HW = sc.HALF_WIDTH
X_START = -10.0
COLLAPSE_DROP = 3.0
SCENE, SCENE_LOAD = "scenes/bridge-pier.sdf", "scenes/bridge-pier-load.sdf"


# ---------------------------------------------------------------- scene

def _node(n: int) -> np.ndarray:
    return np.array(P["xy"][n - 1], dtype=float)


def bar_radius(k: int) -> float:
    if k == PIER_BAR:
        return 0.32
    return 0.06 + 18.0 * float(P["A"][k - 1])


def _ground() -> str:
    xy = np.array(P["xy"])
    v = sc._visual
    out = []
    span = float(C["span"])
    bed = -float(C["pier_h"])
    # banks, the river between the abutments, its bed at the pier foot
    out.append(v("bank_left", sc._pose(-36.0, 0, bed / 2 - 0.05), sc._box(70, 44, -bed), (0.42, 0.55, 0.32, 1)))
    out.append(v("bank_right", sc._pose(span + 36.0, 0, bed / 2 - 0.05), sc._box(70, 44, -bed), (0.42, 0.55, 0.32, 1)))
    out.append(v("river", sc._pose(span / 2, 0, -6.2), sc._box(span + 2.0, 44, 0.4), (0.24, 0.42, 0.58, 1)))
    out.append(v("riverbed", sc._pose(span / 2, 0, bed - 0.6), sc._box(span + 2.0, 44, 1.2), (0.36, 0.33, 0.27, 1)))
    # the abutments reach SEAT past their bearings: the roller's seat on the right ends at the river face
    for name, x0, x1 in (("abutment_left", -2.0, sc.SEAT), ("abutment_right", span - sc.SEAT, span + 2.0)):
        out.append(v(name, sc._pose((x0 + x1) / 2, 0, bed / 2 - 0.1), sc._box(x1 - x0, 2 * HW + 1.4, -bed),
                     (0.66, 0.65, 0.62, 1)))
    for x, tag in ((0.0, "l"), (span, "r")):
        for side in (1, -1):
            out.append(v(f"bearing_{tag}{'p' if side > 0 else 'm'}", sc._pose(x, side * HW, -0.22),
                         sc._box(2 * sc.SEAT, 0.6, 0.3), (0.3, 0.3, 0.32, 1)))
    # the pier's footing on the riverbed (the steel columns are bars of the truss)
    foot = _node(FOOT)
    out.append(v("pier_footing", sc._pose(foot[0], 0, bed - 0.0 + 0.6), sc._box(3.0, 2 * HW + 2.0, 1.2), (0.6, 0.59, 0.56, 1)))
    for name, (a, b) in (("approach_left", (0, 1)), ("ramp_left", (1, 2)), ("approach_right", (ROLLER - 1, ND - 1))):
        pa, pb = xy[a], xy[b]
        d = pb - pa
        L = float(np.hypot(*d))
        pitch = -float(np.arctan2(d[1], d[0]))
        mid = (pa + pb) / 2
        out.append(v(name, sc._pose(mid[0], 0, mid[1] - sc.DECK_THICK / 2, 0, pitch, 0),
                     sc._box(L, 2 * HW - 0.3, sc.DECK_THICK), (0.45, 0.45, 0.47, 1)))
    for name, x0, x1 in (("mark_left", -39.0, -2.0), ("mark_right", span + 1.0, span + 39.0)):
        out.append(v(name, sc._pose((x0 + x1) / 2, 0, 0.004), sc._box(x1 - x0, 0.15, 0.01), (0.95, 0.95, 0.9, 1)))
    return "".join(out)


def _truss() -> str:
    # every bar and deck slab at its rest place (the undeformed truss): the bridge shows before a run
    out = []
    for side, dep in (("l", HW), ("r", -HW)):
        for k, (a, b) in enumerate(P["bars"], start=1):
            pa, pb = _node(a), _node(b)
            d = pb - pa
            L = float(np.hypot(*d))
            mid = (pa + pb) / 2
            pitch = float(np.arctan2(d[0], d[1]))
            out.append(sc._visual(f"bar_{side}_{k:02d}", sc._pose(mid[0], dep, mid[1], 0, pitch, 0),
                                  sc._cyl(bar_radius(k), L), (0.55, 0.57, 0.6, 1)))
    for p in range(ND - 4):
        pa, pb = _node(3 + p), _node(4 + p)
        d = pb - pa
        L = float(np.hypot(*d))
        mid = (pa + pb) / 2
        out.append(sc._visual(f"deck_{p + 1}", sc._pose(mid[0], 0, mid[1], 0, -float(np.arctan2(d[1], d[0])), 0),
                              sc._box(L, 2 * HW - 0.3, sc.DECK_THICK), (0.5, 0.5, 0.52, 1)))
    return "".join(out)


HEADER = """<?xml version="1.0"?>
<!--
  bridge-pier: a two-span continuous truss road bridge (2 x 24 m, eight 6 m panels, 5 m deep at the
  first posts and 7 m over the pier, X-braced next to the pier) on a 12 m steel column in the river.
  Generated by design/build_pier.py. Z-up, metres; the planar model's (x, y) is the world (x, z).

  The two main trusses stand at y = +/-{hw}; both follow the simulated truss. Each bar is the cylinder
  "bar_<l|r>_<k>" (k = Truss2D bar number, 62 = the pier column), stretched between its nodes by a
  segment binding and coloured by Truss/util[k] (coolwarm, -1 = buckling load, +1 = tensile
  strength); a failed bar is drawn snapped. "deck_<p>" are the deck slabs of the eight panels.{truck}
  The roller on the right stands on a seat 2 x 0.3 m long ("bearing_rp", "bearing_rm"): it turns red
  when the roller has rolled off it.
-->
"""


def write_scene(path: Path, with_truck: bool) -> None:
    note = ("\n  \"truck\" is the lorry (centre of mass, posed by Truck/q[1..7]); its wheels turn on the\n"
            "  joints \"axle_*\" bound to Truck/wheel.") if with_truck else ""
    text = HEADER.format(hw=HW, truck=note)
    text += f'<sdf version="1.9">\n  <model name="{path.stem}">\n'
    text += '    <link name="ground">\n      <pose>0 0 0 0 0 0</pose>\n' + _ground() + "    </link>\n"
    text += '    <link name="bridge">\n      <pose>0 0 0 0 0 0</pose>\n' + _truss() + "    </link>\n"
    if with_truck:
        text += sc._truck((X_START, y_start()))
    text += "  </model>\n</sdf>\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)}")


def bindings(truck: str | None, seat: str | None = None) -> list[dict]:
    out = sc.seat_bindings(seat, ("bearing_rp", "bearing_rm")) if seat else []
    for side, dep in (("l", HW), ("r", -HW)):
        for k, (a, b) in enumerate(P["bars"], start=1):
            out.append({"target": f"visual:bar_{side}_{k:02d}", "property": "segment",
                        "signal": [f"Truss/x[{a}]", f"Truss/y[{a}]", f"Truss/x[{b}]", f"Truss/y[{b}]"],
                        "plane": "xz", "depth": dep, "broken": f"Truss/failed[{k}]", "brokenStyle": "snapped"})
            out.append({"target": f"visual:bar_{side}_{k:02d}", "property": "color", "signal": f"Truss/util[{k}]",
                        "colormap": "coolwarm", "range": [-1.0, 1.0]})
    for p in range(ND - 4):
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


# ---------------------------------------------------------------- models

def deck_height(x: float) -> float:
    xy = np.array(P["xy"][:ND])
    return float(np.interp(x, xy[:, 0], xy[:, 1]))


def y_start() -> float:
    return 1.0 * -T["ry"] + T["r"] + deck_height(X_START)


I_DIAG = P["I"][WEAK - 1]
GLOBALS = [
    {"name": "strength", "value": "1.0", "unit": "1",
     "description": "Strength factor of every member: scales the tensile strength fy and the buckling loads"},
    {"name": "slender", "value": bm.num(C["weak_ratio"]), "unit": "1",
     "description": f"Buckling capacity of diagonal {WEAK} (next to the pier) as a fraction of its design section (I = slender x {I_DIAG!r} m^4)"},
    {"name": "v_truck", "value": "15.0", "unit": "m/s", "description": "Lorry speed"},
    {"name": "m_truck", "value": "40000.0", "unit": "kg", "description": "Lorry mass (both trusses; each carries half)"},
    {"name": "k_tyre", "value": bm.num(T["k"]), "unit": "N/m", "description": "Tyre stiffness per axle and truss"},
    {"name": "x_start", "value": bm.num(X_START), "unit": "m", "description": "Start position of the lorry's centre of mass"},
    {"name": "y_start", "value": bm.num(y_start()), "unit": "m",
     "description": "Centre-of-mass height over the unloaded tyres at the start"},
]


def truss(Dg, x, y, *, beta=C["beta"], state="dead", velocity=None, globals_=True, seated=False):
    fix = [list(r) for r in P["fix"]]
    starts = {}
    if state is not None:
        uy = list(P[state]["uy"])
        if seated:
            uy[ROLLER - 1] = -P[state]["R"][f"{ROLLER}y"] / bm.K_SEAT
            fix[ROLLER - 1] = [0, 0]
        starts = {"ux": bm.vec(P[state]["ux"]), "uy": bm.vec(uy)}
    if velocity is not None:
        starts["vx"], starts["vy"] = bm.vec(velocity[0]), bm.vec(velocity[1])
    if globals_:
        inertia = [bm.num(v) for v in P["I"]]
        inertia[WEAK - 1] = f"{I_DIAG!r}*slender"
        I = "[" + ", ".join(inertia) + "]"
        fy, K = f"{C['fy']!r}*strength", f"{C['K']!r}/sqrt(strength)"
    else:
        I, fy, K = bm.vec(P["I"]), bm.num(C["fy"]), bm.num(C["K"])
    Dg.node("Truss", "stdlib:planar/Truss2D", x, y,
            params={"xy": bm.mat(P["xy"]), "A": bm.vec(P["A"]), "I": I, "mn": bm.vec(P["mn"]),
                    "beta": bm.num(beta), "E": bm.num(C["E"]), "rho": bm.num(C["rho"]), "fy": fy,
                    "K": K, "g0": bm.num(C["g0"])},
            constants={"nn": str(NN), "nb": str(NB), "conn": bm.imat(P["bars"]), "fix": bm.imat(fix)},
            starts=starts)


def moving_load(Dg, x, y, P_, s0, v):
    Dg.node("Load", "stdlib:planar/MovingLoad2D", x, y,
            params={"P": bm.num(P_), "s0": bm.num(s0), "v": bm.num(v)}, constants={"nn": str(NN), "nd": str(ND)})
    Dg.sig("Truss", "x", "Load", "x")
    Dg.sig("Load", "Fx", "Truss", "Fx")
    Dg.sig("Load", "Fy", "Truss", "Fy")


def truck(Dg, x, y):
    m = "m_truck/2"
    Dg.node("Truck", "project:Truck2D", x, y,
            params={"m": m, "J": f"{m}*{(8.0 ** 2 + 2.5 ** 2) / 12.0!r}", "g0": bm.num(C["g0"]),
                    "x0": "x_start", "y0": f"y_start - {m}*{C['g0']!r}/(2*k_tyre)",
                    "rx": bm.vec([T["wheelbase"] / 2, -T["wheelbase"] / 2]), "ry": bm.vec([T["ry"], T["ry"]]),
                    "r": bm.num(T["r"]), "k": "k_tyre", "c": bm.num(T["c"]), "v_set": "v_truck", "tau": bm.num(T["tau"]),
                    "depth": bm.num(-sc.LANE)},
            constants={"nn": str(NN), "nd": str(ND)},
            starts={"body/inertia/P": f"[0.0, {m}*v_truck, 0.0]"})
    for s in ("x", "y", "xd", "yd"):
        Dg.sig("Truss", s, "Truck", s)
    Dg.sig("Truck", "Fx", "Seat", "Fxin")
    Dg.sig("Truck", "Fy", "Seat", "Fyin")


def peak(Dg, x, y):
    Dg.node("Peak", "project:PeakUtil", x, y, constants={"nb": str(NB)})
    Dg.sig("Truss", "util", "Peak", "util")


def collapse_stop(Dg, x, y):
    """Stop the run once the bridge has collapsed: the lowest of the two span middles and the pier node 3 m down."""
    for i, (name, node) in enumerate((("LeftSpan", LOAD), ("PierTop", PIER), ("RightSpan", RIGHT))):
        Dg.node(name, "stdlib:continuous/Select", x, y + 90 * i, constants={"N": str(NN), "index": str(node)})
        Dg.sig("Truss", "y", name, "u")
    Dg.node("Low1", "stdlib:continuous/Min", x + 160, y + 40)
    Dg.node("Low2", "stdlib:continuous/Min", x + 300, y + 90)
    Dg.node("Drop", "stdlib:continuous/Gain", x + 440, y + 90, params={"k": "-1.0"})
    Dg.node("Collapsed", "stdlib:sources/StopSimulation", x + 580, y + 90, params={"threshold": bm.num(COLLAPSE_DROP)})
    Dg.sig("LeftSpan", "y", "Low1", "u1")
    Dg.sig("PierTop", "y", "Low1", "u2")
    Dg.sig("Low1", "y", "Low2", "u1")
    Dg.sig("RightSpan", "y", "Low2", "u2")
    Dg.sig("Low2", "y", "Drop", "u")
    Dg.sig("Drop", "y", "Collapsed", "u")


def model(name, comment, Dg, sett, plots, *, globals_=None, truck_=False, dashboard=None):
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": Dg.nodes, "connections": Dg.conns, "subsystemPorts": [], "annotations": []},
        "settings": sett,
        "plots": plots,
    }
    if globals_:
        doc["parameters"] = globals_
    doc["scene"] = {"file": SCENE if truck_ else SCENE_LOAD}
    doc["bindings"] = bindings("Truck" if truck_ else None, "Seat" if truck_ else None)
    if dashboard:
        doc["dashboard"] = dashboard
    path = bm.MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(Dg.nodes)} nodes, {len(Dg.conns)} connections)")


MEMBER_PLOT = [f"Truss/N[{k}]" for k in (WEAK, PARTNER, PIER_POST, PIER_BAR, 2)]
DEFL_PLOT = [f"Truss/y[{n}]" for n in (LOAD, PIER, RIGHT)]


def dashboard():
    zones = [{"from": 0.0, "to": 0.8, "tone": "good"}, {"from": 0.8, "to": 1.0, "tone": "warn"},
             {"from": 1.0, "to": 1.2, "tone": "bad"}]
    return {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x2", "title": "Two spans on a pier",
             "options": {"markdown": True, "text": (
                 "A lorry crosses a 2 x 24 m truss bridge on a steel column in the river. The truss is continuous over "
                 "the pier and the two panels next to it are X-braced, so it is **redundant**: one failed member need not "
                 f"bring it down. Diagonal {WEAK}, next to the pier, is **too slender**: it holds a 20 t lorry, but the "
                 f"overloaded 40 t lorry buckles it, and its X-partner (bar {PARTNER}) takes over the panel shear.\n\n"
                 "Lower the **strength** of all members and the redistributed load is too much: the post and the bottom chord "
                 "next to the buckled diagonal fail, then the pier column buckles, "
                 "and the bridge collapses. Every change runs the model again.")}},
            {"id": "d2", "kind": "slider", "size": "2x1", "title": "Member strength (all bars)", "parameter": "global:strength",
             "options": {"min": 0.3, "max": 1.5, "step": 0.05, "decimals": 2, "unit": "x"}},
            {"id": "d3", "kind": "slider", "size": "2x1", "title": f"Diagonal {WEAK}: buckling capacity", "parameter": "global:slender",
             "options": {"min": 0.2, "max": 1.0, "step": 0.05, "decimals": 2, "unit": "x design"}},
            {"id": "d4", "kind": "slider", "size": "2x1", "title": "Lorry mass", "parameter": "global:m_truck",
             "options": {"min": 5000.0, "max": 60000.0, "step": 1000.0, "decimals": 0, "unit": "kg"}},
            {"id": "d5", "kind": "slider", "size": "2x1", "title": "Lorry speed", "parameter": "global:v_truck",
             "options": {"min": 10.0, "max": 30.0, "step": 0.5, "decimals": 1, "unit": "m/s"}},
            {"id": "d6", "kind": "gauge", "size": "1x1", "title": "Peak utilisation", "signals": ["Peak/peak"],
             "options": {"min": 0.0, "max": 1.2, "decimals": 2, "unit": "", "zones": zones}},
            {"id": "d7", "kind": "value", "size": "1x1", "title": "Failed bars", "signals": ["Truss/nfail"],
             "options": {"decimals": 0, "unit": ""}},
            {"id": "d8", "kind": "indicator", "size": "1x1", "title": "A member failed", "signals": ["Truss/nfail"],
             "options": {"threshold": 0.5, "onWhen": "above"}},
            {"id": "d9", "kind": "indicator", "size": "1x1", "title": "Bridge collapsed", "signals": ["Drop/y"],
             "options": {"threshold": 1.0, "onWhen": "above"}},
            {"id": "d15", "kind": "indicator", "size": "1x1", "title": "Roller off its seat", "signals": ["Seat/unseated"],
             "options": {"threshold": 0.5, "onWhen": "above"}},
            {"id": "d10", "kind": "plot", "size": "4x2", "title": "Member forces", "signals": MEMBER_PLOT},
            {"id": "d11", "kind": "plot", "size": "2x2", "title": "Utilisation",
             "signals": [f"Truss/util[{WEAK}]", f"Truss/util[{PARTNER}]", f"Truss/util[{PIER_BAR}]", "Peak/peak"]},
            {"id": "d12", "kind": "plot", "size": "2x2", "title": "Deflection: left span, pier, right span", "signals": DEFL_PLOT},
            {"id": "d13", "kind": "plot", "size": "2x2", "title": "Lorry position", "signals": ["Truck/g[2]"]},
            {"id": "d14", "kind": "plot", "size": "2x2", "title": "Lorry speed and axle loads", "signals": ["Truck/v", "Truck/fn[1]", "Truck/fn[2]"]},
        ],
    }


def display_dashboard(text, cards):
    return {"cards": [{"id": "d1", "kind": "text", "size": "2x2", "title": "About", "options": {"markdown": True, "text": text}}]
            + [dict(c, id=f"d{i + 2}") for i, c in enumerate(cards)]}


def main():
    write_scene(ROOT / SCENE, True)
    write_scene(ROOT / SCENE_LOAD, False)

    # 1. statics: dead load plus 100 kN in the middle of the left span, started at the linear solution
    Dg = bm.Diagram()
    truss(Dg, 300, 200, state="static", globals_=False)
    moving_load(Dg, 40, 200, C["P_static"], P["xy"][LOAD - 1][0], 0.0)
    R = P["static"]["R"]
    model("bridge-pier-static",
          "Two-span truss on a centre pier under its dead load and 100 kN in the middle of the left span; member forces, reactions and deflection against the stiffness method (design_pier.py).",
          Dg, bm.settings(2.0, 401), [
              bm.plot("p1", "Member forces", MEMBER_PLOT, "N"),
              bm.plot("p2", "Deflection", DEFL_PLOT, "m"),
              bm.plot("p3", "Support reactions", [f"Truss/Ry[{BEARING}]", f"Truss/Ry[{ROLLER}]", f"Truss/Ry[{FOOT}]"], "N"),
          ], dashboard=display_dashboard(
              "Dead load plus a **100 kN** point load in the middle of the left span. The truss is statically "
              f"indeterminate ({int(C['redundants'])} redundants), so the reference is the stiffness method of "
              f"`design/design_pier.py`: the pier column carries {R[f'{FOOT}y'] / 1e3:.1f} kN, the abutments "
              f"{R[f'{BEARING}y'] / 1e3:.1f} and {R[f'{ROLLER}y'] / 1e3:.1f} kN.", [
                  {"kind": "value", "size": "1x1", "title": "Pier reaction", "signals": [f"Truss/Ry[{FOOT}]"], "options": {"decimals": 0, "unit": "N"}},
                  {"kind": "value", "size": "1x1", "title": "Left abutment", "signals": [f"Truss/Ry[{BEARING}]"], "options": {"decimals": 0, "unit": "N"}},
                  {"kind": "value", "size": "1x1", "title": "Right abutment", "signals": [f"Truss/Ry[{ROLLER}]"], "options": {"decimals": 0, "unit": "N"}},
                  {"kind": "value", "size": "1x1", "title": "Deflection under the load", "signals": [f"Truss/y[{LOAD}]"], "options": {"decimals": 4, "unit": "m"}},
                  {"kind": "plot", "size": "4x2", "title": "Member forces", "signals": MEMBER_PLOT},
              ]))

    # 2. free vibration in the first mode, no damping
    phi_x, phi_y = np.array(P["modes"]["phi_x"]), np.array(P["modes"]["phi_y"])
    amp = 2 * np.pi * P["modes"]["f1"] * P["modes"]["amplitude"]       # 5 mm amplitude in the left span
    Dg = bm.Diagram()
    truss(Dg, 300, 200, beta=0.0, state="dead", velocity=(amp * phi_x, amp * phi_y), globals_=False)
    moving_load(Dg, 40, 200, 0.0, 0.0, 0.0)
    model("bridge-pier-modes",
          "Free vibration of the two-span truss in its first mode (the spans swing in opposite directions), no damping: frequency against the eigenvalue problem of design_pier.py, energy balance.",
          Dg, bm.settings(4.0, 4001), [
              bm.plot("p1", "Span deflections", [f"Truss/y[{LOAD}]", f"Truss/y[{RIGHT}]"], "m"),
              bm.plot("p2", "Energy", ["Truss/Ek", "Truss/Ee", "Truss/Eg", "Truss/Ebal"], "J"),
          ], dashboard=display_dashboard(
              f"The truss starts in its first mode at **{P['modes']['f1']:.4f} Hz** (eigenvalues of the stiffness and "
              "lumped mass matrices): the two spans swing in opposite directions about the pier. No damping, so "
              "`Ebal` stays constant.", [
                  {"kind": "plot", "size": "4x2", "title": "Span deflections", "signals": [f"Truss/y[{LOAD}]", f"Truss/y[{RIGHT}]"]},
                  {"kind": "plot", "size": "2x2", "title": "Energy", "signals": ["Truss/Ek", "Truss/Ee", "Truss/Ebal"]},
              ]))

    # 3. the lorry crossing, with the slender diagonal and the dashboard
    Dg = bm.Diagram()
    truss(Dg, 300, 200, state="dead", seated=True)
    bm.seat(Dg, 560, 380, ROLLER, *P["xy"][ROLLER - 1], NN)
    truck(Dg, 40, 200)
    peak(Dg, 560, 200)
    collapse_stop(Dg, 300, 440)
    model("bridge-pier",
          f"A two-span truss bridge on a centre pier with a lorry: the overloaded 40 t lorry buckles the slender diagonal {WEAK} next to the pier, its X-partner takes the panel shear and the redundant truss carries on; with weaker members the chords and posts next to it fail, the pier column buckles and the bridge collapses.",
          Dg, bm.settings(7.0, 1401), [
              bm.plot("p1", "Member forces", MEMBER_PLOT, "N"),
              bm.plot("p2", "Utilisation", [f"Truss/util[{WEAK}]", f"Truss/util[{PARTNER}]", f"Truss/util[{PIER_BAR}]", "Peak/peak"], ""),
              bm.plot("p3", "Deflection", DEFL_PLOT, "m"),
              bm.plot("p4", "Lorry: speed and axle loads", ["Truck/v", "Truck/fn[1]", "Truck/fn[2]"], ""),
              bm.plot("p5", "Failed bars", ["Truss/nfail"], ""),
          ], globals_=GLOBALS, truck_=True, dashboard=dashboard())


if __name__ == "__main__":
    main()
