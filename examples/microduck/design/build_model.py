# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the microduck example: the XL330 library subsystem, the models and the scene.

    uv run examples/microduck/design/build_model.py

* library/XL330.bgsub.json  the actuator, drawn once (design/xl330.py)
* models/xl330-step         one XL330 on the Pollen/BAM pendulum bench, goal pulse 0 -> 1 -> 0 rad
* models/xl330-torque-speed one XL330 with its horn driven by a speed ramp, goal far ahead:
                            the torque-speed curve with the current limit and the friction
* models/microduck-stand    the 14-joint robot (MJCF masses/inertias), 14 XL330 instances on a
                            2S battery bus, foot contacts, released at the STAND pose
* models/microduck-hang     the same robot held by the trunk, the legs stepping to a squat pose

Every number comes from xl330.py (actuator) and robot.py (body).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import robot as rb
import xl330 as xl
from diagram import Diagram, fmt, pose_params, vec

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
LIBRARY = ROOT / "library"

K_HELD = 1.0e5  # N/m and N m/rad, held directions of every Revolute3D


def settings(t_end, solver="Rodas5P", reltol=1e-6, abstol=1e-8, points=1001, max_step=None):
    return {"t_start": 0.0, "t_end": t_end, "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": max_step, "output": {"mode": "points", "points": points}, "event_limit": 100000}


def firmware_globals(v_supply: float) -> list[dict]:
    return [
        {"name": "kp_fw", "value": fmt(xl.KP_FW), "unit": "1",
         "description": "XL330 Position P Gain register (robotd gain 200; standing 0.8x, limp 50)"},
        {"name": "i_limit", "value": fmt(xl.I_LIMIT), "unit": "A",
         "description": "Firmware current limit (BAM/training 1.75 A; impact-guard firmware on the robot 1.0 A)"},
        {"name": "t_latency", "value": fmt(xl.LATENCY), "unit": "s",
         "description": "Command latency, goal written to goal applied (a multiple of 5 ms)"},
        {"name": "v_bat", "value": fmt(v_supply), "unit": "V",
         "description": "Supply voltage (2S Li-ion: 8.2 V full, 7.4 V nominal, 6.6 V empty under load)"},
        {"name": "k_motor", "value": fmt(xl.BAM["kt"]), "unit": "N*m/A",
         "description": "Torque constant at the horn, also the back-EMF constant (BAM XL330 M6 fit)"},
        {"name": "r_motor", "value": fmt(xl.BAM["R"]), "unit": "Ohm",
         "description": "Winding plus driver resistance (BAM XL330 M6 fit)"},
        {"name": "armature", "value": fmt(xl.BAM["armature"]), "unit": "kg*m^2",
         "description": "Rotor and gears reflected to the horn (BAM XL330 M6 fit); the rotor inertia of "
                        "XL330 is armature/288.4^2, the joint of XL330Rigid carries it as Ja"},
    ]


def actuator(d: Diagram, name, x, y, q0=0.0, gap=xl.BACKLASH, bl0=0.0, scale=1.0, inertia=None, kp=None):
    """An XL330 instance: pins the per-actuator values (all at the library value unless given)."""
    params = {"Latency/initial": q0, "Friction/scale": scale}
    if gap != xl.BACKLASH:
        params["Backlash/gap"] = gap
    if inertia is not None:
        params["RotorInertia/i"] = inertia
    if kp is not None:
        params["PGain/k"] = kp
    d.ref(name, "project:XL330", x, y, params=params, starts={"Encoder/phi": q0, "Backlash/phi": bl0})


# ------------------------------------------------------------------ the bench (one XL330)

BENCH = {  # microduck_rl robot/xl330_test_bench/xl330_test_bench.xml: 100 g payload arm
    "m": 0.1, "l": 0.0965688, "J": [8.6729e-05, 6.5566e-05, 1.43854e-04],
}
BENCH_INERTIA = BENCH["J"][2] + BENCH["m"] * BENCH["l"] ** 2
PULSE = {"amplitude": 1.0, "period": 4.0, "duty": 0.2, "t_start": 0.1, "offset": 0.0}  # high 0.1..0.9 s
G0 = 9.81


def bench_goal(t: float) -> float:
    p = PULSE
    return p["amplitude"] if p["t_start"] <= t < p["t_start"] + p["duty"] * p["period"] else 0.0


def bench_invweight(inertia=BENCH_INERTIA) -> float:
    """dof_invweight0 of the play hinge on the bench as MuJoCo computes it: the play hinge and the
    servo hinge on one body (link inertia I about the axis), armatures Ja (servo) and jb (play):
    (M^-1)_bb = (I + Ja) / (I (Ja + jb) + Ja jb)."""
    ja, jb = xl.BAM["armature"], xl.PLAY["jb"]
    return (inertia + ja) / (inertia * (ja + jb) + ja * jb)


def add_pendulum(d: Diagram, x0, y0, rigid=False, ja="armature", vertical=False) -> tuple[str, str]:
    """World -> Mount -> J (Revolute3D, horizontal axis) -> Arm -> BJ -> B; q = 0 hangs down.
    rigid: J is a Revolute3DRigid that carries the servo's armature `ja` (for XL330Rigid; "0.0"
    for XL330Backlash, whose armature is on the motor side). vertical: the axis is vertical, so
    gravity puts no torque on the joint (the reversal bench)."""
    r_wj = np.eye(3) if vertical else np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
    t_wj = np.eye(4)
    t_wj[:3, :3] = r_wj
    t_wj[2, 3] = 0.3
    t_com = np.eye(4)
    t_com[1, 3] = -BENCH["l"]
    d.ref("World", "stdlib:multibond/GroundSpatial", x0, y0)
    d.ref("Mount", "stdlib:multibond/FixedTransform3DNeutral", x0 + 120, y0, params=pose_params(np.linalg.inv(t_wj)))
    if rigid:
        d.ref("J", "stdlib:spatial/Revolute3DRigid", x0 + 240, y0, params={"Ja": ja})
    else:
        d.ref("J", "stdlib:spatial/Revolute3D", x0 + 240, y0,
              params={"kt": K_HELD, "kr": K_HELD, "bt": 2 * math.sqrt(K_HELD * 0.1), "br": 2 * math.sqrt(K_HELD * 1e-4)})
    d.ref("Arm", "stdlib:multibond/FixedTransform3DNeutral", x0 + 360, y0, params=pose_params(t_com))
    d.junction("BJ", "1", x0 + 480, y0)
    d.ref("B", "stdlib:spatial/RigidBody3D", x0 + 480, y0 + 110,
          params={"m": BENCH["m"], "J": vec(BENCH["J"]), "g0": G0})
    d.bond("World", "p", "Mount", "b")
    d.bond("Mount", "a", "J", "parent")
    d.bond("J", "child", "Arm", "a")
    d.bond("Arm", "b", "BJ")
    d.bond("B", "p", "BJ")
    d.ref("Base", "stdlib:spatial/LocalPose3D", x0 + 240, y0 + 240, params=pose_params(t_wj))
    d.ref("WJ", "stdlib:multibond/ComposePose3D", x0 + 360, y0 + 240)
    d.ref("LC", "stdlib:spatial/LocalPose3D", x0 + 360, y0 + 340, params=pose_params(t_com))
    d.ref("PB", "stdlib:multibond/ComposePose3D", x0 + 480, y0 + 240)
    d.sig("Base", "g", "WJ", "gp")
    d.sig("J", "pose", "WJ", "gl")
    d.sig("WJ", "g", "PB", "gp")
    d.sig("LC", "g", "PB", "gl")
    d.sig("PB", "g", "B", "g")
    return "J", "drive"


def rigid_actuator(d: Diagram, name, x, y, q0=0.0, scale=1.0, ws=None, invw=None, gap=None):
    """An XL330Rigid instance (the robot's servo): pins the latency's start to the joint's start.
    invw given: an XL330Backlash instead, with the play hinge's MuJoCo dof_invweight0 pinned (and
    the play `gap`, a global's name or a number, when given)."""
    params = {"Latency/initial": q0}
    if scale != 1.0:
        params["Friction/scale"] = scale
    if ws is not None:
        params["Friction/ws"] = ws
    if invw is None:
        d.ref(name, "project:XL330Rigid", x, y, params=params)
        return
    params["Backlash/invw"] = invw
    if gap is not None:
        params["Backlash/gap"] = gap
    d.ref(name, "project:XL330Backlash", x, y, params=params)


def build_step(rigid=False) -> dict:
    d = Diagram()
    d.ref("Goal", "stdlib:sources/Pulse", 0, 0, params=PULSE)
    d.ref("Supply", "stdlib:bondgraph/Se", 0, 160, params={"e": "v_bat"})
    if rigid:
        rigid_actuator(d, "Servo", 200, 60)
        d.ref("Kp", "stdlib:sources/Constant", 0, 80, params={"value": "kp_fw"})
        d.sig("Kp", "y", "Servo", "kp")
    else:
        actuator(d, "Servo", 200, 60, gap=0.0)
    d.sig("Goal", "y", "Servo", "q_goal")
    d.bond("Supply", "p", "Servo", "vbus")
    drive = add_pendulum(d, 420, 60, rigid=rigid)
    d.bond("Servo", "horn", *drive)
    if rigid:
        d.sig("J", "qout", "Servo", "q")
    name = "xl330-rigid-step" if rigid else "xl330-step"
    what = ("XL330Rigid (the robot's servo: rigid gear, the armature in the joint, the friction's load "
            "torque sampled every 5 ms)" if rigid else "XL330")
    d.note(f"**{what} on the pendulum bench** of microduck_rl (100 g arm, centre of mass 96.6 mm from the "
           "axis), goal 0 -> 1 rad at 0.1 s and back at 0.9 s, kp 200, 7.4 V. Compare with the BAM "
           "identification simulator (design/xl330.py).", 0, -160, 700, 100)
    angle = "J/qout" if rigid else "Servo/Encoder/y"
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "$comment": f"One {'XL330Rigid' if rigid else 'XL330'} instance on the microduck_rl XL330 test bench (pendulum).",
        "diagram": d.document(),
        "settings": settings(1.6, reltol=1e-7, abstol=1e-9, points=1601),
        "parameters": firmware_globals(xl.V_NOMINAL),
        "plots": [
            {"id": "p1", "title": "Goal and encoder angle", "signals": ["Goal/y", angle]},
            {"id": "p2", "title": "Motor current and duty", "signals": ["Servo/Current/y", "Servo/PwmLimit/y"]},
            {"id": "p3", "title": "Torques", "signals": ["Servo/MotorTorque/y", "Servo/Transmit/y", "Servo/Friction/tau_f"]},
        ],
    }


REVERSAL = {"amplitude": 0.3, "period": 4.0, "duty": 0.125, "t_start": 0.1, "offset": 0.0}  # high 0.1..0.6 s
REVERSAL_T_END = 1.0


def build_backlash_bench(reversal=False) -> dict:
    """XL330Backlash on the test bench. reversal=False: the pendulum and goal pulse of xl330-step
    (gravity keeps the play closed on one flank, so the run should follow xl330-rigid-step);
    reversal=True: the same arm turning in a horizontal plane (no gravity torque on the joint),
    goal 0 -> 0.3 rad at 0.1 s and back at 0.6 s, so each reversal crosses the play."""
    d = Diagram()
    d.ref("Goal", "stdlib:sources/Pulse", 0, 0, params=REVERSAL if reversal else PULSE)
    d.ref("Supply", "stdlib:bondgraph/Se", 0, 160, params={"e": "v_bat"})
    invw = bench_invweight()
    rigid_actuator(d, "Servo", 200, 60, invw=invw)
    d.ref("Kp", "stdlib:sources/Constant", 0, 80, params={"value": "kp_fw"})
    d.sig("Kp", "y", "Servo", "kp")
    d.sig("Goal", "y", "Servo", "q_goal")
    d.bond("Supply", "p", "Servo", "vbus")
    drive = add_pendulum(d, 420, 60, rigid=True, ja="0.0", vertical=reversal)
    d.bond("Servo", "horn", *drive)
    d.sig("J", "qout", "Servo", "q")
    name = "xl330-backlash-reversal" if reversal else "xl330-backlash-step"
    if reversal:
        d.note("**XL330Backlash, reversal through the play.** The bench arm turns in a horizontal plane (no "
               "gravity torque), goal 0 -> 0.3 rad at 0.1 s and back at 0.6 s, kp 200, 7.4 V. On each reversal "
               "the gear crosses the 2 deg play before the horn (and the encoder) moves. Compare with MuJoCo "
               "running the same bench with microduck_rl's play hinge (design/backlash_bench.py).", 0, -160, 700, 120)
    else:
        d.note("**XL330Backlash on the pendulum bench** of xl330-step: gravity keeps the play closed, so the "
               "encoder follows xl330-rigid-step except where the load reverses. Compare with MuJoCo running the "
               "same bench with microduck_rl's play hinge (design/backlash_bench.py).", 0, -160, 700, 100)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name,
        "$comment": "One XL330Backlash instance (microduck_rl's 2 deg play hinge) on the microduck_rl XL330 test bench.",
        "diagram": d.document(),
        "settings": settings(REVERSAL_T_END if reversal else 1.6, reltol=1e-7, abstol=1e-9,
                             points=2001 if reversal else 1601),
        "parameters": firmware_globals(xl.V_NOMINAL),
        "plots": [
            {"id": "p1", "title": "Goal and encoder angle", "signals": ["Goal/y", "J/qout"]},
            {"id": "p2", "title": "Play angle (gear minus horn)", "signals": ["Servo/Backlash/phi"]},
            {"id": "p3", "title": "Gear and horn speed", "signals": ["Servo/GearSpeed/y", "Servo/HornSpeed/y"]},
            {"id": "p4", "title": "Motor current and duty", "signals": ["Servo/Current/y", "Servo/PwmLimit/y"]},
        ],
    }


SPEED_RAMP = {"t_start": 0.5, "slope": 4.0, "initial": -8.0, "duration": 7.0}  # -8 .. 20 rad/s


def build_torque_speed(rigid=False) -> dict:
    d = Diagram()
    d.ref("Goal", "stdlib:sources/Constant", 0, 0, params={"value": 1000.0})
    d.ref("Supply", "stdlib:bondgraph/Se", 0, 160, params={"e": "v_bat"})
    if rigid:
        rigid_actuator(d, "Servo", 200, 60)
        d.ref("Kp", "stdlib:sources/Constant", 0, 80, params={"value": "kp_fw"})
        d.ref("Angle", "stdlib:sources/Constant", 0, 120, params={"value": 0.0})
        d.sig("Kp", "y", "Servo", "kp")
        d.sig("Angle", "y", "Servo", "q")
    else:
        actuator(d, "Servo", 200, 60, gap=0.0)
    d.ref("SpeedRamp", "stdlib:sources/Ramp", 420, -60, params=SPEED_RAMP)
    d.ref("Dyno", "stdlib:bondgraph/MSf", 420, 60)
    d.sig("Goal", "y", "Servo", "q_goal")
    d.bond("Supply", "p", "Servo", "vbus")
    d.sig("SpeedRamp", "y", "Dyno", "u")
    d.bond("Dyno", "p", "Servo", "horn")
    d.note("**Torque-speed curve.** A dynamometer (MSf) turns the horn from -8 to 20 rad/s while the goal "
           "is far ahead, so the firmware asks for full PWM. Servo/tau_l is the torque at the horn: the "
           "current-limited stall line (i_limit) then the back-EMF line to the free speed v_bat/kt, minus "
           "the friction and the armature torque.", 0, -200, 700, 120)
    if rigid:
        d.note("XL330Rigid has no armature of its own (the joint carries it), so Servo/Transmit/y here is "
               "kt i minus the friction, without the armature torque of the ramp. The encoder input is held "
               "at 0: the goal is 1000 rad ahead either way.", 0, -320, 700, 100)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "xl330-rigid-torque-speed" if rigid else "xl330-torque-speed",
        "$comment": f"One {'XL330Rigid' if rigid else 'XL330'} instance on a speed dynamometer (no backlash).",
        "diagram": d.document(),
        "settings": settings(8.0, reltol=1e-7, abstol=1e-9, points=1601),
        "parameters": firmware_globals(xl.V_NOMINAL),
        "plots": [
            {"id": "p1", "title": "Horn speed", "signals": ["SpeedRamp/y", "Servo/HornSpeed/y"]},
            {"id": "p2", "title": "Torques", "signals": ["Servo/MotorTorque/y", "Servo/Transmit/y", "Servo/Friction/tau_f"]},
            {"id": "p3", "title": "Current and duty", "signals": ["Servo/Current/y", "Servo/PwmLimit/y"]},
        ],
    }


# ------------------------------------------------------------------ dashboards

def _card(kind, title, size="1x1", parameter=None, signals=None, **options):
    c = {"kind": kind, "size": size, "title": title}
    if parameter is not None:
        c["parameter"] = parameter
    if signals is not None:
        c["signals"] = signals
    c["options"] = options
    return c


def text(title, body):
    return _card("text", title, "2x1", markdown=True, text=body)


def slider(title, name, lo, hi, step, decimals, unit=None):
    opts = {"min": lo, "max": hi, "step": step, "decimals": decimals}
    if unit:
        opts["unit"] = unit
    return _card("slider", title, parameter=f"global:{name}", **opts)


def value(title, signal, decimals, unit=None):
    opts = {"decimals": decimals, "sparkline": True}
    if unit:
        opts["unit"] = unit
    return _card("value", title, signals=[signal], **opts)


def plot(title, signals):
    c = _card("plot", title, "2x2", signals=signals)
    del c["options"]
    return c


KP = ("Position P gain (kp_fw)", "kp_fw", 50.0, 800.0, 10.0, 0)
VBAT = ("Supply voltage", "v_bat", 6.0, 8.4, 0.1, 1, "V")
ILIM = ("Current limit", "i_limit", 0.5, 1.75, 0.05, 2, "A")

DASHBOARDS = {
    "xl330-step": (True, [
        text("XL330 on the bench", "One servo swings the 100 g test arm of microduck_rl to 1 rad and back. "
             "Change the P gain or the supply and compare the encoder with the goal. At kp 200 the "
             "current peaks just under the 1.75 A limit; raise kp_fw and it saturates."),
        slider(*KP), slider(*VBAT),
        value("Encoder angle", "Servo/Encoder/y", 3, "rad"), value("Motor current", "Servo/Current/y", 2, "A"),
        plot("Goal and encoder (rad)", ["Goal/y", "Servo/Encoder/y"]),
        plot("Current (A) and duty", ["Servo/Current/y", "Servo/PwmLimit/y"]),
    ]),
    "xl330-torque-speed": (True, [
        text("Torque-speed curve", "A dynamometer turns the horn from -8 to 20 rad/s with the goal far ahead. "
             "The flat part is the current limit, the slope the back-EMF; lower the limit to the 1.0 A "
             "of the robot's impact-guard firmware, or the supply to an empty pack."),
        slider(*ILIM), slider(*VBAT),
        value("Horn torque", "Servo/Transmit/y", 3, "N m"), value("Horn speed", "Servo/HornSpeed/y", 1, "rad/s"),
        plot("Torques (N m)", ["Servo/MotorTorque/y", "Servo/Transmit/y", "Servo/Friction/tau_f"]),
        plot("Current (A) and duty", ["Servo/Current/y", "Servo/PwmLimit/y"]),
    ]),
    "microduck-stand": (False, [
        text("microduck holding HOME", "No policy: the 14 servos hold the HOME pose and the robot tips "
             "forward within about a second, as the microduck notes say it does in their simulation. "
             "Raise the P gain and see how long it stays up. A run takes a few minutes."),
        slider(*KP), slider(*VBAT),
        value("Trunk quaternion w", "Free/pose[1]", 3), value("Battery current", "BatCurrent/y", 2, "A"),
        plot("Trunk attitude and height", ["Free/pose[1]", "Free/pose[3]", "Free/pose[7]"]),
        plot("Foot normal forces (N)", [f"Foot{s}{k}/f_n" for s in "LR" for k in range(1, 5)]),
    ]),
    "microduck-policy": (False, [
        text("microduck for a policy", "The robot that velstand.onnx drives in the browser demo, run here by itself: "
             "the servos hold HOME and the legs step to a squat at 0.3 s. Without a policy HOME tips forward. "
             "The FMU of this model takes the joint targets and the gain from the host instead. A run takes a few "
             "minutes."),
        slider(*KP), slider(*VBAT),
        value("Trunk height", "trunk_z/u", 4, "m"), value("Projected gravity x", "gravity_x/u", 3),
        plot("Trunk height and projected gravity", ["trunk_z/u", "gravity_x/u", "gravity_z/u"]),
        plot("Sole loads (N)", ["left_foot_contact/u", "right_foot_contact/u"]),
    ]),
    "microduck-hang": (False, [
        text("microduck on a stand", "The trunk is held; at 0.2 s the legs step to a squat pose. Watch the "
             "latency, the current limit, the backlash and the gravity sag. A run takes a few minutes."),
        slider(*KP), slider(*ILIM),
        value("Left knee encoder", "left_knee/Encoder/y", 3, "rad"), value("Battery current", "BatCurrent/y", 2, "A"),
        plot("Left leg goals and encoders (rad)", [s for j in rb.LEGS[:3] for s in (f"Goal_{j}/y", f"{j}/Encoder/y")]),
        plot("Left leg currents (A)", [f"{j}/Current/y" for j in rb.LEGS[:3]]),
    ]),
}


def with_dashboard(doc: dict) -> dict:
    if doc["name"] not in DASHBOARDS:
        return doc
    auto, cards = DASHBOARDS[doc["name"]]
    doc["dashboard"] = {"autoRerun": auto, "cards": [{"id": f"d{k}", **c} for k, c in enumerate(cards, start=1)]}
    return doc


# ------------------------------------------------------------------ main

def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT.parent.parent)}")


def main() -> None:
    import checks

    write_json(LIBRARY / "XL330.bgsub.json", xl.definition())
    write_json(LIBRARY / "XL330Rigid.bgsub.json", xl.definition_rigid())
    write_json(LIBRARY / "XL330Backlash.bgsub.json", xl.definition_backlash())
    write_json(MODELS / "xl330-backlash-step.bgmodel.json", with_dashboard(build_backlash_bench()))
    write_json(MODELS / "xl330-backlash-reversal.bgmodel.json", with_dashboard(build_backlash_bench(reversal=True)))
    write_json(MODELS / "xl330-step.bgmodel.json", with_dashboard(build_step()))
    write_json(MODELS / "xl330-torque-speed.bgmodel.json", with_dashboard(build_torque_speed()))
    write_json(MODELS / "xl330-rigid-step.bgmodel.json", with_dashboard(build_step(rigid=True)))
    write_json(MODELS / "xl330-rigid-torque-speed.bgmodel.json", with_dashboard(build_torque_speed(rigid=True)))
    import scene  # the 3D scenes and link bindings (meshes: design/build_visuals.py)

    scene.write_scenes()
    for build in rb.MODEL_BUILDERS:
        doc = scene.with_scene(with_dashboard(build()))
        write_json(MODELS / f"{doc['name']}.bgmodel.json", doc)
    write_json(ROOT / "expected.json", checks.expected())


if __name__ == "__main__":
    main()
