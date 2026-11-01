# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Writes the models of the `bridge` example (``models/*.bgmodel.json``) from ``design.json``.

    uv run examples/bridge/design/design.py        # the independent numbers first
    uv run examples/bridge/design/build_model.py

The truss is one `stdlib:planar/Truss2D` block (nodes, bars and supports as matrices); the
loads are a `MovingLoad2D` (a point load travelling over the deck) or the project block
`Truck2D` (a two-axle lorry on compliant tyres, driven at a set speed). The buckling model is a
single `Bar2D` strut between two `PinNode2D` nodes. The 3D scene and its bindings come from
``build_scene.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS = ROOT / "models"
sys.path.insert(0, str(HERE))
import build_scene as scene  # noqa: E402

D = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
C = D["constants"]
T = D["truck"]
NN, NB, ND = len(D["xy"]), len(D["bars"]), int(C["nd"])
MID = int(C["mid_node"])
WEAK = int(C["weak_bar"])


def num(x) -> str:
    return repr(float(x))


def vec(v) -> str:
    return "[" + ", ".join(num(x) for x in v) + "]"


def mat(rows, fmt=num) -> str:
    return "[" + "; ".join(" ".join(fmt(x) for x in row) for row in rows) + "]"


def imat(rows) -> str:
    return mat(rows, lambda x: str(int(x)))


class Diagram:
    def __init__(self):
        self.nodes, self.conns, self._ids = [], [], {}

    def node(self, name, ref, x, y, params=None, constants=None, starts=None):
        nid = f"n{len(self.nodes) + 1:02d}"
        self._ids[name] = nid
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False, "params": params or {}, "constants": constants or {},
            "starts": starts or {}, "ui": {"showLabel": True, "color": None},
        })

    def _c(self, kind, a, pa, b, pb):
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind,
                           "from": {"node": self._ids[a], "port": pa}, "to": {"node": self._ids[b], "port": pb},
                           "label": None})

    def bond(self, a, pa, b, pb):
        self._c("bond", a, pa, b, pb)

    def sig(self, a, pa, b, pb):
        self._c("signal", a, pa, b, pb)


def settings(t_end, points, solver="Rodas5P", reltol=1e-6, abstol=1e-8):
    return {"t_start": 0.0, "t_end": float(t_end), "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 10000}


def truss(Dg, x, y, *, area=None, beta=C["beta"], state="dead", velocity=None):
    """The Truss2D node; `state` picks the static starts (dead, static or none)."""
    A = list(D["A"]) if area is None else area
    starts = {}
    if state is not None:
        starts = {"ux": vec(D[state]["ux"]), "uy": vec(D[state]["uy"])}
    if velocity is not None:
        starts["vx"], starts["vy"] = vec(velocity[0]), vec(velocity[1])
    Dg.node("Truss", "stdlib:planar/Truss2D", x, y,
            params={"xy": mat(D["xy"]), "A": vec(A), "I": vec(D["I"]), "mn": vec(D["mn"]),
                    "beta": num(beta), "E": num(C["E"]), "rho": num(C["rho"]), "fy": num(C["fy"]),
                    "K": num(C["K"]), "g0": num(C["g0"])},
            constants={"nn": str(NN), "nb": str(NB), "conn": imat(D["bars"]), "fix": imat(D["fix"])},
            starts=starts)


def moving_load(Dg, x, y, P, s0, v):
    Dg.node("Load", "stdlib:planar/MovingLoad2D", x, y,
            params={"P": num(P), "s0": num(s0), "v": num(v)}, constants={"nn": str(NN), "nd": str(ND)})
    Dg.sig("Truss", "x", "Load", "x")
    Dg.sig("Load", "Fx", "Truss", "Fx")
    Dg.sig("Load", "Fy", "Truss", "Fy")


def deck_height(x):
    xy = np.array(D["xy"][:ND])
    return float(np.interp(x, xy[:, 0], xy[:, 1]))


TRUCK_GLOBALS = [
    {"name": "v_truck", "value": "10.0", "unit": "m/s", "description": "Lorry speed"},
    {"name": "m_truck", "value": "20000.0", "unit": "kg", "description": "Lorry mass (both trusses; each carries half)"},
    {"name": "k_tyre", "value": num(T["k"]), "unit": "N/m", "description": "Tyre stiffness per axle and truss"},
    {"name": "x_start", "value": "-25.0", "unit": "m", "description": "Start position of the lorry's centre of mass"},
    {"name": "y_start", "value": num(1.0 * -T["ry"] + T["r"] + deck_height(-25.0)),
     "unit": "m", "description": "Centre-of-mass height over the unloaded tyres at the start"},
]


def truck(Dg, x, y):
    m = "m_truck/2"
    Dg.node("Truck", "project:Truck2D", x, y,
            params={"m": m, "J": f"{m}*{(8.0 ** 2 + 2.5 ** 2) / 12.0!r}", "g0": num(C["g0"]),
                    "x0": "x_start", "y0": f"y_start - {m}*{C['g0']!r}/(2*k_tyre)",
                    "rx": vec([T["wheelbase"] / 2, -T["wheelbase"] / 2]), "ry": vec([T["ry"], T["ry"]]),
                    "r": num(T["r"]), "k": "k_tyre", "c": num(T["c"]), "v_set": "v_truck", "tau": num(T["tau"]),
                    "depth": num(-scene.LANE)},
            constants={"nn": str(NN), "nd": str(ND)},
            starts={"body/inertia/P": f"[0.0, {m}*v_truck, 0.0]"})
    for s in ("x", "y", "xd", "yd"):
        Dg.sig("Truss", s, "Truck", s)
    Dg.sig("Truck", "Fx", "Truss", "Fx")
    Dg.sig("Truck", "Fy", "Truss", "Fy")


COLLAPSE_DROP = 3.0     # the run stops when the midspan has dropped this far (a collapse)


def collapse_stop(Dg, x, y):
    """Stop the run once the bridge has collapsed: the midspan node 3 m below its start."""
    Dg.node("Midspan", "stdlib:continuous/Select", x, y, constants={"N": str(NN), "index": str(MID)})
    Dg.node("Drop", "stdlib:continuous/Gain", x + 160, y, params={"k": "-1.0"})
    Dg.node("Collapsed", "stdlib:sources/StopSimulation", x + 320, y, params={"threshold": num(COLLAPSE_DROP)})
    Dg.sig("Truss", "y", "Midspan", "u")
    Dg.sig("Midspan", "y", "Drop", "u")
    Dg.sig("Drop", "y", "Collapsed", "u")


def model(name, comment, Dg, sett, plots, *, globals_=None, bindings=True, dashboard=None, broken=True):
    doc = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": Dg.nodes, "connections": Dg.conns, "subsystemPorts": [], "annotations": []},
        "settings": sett,
        "plots": plots,
    }
    if globals_:
        doc["parameters"] = globals_
    if bindings:
        has_truck = any(n["name"] == "Truck" for n in Dg.nodes)
        doc["scene"] = {"file": "scenes/bridge.sdf" if has_truck else "scenes/bridge-load.sdf"}
        doc["bindings"] = scene.bindings(truck="Truck" if has_truck else None, broken=broken)
    if dashboard:
        doc["dashboard"] = dashboard
    path = MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} ({len(Dg.nodes)} nodes, {len(Dg.conns)} connections)")


def plot(pid, title, signals, unit=""):
    # The plot contract has no axis label; the unit goes into the title.
    return {"id": pid, "title": f"{title} [{unit}]" if unit else title, "signals": signals}


MEMBER_PLOT = [f"Truss/N[{k}]" for k in (3, 9, 12, WEAK, 17)]


def main():
    MODELS.mkdir(exist_ok=True)

    # 1. statics: dead load plus 100 kN at midspan, started at the linear solution, damped
    Dg = Diagram()
    truss(Dg, 300, 200, state="static")
    moving_load(Dg, 40, 200, C["P_static"], 15.0, 0.0)
    model("bridge-static",
          "Warren truss under its dead load and a 100 kN point load at midspan; member forces against the method of joints (design.py).",
          Dg, settings(2.0, 401), [
              plot("p1", "Member forces", MEMBER_PLOT, "N"),
              plot("p2", "Midspan deflection", [f"Truss/y[{MID}]"], "m"),
              plot("p3", "Support reactions", ["Truss/Ry[3]", "Truss/Ry[9]"], "N"),
          ])

    # 2. free vibration in the first bending mode, no damping
    phi_x, phi_y = np.array(D["modes"]["phi_x"]), np.array(D["modes"]["phi_y"])
    amp = 2 * np.pi * D["modes"]["f1"] * 0.005                         # 5 mm midspan amplitude
    Dg = Diagram()
    truss(Dg, 300, 200, beta=0.0, state="dead", velocity=(amp * phi_x, amp * phi_y))
    moving_load(Dg, 40, 200, 0.0, 0.0, 0.0)
    model("bridge-modes",
          "Free vibration in the first vertical bending mode (no damping): frequency against the eigenvalue problem of design.py, energy balance.",
          Dg, settings(5.0, 5001), [
              plot("p1", "Midspan deflection", [f"Truss/y[{MID}]"], "m"),
              plot("p2", "Energy", ["Truss/Ek", "Truss/Ee", "Truss/Eg", "Truss/Ebal"], "J"),
          ], bindings=True)

    # 3. a 100 kN point load crossing at 5 m/s (quasi-static)
    Dg = Diagram()
    truss(Dg, 300, 200, state="dead")
    moving_load(Dg, 40, 200, C["P_static"], -5.0, 5.0)
    model("bridge-moving-load",
          "A 100 kN point load crossing at 5 m/s: influence lines of the member forces and the midspan deflection.",
          Dg, settings(8.0, 1601), [
              plot("p1", "Member forces", MEMBER_PLOT, "N"),
              plot("p2", "Midspan deflection", [f"Truss/y[{MID}]"], "m"),
              plot("p3", "Support reactions", ["Truss/Ry[3]", "Truss/Ry[9]"], "N"),
          ])

    # 4. Euler buckling of one strut (Bar2D between two PinNode2D, pushed by a ramp)
    Dg = Diagram()
    Dg.node("A", "stdlib:planar/PinNode2D", 40, 200, params={"m": "1.0", "x0": "0.0", "y0": "0.0", "g0": "0.0"},
            constants={"support": "1"})
    Dg.node("Strut", "stdlib:planar/Bar2D", 260, 200, params={"A": "1.0e-3", "I": "1.0e-8", "rho": "0.0", "beta": "0.0"})
    Dg.node("B", "stdlib:planar/PinNode2D", 480, 200, params={"m": "100.0", "x0": "2.0", "y0": "0.0", "g0": "0.0"},
            constants={"support": "2"})
    Dg.node("Push", "stdlib:multibond/ExternalWrenchPlanar", 700, 200)
    Dg.node("Ramp", "stdlib:sources/Ramp", 700, 380, params={"slope": "-1.0e5"})
    Dg.node("Zero", "stdlib:sources/Constant", 480, 380, params={"value": "0.0"})
    Dg.bond("A", "p", "Strut", "a")
    Dg.bond("Strut", "b", "B", "p")
    Dg.bond("Push", "p", "B", "p")
    Dg.sig("A", "g", "Strut", "ga")
    Dg.sig("B", "g", "Strut", "gb")
    Dg.sig("Ramp", "y", "Push", "wx")
    Dg.sig("Zero", "y", "Push", "wr")
    Dg.sig("Zero", "y", "Push", "wy")
    model("strut-buckling",
          "A 2 m pin-ended strut pushed by a load growing at 100 kN/s: it fails at the Euler load pi^2 E I / L^2 = 5181.5 N.",
          Dg, settings(0.1, 2001), [
              plot("p1", "Axial force and Euler load", ["Strut/N", "Strut/Pcr"], "N"),
              plot("p2", "Failure flag", ["Strut/broken"], ""),
              plot("p3", "Energy lost at failure", ["Strut/Elost"], "J"),
          ], bindings=False)

    # 5. a lorry crossing at a safe speed
    truck_plots = [
        plot("p1", "Member forces", MEMBER_PLOT, "N"),
        plot("p2", "Utilisation of the second diagonal", [f"Truss/util[{WEAK}]"], ""),
        plot("p3", "Midspan deflection", [f"Truss/y[{MID}]"], "m"),
        plot("p4", "Lorry: speed and axle loads", ["Truck/v", "Truck/fn[1]", "Truck/fn[2]"], ""),
        plot("p5", "Failed bars", ["Truss/nfail"], ""),
    ]
    Dg = Diagram()
    truss(Dg, 300, 200, state="dead")
    truck(Dg, 40, 200)
    collapse_stop(Dg, 300, 420)
    model("bridge-crossing",
          "A 20 t lorry crossing the bridge at 10 m/s over the settled approach slab: every member stays well inside its strength.",
          Dg, settings(7.0, 1401), truck_plots, globals_=TRUCK_GLOBALS)

    # 6. the same bridge with an undersized diagonal: an overloaded 40 t lorry at 15 m/s breaks it
    area = list(D["A"])
    area[WEAK - 1] = D["vehicle"]["weak_area"]
    Dg = Diagram()
    truss(Dg, 300, 200, area=area, state="dead")
    truck(Dg, 40, 200)
    collapse_stop(Dg, 300, 420)
    fail_globals = [dict(g) for g in TRUCK_GLOBALS]
    fail_globals[0]["value"] = "15.0"
    fail_globals[1]["value"] = "40000.0"
    model("bridge-failure",
          "The second diagonal is undersized (1.4 x the quasi-static force of a 20 t lorry): it holds the 20 t lorry at any speed, but an overloaded 40 t lorry at 15 m/s snaps it and the bridge folds.",
          Dg, settings(4.0, 1601), truck_plots, globals_=fail_globals, dashboard=dashboard())


def dashboard():
    return {
        "autoRerun": True,
        "cards": [
            {"id": "d1", "kind": "text", "size": "2x1", "title": "Bridge",
             "options": {"markdown": True, "text": (
                 "An overloaded 40 t lorry crosses the truss bridge. The second diagonal from the left is **undersized**: it "
                 "holds a 20 t lorry at any speed, but not this one. The settled approach slab makes the lorry bounce, which "
                 "adds to the load. Move the **speed** or the **mass** and the model runs again.")}},
            {"id": "d2", "kind": "slider", "size": "2x1", "title": "Lorry speed", "parameter": "global:v_truck",
             "options": {"min": 2.0, "max": 30.0, "step": 0.5, "decimals": 1, "unit": "m/s"}},
            {"id": "d3", "kind": "slider", "size": "2x1", "title": "Lorry mass", "parameter": "global:m_truck",
             "options": {"min": 5000.0, "max": 50000.0, "step": 1000.0, "decimals": 0, "unit": "kg"}},
            {"id": "d4", "kind": "gauge", "size": "1x1", "title": "Diagonal 13 utilisation", "signals": [f"Truss/util[{WEAK}]"],
             "options": {"min": -1.0, "max": 1.2, "decimals": 2, "unit": "",
                         "zones": [{"from": -1.0, "to": 0.8, "tone": "good"}, {"from": 0.8, "to": 1.0, "tone": "warn"},
                                   {"from": 1.0, "to": 1.2, "tone": "bad"}]}},
            {"id": "d5", "kind": "value", "size": "1x1", "title": "Failed bars", "signals": ["Truss/nfail"],
             "options": {"decimals": 0, "unit": ""}},
            {"id": "d6", "kind": "plot", "size": "4x2", "title": "Member forces", "signals": MEMBER_PLOT},
            {"id": "d7", "kind": "plot", "size": "2x2", "title": "Midspan deflection", "signals": [f"Truss/y[{MID}]"]},
            {"id": "d8", "kind": "plot", "size": "2x2", "title": "Lorry axle loads", "signals": ["Truck/fn[1]", "Truck/fn[2]"]},
        ],
    }


if __name__ == "__main__":
    main()
