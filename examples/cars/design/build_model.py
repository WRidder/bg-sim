# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Generate the models and the bgsim.project.json of the `cars` example.

    uv run examples/cars/design/reference.py     # first: the independent references (design.json)
    uv run examples/cars/design/build_model.py

Every model is the same vehicle bond graph (`car.py`) with different drivers, grounds and start
states: the race car on flat ground (drop test, skid pad, top speed and braking) and the buggy
(drop test, a 25 % grade, rolling hills). The `*-sim` models are the FMU sources of the
host applications (apps/car-sim): their driver inputs are export inputs.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(HERE))

from bg import Diagram, ex, g, model_doc, num, settings, vec  # noqa: E402
from car import constant, vehicle, view  # noqa: E402
from vehicles import CORNERS, vehicles  # noqa: E402

V = vehicles()
DESIGN = json.loads((HERE / "design.json").read_text(encoding="utf-8")) if (HERE / "design.json").exists() else {}
# Pedal ramp durations (s). The end of a ramp is a time kink of its TimeTable; it is kept off the
# 10 ms output grid on purpose: a kink a few ulps from an output instant (10.0 + 0.05 against the
# grid point 10.049999...) traps the event root finder at that instant until the event limit (W206).
RAMP = 0.055
SIM_RAMP = 0.205

# The rolling hills of the buggy (an analytic height field: the TerrainSurface parameters).
# h(x, y) = h0 + sx x + sy y + sum a_i cos(kx_i x + ky_i y + ph_i); wavelengths 25..140 m.
HILLS = {
    "h0": 0.0, "sx": 0.0, "sy": 0.0,
    "a": [2.2, 1.4, 0.9, 0.45, 0.25, 0.12],
    "kx": [2 * math.pi / 140, 2 * math.pi / 90 * 0.6, -2 * math.pi / 70 * 0.8, 2 * math.pi / 45, 2 * math.pi / 33 * 0.3, 2 * math.pi / 25],
    "ky": [2 * math.pi / 160 * 0.5, 2 * math.pi / 90 * 0.8, 2 * math.pi / 70 * 0.6, -2 * math.pi / 55, 2 * math.pi / 33 * 0.95, 2 * math.pi / 40],
    "ph": [0.3, 1.9, 4.0, 2.6, 0.7, 5.1],
}


def drivers(d: Diagram, values: dict) -> None:
    """The driver signals Steer, Throttle, Brake, Reverse, Handbrake, Mu1..Mu4.
    A value is a number (Constant) or a tuple: ("table", t_start, dt, values) a linear
    TimeTable, ("step", t, before, after) a Step, ("hold", v_ref, xi0) a SpeedHold on the
    throttle (fed by Telemetry/speed)."""
    base = {"Steer": 0.0, "Throttle": 0.0, "Brake": 0.0, "Reverse": 0.0, "Handbrake": 0.0,
            "Mu1": 1.0, "Mu2": 1.0, "Mu3": 1.0, "Mu4": 1.0}
    base.update(values)
    for i, (name, val) in enumerate(base.items()):
        x, y = -900, -600 + 120 * i
        if not isinstance(val, tuple):
            constant(d, name, val, x, y)
        elif val[0] == "table":
            _, t0, dt, vals = val
            d.node(name, "stdlib:sources/TimeTable", x, y,
                   params={"t_start": num(t0), "sample_time": num(dt), "values": vec(vals), "method": "1"},
                   constants={"N": len(vals)})
        elif val[0] == "step":
            _, ts, a, b = val
            d.node(name, "stdlib:sources/Step", x, y, params={"t_step": num(ts), "initial": num(a), "final": num(b)})
        elif val[0] == "ramp":
            ramp_node(d, name, x, y, *val[1:])
        elif val[0] == "hold":
            _, vref, xi0 = val
            d.node(name, "project:SpeedHold", x, y, params={"kp": "0.5", "ki": "0.3"}, starts={"xi": num(xi0)})
            constant(d, "VRef", vref, x - 200, y)
            d.sig("VRef", "y", name, "v_ref")
            d.sig("Telemetry", "speed", name, "v")
        else:
            raise ValueError(val)


def staircase(levels, t_first, hold, ramp, t_end):
    """A linear TimeTable: 0 until t_first, then each level reached after `ramp` and held for
    `hold` seconds."""
    dt = ramp
    n = int(round(t_end / dt)) + 1
    vals = []
    for k in range(n):
        t = k * dt
        lev = 0.0
        for j, L in enumerate(levels):
            if t >= t_first + j * hold + ramp - 1e-9:
                lev = L
        vals.append(lev)
    return ("table", 0.0, dt, vals)


def plot(pid, title, signals, y_label=None):
    p = {"id": pid, "title": title, "signals": signals}
    if y_label:
        p["yLabel"] = y_label
    return p


PLOTS_RIDE = [
    plot("p_z", "CG height and attitude", ["Telemetry/z", "Telemetry/pitch", "Telemetry/roll"]),
    plot("p_fz", "Tyre loads", [f"{c}/Tyre/Fz" for c in CORNERS]),
    plot("p_travel", "Suspension travel (bump +)", [f"{c}/Strut/travel" for c in CORNERS]),
]
PLOTS_DRIVE = [
    plot("p_speed", "Speed", ["Telemetry/kmh"]),
    plot("p_motor", "Rear motor", ["MotorR/n_rpm", "MotorR/tau", "MotorR/tlim"]),
    plot("p_power", "Rear motor power and pedals", ["MotorR/P", "Throttle/y", "Brake/y"]),
    plot("p_battery", "Battery", ["Battery/soc", "Battery/V", "Battery/I"]),
    plot("p_acc", "Accelerations (g)", ["Telemetry/ax", "Telemetry/ay"]),
    plot("p_fz", "Tyre loads", [f"{c}/Tyre/Fz" for c in CORNERS]),
    plot("p_slip", "Longitudinal slip", [f"{c}/Tyre/kappa" for c in CORNERS]),
]
PLOTS_CORNER = [
    plot("p_lat", "Lateral acceleration and yaw rate", ["Telemetry/ay", "Telemetry/r"]),
    plot("p_beta", "Body slip and steering", ["Telemetry/beta", "Steering/dl", "Steering/dr"]),
    plot("p_alpha", "Slip angles", [f"{c}/Tyre/alpha" for c in CORNERS]),
    plot("p_fz", "Tyre loads", [f"{c}/Tyre/Fz" for c in CORNERS]),
    plot("p_roll", "Roll and speed", ["Telemetry/roll", "Telemetry/speed"]),
]


def scene_for(name: str) -> tuple[str, list]:
    """Scene file and pose bindings: the chassis, the four wheels (spin included) and the world
    (track or terrain), all relative to the chassis' horizontal position (CarView)."""
    veh = "racecar" if name.startswith("racecar") else "buggy"
    world = "hills" if name.startswith("buggy-hills") or name == "buggy-sim" else (
        "grade" if name.startswith("buggy-grade") else ("track" if name == "racecar-sim" else "flat"))
    scene = f"scenes/{veh}-{world}.sdf"
    sig = lambda port: [f"View/{port}[{i}]" for i in range(1, 8)]  # noqa: E731
    b = [{"target": "link:chassis", "property": "pose", "signal": sig("body")}]
    for i, c in enumerate(CORNERS):
        b.append({"target": f"link:wheel_{c.lower()}", "property": "pose", "signal": sig(f"w{i + 1}")})
        b.append({"target": f"link:hub_{c.lower()}", "property": "pose", "signal": sig(f"c{i + 1}")})
    b.append({"target": "link:world", "property": "pose", "signal": sig("ground")})
    return scene, b


def tune(d: Diagram, node: str, **params) -> None:
    """Replace parameters of a built node by expressions (globals the dashboard moves)."""
    n = next(n for n in d.nodes if n["name"] == node)
    n["params"].update({k: str(v) for k, v in params.items()})


def model(name, comment, v, start, drv, t_end, points, plots, ground="flat", terrain=None, extra=None,
          tuned=None, params=None):
    d = Diagram()
    drivers(d, drv)
    vehicle(d, v, start, ground=ground, terrain=terrain)
    view(d)
    if extra:
        extra(d)
    for node, kw in (tuned or {}).items():
        tune(d, node, **kw)
    scene, bindings = scene_for(name)
    return model_doc(name, comment, d, settings(t_end, points), plots, scene, bindings, params or [],
                     DASHBOARDS.get(name))


# --------------------------------------------------------------------------- dashboards
def d_text(cid, title, body, size="2x1"):
    return {"id": cid, "kind": "text", "size": size, "title": title, "options": {"markdown": True, "text": body}}


def d_slider(cid, title, param, lo, hi, step, decimals, unit=None, size="2x1"):
    o = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        o["unit"] = unit
    return {"id": cid, "kind": "slider", "size": size, "title": title, "parameter": f"global:{param}", "options": o}


def d_plot(cid, title, signals, size="2x2"):
    return {"id": cid, "kind": "plot", "size": size, "title": title, "signals": signals}


def d_gauge(cid, title, sig, lo, hi, decimals, unit, zones=None):
    o = {"min": lo, "max": hi, "decimals": decimals, "unit": unit}
    if zones:
        o["zones"] = [{"from": a, "to": b, "tone": t} for a, b, t in zones]
    return {"id": cid, "kind": "gauge", "size": "1x1", "title": title, "signals": [sig], "options": o}


def _dash_drive(motors):
    cards = [d_gauge("g1", "Speed", "Telemetry/kmh", 0.0, 300.0, 0, "km/h"),
             d_gauge("g2", "State of charge", "Battery/soc", 0.0, 1.0, 3, "",
                     [(0.0, 0.15, "bad"), (0.15, 1.0, "good")])]
    for k, a in enumerate(motors):
        cards.append(d_plot(f"m{k}", f"Motor {a}: torque and its limit (N m)", [f"Motor{a}/tau", f"Motor{a}/tlim"]))
    cards += [d_plot("b1", "Battery voltage (V) and current (A)", ["Battery/V", "Battery/I"]),
              d_plot("b2", "Speed (km/h)", ["Telemetry/kmh"])]
    return cards


DASHBOARDS = {
    "racecar-settle": {"autoRerun": True, "cards": [
        d_text("t", "Drop test", "The race car released 3 cm above its static ride height: heave and pitch ring down on "
               "the springs, the dampers and the tyres."),
        d_plot("p1", "CG height (m)", ["Telemetry/z"], "4x2"),
        d_plot("p2", "Tyre loads (N)", [f"{c}/Tyre/Fz" for c in CORNERS])]},
    "buggy-settle": {"autoRerun": True, "cards": [
        d_text("t", "Drop test", "The buggy released 3 cm above its static ride height on its soft, long-travel suspension."),
        d_plot("p1", "CG height (m)", ["Telemetry/z"], "4x2"),
        d_plot("p2", "Tyre loads (N)", [f"{c}/Tyre/Fz" for c in CORNERS])]},
    "racecar-skidpad": {"autoRerun": True, "cards": [
        d_text("t", "Skid pad", "25 m/s with three left steering levels. The race car is slightly oversteering at low "
               "lateral acceleration and the loads move to the right-hand tyres."),
        d_gauge("g1", "Lateral acceleration", "Telemetry/ay", 0.0, 1.5, 2, "g"),
        d_plot("p1", "Yaw rate (rad/s)", ["Telemetry/r"], "4x2"),
        d_plot("p2", "Tyre loads (N)", [f"{c}/Tyre/Fz" for c in CORNERS]),
        d_plot("p3", "Slip angles (rad)", [f"{c}/Tyre/alpha" for c in CORNERS])]},
    "racecar-launch": {"autoRerun": True, "cards": [
        d_text("t", "Launch", "Full accelerator from rest: the motor at its **torque limit** up to the base speed "
               "(P_max / T_max), then at its **power limit**. Move the limits."),
        d_slider("s1", "Motor torque limit (N m)", "T_max", 100.0, 400.0, 10.0, 0, "N m"),
        d_slider("s2", "Motor power limit (kW)", "P_max_kw", 50.0, 300.0, 5.0, 0, "kW"),
        *_dash_drive(["R"])]},
    "racecar-straight": {"autoRerun": True, "cards": [
        d_text("t", "Top speed and braking", "At the top speed the 260 kW balance the drag. At 10 s the brake pedal goes "
               "down: the motor **regenerates** up to its torque and power limits, the friction brakes do the rest."),
        d_slider("s1", "Brake pedal from 10 s", "brake_set", 0.1, 1.0, 0.05, 2),
        d_slider("s2", "Regeneration power limit (kW)", "P_regen_kw", 0.0, 250.0, 5.0, 0, "kW"),
        *_dash_drive(["R"])]},
    "buggy-grade": {"autoRerun": True, "cards": [
        d_text("t", "25 % grade", "The buggy holds 5 m/s up a 25 % grade with one motor per axle; the load moves to the "
               "rear axle."),
        d_gauge("g0", "Accelerator", "Throttle/y", 0.0, 1.0, 3, ""),
        *_dash_drive(["F", "R"]),
        d_plot("p1", "Tyre loads (N)", [f"{c}/Tyre/Fz" for c in CORNERS])]},
    "buggy-hills": {"autoRerun": True, "cards": [
        d_text("t", "Rolling hills", "The buggy over the analytic hills with a few steering inputs. The FL contact height "
               "and the terrain height there coincide."),
        d_slider("s1", "Speed set point (m/s)", "v_set", 3.0, 14.0, 0.5, 1, "m/s"),
        d_plot("p1", "FL contact height and terrain (m)", ["FL/Tyre/zc", "TerrainProbe/hq"], "4x2"),
        d_plot("p2", "Suspension travel (m)", [f"{c}/Strut/travel" for c in CORNERS]),
        d_plot("p3", "Tyre loads (N)", [f"{c}/Tyre/Fz" for c in CORNERS]),
        d_gauge("g1", "Speed", "Telemetry/kmh", 0.0, 60.0, 0, "km/h")]},
    "racecar-sim": {"autoRerun": True, "cards": [
        d_text("t", "The FMU source", "The race car with the car-sim interface. In bg-sim a short test drive feeds the "
               "inputs; in the FMU the host drives."),
        d_slider("s1", "Start charge", "soc0", 0.05, 1.0, 0.05, 2),
        *_dash_drive(["R"])]},
    "buggy-sim": {"autoRerun": True, "cards": [
        d_text("t", "The FMU source", "The buggy with the car-sim interface on the hills. In bg-sim a short test drive feeds "
               "the inputs; in the FMU the host drives."),
        d_slider("s1", "Start charge", "soc0", 0.05, 1.0, 0.05, 2),
        *_dash_drive(["F", "R"])]},
}


def settle(veh: str) -> dict:
    v = V[veh]
    return model(f"{veh}-settle", f"The {v['title'].lower()} dropped from 3 cm above its static ride height onto flat "
                 "ground: heave and pitch settle on the suspension and the tyres to the static corner loads "
                 "(design/reference.py: the 7-DOF ride model).",
                 v, {"dz": 0.03}, {}, 3.0, 601, PLOTS_RIDE)


def skidpad() -> dict:
    v = V["racecar"]
    st = staircase([-0.04, -0.08, -0.12], 1.0, 6.0, 0.5, 19.0)
    return model("racecar-skidpad", "Steady-state cornering at 25 m/s: a staircase of left steering inputs "
                 "(0.04, 0.08, 0.12 of full lock), the speed held by a PI on the accelerator. "
                 "Lateral acceleration, yaw rate, body slip and the four tyre loads against the nonlinear "
                 "four-wheel steady state and the linear bicycle model (design/reference.py).",
                 v, {"v": 25.0}, {"Steer": st, "Throttle": ("hold", 25.0, 0.13)},
                 19.0, 951, PLOTS_CORNER)


def launch() -> dict:
    v = V["racecar"]
    return model("racecar-launch", "Full accelerator from standstill for 12 s: the motor at its torque limit up to "
                 "the base speed, then at its power limit; speed, motor speed and torque, battery current and charge "
                 "against the 1-D longitudinal model of design/reference.py (tyre slip, wheel and rotor inertia, the "
                 "shaft, the battery).",
                 v, {"v": 0.0}, {"Throttle": 1.0}, 12.0, 1201, PLOTS_DRIVE,
                 tuned={"MotorR": {"T_max": "T_max", "P_max": "1000 * P_max_kw"}},
                 params=[g("T_max", v["motor"]["T_max"], "N*m", "Motor torque limit"),
                         g("P_max_kw", v["motor"]["P_max"] / 1000.0, None, "Motor power limit in kW")])


def straight() -> dict:
    v = V["racecar"]
    ts = DESIGN.get("racecar", {}).get("top_speed", {"V": 74.0, "twist": 0.0})
    tb = 10.0
    return model("racecar-straight", "Flat out from the top speed of the reference (design/reference.py: the motor at "
                 "its power limit against drag, rolling resistance and tyre slip) for 10 s, then the accelerator "
                 "released and the brake pedal at 50 %: regenerative braking on the rear motor within its torque and "
                 "power limits, the friction brakes for the rest, against the 1-D longitudinal model.",
                 v, {"v": ts["V"], "twistR": ts.get("twist", 0.0)},
                 {"Throttle": ("ramp", tb, RAMP, 1.0, 0.0), "Brake": ("ramp", tb, RAMP, 0.0, "brake_set")},
                 tb + 4.0, 1401, PLOTS_DRIVE,
                 tuned={"MotorR": {"P_regen": "1000 * P_regen_kw"}},
                 params=[g("brake_set", 0.5, None, "Brake pedal from 10 s (0..1)"),
                         g("P_regen_kw", v["motor"]["P_regen"] / 1000.0, None, "Regeneration power limit in kW")])


def grade() -> dict:
    v = V["buggy"]
    slope = 0.25
    gam = math.atan(slope)
    q = (math.cos(-gam / 2), 0.0, math.sin(-gam / 2), 0.0)
    h = v["h_s"]
    start = {"v": 5.0, "q": q, "x": -h * math.sin(gam), "z": h * math.cos(gam)}
    terrain = {"h0": 0.0, "sx": slope, "sy": 0.0, "a": [0.0], "kx": [0.0], "ky": [0.0], "ph": [0.0]}
    return model("buggy-grade", "The buggy climbing a 25 % grade (14 deg) at 5 m/s, one motor per axle, "
                 "the speed held by a PI on the throttle: the throttle it needs and the axle loads against the "
                 "steady state of design/reference.py (grade resistance, load transfer on the slope, the two "
                 "axle drives at the same torque).",
                 v, start, {"Throttle": ("hold", 5.0, 0.2)}, 12.0, 601, PLOTS_DRIVE,
                 ground="terrain", terrain=terrain)


def hills() -> dict:
    v = V["buggy"]
    # level start, every wheel at or above the ground at the static travel (the low ones drop)
    hmax = max(height(HILLS, v["corners"][c]["x"], v["corners"][c]["y"]) for c in CORNERS)
    start = {"v": 8.0, "z": hmax + v["h_s"] + 0.01}
    steer = staircase([0.0, -0.15, 0.1, 0.0], 4.0, 6.0, 1.0, 30.0)

    def probe(d: Diagram):
        # the terrain under the FL contact point, evaluated where the tyre says it touches
        d.node("ProbeFL", "project:XYPose", 300, 1100)
        d.sig("FL", "xc", "ProbeFL", "x")
        d.sig("FL", "yc", "ProbeFL", "y")
        d.node("TerrainProbe", "stdlib:contact/TerrainSurface", 500, 1100,
               params={"h0": num(HILLS["h0"]), "sx": num(HILLS["sx"]), "sy": num(HILLS["sy"]), "a": vec(HILLS["a"]),
                       "kx": vec(HILLS["kx"]), "ky": vec(HILLS["ky"]), "ph": vec(HILLS["ph"])},
               constants={"N": len(HILLS["a"])})
        d.sig("ProbeFL", "g", "TerrainProbe", "g")

    plots = PLOTS_DRIVE + [plot("p_contact", "FL contact height and the terrain there", ["FL/Tyre/zc", "TerrainProbe/hq"])]
    return model("buggy-hills", "The buggy over rolling hills (an analytic height field, wavelengths 25..140 m, "
                 "up to 4 m high) at 8 m/s with a few steering inputs: the tyres follow the "
                 "terrain's height and normal; the FL contact point lies on the terrain.",
                 v, start, {"Steer": steer, "Throttle": ("hold", "v_set", 0.25)}, 30.0, 1501, plots,
                 ground="terrain", terrain=HILLS, extra=probe,
                 params=[g("v_set", 8.0, "m/s", "Speed set point of the speed hold")])


# The FMU interface of the sim models (apps/car-sim): export inputs (marker, role, start) and
# outputs (marker, node, port). The roles are the vehicle's driver signals (car.vehicle).
SIM_INPUTS = [
    ("steer", "Steer", 0.0, "steering, -1 full left .. +1 full right"),
    ("throttle", "Throttle", 0.0, "accelerator pedal 0..1"),
    ("brake", "Brake", 0.0, "brake pedal 0..1 (regeneration first, then the friction brakes)"),
    ("reverse", "Reverse", 0.0, "0 forward, 1 reverse"),
    ("handbrake", "Handbrake", 0.0, "handbrake 0..1 (rear friction brakes)"),
    ("mu_fl", "Mu1", 1.0, "friction scale of the surface under the FL tyre"),
    ("mu_fr", "Mu2", 1.0, "friction scale under FR"),
    ("mu_rl", "Mu3", 1.0, "friction scale under RL"),
    ("mu_rr", "Mu4", 1.0, "friction scale under RR"),
]


def sim_outputs(v: dict) -> list:
    out = [(f"chassis_{k}", "ChassisPose", k) for k in ("px", "py", "pz", "qw", "qx", "qy", "qz")]
    out += [(k, "Telemetry", p) for k, p in (("speed", "speed"), ("kmh", "kmh"), ("u", "u"), ("v", "v"),
                                             ("ax_g", "ax"), ("ay_g", "ay"), ("yaw", "yaw"), ("pitch", "pitch"),
                                             ("roll", "roll"), ("yaw_rate", "r"), ("beta", "beta"))]
    for c in CORNERS:
        w = c.lower()
        out += [(f"{w}_{k}", f"Pose{c}", k) for k in ("px", "py", "pz", "qw", "qx", "qy", "qz")]
        out += [(f"{w}_spin", c, "th"), (f"{w}_omega", c, "omega"), (f"{w}_fz", c, "load"), (f"{w}_kappa", c, "kappa"),
                (f"{w}_alpha", c, "alpha"), (f"{w}_travel", c, "susp"), (f"{w}_xc", c, "xc"), (f"{w}_yc", c, "yc"),
                (f"{w}_zc", c, "zc")]
    out += [("steer_fl", "Steering", "dl"), ("steer_fr", "Steering", "dr")]
    for ax in v["motors"]:
        a = ax.lower()
        out += [(f"motor_{a}_rpm", "Motor" + ax, "n_rpm"), (f"motor_{a}_torque", "Motor" + ax, "tau"),
                (f"motor_{a}_tlim", "Motor" + ax, "tlim"), (f"motor_{a}_power", "Motor" + ax, "P"),
                (f"motor_{a}_regen", "Motor" + ax, "regen")]
    out += [("soc", "Battery", "soc"), ("battery_v", "Battery", "V"), ("battery_a", "Battery", "I"),
            ("battery_w", "Battery", "P")]
    return out


def sim(veh: str) -> dict:
    """`racecar-sim` (flat ground: the race track lies on z = 0, the host sets the friction per
    wheel from the surface under it) and `buggy-sim` (the hills): the FMU sources of the
    car-sim host. A short test drive feeds the ExportInputPass markers in bg-sim."""
    v = V[veh]
    d = Diagram()
    if veh == "racecar":
        stim = {"Steer": staircase([0.0, -0.1, 0.0], 2.0, 3.0, 0.5, 12.0), "Throttle": ("ramp", 1.0, SIM_RAMP, 0.0, 0.7),
                "Brake": ("ramp", 9.0, SIM_RAMP, 0.0, 0.6)}
        z0 = v["h_s"]
    else:
        stim = {"Steer": staircase([0.0, 0.2, 0.0], 3.0, 3.0, 0.5, 12.0), "Throttle": ("ramp", 1.0, SIM_RAMP, 0.0, 0.5),
                "Brake": ("ramp", 9.0, SIM_RAMP, 0.0, 0.5)}
        z0 = max(height(HILLS, v["corners"][c]["x"], v["corners"][c]["y"]) for c in CORNERS) + v["h_s"] + 0.01
    # the start pose and charge are globals (FMU parameters): the host places the car
    start = {"v": 0.0, "soc": "soc0", "x": "x0", "y": "y0", "z": "z0",
             "q": ("cos(0.5 * yaw0)", "0.0", "0.0", "sin(0.5 * yaw0)")}
    # the stimulus nodes are named Stim<role>; the markers carry the roles' signals
    renamed = {}
    for role, val in stim.items():
        renamed["Stim" + role] = val
    drivers_named(d, renamed)
    drv = {}
    for k, (marker, role, start_v, _) in enumerate(SIM_INPUTS):
        d.node(marker, "stdlib:converters/ExportInputPass", -600, -600 + 110 * k, params={"value": num(start_v)})
        src = "Stim" + role
        if src not in renamed:
            constant(d, src, start_v, -900, -600 + 110 * k)
        d.sig(src, "y", marker, "u")
        drv[role] = marker
    ground = "flat" if veh == "racecar" else "terrain"
    vehicle(d, v, start, ground=ground, terrain=HILLS if veh == "buggy" else None, drv=drv)
    view(d)
    d.node("ChassisPose", "project:PoseSplit", 2600, -800)
    d.sig("Pose", "g", "ChassisPose", "g")
    for i, c in enumerate(CORNERS):
        d.node(f"Pose{c}", "project:PoseSplit", 2600, -650 + 150 * i)
        d.sig(c, "g", f"Pose{c}", "g")
    for k, (marker, node, port) in enumerate(sim_outputs(v)):
        d.node(marker, "stdlib:converters/ExportOutput", 2900 + 220 * (k // 25), -800 + 60 * (k % 25))
        d.sig(node, port, marker, "u")
    scene, bindings = scene_for(f"{veh}-sim")
    params = [{"name": "soc0", "value": num(v["battery"]["soc0"]), "unit": None,
               "description": "Battery state of charge at the start (0..1)"},
              {"name": "x0", "value": "0.0", "unit": "m", "description": "Start position of the chassis CG, world x"},
              {"name": "y0", "value": "0.0", "unit": "m", "description": "Start position, world y"},
              {"name": "z0", "value": num(z0), "unit": "m",
               "description": "Start height of the chassis CG (the static ride height over the ground under the wheels "
                              "plus a little: the car drops onto its wheels)"},
              {"name": "yaw0", "value": "0.0", "unit": "rad", "description": "Start heading (0 = world x)"}]
    plots = [plot("p_speed", "Speed and pedals", ["Telemetry/kmh", "throttle/y", "brake/y"]),
             plot("p_motor", "Rear motor", ["MotorR/n_rpm", "MotorR/tau", "MotorR/tlim"]),
             plot("p_battery", "Battery", ["Battery/soc", "Battery/V", "Battery/I"]),
             plot("p_fz", "Tyre loads", [f"{c}/Tyre/Fz" for c in CORNERS])]
    world = "the race track (flat, z = 0)" if veh == "racecar" else "the rolling hills of buggy-hills"
    return model_doc(f"{veh}-sim", f"The drivable {v['title'].lower()} on {world}, with the FMU interface of the "
                     "car-sim host as export markers: inputs steer, throttle, brake, reverse, handbrake and the "
                     "friction scale per wheel; outputs the chassis and carrier poses, spin angles, tyre and "
                     "suspension states, telemetry, motor and battery. A short test drive feeds the inputs in "
                     "bg-sim. Generated by design/build_model.py.",
                     d, settings(12.0, 1201), plots, scene, bindings, params, DASHBOARDS.get(f"{veh}-sim"))


def drivers_named(d: Diagram, values: dict) -> None:
    """Stimulus nodes (numbers or tuples as in `drivers`, without the speed hold)."""
    for i, (name, val) in enumerate(values.items()):
        x, y = -900, -600 + 110 * i
        if not isinstance(val, tuple):
            constant(d, name, val, x, y)
        elif val[0] == "table":
            _, t0, dt, vals = val
            d.node(name, "stdlib:sources/TimeTable", x, y,
                   params={"t_start": num(t0), "sample_time": num(dt), "values": vec(vals), "method": "1"},
                   constants={"N": len(vals)})
        elif val[0] == "step":
            _, ts, a, b = val
            d.node(name, "stdlib:sources/Step", x, y, params={"t_step": num(ts), "initial": num(a), "final": num(b)})
        elif val[0] == "ramp":
            ramp_node(d, name, x, y, *val[1:])
        else:
            raise ValueError(val)


def ramp_node(d: Diagram, name, x, y, t0, dur, a, b) -> None:
    """A pedal change from a to b over [t0, t0 + dur]: a linear TimeTable of two samples (a and b
    may be global expressions). Pedal changes are ramps, not steps: a step that moves a
    min/max/clamp across its corner at the same instant makes the event handling re-fire at that
    instant (W206)."""
    d.node(name, "stdlib:sources/TimeTable", x, y,
           params={"t_start": num(t0), "sample_time": num(dur), "values": f"[{ex(a)}, {ex(b)}]", "method": "1"},
           constants={"N": 2})


def height(t: dict, x: float, y: float) -> float:
    return t["h0"] + t["sx"] * x + t["sy"] * y + sum(
        a * math.cos(kx * x + ky * y + ph) for a, kx, ky, ph in zip(t["a"], t["kx"], t["ky"], t["ph"]))


# --------------------------------------------------------------------------- expected.json
DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E101", "E102", "E106", "W206"],
        "note": "no algebraic loop, no causality conflict, no domain mismatch, no event storm"}


def cv(signal, t, value, note=None, **tol):
    c = {"kind": "cursor_value", "signal": signal, "t": round(float(t), 6), "value": float(value), **tol}
    if note:
        c["note"] = note
    return c


def at(ref: dict, key: str, t: float) -> float:
    return float(ref[key][min(range(len(ref["t"])), key=lambda k: abs(ref["t"][k] - t))])


def expected() -> dict:
    rc, bg = DESIGN["racecar"], DESIGN["buggy"]
    checks: dict[str, list] = {}
    # drop tests: the 7-DOF ride model of reference.py (heave, pitch, four unsprung masses, tyre springs)
    for veh, d in (("racecar", rc), ("buggy", bg)):
        dr = d["drop"]
        ch = [{"kind": "scene_bindings"}, DIAG]
        for k, t in enumerate(dr["t"]):
            ch.append(cv("Pose/pz", t, dr["z"][k], "CG height of the 7-DOF ride model (design/reference.py)" if k == 0
                         else None, abs=2e-4))
        for k, t in enumerate(dr["t"]):
            if t >= 0.3:
                ch.append(cv("FL/Tyre/Fz", t, dr["Fz_FL"][k], None, rtol=5e-3, abs=2.0))
                ch.append(cv("RL/Tyre/Fz", t, dr["Fz_RL"][k], None, rtol=5e-3, abs=2.0))
        for c in CORNERS:
            ch.append(cv(f"{c}/Tyre/Fz", 3.0, d["corners"][c]["Fz"], "static corner load", rtol=1e-3))
        checks[f"{veh}-settle"] = ch
    # skid pad: the nonlinear four-wheel steady state at each steering level
    ch = [{"kind": "scene_bindings"}, DIAG]
    for k, t in enumerate((7.0, 13.0, 19.0)):
        c = rc["corner"][k]
        ch.append(cv("Telemetry/r", t, c["r"], f"yaw rate at steer {c['steer']}: four-wheel steady state", rtol=5e-3))
        ch.append(cv("Telemetry/beta", t, c["beta"], "body slip angle", rtol=1e-2, abs=2e-4))
        for i, w in enumerate(CORNERS):
            ch.append(cv(f"{w}/Tyre/Fz", t, c["Fz"][i], None, rtol=1e-2))
    checks["racecar-skidpad"] = ch
    # launch: the 1-D longitudinal model (tyre slip, wheel and rotor inertia, shaft, battery, traction control)
    la = rc["launch"]
    ch = [{"kind": "scene_bindings"}, DIAG]
    for t in (2.0, 4.0, 6.0, 8.0, 10.0, 12.0):
        ch.append(cv("Telemetry/speed", t, at(la, "V", t),
                     "1-D longitudinal model; the model's tyre patch transient costs 0.2 m/s in the first 0.1 s"
                     if t == 2.0 else None, abs=0.35))
    for t in (2.0, 4.0):
        ch.append(cv("MotorR/tau", t, 300.0, "at the torque limit below the base speed" if t == 2.0 else None, rtol=1e-3))
    for t in (8.0, 12.0):
        ch.append(cv("MotorR/tau", t, at(la, "motor_torque", t), "at the power limit P_max / w", rtol=1e-2))
        ch.append(cv("MotorR/n_rpm", t, at(la, "motor_rpm", t), None, rtol=1e-2))
    for t in (4.0, 8.0, 12.0):
        ch.append(cv("Battery/soc", t, at(la, "soc", t), "battery charge: open-circuit voltage, R, the motor power"
                     if t == 4.0 else None, abs=3e-4))
    checks["racecar-launch"] = ch
    # straight: the top-speed equilibrium (power limit against drag, rolling resistance, slip), then regen braking
    ts, st = rc["top_speed"], rc["straight"]
    ch = [{"kind": "scene_bindings"}, DIAG,
          cv("Telemetry/speed", 9.9, ts["V"], "top speed: 260 kW against the drag, rolling resistance and slip", rtol=5e-3),
          cv("MotorR/tau", 9.9, ts["motor_torque"], "motor at the power limit", rtol=1e-2),
          cv("MotorR/n_rpm", 9.9, ts["motor_rpm"], None, rtol=5e-3),
          cv("Battery/I", 9.9, ts["battery_current"], "battery current at full power", rtol=1e-2)]
    for t in (11.0, 12.0, 13.0, 14.0):
        ch.append(cv("Telemetry/speed", t, at(st, "V", t), "regenerative plus friction braking at 50 % pedal"
                     if t == 11.0 else None, abs=0.6))
    for t in (10.5, 12.0):
        ch.append(cv("MotorR/tau", t, at(st, "motor_torque", t), "regen torque: power limit, then the pedal share"
                     if t == 10.5 else None, rtol=3e-2))
    checks["racecar-straight"] = ch
    # grade: the steady climb
    gr = bg["grade"]
    ch = [{"kind": "scene_bindings"}, DIAG,
          cv("Throttle/y", 12.0, gr["throttle"], "accelerator for 5 m/s up 25 %: steady state of design/reference.py", rtol=1e-2),
          cv("MotorF/tau", 12.0, gr["motor_torque"], "each motor", rtol=1e-2),
          cv("MotorR/tau", 12.0, gr["motor_torque"], None, rtol=1e-2),
          cv("MotorF/n_rpm", 12.0, gr["motor_rpm_f"], None, rtol=1e-2),
          cv("MotorR/n_rpm", 12.0, gr["motor_rpm_r"], None, rtol=1e-2),
          cv("FL/Tyre/Fz", 12.0, gr["Fz"][0], "load transfer to the rear on the slope", rtol=1e-2),
          cv("RL/Tyre/Fz", 12.0, gr["Fz"][2], None, rtol=1e-2),
          cv("Battery/I", 12.0, gr["battery_current"], None, rtol=3e-2)]
    checks["buggy-grade"] = ch
    checks["buggy-hills"] = [
        {"kind": "scene_bindings"}, DIAG,
        {"kind": "compare_signals", "signal": "FL/Tyre/zc", "signal_b": "TerrainProbe/hq", "from_t": 0.5,
         "max_abs": 2e-3, "note": "the FL contact point lies on the terrain (a second TerrainSurface at the contact x, y)"},
        {"kind": "min_ge", "signal": "FL/Tyre/Fz", "from_t": 0.5, "value": 300.0, "note": "the wheels stay on the ground"},
        {"kind": "min_ge", "signal": "RR/Tyre/Fz", "from_t": 0.5, "value": 300.0},
        cv("Telemetry/speed", 30.0, 8.0, "the speed hold", abs=1.0)]
    for veh in ("racecar", "buggy"):
        checks[f"{veh}-sim"] = [{"kind": "scene_bindings"}, DIAG,
                                {"kind": "max_abs_le", "signal": "Telemetry/speed", "value": 40.0,
                                 "note": "the bg-sim test drive of the FMU source runs"}]
    return {"project": "cars",
            "description": "Electric race car and buggy (3D multibond bond graphs). Numbers come from design/design.json: "
                           "the independent scipy references of design/reference.py (7-DOF ride model, four-wheel "
                           "steady-state cornering, 1-D longitudinal model with the motor envelope and the battery, "
                           "the grade equilibrium).",
            "models": {k: {"checks": v} for k, v in checks.items()}}


def main() -> int:
    out = EXAMPLE / "models"
    out.mkdir(exist_ok=True)
    models = {
        "racecar-settle": settle("racecar"),
        "racecar-skidpad": skidpad(),
        "racecar-launch": launch(),
        "racecar-straight": straight(),
        "buggy-settle": settle("buggy"),
        "buggy-grade": grade(),
        "buggy-hills": hills(),
        "racecar-sim": sim("racecar"),
        "buggy-sim": sim("buggy"),
    }
    only = sys.argv[1:]
    for nm, doc in models.items():
        if only and nm not in only:
            continue
        (out / f"{nm}.bgmodel.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("wrote", nm)
    proj = {"format": "bgsim.project", "language": "0.1.0", "name": "cars", "models": list(models),
            "libraryDir": "library", "scenesDir": "scenes"}
    (EXAMPLE / "bgsim.project.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8", newline="\n")
    (HERE / "hills.json").write_text(json.dumps(HILLS, indent=2) + "\n", encoding="utf-8", newline="\n")
    if DESIGN:
        (EXAMPLE / "expected.json").write_text(json.dumps(expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
        print("wrote expected.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
