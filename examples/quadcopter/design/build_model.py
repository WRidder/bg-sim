# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Generate `models/quadcopter.bgmodel.json` from the data and gains of `design.py`.

The diagram is a plain node/connection list, so it is generated rather than hand-written: four
rotor chains and the three cascaded controller blocks repeat a lot. Run

    uv run examples/quadcopter/design/build_model.py

after every change of `design.py`; the model document is then reproducible from the design data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402

ROOT = HERE.parent
Z0 = 0.085                        # m  CoM height of the airframe standing on its legs
T_END = 18.0

nodes: list[dict] = []
conns: list[dict] = []
_ids = {"n": 0, "c": 0}


def node(name: str, ref: str, x: float, y: float, params: dict | None = None, starts: dict | None = None,
         constants: dict | None = None) -> str:
    _ids["n"] += 1
    nid = f"n{_ids['n']:02d}"
    nodes.append({
        "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": x, "y": y},
        "rotation": 0, "flipX": False,
        "params": {k: str(v) for k, v in (params or {}).items()},
        "constants": {k: str(v) for k, v in (constants or {}).items()},
        "starts": {k: str(v) for k, v in (starts or {}).items()},
        "ui": {"showLabel": True, "color": None},
    })
    return nid


def conn(kind: str, a: str, ap: str, b: str, bp: str, label: str | None = None) -> None:
    _ids["c"] += 1
    conns.append({
        "id": f"{kind[0]}{_ids['c']:02d}", "kind": kind, "from": {"node": a, "port": ap},
        "to": {"node": b, "port": bp}, "route": [], "label": label,
    })


def sig(a, ap, b, bp, label=None):
    conn("signal", a, ap, b, bp, label)


def build() -> dict:
    p = d.PARAMS
    # ------------------------------------------------------------------ airframe (multibond)
    world = node("World", "stdlib:multibond/GroundSpatial", 40, 420)
    free = node("Free", "stdlib:spatial/Free3D", 220, 420, starts={"pz": Z0})
    body = node("Body", "stdlib:spatial/RigidBody3D", 420, 420,
                params={"m": d.M_TRUE, "J": p["J"], "g0": d.G}, starts={"inertia/P": "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"})
    wrench = node("Wrench", "stdlib:multibond/ExternalWrenchSpatial", 420, 560)
    conn("bond", world, "p", free, "parent")
    conn("bond", free, "child", body, "p")
    conn("bond", wrench, "p", body, "p")
    for k in range(1, 7):
        se = node(f"FreeSe{k}", "stdlib:bondgraph/Se", 220, 560 + 50 * k, params={"e": "0.0"})
        conn("bond", se, "p", free, f"drive{k}")
    sig(free, "pose", body, "g", "pose chart (qw qx qy qz x y z)")

    # ------------------------------------------------------------------ landing gear (compliant contacts)
    legs: list[str] = []
    ground = node("Ground", "stdlib:contact/ContactSurface", 40, 300)
    for k, (fx, fy) in enumerate(d.FEET, start=1):
        lo = node(f"Local{k}", "stdlib:spatial/LocalPose3D", 220, 1250 + 70 * k, params={"x": fx, "y": fy, "z": -Z0})
        cp = node(f"Compose{k}", "stdlib:multibond/ComposePose3D", 400, 1250 + 70 * k)
        mt = node(f"Mount{k}", "stdlib:multibond/FixedTransform3DNeutral", 580, 1250 + 70 * k, params={"x": -fx, "y": -fy, "z": Z0})
        ct = node(f"Leg{k}", "stdlib:contact/ContactPoint", 760, 1250 + 70 * k, params=d.CONTACT)
        conn("bond", body, "p", mt, "b")
        conn("bond", mt, "a", ct, "p")
        sig(free, "pose", cp, "gp")
        sig(lo, "g", cp, "gl")
        sig(cp, "g", ct, "g")
        sig(ground, "o", ct, "o")
        sig(ground, "fr", ct, "fr")
        legs.append(ct)

    # ------------------------------------------------------------------ propulsion
    rw = node("RW", "project:RotorWrench", 620, 560,
              params={"rx": p["rx"], "ry": p["ry"], "spin": p["spin"], "kt": d.K_T, "bm": d.B_M, "Jr": d.J_M,
                      "m": d.M_TRUE, "cdx": d.CD[0], "cdy": d.CD[1], "cdz": d.CD[2], "cdr": d.CDR})
    for axis, port in zip(("tx", "ty", "tz", "fx", "fy", "fz"), ("tx", "ty", "tz", "fx", "fy", "fz")):
        sig(rw, axis, wrench, port)
    pk_t = node("PackT", "project:Pack4", 900, 700)
    pk_i = node("PackI", "project:Pack4", 900, 780)
    pk_w = node("PackW", "project:Pack4", 900, 860)
    pk_p = node("PackP", "project:Pack4", 900, 940)
    bat = node("Bat", "project:Battery", 1080, 940,
               params={"V_full": d.V_FULL, "V_empty": d.V_EMPTY, "R_int": d.R_INT, "capacity": d.CAPACITY})
    sig(pk_p, "y", bat, "P")
    sig(pk_t, "y", rw, "T")
    sig(pk_i, "y", rw, "i")
    sig(pk_w, "y", rw, "w")
    sig(free, "pose", rw, "pose")
    sig(body, "V", rw, "V")
    drv, prop, esc = [], [], []
    for k in range(1, 5):
        y = 60 + 150 * (k - 1)
        dr = node(f"Drv{k}", "stdlib:drives/ElectricDrive", 1300, y,
                  params={"R_w": d.R_W, "L": d.L_W, "k_t": d.K_T, "J_m": d.J_M, "b_m": d.B_M})
        pr = node(f"Prop{k}", "project:Propeller", 1500, y, params={"kT": d.KT_PROP, "kQ": d.KQ_PROP})
        es = node(f"Esc{k}", "project:Esc", 1100, y,
                  params={"k_e": d.K_E, "k_t": d.K_T, "R_w": d.R_W, "kQ": d.KQ_PROP, "b_m": d.B_M,
                          "Kp": p["esc"]["Kp"], "Ki": p["esc"]["Ki"]})
        conn("wire", dr, "shaft", pr, "shaft")
        sig(es, "u", dr, "u")
        sig(dr, "w", es, "w")
        sig(bat, "V", es, "vbat")
        sig(pr, "T", pk_t, f"u{k}")
        sig(dr, "i", pk_i, f"u{k}")
        sig(dr, "w", pk_w, f"u{k}")
        sig(dr, "P_el", pk_p, f"u{k}")
        drv.append(dr), prop.append(pr), esc.append(es)

    # ------------------------------------------------------------------ wind (discrete gusts + lag)
    wind = node("Wind", "project:Wind", 40, 1000, params={"mean": "[wind_x, wind_y, 0.0]", "sigma": "wind_sigma"})
    gust = node("Gust", "project:Gust", 220, 1000, params={"tau": 1.0}, starts={"x": "[wind_x, wind_y, 0.0]"})
    sig(wind, "wind", gust, "u")
    pk_f = node("PackLeg", "project:Pack4", 900, 1020)
    for k, ct in enumerate(legs, start=1):
        sig(ct, "f_n", pk_f, f"u{k}")
    sig(pk_f, "y", rw, "leg", "landing-gear normal forces")

    # ------------------------------------------------------------------ truth taps and sensors
    truth = node("Truth", "project:Truth", 620, 420)
    sig(free, "pose", truth, "pose")
    sig(body, "V", truth, "V")
    imu = node("Imu", "project:ImuSensor", 620, 760,
               params={"bgc": p["lp"]["bgc"], "agc": p["lp"]["agc"], "bac": p["lp"]["bac"], "aac": p["lp"]["aac"]})
    gps = node("Gps", "project:GpsSensor", 620, 900)
    sig(truth, "wb", imu, "w")
    sig(rw, "fs", imu, "f", "true specific force")
    sig(truth, "p", gps, "p")
    sig(truth, "vw", gps, "v")
    sig(truth, "yaw", gps, "yaw")

    # ------------------------------------------------------------------ flight controller
    nav = node("Nav", "project:NavFilter", 820, 60, params={**p["nav"], "g0": d.G},
               starts={"ps": f"[0.0, 0.0, {Z0}]"})
    clock = node("Clock", "stdlib:sources/Time", 600, 60)
    mission = node("Mission", "project:Waypoints", 820, 220, params={"p0": f"[0.0, 0.0, {Z0}]", "t_disarm": 17.4})
    pos = node("Pos", "project:PositionCtrl", 1000, 220,
               params={"m_nom": d.M_NOM, "g0": d.G, **{k: v for k, v in p["outer"].items() if k in ("Kp_xy", "Kv_xy", "Ki_xy", "Kp_z", "Kv_z", "Ki_z")}})
    att = node("Att", "project:AttitudeCtrl", 1180, 220, params={"K_rp": p["outer"]["K_rp"]})
    rate = node("Rate", "project:RateCtrl", 1180, 360, params=p["rate"])
    mix = node("Mix", "project:QuadMixer", 1000, 360,
               params={"Minv": p["Minv"], "kT": d.KT_PROP, "T_min": d.T_MIN, "T_max": d.T_MAX})
    unp = node("Unp", "project:Unpack4", 1000, 500)
    sig(clock, "y", mission, "tm")
    sig(imu, "gyro_f", nav, "gyro"), sig(imu, "acc_f", nav, "acc")
    sig(gps, "pm", nav, "pm"), sig(gps, "vm", nav, "vm"), sig(gps, "psim", nav, "psim"), sig(gps, "n", nav, "n")
    sig(mission, "p_sp", pos, "p_sp"), sig(mission, "v_sp", pos, "v_sp"), sig(mission, "a_sp", pos, "a_sp"), sig(mission, "psi_sp", pos, "psi_sp")
    sig(mission, "armed", pos, "armed"), sig(mission, "armed", rate, "armed"), sig(mission, "armed", mix, "armed")
    sig(nav, "p", pos, "p"), sig(nav, "v", pos, "v"), sig(nav, "q", pos, "q")
    sig(nav, "q", att, "q"), sig(pos, "qd", att, "qd"), sig(mission, "psi_rate", att, "yaw_rate_ff")
    sig(att, "w_sp", rate, "w_sp"), sig(nav, "w", rate, "w")
    sig(pos, "F", mix, "F"), sig(rate, "tau", mix, "tau")
    sig(mix, "w_cmd", unp, "u")
    for k in range(4):
        sig(unp, f"y{k + 1}", esc[k], "w_cmd")

    err = node("Err", "project:EstError", 820, 560)
    sig(nav, "p", err, "phat"), sig(nav, "v", err, "vhat"), sig(nav, "q", err, "qhat")
    sig(truth, "p", err, "p"), sig(truth, "vw", err, "v"), sig(truth, "q", err, "q"), sig(mission, "p_sp", err, "p_sp")

    # the dashboard's discrete gust, on top of the turbulence (off by default)
    pulse = node("GustPulse", "project:GustPulse", 400, 1000,
                 params={"A": "gust_speed", "dir_deg": "gust_dir", "t0": "gust_t", "T": "gust_T"})
    sig(gust, "y", pulse, "u")
    sig(pulse, "y", rw, "wind", "wind velocity (world)")

    plots = [
        {"id": "p1", "title": "Position and set-point (m)",
         "signals": ["Truth/x", "Truth/y", "Truth/z", "Mission/p_sp[1]", "Mission/p_sp[2]", "Mission/p_sp[3]"]},
        {"id": "p2", "title": "Altitude: truth, estimate and set-point (m)",
         "signals": ["Truth/z", "Nav/p[3]", "Mission/p_sp[3]"]},
        {"id": "p3", "title": "Attitude (rad): roll, pitch, yaw and yaw set-point",
         "signals": ["Truth/roll", "Truth/pitch", "Truth/yaw", "Mission/psi_sp"]},
        {"id": "p4", "title": "Rotor speeds (rad/s)", "signals": [f"Drv{k}/rotor/w" for k in range(1, 5)]},
        {"id": "p5", "title": "Roll rate: set-point, estimate and truth (rad/s)",
         "signals": ["Att/w_sp[1]", "Nav/w[1]", "Truth/wb[1]"]},
        {"id": "p6", "title": "Navigation filter errors", "signals": ["Err/pos", "Err/vel", "Err/att"]},
        {"id": "p9", "title": "Tracking error: distance to the set-point (m)", "signals": ["Err/track"]},
        {"id": "p7", "title": "Battery voltage (V) and current (A)", "signals": ["Bat/V", "Bat/I"]},
        {"id": "p8", "title": "Landing-gear normal forces (N)", "signals": [f"Leg{k}/f_n" for k in range(1, 5)]},
        {"id": "p10", "title": "Wind at the airframe (m/s): x, y and the discrete gust",
         "signals": ["GustPulse/y[1]", "GustPulse/y[2]", "GustPulse/g"]},
    ]
    bindings = [{"target": "link:body", "property": "pose",
                 "signal": ["Truth/q[1]", "Truth/q[2]", "Truth/q[3]", "Truth/q[4]", "Truth/x", "Truth/y", "Truth/z"]}]
    for k in range(1, 5):
        bindings.append({"target": f"joint:rotor_{k}", "property": "position", "signal": f"Drv{k}/rotor/phi",
                         "gain": float(d.SPIN[k - 1]), "offset": 0.0})
    bindings.append({"target": "joint:wind_vane", "property": "position", "signal": "GustPulse/heading"})
    bindings.append({"target": "visual:vane_arrow", "property": "color", "signal": "GustPulse/speed",
                     "colormap": "heat", "range": [0.0, 8.0]})

    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "quadcopter",
        "$comment": "X5.7: a 450 mm X quadcopter with a PX4-style cascaded flight controller. Generated by design/build_model.py from design/design.py; see the README.",
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": T_END, "solver": "auto", "reltol": 1e-4, "abstol": 1e-6,
                     "max_step": None, "output": {"mode": "points", "points": int(T_END * 100) + 1}, "event_limit": 100000},
        "plots": plots,
        "scene": {"file": "scenes/quadcopter.sdf"},
        "bindings": bindings,
        "parameters": GLOBALS,
        "dashboard": dashboard(),
    }


def glob(name, value, unit, description):
    return {"name": name, "value": value, "unit": unit, "description": description}


GLOBALS = [
    glob("wind_x", "0.4", "m/s", "Mean wind, world x (the wind blows towards +x)"),
    glob("wind_y", "-0.2", "m/s", "Mean wind, world y"),
    glob("wind_sigma", str(d.WIND_SIGMA), "m/s",
         "Turbulence: standard deviation of the Gaussian gusts (a new one every 0.5 s, 1 s lag)"),
    glob("gust_speed", "0.0", "m/s", "Peak speed of the discrete 1-cos gust (0: off)"),
    glob("gust_dir", "90.0", "deg", "Direction the gust blows towards (world, from +x; 90 = +y)"),
    glob("gust_t", "6.0", "s", "Start of the gust"),
    glob("gust_T", "2.0", "s", "Duration of the gust"),
]


def dashboard() -> dict:
    def slider(cid, title, param, lo, hi, step, decimals, unit):
        return {"id": cid, "kind": "slider", "size": "1x1", "title": title, "parameter": f"global:{param}",
                "options": {"min": lo, "max": hi, "step": step, "decimals": decimals, "unit": unit}}

    def value(cid, title, signal, decimals, unit):
        return {"id": cid, "kind": "value", "size": "1x1", "title": title, "signals": [signal],
                "options": {"decimals": decimals, "unit": unit, "sparkline": True}}

    # rows of four columns: intro, mean wind | turbulence, gust | duration, readouts | readouts | plots.
    # No automatic re-run: the 18 s mission takes about a minute.
    return {"autoRerun": False, "cards": [
        {"id": "intro", "kind": "text", "size": "2x1", "title": "Quadcopter in the wind", "options": {"markdown": True, "text":
            "The wind drags on the airframe: a **mean wind**, **turbulence** (Gaussian gusts) and a "
            "**discrete gust** (1-cos, off at 0 m/s). Press **Run** after a change: the 18 s mission takes about a minute."}},
        slider("wind_x", "Mean wind x", "wind_x", -5.0, 5.0, 0.1, 1, "m/s"),
        slider("wind_y", "Mean wind y", "wind_y", -5.0, 5.0, 0.1, 1, "m/s"),
        slider("sigma", "Turbulence", "wind_sigma", 0.0, 2.0, 0.05, 2, "m/s"),
        slider("gust", "Gust peak", "gust_speed", 0.0, 8.0, 0.25, 2, "m/s"),
        slider("gust_dir", "Gust towards", "gust_dir", -180.0, 180.0, 5.0, 0, "deg"),
        slider("gust_t", "Gust at", "gust_t", 1.0, 16.0, 0.25, 2, "s"),
        slider("gust_T", "Gust duration", "gust_T", 0.25, 5.0, 0.25, 2, "s"),
        value("wind_speed", "Wind speed", "GustPulse/speed", 2, "m/s"),
        value("track", "Distance to the set-point", "Err/track", 3, "m"),
        {"id": "tilt", "kind": "gauge", "size": "1x1", "title": "Tilt (limit 25 deg)", "signals": ["Truth/tilt"],
         "options": {"min": 0.0, "max": 0.5, "decimals": 3, "unit": "rad",
                     "zones": [{"from": 0.0, "to": 0.35, "tone": "good"}, {"from": 0.35, "to": 0.436, "tone": "warn"},
                               {"from": 0.436, "to": 0.5, "tone": "bad"}]}},
        value("alt", "Altitude", "Truth/z", 3, "m"),
        {"id": "rotor", "kind": "gauge", "size": "1x1", "title": "Rotor 1 speed", "signals": ["Drv1/rotor/w"],
         "options": {"min": 0.0, "max": 800.0, "decimals": 0, "unit": "rad/s",
                     "zones": [{"from": 0.0, "to": 700.0, "tone": "good"}, {"from": 700.0, "to": 775.0, "tone": "warn"},
                               {"from": 775.0, "to": 800.0, "tone": "bad"}]}},
        value("current", "Battery current", "Bat/I", 1, "A"),
        value("soc", "State of charge", "Bat/soc", 4, ""),
        {"id": "plot_wind", "kind": "plot", "size": "4x2", "title": "Wind at the airframe (m/s)",
         "signals": ["GustPulse/y[1]", "GustPulse/y[2]", "GustPulse/g"]},
        {"id": "plot_pos", "kind": "plot", "size": "4x2", "title": "Position and set-point (m)",
         "signals": ["Truth/x", "Truth/y", "Truth/z", "Mission/p_sp[1]", "Mission/p_sp[2]", "Mission/p_sp[3]"]},
        {"id": "plot_err", "kind": "plot", "size": "4x2", "title": "Distance to the set-point (m) and tilt (rad)",
         "signals": ["Err/track", "Truth/tilt"]},
    ]}


# ----------------------------------------------------------------------------- 3D scene
def _visual(name, geometry, pose, rgba):
    x, y, z, roll, pitch, yaw = pose
    return (
        f'      <visual name="{name}">\n'
        f'        <pose>{x:.5g} {y:.5g} {z:.5g} {roll:.7g} {pitch:.7g} {yaw:.7g}</pose>\n'
        f'        <geometry>{geometry}</geometry>\n'
        f'        <material><diffuse>{rgba}</diffuse></material>\n'
        f'      </visual>\n'
    )


def _box(sx, sy, sz):
    return f"<box><size>{sx:.5g} {sy:.5g} {sz:.5g}</size></box>"


def _cyl(r, h):
    return f"<cylinder><radius>{r:.5g}</radius><length>{h:.5g}</length></cylinder>"


def build_scene() -> str:
    import math

    out = []
    out.append('''<?xml version="1.0"?>
<!--
  quadcopter (X5.7): a 450 mm X quadcopter with four spinning rotors above a ground plane. Generated by
  design/build_model.py from the numbers of design/design.py.

  Z-up, metres. The link "body" is the airframe frame at the centre of mass (x forward, y left, z up); its
  pose is bound to the seven pose signals of the model. The four rotor links sit above the motors and turn
  about the body z axis (joints "rotor_1" .. "rotor_4", bound to the integrated rotor angles; the clockwise
  rotors 3 and 4 carry gain -1). The front of the airframe is marked by the red nose block; one blade tip of
  every rotor is orange so the rotation is visible. The pads on the ground mark the mission: take-off at the
  origin, then (2, 0), (2, 2) and back.
-->
<sdf version="1.9">
  <model name="quadcopter">
    <link name="ground">
      <pose>0 0 0 0 0 0</pose>
''')
    out.append(_visual("floor", _box(8.0, 8.0, 0.02), (0.8, 0.8, -0.01, 0, 0, 0), "0.62 0.64 0.66 1"))
    for i, (px, py, col) in enumerate([(0.0, 0.0, "0.2 0.6 0.3 1"), (2.0, 0.0, "0.9 0.75 0.2 1"), (2.0, 2.0, "0.9 0.75 0.2 1")]):
        out.append(_visual(f"pad_{i}", _cyl(0.22, 0.006), (px, py, 0.003, 0, 0, 0), col))
    out.append("    </link>\n\n    <link name=\"body\">\n      <pose>0 0 0 0 0 0</pose>\n")
    out.append(_visual("plate_bottom", _box(0.17, 0.12, 0.012), (0, 0, -0.012, 0, 0, 0), "0.1 0.1 0.12 1"))
    out.append(_visual("battery", _box(0.13, 0.045, 0.032), (0, 0, -0.04, 0, 0, 0), "0.25 0.3 0.7 1"))
    out.append(_visual("plate_top", _box(0.12, 0.10, 0.006), (0, 0, 0.014, 0, 0, 0), "0.15 0.15 0.18 1"))
    out.append(_visual("electronics", _box(0.06, 0.05, 0.016), (-0.01, 0, 0.026, 0, 0, 0), "0.2 0.55 0.35 1"))
    out.append(_visual("nose", _box(0.035, 0.03, 0.014), (0.105, 0, 0.012, 0, 0, 0), "0.9 0.15 0.15 1"))
    for k in range(4):
        rx, ry = float(d.RX[k]), float(d.RY[k])
        yaw = math.atan2(ry, rx)
        length = d.ARM
        out.append(_visual(f"arm_{k + 1}", _box(length, 0.022, 0.012), (rx / 2, ry / 2, 0.0, 0, 0, yaw), "0.12 0.12 0.14 1"))
        out.append(_visual(f"motor_{k + 1}", _cyl(0.0135, 0.032), (rx, ry, 0.016, 0, 0, 0), "0.7 0.7 0.72 1"))
    for k, (fx, fy) in enumerate(d.FEET, start=1):
        out.append(_visual(f"strut_{k}", _cyl(0.004, 0.066), (fx, fy, -0.05, 0, 0, 0), "0.12 0.12 0.14 1"))
        out.append(_visual(f"foot_{k}", f"<sphere><radius>0.008</radius></sphere>", (fx, fy, -0.077, 0, 0, 0), "0.1 0.1 0.1 1"))
        out.append(_visual(f"brace_{k}", _box(math.hypot(fx, fy) * 0.8, 0.006, 0.006),
                           (fx * 0.4, fy * 0.4, -0.02, 0, 0, math.atan2(fy, fx)), "0.12 0.12 0.14 1"))
    out.append("    </link>\n")
    for k in range(4):
        rx, ry = float(d.RX[k]), float(d.RY[k])
        out.append(f'\n    <link name="rotor_{k + 1}_link">\n      <pose>{rx:.5g} {ry:.5g} 0.047 0 0 0</pose>\n')
        out.append(_visual(f"blade_{k + 1}", _box(0.254, 0.018, 0.003), (0, 0, 0, 0, 0, 0), "0.08 0.08 0.1 1"))
        out.append(_visual(f"tip_{k + 1}", _box(0.05, 0.019, 0.0035), (0.102, 0, 0, 0, 0, 0), "1.0 0.5 0.05 1"))
        out.append(_visual(f"hub_{k + 1}", _cyl(0.012, 0.012), (0, 0, 0, 0, 0, 0), "0.8 0.8 0.82 1"))
        out.append("    </link>\n")
    for k in range(1, 5):
        out.append(
            f'\n    <joint name="rotor_{k}" type="continuous">\n      <parent>body</parent>\n'
            f'      <child>rotor_{k}_link</child>\n      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n'
        )
    # wind vane beside the pads: turns to the heading the wind blows towards, coloured by the wind speed
    out.append('\n    <link name="vane_link">\n      <pose>-1.2 -1.2 0.9 0 0 0</pose>\n')
    out.append(_visual("vane_mast", _cyl(0.012, 0.9), (0, 0, -0.45, 0, 0, 0), "0.5 0.5 0.55 1"))
    out.append(_visual("vane_arrow", _box(0.36, 0.03, 0.03), (0.08, 0, 0, 0, 0, 0), "0.9 0.9 0.9 1"))
    out.append(_visual("vane_tip", _box(0.07, 0.09, 0.03), (0.28, 0, 0, 0, 0, 0), "0.9 0.3 0.1 1"))
    out.append(_visual("vane_tail", _box(0.03, 0.14, 0.12), (-0.1, 0, 0, 0, 0, 0), "0.5 0.5 0.55 1"))
    out.append("    </link>\n")
    out.append(
        '\n    <joint name="wind_vane" type="continuous">\n      <parent>ground</parent>\n'
        '      <child>vane_link</child>\n      <axis><xyz>0 0 1</xyz></axis>\n    </joint>\n'
    )
    out.append("  </model>\n</sdf>\n")
    return "".join(out)


def main() -> int:
    model = build()
    out = ROOT / "models" / "quadcopter.bgmodel.json"
    out.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(nodes)} nodes, {len(conns)} connections)")
    # The determinism twin: the same document, stopped at 9 s on the same 10 ms output grid. Its discrete
    # parts (noise sequences, ticks) must reproduce the 18 s run exactly (expected.json compares them).
    repeat = json.loads(json.dumps(model))
    repeat["name"] = "quadcopter-repeat"
    repeat["$comment"] = "Determinism twin of quadcopter: identical diagram, t_end = 9 s on the same output grid; see expected.json."
    repeat["settings"]["t_end"] = 9.0
    repeat["settings"]["output"]["points"] = 901
    del repeat["dashboard"]
    # The wind reference: climb to 1 m and hover for 12 s in a steady 4 m/s wind along x, no turbulence. At
    # rest the tilt balances drag and weight (design.wind_tilt; expected.json checks it).
    hover = json.loads(json.dumps(model))
    hover["name"] = "quadcopter-wind-hover"
    hover["$comment"] = ("The quadcopter of the mission model hovering at 1 m in a steady 4 m/s wind (no turbulence): the "
                         "settled tilt is the static drag balance of design.wind_tilt. Generated by design/build_model.py.")
    mission = next(n for n in hover["diagram"]["nodes"] if n["name"] == "Mission")
    mission["params"].update({"ts": "[1.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0, 99.0]", "t_disarm": "99.0"})
    # the sensor noise makes the attitude jitter; a 2 s low-pass of the pitch gives its mean
    hover["diagram"]["nodes"].append({
        "id": "n99", "name": "PitchAvg", "block": {"ref": "stdlib:continuous/FirstOrder"}, "position": {"x": 1400, "y": 1000},
        "rotation": 0, "flipX": False, "params": {"k": "1.0", "tau": "2.0"}, "constants": {}, "starts": {"x": "0.0"},
        "ui": {"showLabel": True, "color": None}})
    truth_id = next(n["id"] for n in hover["diagram"]["nodes"] if n["name"] == "Truth")
    hover["diagram"]["connections"].append({"id": "s999", "kind": "signal", "from": {"node": truth_id, "port": "pitch"},
                                            "to": {"node": "n99", "port": "u"}, "route": [], "label": None})
    hover["plots"].append({"id": "p11", "title": "Pitch and its 2 s mean (rad)", "signals": ["Truth/pitch", "PitchAvg/y"]})
    values = {"wind_x": "4.0", "wind_y": "0.0", "wind_sigma": "0.0"}
    for g in hover["parameters"]:
        g["value"] = values.get(g["name"], g["value"])
    hover["settings"]["t_end"] = 12.0
    hover["settings"]["output"]["points"] = 1201
    del hover["dashboard"]
    (ROOT / "models" / "quadcopter-wind-hover.bgmodel.json").write_text(
        json.dumps(hover, indent=2) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "models" / "quadcopter-repeat.bgmodel.json").write_text(
        json.dumps(repeat, indent=2) + "\n", encoding="utf-8", newline="\n")
    sdf = ROOT / "scenes" / "quadcopter.sdf"
    sdf.write_text(build_scene(), encoding="utf-8", newline="\n")
    print(f"wrote {sdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
