# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the library blocks, models, scenes and dashboards of `quad-pendulum` from the design files.

    uv run examples/quad-pendulum/design/build_models.py

Reads `design/design_<rig>.json` and, if present, `design/design_<rig>_short.json` (written by `design.py`:
the full-travel and the short-travel controller of the same plant; so far the cart has both, the rotary arm
the full-travel one) and writes

- `library/QuadCartCtrl.jl`, `QuadCartTraj.jl`, `QuadCartMonitor.jl` and the `QuadRotary*` blocks (with a
  short-travel design both controllers in one firmware block; the dashboard's select `Traj/controller`
  picks one at run time);
- `models/quad-pendulum-swingup`, `-balance`, `-free` (cart) and `quad-rotary-swingup`, `-balance`,
  `-free` (rotary arm);
- `scenes/quad-pendulum.sdf`, `scenes/quad-pendulum-rotary.sdf`;
- `bgsim.project.json`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import blocks  # noqa: E402
import models as M  # noqa: E402
import scenes  # noqa: E402


def load(kind):
    p = HERE / f"design_{kind}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def card(cid, kind, size, title, **kw):
    c = {"id": cid, "kind": kind, "size": size, "title": title}
    c.update(kw)
    return c


def dashboard(dz, dzs, *, balance: bool, rotary: bool, auto: bool) -> dict:
    n = len(dz["L"])
    u_unit = "N m" if rotary else "N"
    s_sig = "J1/qout" if rotary else "Rail/qout"
    s_title = "Arm angle" if rotary else "Cart x"
    s_unit = "rad" if rotary else "m"
    u_title = "Torque" if rotary else "F"
    rig = "rotary arm" if rotary else "cart"
    if balance:
        text = (f"**Balance only.** The chain starts near upright, leaning by the start angles below, and the 1 kHz LQR "
                f"holds it. A tip push at {dz['balance']['push']['t_start']:g} s (50 ms) tests the recovery. Change an input: "
                + ("the model runs again on its own." if auto else "then press **Run**.")
                + " Try the actuator delay (1 ms steps), the quantised encoders, a heavier chain (the gains stay those of the nominal chain).")
    else:
        text = (f"**Swing-up and balance.** From hanging at rest the {rig} follows an offline-optimised trajectory "
                f"(feed-forward + time-varying LQR, **SWINGING UP**) and the 1 kHz LQR catches the chain upright (**BALANCING**). "
                "The stacked plot shows the energy of every link (kinetic + potential from the hanging rest) against the "
                f"UPRIGHT level {dz['E_up']:.2f} J. The swing-up run takes about a minute: change an input, then press **Run**.")
    two = dzs is not None
    if two:
        lim2 = f"±{dzs['travel']:g} m" if not rotary else f"±{math.degrees(dzs['travel']):.0f}°"
        text += (f" **Controller:** *full travel* plans the swing-up with the whole {'rail' if not rotary else 'arm range'}; "
                 f"*short travel* keeps the {'cart' if not rotary else 'arm'} within {lim2} (planned with that limit, same plant).")
    cards = [
        card("intro", "text", "2x1", "Quadruple inverted pendulum" + (" on a rotary arm" if rotary else ""),
             options={"markdown": True, "text": text}),
        card("swing", "indicator", "1x1", "SWINGING UP", signals=["Ctrl/swinging"], options={"threshold": 0.5, "onWhen": "above"}),
        card("bal", "indicator", "1x1", "BALANCING", signals=["Ctrl/balancing"], options={"threshold": 0.5, "onWhen": "above"}),
        card("time", "value", "1x1", "Time", signals=["Clock/y"], options={"decimals": 2, "unit": "s"}),
    ]
    for i in range(n):
        cards.append(card(f"th{i + 1}", "value", "1x1", f"θ{i + 1} from vertical", signals=[f"Mon/th{i + 1}"],
                          options={"decimals": 2, "unit": "deg", "zones": [{"from": -0.5, "to": 0.5, "tone": "good"}]}))
    if two:
        cards += [
            card("controller", "select", "2x1", f"Controller (full travel / short travel {lim2})", parameter="Traj/controller"),
            card("use", "value", "1x1", "Travel used", signals=["Mon/use"],
                 options={"decimals": 0, "unit": "% of limit", "sparkline": True,
                          "zones": [{"from": 0, "to": 80, "tone": "good"}, {"from": 80, "to": 100, "tone": "warn"},
                                    {"from": 100, "to": 1000, "tone": "bad"}]}),
        ]
    cards += [
        card("s", "value", "1x1", s_title, signals=[s_sig], options={"decimals": 3, "unit": s_unit, "sparkline": True}),
        card("u", "value", "1x1", u_title, signals=["Ctrl/u"], options={"decimals": 2, "unit": u_unit, "sparkline": True}),
        card("energy", "plot", "4x2", "Energy per link, stacked (J): E1, E1+E2, .. , total, and the UPRIGHT level",
             signals=[f"Mon/S{i + 1}" for i in range(n)] + ["Mon/E_up"]),
        card("angles", "plot", "2x2", "Link angles from vertical (deg)", signals=[f"Mon/th{i + 1}" for i in range(n)]),
        (card("su", "plot", "2x2", f"{s_title} ({s_unit}) with the controller's travel limit, and {u_title.lower()} ({u_unit})",
              signals=[s_sig, "Mon/lim_hi", "Mon/lim_lo", "Ctrl/u"]) if two else
         card("su", "plot", "2x2", f"{s_title} ({s_unit}) and {u_title.lower()} ({u_unit})", signals=[s_sig, "Ctrl/u"])),
    ]
    # inputs
    if balance:
        for i in range(n):
            cards.append(card(f"in_th{i + 1}", "slider", "1x1", f"Start θ{i + 1}", parameter=f"global:th0_{i + 1}",
                              options={"min": -4.0, "max": 4.0, "step": 0.1, "decimals": 1, "unit": "deg"}))
    push_max = 1.0 if not rotary else 0.1
    cards += [
        card("in_m", "slider", "1x1", "Link mass scale", parameter="global:m_scale",
             options={"min": 0.8, "max": 1.2, "step": 0.01, "decimals": 2, "unit": ""}),
        card("in_push", "slider", "1x1", "Tip push (50 ms)", parameter="PushPulse/amplitude",
             options={"min": 0.0, "max": push_max, "step": push_max / 50, "decimals": 3, "unit": "N"}),
        card("in_delay", "slider", "1x1", "Actuator delay", parameter="Ctrl/delay_n",
             options={"min": 0.0, "max": 10.0, "step": 1.0, "decimals": 0, "unit": "ms"}),
        card("in_quant", "toggle", "1x1", "Quantised encoders", parameter="Ctrl/quant"),
        card("in_umax", "slider", "1x1", f"{u_title} limit", parameter="Ctrl/u_max",
             options={"min": dz["u_max"] * 0.25, "max": dz["u_max"], "step": dz["u_max"] / 40, "decimals": 1 if not rotary else 2,
                      "unit": u_unit}),
        card("ledger", "plot", "2x2", "Energy ledger (J): E_tot, W_in, W_loss and E_tot − W_in + W_loss",
             signals=["Mon/E_tot", "Mon/W_in", "Mon/W_loss", "Mon/ledger"]),
        card("vcost", "plot", "2x2", "Catch region: LQR cost-to-go z'Pz (catch below " + f"{dz['catch_tol']:g})",
             signals=["Ctrl/vcost"]),
    ]
    return {"autoRerun": auto, "cards": cards}


def globals_(dz, balance):
    p = [M.gpar("m_scale", "1.0", None, "Scale of the link masses and inertias of the plant (the controller keeps the nominal gains)")]
    if balance:
        for i, v in enumerate(dz["balance"]["th0"]):
            p.append(M.gpar(f"th0_{i + 1}", repr(float(v)), "deg", f"Start angle of link {i + 1} from the upward vertical"))
    return p


def main():
    lib = ROOT / "library"
    mod = ROOT / "models"
    scn = ROOT / "scenes"
    for d in (lib, mod, scn):
        d.mkdir(exist_ok=True)
    names = []
    for kind in ("cart", "rotary"):
        dz, dzs = load(kind), load(f"{kind}_short")
        if dz is None:
            print(f"no design_{kind}.json: skipped")
            continue
        two = dzs is not None
        dzt = dzs if two else dz  # the longer-running swing-up sets the model's end time
        (lib / f"{dz['ctrl_block']}.jl").write_text(blocks.ctrl_source(dz, dzs), encoding="utf-8", newline="\n")
        (lib / f"{dz['ctrl_block'].replace('Ctrl', 'Traj')}.jl").write_text(blocks.traj_source(dz, dzs), encoding="utf-8", newline="\n")
        (lib / f"{dz['monitor_block']}.jl").write_text(blocks.monitor_source(dz, two), encoding="utf-8", newline="\n")
        rotary = kind == "rotary"
        prefix = "quad-rotary" if rotary else "quad-pendulum"
        build = M.build_rotary if rotary else M.build_cart
        t_end = max(dz["t_end"], dzt["t_end"])
        rig = "rotary arm (Furuta)" if rotary else "cart"
        bal = dz["balance"]
        push = {"amplitude": bal["push"]["amplitude"], "t_start": bal["push"]["t_start"], "duration": bal["push"]["duration"]}
        push_sw = dict(push, amplitude=0.0, t_start=dz["t_on"] + max(dz["t_s"], dzt["t_s"]) + 1.5)
        common = ("Plant: planar multibond bond graph (Prismatic2D rail, four Revolute2DCompliant joints with 1e8 N/m pivots, "
                  "RigidBody2D cart and links), ideal force actuator with viscous rail friction and soft end stops"
                  if not rotary else
                  "Plant: spatial multibond bond graph (Revolute3D arm joint about the vertical, four Revolute3D pendulum joints "
                  "about the arm axis, 1e8 stiff holds, RigidBody3D arm and links), ideal torque on the arm with bearing friction and hub inertia")
        sw = build(dz, name=f"{prefix}-swingup", mode="swingup", t_end=t_end, points=int(round(t_end * 200)) + 1,
                   comment=(f"Quadruple inverted pendulum on a {rig}: swing-up from hanging and balance. {common}. Firmware "
                            f"{dz['ctrl_block']} at 1 kHz: hold until {dz['t_on']:g} s, feed-forward + discrete TVLQR along the "
                            + (f"offline collocation trajectory (T_s = {dz['t_s']:g} s; short-travel controller {dzs['t_s']:g} s), latched LQR once in the catch region. "
                               "Traj/controller picks the full-travel (0) or the short-travel (1) controller. " if two else
                               f"offline collocation trajectory (T_s = {dz['t_s']:g} s), latched LQR once in the catch region. ")
                            + f"{dz['monitor_block']}: link angles, energy per link from the body twists and poses, the energy ledger."),
                   parameters=globals_(dz, False), dashboard=dashboard(dz, dzs, balance=False, rotary=rotary, auto=False), push=push_sw, two=two)
        th0 = [math.radians(v) for v in bal["th0"]]
        kw = {"phi0": th0} if rotary else {"th0": th0}
        bl = build(dz, name=f"{prefix}-balance", mode="balance", t_end=bal["t_end"], points=int(round(bal["t_end"] * 200)) + 1,
                   comment=(f"Quadruple inverted pendulum on a {rig}: balance only, from a disturbed upright start (global "
                            f"th0_1..th0_4, deg) with a 50 ms tip push at {push['t_start']:g} s. {common}. The firmware starts "
                            "latched in the balance phase (balance_only)."),
                   parameters=globals_(dz, True), dashboard=dashboard(dz, dzs, balance=True, rotary=rotary, auto=False), push=push, two=two, **kw)
        fr = dz["free"]
        if rotary:
            fkw = {"phi0": fr["z0"][1:], "s0": fr["z0"][0]}
        else:
            fkw = {"th0": fr["z0"][1:], "x0": fr["z0"][0]}
        fe = build(dz, name=f"{prefix}-free", mode="free", t_end=fr["t_end"], points=int(round(fr["t_end"] * 1000)) + 1,
                   comment=(f"Twin check of the {rig} plant: the same bond graph released at rest from a non-trivial pose with "
                            "the actuator off (t_on far in the future). design.py integrates its Lagrangian model from the same "
                            "pose; expected.json compares the joint angles and the base."),
                   reltol=1e-10, abstol=1e-12, two=two, **fkw)
        for doc in (sw, bl, fe):
            M.write(mod / f"{doc['name']}.bgmodel.json", doc)
            names.append(doc["name"])
        limit = dzs["travel"] if two else None
        sdf = scenes.rotary_sdf(dz, limit) if rotary else scenes.cart_sdf(dz, limit)
        (scn / ("quad-pendulum-rotary.sdf" if rotary else "quad-pendulum.sdf")).write_text(sdf, encoding="utf-8", newline="\n")
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "quad-pendulum", "models": names,
            "libraryDir": "library", "scenesDir": "scenes"}
    (ROOT / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", ", ".join(names))


if __name__ == "__main__":
    main()
