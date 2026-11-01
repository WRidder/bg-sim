# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write the cantilever-sections example: model, scene, expected checks, project file.

Three 2 m steel cantilevers side by side, clamped to one wall: a solid round bar, a solid
square bar and an IPE 100 I-beam (strong axis, web vertical) of the same area, so the same
mass per metre. One tip load (stepped/ramped constant force, sine, constant + sine or a
frequency sweep, the project block `TipLoad`) pushes every tip down. Each beam is the project
block `ModalCantilever` (three clamped-free assumed modes, the modal bond graph of the
cantilever-modes example), its section given by global parameters.

The expected values come from `reference.json`, written by the independent reference
`reference.py` (section properties, Euler-Bernoulli formulas, a finite element model):

    uv run examples/cantilever-sections/design/reference.py
    uv run examples/cantilever-sections/design/build.py
    uv run examples/run_checks.py --only cantilever-sections
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "cantilever-sections"
REF = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
INP = REF["inputs"]
BEAMS = REF["beams"]

E, RHO, FY, L, ZETA, G0 = INP["E"], INP["rho"], INP["fy"], INP["L"], INP["zeta"], INP["g0"]
IPE = INP["ipe"]
F0, T0 = INP["F0"], INP["t0"]
EPS_Y = FY / E  # yield strain: the full colour of the strain colouring
T_END = 10.0
T_END_SINE = 12.0
#: (instance name, label, beam key, the section's globals A, I, c)
INSTANCES = [
    ("Round", "round bar", "round", "A_rod", "I_rod", "d_rod/2"),
    ("Square", "square bar", "square", "A_sq", "I_sq", "a_sq/2"),
    ("IPE", "IPE 100", "ipe", "A_ipe", "I_ipe", "h/2"),
]
# scene layout (world z up, the wall face is the plane x = 0)
Z_BEAM = 1.2
Y_OF = {"round": -0.45, "square": 0.0, "ipe": 0.45}


def node(nid, name, block, x, y, params=None):
    return {
        "id": nid,
        "name": name,
        "block": block,
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": {},
        "starts": {},
        "ui": {"showLabel": True, "color": None},
    }


def end(nid, port=None):
    return {"node": nid} if port is None else {"node": nid, "port": port}


def conn(cid, kind, a, b):
    return {"id": cid, "kind": kind, "from": a, "to": b, "route": [], "label": None}


def globals_() -> list[dict]:
    g = [
        ("E", repr(E), "Pa", "Young's modulus (steel)"),
        ("rho", repr(RHO), "kg/m^3", "Density (steel)"),
        ("fy", repr(FY), "Pa", "Yield strength (S235)"),
        ("L", repr(L), "m", "Length of every beam, wall to tip"),
        ("zeta", repr(ZETA), None, "Modal damping ratio, every mode of every beam"),
        ("g0", "0.0", "m/s^2", "Gravity on the beams' own weight (0: tip force only; 9.81 adds the weight)"),
        ("Pi", "3.141592653589793", None, "pi (a global expression cannot use the built-in constant)"),
        ("h", repr(IPE["h"]), "m", "IPE 100: height"),
        ("b", repr(IPE["b"]), "m", "IPE 100: flange width"),
        ("tw", repr(IPE["tw"]), "m", "IPE 100: web thickness"),
        ("tf", repr(IPE["tf"]), "m", "IPE 100: flange thickness"),
        ("A_ipe", "2*b*tf + (h - 2*tf)*tw", "m^2", "I-beam area (no root fillets)"),
        ("I_ipe", "(b*h^3 - (b - tw)*(h - 2*tf)^3)/12", "m^4", "I-beam second moment, strong axis"),
        ("d_rod", "sqrt(4*A_ipe/Pi)", "m", "Round bar diameter: the I-beam's area"),
        ("A_rod", "Pi*d_rod^2/4", "m^2", "Round bar area"),
        ("I_rod", "Pi*d_rod^4/64", "m^4", "Round bar second moment"),
        ("a_sq", "sqrt(A_ipe)", "m", "Square bar side: the I-beam's area"),
        ("A_sq", "a_sq^2", "m^2", "Square bar area"),
        ("I_sq", "a_sq^4/12", "m^4", "Square bar second moment"),
    ]
    return [{"name": n, "value": v, "unit": u, "description": d} for (n, v, u, d) in g]


def bindings() -> list[dict]:
    strain = {"colormap": "coolwarm", "range": [-EPS_Y, EPS_Y]}
    off = (IPE["h"] - IPE["tf"]) / 2

    def deform(visual, inst, beam):
        return {
            "target": f"visual:{visual}",
            "property": "deformation",
            "family": "bending-y",
            "basis": "clamped-free",
            "beam": beam,
            "signal": [f"{inst}/eta[{i}]" for i in (1, 2, 3)],
            "strain": strain,
        }

    return [
        deform("round_bar", "Round", {"axis": "+z", "y": "+x"}),
        deform("square_bar", "Square", {"axis": "+x", "y": "-z"}),
        deform("ipe_top", "IPE", {"axis": "+x", "y": "-z", "neutral": [off, 0]}),
        deform("ipe_web", "IPE", {"axis": "+x", "y": "-z"}),
        deform("ipe_bottom", "IPE", {"axis": "+x", "y": "-z", "neutral": [-off, 0]}),
    ]


def dashboard() -> dict:
    f1 = {k: BEAMS[k]["f_eb"][0] for k in ("round", "square", "ipe")}
    intro = (
        "Three **2 m steel cantilevers of the same mass per metre** (7.77 kg/m): a round bar, a square bar "
        "and an **IPE 100** on its strong axis. One tip force pushes all three down. Pick the **load**, press **Run**, "
        "and open the **3D View**: the beams are coloured by the bending stress of their outer fibre "
        "(grey 0, dark red at the yield stress 235 MPa). The 3D deflection is drawn **x10 (exaggerated)** by default; "
        "pick x1 in the view for true scale.\n\n"
        f"First eigenfrequencies: round {f1['round']:.2f} Hz, square {f1['square']:.2f} Hz, IPE {f1['ipe']:.1f} Hz. "
        "A sine at the round bar's frequency (the default 6.42 Hz) shows resonance."
    )

    def slider(cid, title, param, lo, hi, step, decimals, unit):
        return {"id": cid, "kind": "slider", "size": "1x1", "title": title, "parameter": param,
                "options": {"min": lo, "max": hi, "step": step, "decimals": decimals, "unit": unit}}

    cards = [
        {"id": "intro", "kind": "text", "size": "2x2", "title": "Same mass, three sections",
         "options": {"markdown": True, "text": intro}},
        {"id": "mode", "kind": "select", "size": "2x1", "title": "Load", "parameter": "Load/mode"},
        slider("F0", "Constant force F0 (down)", "Load/F0", 0.0, 1000.0, 10.0, 0, "N"),
        slider("t_ramp", "Ramp time (0: step)", "Load/t_ramp", 0.0, 3.0, 0.05, 2, "s"),
        slider("Fa", "Sine amplitude", "Load/Fa", 0.0, 100.0, 1.0, 0, "N"),
        slider("f", "Sine frequency", "Load/f", 0.5, 60.0, 0.01, 2, "Hz"),
        slider("zeta", "Damping ratio", "global:zeta", 0.002, 0.1, 0.002, 3, ""),
        slider("g0", "Own weight (0 off, 9.81 on)", "global:g0", 0.0, 9.81, 9.81, 2, "m/s²"),
    ]
    for inst, label, key, *_ in INSTANCES:
        cards.append({"id": f"w_{key}", "kind": "value", "size": "1x1", "title": f"Tip deflection, {label}",
                      "signals": [f"{inst}/w_mm"], "options": {"decimals": 2, "unit": "mm", "sparkline": True}})
    cards.append({"id": "force", "kind": "value", "size": "1x1", "title": "Tip force (down)",
                  "signals": ["Load/F"], "options": {"decimals": 1, "unit": "N", "sparkline": True}})
    for inst, label, key, *_ in INSTANCES:
        cards.append({"id": f"s_{key}", "kind": "value", "size": "1x1", "title": f"Root stress, {label}",
                      "signals": [f"{inst}/sigma_MPa"], "options": {"decimals": 1, "unit": "MPa", "sparkline": True}})
    cards.append({"id": "spacer_m", "kind": "text", "size": "1x1", "title": "Root moment",
                  "options": {"markdown": True, "text": "Root bending moment `M` (N m) and stress `sigma` are from the equilibrium of the whole beam. **Utilisation** is |sigma| / fy: 1 is first yield at the wall."}})
    for inst, label, key, *_ in INSTANCES:
        cards.append({"id": f"u_{key}", "kind": "gauge", "size": "1x1", "title": f"Utilisation, {label}",
                      "signals": [f"{inst}/util"],
                      "options": {"min": 0.0, "max": 1.2, "decimals": 2, "unit": "",
                                  "zones": [{"from": 0.0, "to": 0.6, "tone": "good"}, {"from": 0.6, "to": 1.0, "tone": "warn"},
                                            {"from": 1.0, "to": 1.2, "tone": "bad"}]}})
    cards.append({"id": "M_ipe", "kind": "value", "size": "1x1", "title": "Root moment, IPE 100",
                  "signals": ["IPE/M"], "options": {"decimals": 1, "unit": "N m", "sparkline": True}})
    cards += [
        {"id": "p_w", "kind": "plot", "size": "4x2", "title": "Tip deflection (mm, down)",
         "signals": [f"{inst}/w_mm" for inst, *_ in INSTANCES]},
        {"id": "p_s", "kind": "plot", "size": "4x2", "title": "Bending stress at the wall (MPa)",
         "signals": [f"{inst}/sigma_MPa" for inst, *_ in INSTANCES]},
        {"id": "p_u", "kind": "plot", "size": "2x2", "title": "Utilisation |sigma| / fy",
         "signals": [f"{inst}/util" for inst, *_ in INSTANCES]},
        {"id": "p_f", "kind": "plot", "size": "2x2", "title": "Tip force (N, down)", "signals": ["Load/F"]},
    ]
    return {"autoRerun": False, "cards": cards}


def model() -> dict:
    nodes = [node("n1", "Load", {"ref": "project:TipLoad"}, 40, 220)]
    conns = []
    for k, (inst, _label, _key, a, i, c) in enumerate(INSTANCES):
        y = 60 + 160 * k
        src, beam = f"n{10 + k}", f"n{20 + k}"
        nodes.append(node(src, f"F{inst}", {"ref": "stdlib:bondgraph/MSe"}, 300, y))
        nodes.append(node(beam, inst, {"ref": "project:ModalCantilever"}, 560, y, {
            "L": "L", "E": "E", "rho": "rho", "A": a, "I": i, "c": c, "fy": "fy", "zeta": "zeta", "g0": "g0",
        }))
        conns.append(conn(f"c{10 + k}", "signal", end("n1", "F"), end(src, "u")))
        conns.append(conn(f"c{20 + k}", "bond", end(src, "p"), end(beam, "tip")))
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": NAME,
        "parameters": globals_(),
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {
            "t_start": 0.0,
            "t_end": T_END,
            "solver": "auto",
            "reltol": 1e-08,
            "abstol": 1e-11,
            "max_step": None,
            "output": {"mode": "points", "points": 10001},
            "event_limit": 10000,
        },
        "plots": [
            {"id": "p1", "title": "Tip deflection (mm, down)", "signals": [f"{n}/w_mm" for n, *_ in INSTANCES]},
            {"id": "p2", "title": "Bending stress at the wall (MPa)", "signals": [f"{n}/sigma_MPa" for n, *_ in INSTANCES]},
            {"id": "p3", "title": "Utilisation |sigma| / fy", "signals": [f"{n}/util" for n, *_ in INSTANCES]},
            {"id": "p4", "title": "Root bending moment (N m) and tip force (N)", "signals": [*(f"{n}/M" for n, *_ in INSTANCES), "Load/F"]},
        ],
        "scene": {"file": f"scenes/{NAME}.sdf", "exaggeration": 10},
        "bindings": bindings(),
        "dashboard": dashboard(),
    }


def _box(name, pose, size, rgba):
    return (f'      <visual name="{name}">\n        <pose>{pose}</pose>\n'
            f'        <geometry><box><size>{size[0]:.6g} {size[1]:.6g} {size[2]:.6g}</size></box></geometry>\n'
            f'        <material><diffuse>{rgba}</diffuse></material>\n      </visual>\n')


def scene() -> str:
    d = BEAMS["round"]["section"]["d"]
    a = BEAMS["square"]["section"]["a"]
    h, b, tw, tf = IPE["h"], IPE["b"], IPE["tw"], IPE["tf"]
    steel = "0.82 0.83 0.85 1"
    plate = "0.25 0.26 0.28 1"
    yr, ys, yi = Y_OF["round"], Y_OF["square"], Y_OF["ipe"]
    v = ""
    v += _box("wall", "-0.15 0 1.0 0 0 0", (0.3, 1.8, 2.0), "0.62 0.6 0.56 1")
    v += _box("floor", "1.1 0 -0.01 0 0 0", (3.0, 2.2, 0.02), "0.5 0.52 0.55 1")
    for key, y in (("round", yr), ("square", ys), ("ipe", yi)):
        v += _box(f"plate_{key}", f"0.006 {y} {Z_BEAM} 0 0 0", (0.012, 0.16, 0.18), plate)
    v += (f'      <visual name="round_bar">\n        <pose>{L / 2 + 0.012:.6g} {yr} {Z_BEAM} 0 1.5707963267948966 0</pose>\n'
          f'        <geometry><cylinder><radius>{d / 2:.6g}</radius><length>{L:.6g}</length></cylinder></geometry>\n'
          f'        <material><diffuse>{steel}</diffuse></material>\n      </visual>\n')
    x = L / 2 + 0.012
    v += _box("square_bar", f"{x:.6g} {ys} {Z_BEAM} 0 0 0", (L, a, a), steel)
    v += _box("ipe_top", f"{x:.6g} {yi} {Z_BEAM + (h - tf) / 2:.6g} 0 0 0", (L, b, tf), steel)
    v += _box("ipe_web", f"{x:.6g} {yi} {Z_BEAM} 0 0 0", (L, tw, h - 2 * tf), steel)
    v += _box("ipe_bottom", f"{x:.6g} {yi} {Z_BEAM - (h - tf) / 2:.6g} 0 0 0", (L, b, tf), steel)
    return f"""<?xml version="1.0"?>
<!--
  cantilever-sections: three 2 m steel cantilevers of the same area (7.77 kg/m), clamped to one
  wall (the plane x = 0, world z up), the tips at x = {L + 0.012:.3f} (the beams start at the 12 mm
  steel plates on the wall face):

    round_bar    a solid round bar, d = {d * 1e3:.2f} mm (a cylinder along its own z, turned to world x)
    square_bar   a solid square bar, a = {a * 1e3:.2f} mm
    ipe_top/web/bottom   an IPE 100 (h {h * 1e3:.0f}, b {b * 1e3:.0f}, tw {tw * 1e3:.1f}, tf {tf * 1e3:.1f} mm), web vertical

  Every beam visual takes a deformation binding (bending-y, clamped-free, the three modal
  coordinates <Beam>/eta[1..3]) with the beam y axis pointing down, and a strain colouring.
  The I-beam is three boxes: the flanges bend about the neutral axis of the whole section
  (`neutral` in the beam mapping), so their sections turn with the web's and their strain is
  the h/2 outer-fibre strain. The link is static: the beams are clamped, only their elastic
  deformation moves.
-->
<sdf version="1.9">
  <model name="cantilever_sections">
    <link name="rig">
      <pose>0 0 0 0 0 0</pose>
{v}    </link>
  </model>
</sdf>
"""


def expected() -> dict:
    r, s, i = BEAMS["round"], BEAMS["square"], BEAMS["ipe"]
    by = {"Round": r, "Square": s, "IPE": i}
    base: list[dict] = [{"kind": "no_diagnostics", "codes": ["E101", "E102", "E006", "W201", "W202"]}, {"kind": "scene_bindings"}]
    for inst, b in by.items():
        st = b["static"]
        base += [
            {"kind": "final_value", "signal": f"{inst}/w", "t": T_END, "value": st["w_tip"], "rtol": 2e-3,
             "note": f"Euler-Bernoulli F L^3/(3 E I) with I = {b['section']['I']:.6e} m^4; three modes give {st['w_tip_3modes'] / st['w_tip']:.5f} of it"},
            {"kind": "final_value", "signal": f"{inst}/M", "t": T_END, "value": st["M_root"], "rtol": 1e-3,
             "note": "root bending moment F L (equilibrium)"},
            {"kind": "final_value", "signal": f"{inst}/sigma", "t": T_END, "value": st["sigma"], "rtol": 1e-3,
             "note": f"M / W with W = I / c = {b['section']['W']:.6e} m^3"},
            {"kind": "final_value", "signal": f"{inst}/util", "t": T_END, "value": st["util"], "rtol": 1e-3,
             "note": "sigma / fy, fy = 235 MPa"},
            {"kind": "final_value", "signal": f"{inst}/M_modal", "t": T_END, "value": st["M_modal_3modes"], "rtol": 1e-3,
             "note": "the root moment from the curvature of three modes, 4 F L (1/l1^2 - 1/l2^2 + 1/l3^2) = 1.0210 F L: the series the viewer's strain colour uses"},
            {"kind": "final_value", "signal": f"{inst}/f[1]", "t": T_END, "value": b["f_eb"][0], "rtol": 1e-6,
             "note": "first root of 1 + cos(bL) cosh(bL) = 0 (brentq)"},
            {"kind": "final_value", "signal": f"{inst}/f[2]", "t": T_END, "value": b["f_eb"][1], "rtol": 1e-6, "note": "second root"},
            {"kind": "max_abs", "signal": f"{inst}/w", "from_t": 0.0, "to_t": T_END, "value": b["step"]["w_max_fe"], "rtol": 5e-3,
             "note": f"largest tip deflection after the step: the finite element step response ({REF['inputs']['n_el']} elements, every mode damped by zeta), {b['step']['overshoot']:.4f} x static"},
            {"kind": "fft_peak", "signal": f"{inst}/w", "from_t": T0, "to_t": 2.5 if inst == "IPE" else T_END,
             "min_hz": 2.0, "max_hz": 100.0, "value": b["f_eb"][0], "rtol": 0.01,
             "note": "the ring-down after the step is at the first Euler-Bernoulli eigenfrequency (damped by sqrt(1 - zeta^2) = 0.9998)"},
        ]
        if inst != "IPE":  # the I-beam's moment peak rides on its 516 Hz third mode: the 1 kHz output grid cannot resolve it
            base += [
                {"kind": "max_abs", "signal": f"{inst}/M", "from_t": 0.0, "to_t": T_END, "value": b["step"]["M_max_fe"], "rtol": 0.02,
                 "note": f"largest root moment after the step, {b['step']['M_max_fe'] / st['M_root']:.3f} F L: the finite element step response with every mode (the higher modes add to the first mode's 1.90)"},
                {"kind": "max_abs", "signal": f"{inst}/util", "from_t": 0.0, "to_t": T_END, "value": b["step"]["util_max_fe"], "rtol": 0.02,
                 "note": "the largest utilisation after the step (above 1: the elastic model does not yield)"},
            ]
    base += [
        {"kind": "ratio", "signal": "Round/w", "signal_b": "IPE/w", "t": T_END, "value": i["section"]["I"] / r["section"]["I"], "rtol": 2e-3,
         "note": "same mass, the I-beam is I_ipe / I_rod times stiffer"},
        {"kind": "ratio", "signal": "Square/w", "signal_b": "IPE/w", "t": T_END, "value": i["section"]["I"] / s["section"]["I"], "rtol": 2e-3,
         "note": "and I_ipe / I_sq times stiffer than the square bar"},
        {"kind": "max_abs", "signal": "Load/F", "value": F0, "rtol": 1e-12, "note": "the constant tip force"},
    ]

    def sine_checks(key: str) -> list[dict]:
        out: list[dict] = [{"kind": "no_diagnostics", "codes": ["E101", "E102", "E006", "W201", "W202"]}]
        for inst, b in by.items():
            v = b[key]
            out += [
                {"kind": "max_abs", "signal": f"{inst}/w", "from_t": 10.0, "to_t": T_END_SINE, "value": v["w_amp"], "rtol": 0.01,
                 "note": f"steady-state amplitude of the finite element frequency response at {v['f']:.4f} Hz, zeta on every mode ({v['dyn_factor']:.3f} x the static deflection of Fa)"},
                {"kind": "max_abs", "signal": f"{inst}/M", "from_t": 10.0, "to_t": T_END_SINE, "value": v["M_amp"], "rtol": 0.01,
                 "note": "root-moment amplitude, F L + w^2 int s rho A w ds of the finite element response"},
                {"kind": "max_abs", "signal": f"{inst}/sigma", "from_t": 10.0, "to_t": T_END_SINE, "value": v["sigma_amp"], "rtol": 0.01,
                 "note": "stress amplitude M / W"},
            ]
        return out

    off, res = r["sine_off"], r["sine_res"]
    sine_settings = {"t_end": T_END_SINE, "output": {"points": 24001}}
    weight: list[dict] = [{"kind": "no_diagnostics", "codes": ["E101", "E102", "E006", "W201", "W202"]}]
    for inst, b in by.items():
        wt = b["weight"]
        weight += [
            {"kind": "final_value", "signal": f"{inst}/w", "t": T_END, "value": wt["w_tip"], "rtol": 2e-3,
             "note": f"F L^3/(3 E I) + q L^4/(8 E I), q = rho A g = {wt['q']:.4f} N/m; three modes give {wt['w_tip_3modes'] / wt['w_tip']:.5f} of it"},
            {"kind": "final_value", "signal": f"{inst}/M", "t": T_END, "value": wt["M_root"], "rtol": 1e-3, "note": "F L + q L^2 / 2"},
            {"kind": "final_value", "signal": f"{inst}/sigma", "t": T_END, "value": wt["sigma"], "rtol": 1e-3, "note": "(F L + q L^2/2) / W"},
        ]
    return {
        "project": NAME,
        "description": "Three equal-mass steel cantilevers (round, square, IPE 100) under one tip force: static deflection, root moment, stress and utilisation against Euler-Bernoulli, eigenfrequencies against the characteristic equation, step and sine responses against an independent finite element model with modal damping.",
        "models": {
            NAME: {"checks": base},
            f"{NAME}-sine": {
                "model": NAME, "settings": sine_settings,
                "overrides": {"Load/mode": 1, "Load/Fa": off["Fa"], "Load/f": off["f"]},
                "checks": sine_checks("sine_off"),
            },
            f"{NAME}-resonance": {
                "model": NAME, "settings": sine_settings,
                "overrides": {"Load/mode": 1, "Load/Fa": res["Fa"], "Load/f": res["f"]},
                "checks": sine_checks("sine_res"),
            },
            f"{NAME}-weight": {
                "model": NAME, "overrides": {"global:g0": G0},
                "checks": weight,
            },
            f"{NAME}-sweep": {
                "model": NAME, "overrides": {"Load/mode": 3, "Load/Fa": 10.0},
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E006", "W201", "W202"]},
                    {"kind": "max_abs", "signal": "Load/F", "value": 10.0, "rtol": 1e-3, "note": "the sweep amplitude"},
                    {"kind": "max_abs_le", "signal": "IPE/util", "value": 0.08,
                     "note": "passing its 29.4 Hz resonance (near 7.5 s), the 10 N sweep stresses the I-beam about as much as the 250 N static load (0.065), and no more"},
                    {"kind": "max_abs_le", "signal": "Round/util", "value": 0.3,
                     "note": "the sweep crosses the round bar's 6.42 Hz resonance in about 0.07 s, too fast to build up the steady resonance amplitude: it peaks near 0.2, against 0.55 for a steady 10 N sine at 6.42 Hz"},
                ],
            },
        },
    }


def main() -> None:
    for sub in ("models", "scenes"):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    with open(ROOT / "models" / f"{NAME}.bgmodel.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(model(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(ROOT / "scenes" / f"{NAME}.sdf", "w", encoding="utf-8", newline="\n") as f:
        f.write(scene())
    with open(ROOT / "expected.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(expected(), f, indent=2)
        f.write("\n")
    with open(ROOT / "bgsim.project.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"format": "bgsim.project", "language": "0.1.0", "name": NAME, "models": [NAME],
                   "libraryDir": "library", "scenesDir": "scenes"}, f, indent=2)
        f.write("\n")
    for k, b in BEAMS.items():
        print(f"{k:7s} I {b['section']['I']:.6e} m^4  w {b['static']['w_tip'] * 1e3:.3f} mm  sigma {b['static']['sigma'] / 1e6:.2f} MPa  f1 {b['f_eb'][0]:.4f} Hz")
    print(f"yield strain {EPS_Y:.6e}; sine check {BEAMS['round']['sine_off']['f']} Hz, resonance {BEAMS['round']['sine_res']['f']:.6f} Hz")


if __name__ == "__main__":
    main()
