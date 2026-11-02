# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The dashboards of the eight models of the double-cart lab rig, and the monitor block they read.

The model generators call this module before they write a model (`design.py --write` / `--models`,
`rlmodels.py`, `robustmodels.py`), so a regeneration keeps the dashboards:

``add_monitor(doc, sample_time)``
    Adds ``Mon`` (``project:DoubleCartLabMonitor``) to a closed-loop model: the absolute link angles from
    upright in degrees, the larger of the two, the peak cart travel, and the limit lines of the cart plot
    (end stops +-1.0 m, the robustness test's +-0.95 m). It is sampled at the model's controller rate
    (`sample_time`), so it adds no solver stops. The plant model (the FMU source) gets no monitor.
``add_dashboard(doc, kind)``
    The dashboard of one model kind. All eight share one layout: a text card and two readouts, four value
    cards (the two angles, voltage, current), four plots (angles, cart with the limit lines, voltage and
    current, phase or the model's own signal), and a row of sliders for the next run.

    uv run examples/pendulum-double-cart-lab/design/dashboards.py

writes ``library/DoubleCartLabMonitor.jl``.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MONITOR = "DoubleCartLabMonitor"
CUT = math.radians(1.0)  # the wrap of the angles: [-181, 179) deg, so a link hanging at rest reads -180, not +-180

MONITOR_SOURCE = """\
@block DoubleCartLabMonitor begin
    # What the dashboards of the double-cart lab rig show (written by design/dashboards.py: do not edit).
    # Sampled at the controller's own rate (`sample_time`), so the block adds no solver stops: the absolute
    # link angles from the upward vertical in degrees, wrapped to [-181, 179) (from the joint encoders,
    # th1 = q1 - 90 deg, th2 = th1 + q2, the convention of the firmware; the cut sits 1 deg past -180 deg,
    # so a link hanging at rest does not flicker between -180 and +180), the larger of the two, and the peak
    # cart travel |x| since the start. The constant outputs are the limit lines of the cart plot: the rubber
    # end stops at +-x_rail and the robustness test's pass limit +-x_pass.
    @constants sample_time::Real = 0.001, [unit = "s", min = 1.0e-12, description = "Sample time (the controller's period)"]
    @inputs begin
        x::Real, [unit = "m", description = "Cart position (Rail/qout)"]
        q1::Real, [unit = "rad", description = "Joint 1 encoder: link 1 from the rail's x axis (Joint1/qout)"]
        q2::Real, [unit = "rad", description = "Joint 2 encoder: link 2 relative to link 1 (Joint2/qout)"]
    end
    @parameters begin
        x_rail::Real = 1.0, [unit = "m", description = "End stops: the free travel of the cart centre"]
        x_pass::Real = 0.95, [unit = "m", description = "Travel limit of the robustness test's pass rule"]
    end
    @variables begin
        a1::Real = -180.0, [description = "Link 1 from upright (deg), sampled"]
        a2::Real = -180.0, [description = "Link 2 from upright (deg), sampled"]
        xp::Real = 0.0, [unit = "m", description = "Peak |x| so far, sampled"]
    end
    @outputs begin
        th1::Real, [description = "Link 1 from the upward vertical (deg), wrapped to [-181, 179)"]
        th2::Real, [description = "Link 2 from the upward vertical (deg), wrapped to [-181, 179)"]
        dev::Real, [description = "The larger |angle| of the two links from upright (deg)"]
        x_peak::Real, [unit = "m", description = "Peak cart travel |x| since the start"]
        stop_hi::Real, [unit = "m", description = "End stop at +x_rail"]
        stop_lo::Real, [unit = "m", description = "End stop at -x_rail"]
        lim_hi::Real, [unit = "m", description = "Pass limit of the robustness test, +x_pass"]
        lim_lo::Real, [unit = "m", description = "Pass limit of the robustness test, -x_pass"]
    end
    @discrete Ts = sample_time begin
        t1 = q1 - 1.5707963267948966
        t2 = t1 + q2
        a1 = (mod(t1 + 3.159045946109736, 6.283185307179586) - 3.159045946109736) * 57.29577951308232
        a2 = (mod(t2 + 3.159045946109736, 6.283185307179586) - 3.159045946109736) * 57.29577951308232
        xp = max(xp, abs(x))
    end
    @equations begin
        th1 ~ a1
        th2 ~ a2
        dev ~ max(abs(a1), abs(a2))
        x_peak ~ xp
        stop_hi ~ x_rail
        stop_lo ~ -x_rail
        lim_hi ~ x_pass
        lim_lo ~ -x_pass
    end
end
"""


def write_monitor_block(lib: Path = ROOT / "library") -> Path:
    path = lib / f"{MONITOR}.jl"
    path.write_text(MONITOR_SOURCE, encoding="utf-8", newline="\n")
    return path


# ----------------------------------------------------------------------------- the monitor node
def _node(doc, name):
    return next((n for n in doc["diagram"]["nodes"] if n["name"] == name), None)


def _next_id(items, prefix: str) -> str:
    numbers = [int(m.group(1)) for item in items if (m := re.fullmatch(prefix + r"(\d+)", item["id"]))]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def _wrap_deg(a: float) -> float:
    """The block's wrap: [-181, 179) deg, the cut 1 deg below -180 deg."""
    return math.degrees((a + math.pi + CUT) % (2 * math.pi) - math.pi - CUT)


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def add_monitor(doc: dict, sample_time: float) -> dict:
    """``Mon`` on the rail and joint encoders; its sampled values start at the model's start pose."""
    nodes, conns = doc["diagram"]["nodes"], doc["diagram"]["connections"]
    q1 = _float(_node(doc, "Joint1")["params"].get("q0"), -math.pi / 2)
    q2 = _float(_node(doc, "Joint2")["params"].get("q0"), 0.0)
    x0 = _float(_node(doc, "EndStops")["starts"].get("x"), 0.0)
    t1 = q1 - math.pi / 2
    nid = _next_id(nodes, "n")
    nodes.append({
        "id": nid, "name": "Mon", "block": {"ref": f"project:{MONITOR}"}, "position": {"x": 80, "y": 980},
        "rotation": 0, "flipX": False, "params": {}, "constants": {"sample_time": repr(float(sample_time))},
        "starts": {"a1": repr(round(_wrap_deg(t1), 9)), "a2": repr(round(_wrap_deg(t1 + q2), 9)),
                   "xp": repr(abs(x0))},
        "ui": {"showLabel": True, "color": None},
    })
    for src, port, to in (("Rail", "qout", "x"), ("Joint1", "qout", "q1"), ("Joint2", "qout", "q2")):
        conns.append({"id": _next_id(conns, "s"), "kind": "signal",
                      "from": {"node": _node(doc, src)["id"], "port": port}, "to": {"node": nid, "port": to}})
    return doc


# ----------------------------------------------------------------------------- the dashboards
def card(cid, kind, size, title, **kw):
    c = {"id": cid, "kind": kind, "size": size, "title": title}
    c.update(kw)
    return c


def _slider(cid, title, parameter, lo, hi, step, decimals, unit):
    return card(cid, "slider", "1x1", title, parameter=parameter,
                options={"min": lo, "max": hi, "step": step, "decimals": decimals, "unit": unit})


GOOD_ANGLE = [{"from": -2.0, "to": 2.0, "tone": "good"}]
TRAVEL_ZONES = [{"from": 0.0, "to": 0.8, "tone": "good"}, {"from": 0.8, "to": 0.95, "tone": "warn"},
                {"from": 0.95, "to": 2.0, "tone": "bad"}]
PHASE3 = [{"from": -0.5, "to": 0.5, "tone": "info"}, {"from": 0.5, "to": 1.5, "tone": "warn"},
          {"from": 1.5, "to": 2.5, "tone": "good"}, {"from": 2.5, "to": 3.5, "tone": "bad"}]
PUSH_T = "Tip push at (40 ms)"

#: Per model kind: the text, the voltage signal, the phase readout, the fourth plot and the sliders.
KINDS = {
    "swingup": {
        "title": "Swing-up, balance and a push",
        "text": ("**Nominal firmware**, 1 kHz. Hanging until 1 s, planned swing-up, LQR catch at 4.0 s, 0.45 N tip "
                 "push at 7.5 s. Expect 10.7° after the push, 15.0 V, 0.39 m. Set a slider, press **Run** (about a "
                 "minute)."),
        "u": "Ctrl/u", "phase": ("Ctrl/phase", "Phase (0 to 2)"),
        "plot4": ("Phase (0 hold, 1 swing-up, 2 balance) and tip push (N)", ["Ctrl/phase", "PushPulse/y"]),
        "sliders": [("in_push", "Tip push (40 ms)", "PushPulse/amplitude", 0.0, 1.2, 0.05, 2, "N"),
                    ("in_tpush", PUSH_T, "PushPulse/t_start", 5.0, 11.0, 0.5, 1, "s"),
                    ("in_m2", "Link 2 mass (gains stay nominal)", "Body2/m", 0.15, 0.25, 0.005, 3, "kg")],
    },
    "balance": {
        "title": "Balance and a large push",
        "text": ("**Nominal LQR from the first tick.** A 2° lean is caught, then a 0.70 N tip push at 2 s (78 % of the "
                 "largest the design recovers). Expect 17.3°, 20.7 V, 0.24 m. Above 0.9 N it fails."),
        "u": "Ctrl/u", "phase": ("Ctrl/phase", "Phase (2 = balance)"),
        "plot4": ("Phase (2 balance) and tip push (N)", ["Ctrl/phase", "PushPulse/y"]),
        "sliders": [("in_push", "Tip push (40 ms)", "PushPulse/amplitude", 0.0, 1.2, 0.05, 2, "N"),
                    ("in_tpush", PUSH_T, "PushPulse/t_start", 0.5, 4.0, 0.25, 2, "s"),
                    ("in_m2", "Link 2 mass (gains stay nominal)", "Body2/m", 0.15, 0.25, 0.005, 3, "kg")],
    },
    "free": {
        "title": "Free swing (no control)",
        "text": ("**No control, motor shorted.** Released from rest at θ = (−126°, −69°), x = 0.05 m, for 2 s. The "
                 "bond graph matches the twin to 4.3e-4 rad (the fourth plot: the checked joint angles)."),
        "u": "Ctrl/u", "phase": ("Ctrl/phase", "Phase (0 = hold)"),
        "plot4": ("Joint encoder angles (rad): the twin check", ["Joint1/qout", "Joint2/qout"]),
        "sliders": [("in_m2", "Link 2 mass", "Body2/m", 0.15, 0.25, 0.005, 3, "kg"),
                    ("in_b2", "Joint 2 viscous friction", "Joint2/b", 0.0, 0.002, 0.0001, 4, "N m s/rad")],
    },
    "plant": {
        "title": "The plant of the RL environment",
        "text": ("**The plant alone, the FMU source for RL.** In: voltage `V`, tip force `F_push`. Out: encoders `x`, "
                 "`q1`, `q2` (rad), and `v`, `w1`, `w2`, `i_m`. Realism parameters are globals. Set a test voltage, "
                 "press **Run**."),
        "u": "V/y", "phase": None,
        "plot4": ("Realism forces: cart (N), joints (N m)", ["Realism/F", "Realism/tau1", "Realism/tau2"]),
        "sliders": [("in_v", "Test voltage V", "V/value", -6.0, 6.0, 0.5, 1, "V"),
                    ("in_f", "Tip force F_push (constant)", "F_push/value", -0.5, 0.5, 0.05, 2, "N"),
                    ("in_mcart", "Cart mass (global m_cart)", "global:m_cart", 0.76, 0.84, 0.01, 2, "kg")],
    },
    "rl": {
        "title": "Learned controller (R0.7)",
        "text": ("**One neural network** (R0.7, 200 Hz, imitation + PPO) on the ideal plant: swing-up from 1 s, "
                 "balance, a 0.45 N push at 7.5 s. Expect upright 2.7 s after the start, 10.9° after the push, 15.2 V, "
                 "0.39 m."),
        "u": "Policy/u", "phase": None,
        "plot4": ("Link angles the policy sees (rad) and tip push (N)", ["Policy/th1", "Policy/th2", "PushPulse/y"]),
        "sliders": [("in_push", "Tip push (40 ms)", "PushPulse/amplitude", 0.0, 1.2, 0.05, 2, "N"),
                    ("in_tpush", PUSH_T, "PushPulse/t_start", 5.0, 11.0, 0.5, 1, "s")],
    },
    "rl-robust": {
        "title": "Robust learned controller (R1)",
        "text": ("**R1 policy** (domain randomisation) on the realistic plant: realism forces, encoder noise, 2 ms "
                 "delay. Nominal scenario. Expect upright at 3.97 s, about 1° of jitter, 10.8° after the push, voltage "
                 "chatter."),
        "u": "Policy/u", "phase": None,
        "plot4": ("Measured link angles the policy sees (rad) and tip push (N)",
                  ["Policy/th1", "Policy/th2", "PushPulse/y"]),
        "sliders": [("in_push", "Tip push (40 ms)", "PushPulse/amplitude", 0.0, 1.2, 0.05, 2, "N"),
                    ("in_tpush", PUSH_T, "PushPulse/t_start", 5.0, 11.0, 0.5, 1, "s"),
                    ("in_noise", "Joint encoder noise (global)", "global:joint_noise", 0.0, 0.08, 0.01, 2, "deg"),
                    ("in_delay", "Loop delay (global)", "global:loop_delay", 0.0, 2.0, 1.0, 0, "ms")],
    },
    "robust": {
        "title": "Robust classical firmware",
        "text": ("**Robust classical firmware** (C1 multi-model LQR on an observer, 2 ms delay in the loop; C2 "
                 "tables). Timed scenario: swing-up from 1 s, catch 4.0 s, 0.45 N push 7.5 s. Expect 12.9°, 0.21 m."),
        "u": "Ctrl/u", "phase": ("Ctrl/phase", "Phase (0 to 3)"),
        "plot4": ("Phase (0 hold, 1 swing-up, 2 balance, 3 settle), link energy (J), tip push (N)",
                  ["Ctrl/phase", "Ctrl/energy", "PushPulse/y"]),
        "sliders": [("in_push", "Tip push (40 ms)", "PushPulse/amplitude", 0.0, 1.2, 0.05, 2, "N"),
                    ("in_tpush", PUSH_T, "PushPulse/t_start", 5.0, 11.0, 0.5, 1, "s"),
                    ("in_m2", "Link 2 mass (gains stay nominal)", "Body2/m", 0.15, 0.25, 0.005, 3, "kg")],
    },
    "recover": {
        "title": "Knock-down and recovery (C3)",
        "text": ("**State-driven firmware (C3).** Catch at 3.75 s; a 1.5 N / 100 ms knock-down at 7 s drops it; energy "
                 "removal, hanging rest, re-arm at 9.9 s, re-catch at 12.6 s. Expect one drop, 0.77 m peak, upright at "
                 "20 s."),
        "u": "Ctrl/u", "phase": ("Ctrl/phase", "Phase (0 to 3)"),
        "plot4": ("Phase (0 hold, 1 swing-up, 2 balance, 3 settle), link energy (J), tip push (N)",
                  ["Ctrl/phase", "Ctrl/energy", "PushPulse/y"]),
        "sliders": [("in_push", "Knock-down push (100 ms)", "PushPulse/amplitude", 0.0, 2.5, 0.1, 1, "N"),
                    ("in_tpush", "Knock-down at", "PushPulse/t_start", 5.0, 9.0, 0.25, 2, "s")],
    },
}


def dashboard(kind: str) -> dict:
    k = KINDS[kind]
    plant = kind == "plant"
    cards = [card("intro", "text", "2x1", k["title"], options={"markdown": True, "text": k["text"]})]
    if k["phase"] is not None:
        signal, title = k["phase"]
        cards.append(card("phase", "value", "1x1", title, signals=[signal],
                          options={"decimals": 0, "unit": "", "zones": PHASE3}))
    elif plant:
        cards.append(card("phase", "value", "1x1", "Cart x", signals=["Rail/qout"],
                          options={"decimals": 3, "unit": "m", "sparkline": True}))
    else:
        cards.append(card("phase", "value", "1x1", "Larger |θ| from upright", signals=["Mon/dev"],
                          options={"decimals": 2, "unit": "deg", "zones": [{"from": 0.0, "to": 2.0, "tone": "good"}]}))
    if plant:
        cards.append(card("xpeak", "value", "1x1", "Cart velocity", signals=["Rail/qdout"],
                          options={"decimals": 3, "unit": "m/s", "sparkline": True}))
        cards += [
            card("th1", "value", "1x1", "q1: link 1 from the rail axis", signals=["Joint1/qout"],
                 options={"decimals": 3, "unit": "rad"}),
            card("th2", "value", "1x1", "q2: link 2 relative to link 1", signals=["Joint2/qout"],
                 options={"decimals": 3, "unit": "rad"}),
        ]
    else:
        cards.append(card("xpeak", "value", "1x1", "Peak cart travel |x|", signals=["Mon/x_peak"],
                          options={"decimals": 3, "unit": "m", "zones": TRAVEL_ZONES}))
        cards += [
            card("th1", "value", "1x1", "θ1 from upright", signals=["Mon/th1"],
                 options={"decimals": 2, "unit": "deg", "zones": GOOD_ANGLE}),
            card("th2", "value", "1x1", "θ2 from upright", signals=["Mon/th2"],
                 options={"decimals": 2, "unit": "deg", "zones": GOOD_ANGLE}),
        ]
    cards += [
        card("u", "value", "1x1", "Motor voltage", signals=[k["u"]],
             options={"decimals": 2, "unit": "V", "sparkline": True,
                      "zones": [{"from": -24.0, "to": -23.5, "tone": "bad"}, {"from": 23.5, "to": 24.0, "tone": "bad"}]}),
        card("i", "value", "1x1", "Motor current", signals=["Motor/isense/y"],
             options={"decimals": 2, "unit": "A", "sparkline": True}),
    ]
    if plant:
        cards += [
            card("angles", "plot", "2x2", "Joint encoder angles q1, q2 (rad): the FMU outputs",
                 signals=["Joint1/qout", "Joint2/qout"]),
            card("cart", "plot", "2x2", "Cart position x (m): the FMU output; end stops at ±1.0 m",
                 signals=["Rail/qout"]),
        ]
    else:
        cards += [
            card("angles", "plot", "2x2", "Link angles from upright (deg)", signals=["Mon/th1", "Mon/th2"]),
            card("cart", "plot", "2x2", "Cart position (m), end stops ±1.0 m, test limit ±0.95 m",
                 signals=["Rail/qout", "Mon/stop_hi", "Mon/stop_lo", "Mon/lim_hi", "Mon/lim_lo"]),
        ]
    title4, signals4 = k["plot4"]
    cards += [
        card("ui", "plot", "2x2", "Motor voltage (V) and current (A)", signals=[k["u"], "Motor/isense/y"]),
        card("plot4", "plot", "2x2", title4, signals=signals4),
    ]
    cards += [_slider(*s) for s in k["sliders"]]
    return {"autoRerun": False, "cards": cards}


def add_dashboard(doc: dict, kind: str) -> dict:
    doc["dashboard"] = dashboard(kind)
    return doc


def finish(doc: dict, kind: str, sample_time: float | None) -> dict:
    """Monitor (unless `sample_time` is None) and dashboard: what every generator applies last."""
    if sample_time is not None:
        add_monitor(doc, sample_time)
    return add_dashboard(doc, kind)


if __name__ == "__main__":
    print("wrote", write_monitor_block())
