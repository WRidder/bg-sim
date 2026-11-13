# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""The Dynamixel XL330-M288-T actuator of the microduck: every number with its source, the
library subsystem `XL330` (library/XL330.bgsub.json) and an independent reference simulator.

Sources (all read as data; no downloaded code was run):

* [BAM-A] Rhoban BAM, bam/params/xl330/m6.json at commit 62bd8ce12154340be97e06f7f41a0ca8f116d967
  (branch mjlab_frictionloss). This is the commit microduck_rl's uv.lock pins, so it is the
  actuator the microduck policies are trained against.
* [BAM-B] Rhoban BAM, bam/params/xl330/m6.json on main (b41c117f1e, refit of 2026-08-01). A
  newer fit of the same servo with an identified command delay; listed for comparison only.
* [BAM-CODE] Rhoban BAM, bam/dynamixel/actuator.py (XL330Actuator: error gain, kp divisor 256,
  PWM limit 885, max_current 1.75 A), bam/actuator.py (VoltageControlledActuator: the firmware
  law and the current-limit duty window), bam/model.py (the M6 friction budget),
  bam/simulate.py (the identification simulator ported below), same commit as [BAM-A].
* [ROBOTIS] https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/ (gear ratio 288.4, 4096
  counts/rev, Position P gain KPP = P/128, PWM limit 885 = 100 %, current limit 1750 mA, only
  enforced in the current-based modes).
* [DUCK] github.com/pollen-robotics/microduck at 039a1a845ddb365a458428dae234366cf1b7673a:
  duck-control/src/model.rs (current_limit 1000 mA on the impact-guard firmware, 1 Mbps,
  return delay 0), duck-control/src/bus.rs (P gain written per joint, I = D = 0),
  deploy/robotd.toml (gain 200, 50 Hz loop, 2S Li-ion 6.6..8.2 V).
* [RL] github.com/pollen-robotics/microduck_rl at 0daab160d3fb1c2cbaba16a4a19052f36709dd9e:
  robot/microduck_constants.py (kp_fw 200, vin 6.5..8.2 V, delay 3..6 sim steps),
  tasks/microduck_velocity_env_cfg.py (friction scale 0.9..1.1, armature 0.9..1.1),
  robot/microduck/add_backlash.py (2 deg total backlash).

Run `uv run examples/microduck/design/xl330.py` for the derived numbers.
"""

from __future__ import annotations

import math

import numpy as np

# ------------------------------------------------------------------ parameters

# [BAM-A] xl330/m6.json (output-side, lumped: kt includes the gear ratio, R includes the driver)
BAM = {
    "kt": 0.36601349688984386,  # N m / A at the output (= V s/rad of back-EMF at the output)
    "R": 2.8113923539223227,  # Ohm
    "armature": 0.0018077432831600838,  # kg m^2, reflected rotor + gear inertia at the output
    "friction_base": 0.004771183165566,
    "friction_stribeck": 0.004676345799486616,
    "load_friction_motor": 0.2667860954283698,
    "load_friction_external": 8.515871897059342e-06,
    "load_friction_motor_stribeck": 1.0722918395099123e-05,
    "load_friction_external_stribeck": 0.08077928978935671,
    "load_friction_motor_quad": 0.009972471242139415,
    "load_friction_external_quad": 0.004902565732332559,
    "dtheta_stribeck": 2.890372094130307,
    "alpha": 8.683259907618984,
    "friction_viscous": 0.005359668274599504,
}
# [BAM-B] for the comparison table only
BAM_MAIN = {"kt": 0.3459739511711113, "R": 2.501880848390462, "armature": 0.001573222677933975,
            "command_delay": 0.010220594809412403, "friction_base": 0.011919956825702578,
            "friction_viscous": 0.005788445053875673}

GEAR = 288.4  # [ROBOTIS]
COUNTS = 4096  # [ROBOTIS] counts per revolution
KP_DIVISOR = 256  # [BAM-CODE] "empirically observed for XL330 (manual mentions 128)"
PWM_LIMIT = 885  # [BAM-CODE], [ROBOTIS]: 885 = 100 % duty
ERROR_GAIN = (COUNTS / (2 * math.pi)) / (KP_DIVISOR * PWM_LIMIT)  # duty per (rad * kp register)
KP_FW = 200.0  # [DUCK] robotd gain, [RL] kp_fw
I_LIMIT = 1.75  # A, [BAM-CODE] max_current, what training uses (see README: the robot uses 1.0)
MAX_PWM = 1.0
V_NOMINAL = 7.4  # V, 2S Li-ion nominal; [RL] trains on 6.5..8.2 V
LATENCY = 0.02  # s, assumption inside [RL]'s 15..30 ms (3..6 steps of 5 ms)
LATENCY_TICK = 0.005  # s, sample period of the delay line (the 5 ms physics step of BAM and microduck_rl)
BACKLASH = math.radians(2.0)  # rad total, [RL] add_backlash.py (assumption of the RL work)
K_GEAR = 100.0  # N m / rad, ASSUMED tooth contact stiffness (not identified)
D_GEAR = 0.1  # N m s / rad, ASSUMED contact damping
W_S = 0.002  # rad/s, friction regularisation (modelling choice)

J_ROTOR = BAM["armature"] / GEAR**2  # motor-side inertia that reflects to the BAM armature
K_MOTOR = BAM["kt"] / GEAR  # motor-side torque constant


def friction_params(scale: str | float = 1.0) -> dict:
    b = BAM
    return {
        "fb": b["friction_base"], "fs": b["friction_stribeck"],
        "lfm": b["load_friction_motor"], "lfe": b["load_friction_external"],
        "lfms": b["load_friction_motor_stribeck"], "lfes": b["load_friction_external_stribeck"],
        "lfmq": b["load_friction_motor_quad"], "lfeq": b["load_friction_external_quad"],
        "dtheta_s": b["dtheta_stribeck"], "alpha": b["alpha"], "fv": b["friction_viscous"],
        "scale": scale, "ws": W_S,
    }


# ------------------------------------------------------------------ the library subsystem

PINS_PARAMS = ["PGain/k", "Friction/scale", "RotorInertia/i", "Backlash/gap", "Latency/initial"]
PINS_STARTS = ["Encoder/phi", "Backlash/phi"]

EG_EXPR = "4096/(2*pi)/(256*885)"  # ERROR_GAIN as an expression the user can read


def definition() -> dict:
    """library/XL330.bgsub.json.

    Globals the definition reads (every model of the project defines them, `motor_globals`):
    `kp_fw` (Position P gain register), `i_limit` (A, firmware current limit), `t_latency` (s,
    command latency) and the BAM fit `k_motor` (N m/A at the output), `r_motor` (Ohm) and
    `armature` (kg m^2 at the output; the rotor inertia inside is armature/288.4^2).
    """
    from diagram import Diagram

    d = Diagram()
    # ---- firmware: goal -> latency -> P law -> current-limit window -> PWM limit -> duty
    y0 = 0
    d.ref("Latency", "stdlib:continuous/TransportDelay", 80, y0, params={"initial": 0.0},
          constants={"delay_time": "t_latency", "sample_period": LATENCY_TICK})
    d.ref("GoalMux", "stdlib:continuous/Mux2", 220, y0 + 20)
    d.ref("Error", "stdlib:continuous/Sum", 340, y0 + 20, params={"signs": "[1.0, -1.0]"})
    d.ref("PGain", "stdlib:continuous/Gain", 460, y0 + 20, params={"k": f"kp_fw*{EG_EXPR}"})
    d.ref("Floor", "stdlib:continuous/Max", 600, y0 + 40)
    d.ref("Ceil", "stdlib:continuous/Min", 720, y0 + 40)
    d.ref("PwmLimit", "stdlib:continuous/Saturation", 840, y0 + 40,
          params={"lower": -MAX_PWM, "upper": MAX_PWM})
    # current-limit window: duty in [(kt w - R I)/V, (kt w + R I)/V]
    y1 = y0 + 200
    d.ref("Emf", "stdlib:continuous/Gain", 340, y1, params={"k": "k_motor"})
    d.ref("EmfDuty", "stdlib:continuous/Divide", 460, y1)
    d.ref("RIlim", "stdlib:sources/Constant", 340, y1 + 100, params={"value": "r_motor*i_limit"})
    d.ref("Span", "stdlib:continuous/Divide", 460, y1 + 100)
    d.ref("HiMux", "stdlib:continuous/Mux2", 560, y1 - 20)
    d.ref("Hi", "stdlib:continuous/Sum", 660, y1 - 20, params={"signs": "[1.0, 1.0]"})
    d.ref("LoMux", "stdlib:continuous/Mux2", 560, y1 + 80)
    d.ref("Lo", "stdlib:continuous/Sum", 660, y1 + 80, params={"signs": "[1.0, -1.0]"})
    d.sig("Latency", "y", "GoalMux", "u1")
    d.sig("GoalMux", "y", "Error", "u")
    d.sig("Error", "y", "PGain", "u")
    d.sig("PGain", "y", "Floor", "u1")
    d.sig("Lo", "y", "Floor", "u2")
    d.sig("Floor", "y", "Ceil", "u1")
    d.sig("Hi", "y", "Ceil", "u2")
    d.sig("Ceil", "y", "PwmLimit", "u")
    d.sig("Emf", "y", "EmfDuty", "u1")
    d.sig("RIlim", "y", "Span", "u1")
    d.sig("EmfDuty", "y", "HiMux", "u1")
    d.sig("Span", "y", "HiMux", "u2")
    d.sig("HiMux", "y", "Hi", "u")
    d.sig("EmfDuty", "y", "LoMux", "u1")
    d.sig("Span", "y", "LoMux", "u2")
    d.sig("LoMux", "y", "Lo", "u")
    # ---- power: supply -> H-bridge (MTF, duty) -> winding (R) -> GY (kt/N) -> rotor (I) ->
    #      gear (TF 1/N) -> output (friction) -> transmitted-torque sensor -> backlash -> horn
    y2 = y0 + 480
    d.junction("Supply", "0", 80, y2)
    d.ref("VbusSense", "stdlib:bondgraph/De", 80, y2 + 110)
    d.ref("HBridge", "stdlib:bondgraph/MTF", 200, y2)
    d.junction("Winding", "1", 320, y2)
    d.ref("Rw", "stdlib:bondgraph/R", 280, y2 + 110, params={"r": "r_motor"})
    d.ref("Current", "stdlib:bondgraph/Df", 360, y2 + 110)
    d.ref("Motor", "stdlib:converters/EMConverter", 440, y2, params={"k": f"k_motor/{GEAR!r}"})
    d.ref("Gnd", "stdlib:electrical/Ground", 440, y2 + 110)
    d.junction("Rotor", "1", 560, y2)
    d.ref("RotorInertia", "stdlib:bondgraph/I", 520, y2 + 110,
          params={"i": f"armature/{GEAR!r}^2"})
    d.ref("RotorSpeed", "stdlib:converters/SpeedSensor", 600, y2 + 110)
    d.ref("Gear", "stdlib:bondgraph/TF", 680, y2, params={"n": f"1/{GEAR!r}"})
    d.junction("Output", "1", 800, y2)
    d.ref("Friction", "project:BamFriction", 760, y2 + 130, params=friction_params())
    d.ref("Speed", "stdlib:converters/SpeedSensor", 840, y2 + 130)
    d.ref("Transmit", "stdlib:converters/TorqueSensor", 920, y2)
    d.junction("Link", "1", 1040, y2)
    d.ref("Backlash", "project:SmoothBacklash", 1140, y2,
          params={"k": K_GEAR, "d": D_GEAR, "gap": BACKLASH})
    d.junction("Horn", "1", 1260, y2)
    d.ref("Encoder", "stdlib:converters/AngleSensor", 1220, y2 + 110)
    d.ref("HornSpeed", "stdlib:converters/SpeedSensor", 1300, y2 + 110)
    d.ref("MotorTorque", "stdlib:continuous/Gain", 440, y2 + 200, params={"k": "k_motor"})
    d.bond("Supply", None, "VbusSense", "p")
    d.bond("Supply", None, "HBridge", "p2")
    d.bond("HBridge", "p1", "Winding")
    d.bond("Winding", None, "Rw", "p")
    d.bond("Winding", None, "Current", "p")
    d.bond("Winding", None, "Motor", "n")
    d.wire("Motor", "p", "Gnd", "p")
    d.bond("Rotor", None, "Motor", "shaft")
    d.bond("Rotor", None, "RotorInertia", "p")
    d.bond("Rotor", None, "RotorSpeed", "a")
    d.bond("Rotor", None, "Gear", "p1")
    d.bond("Gear", "p2", "Output")
    d.bond("Output", None, "Friction", "p")
    d.bond("Output", None, "Speed", "a")
    d.bond("Output", None, "Transmit", "a")
    d.bond("Link", None, "Transmit", "b")
    d.bond("Link", None, "Backlash", "a")
    d.bond("Horn", None, "Backlash", "b")
    d.bond("Horn", None, "Encoder", "a")
    d.bond("Horn", None, "HornSpeed", "a")
    # ---- signals between the two halves
    d.sig("PwmLimit", "y", "HBridge", "u")
    d.sig("Encoder", "y", "GoalMux", "u2")
    d.sig("Speed", "y", "Emf", "u")
    d.sig("VbusSense", "y", "EmfDuty", "u2")
    d.sig("VbusSense", "y", "Span", "u2")
    d.sig("Current", "y", "MotorTorque", "u")
    d.sig("MotorTorque", "y", "Friction", "tau_m")
    d.sig("Transmit", "y", "Friction", "tau_l")
    # ---- ports
    d.signal_port("q_goal", "input", "Latency", "u", "rad")
    d.power_port("vbus", "Electrical", "Supply")
    d.power_port("horn", "Rotation", "Horn")
    d.signal_port("q", "output", "Encoder", "y", "rad")
    d.signal_port("dq", "output", "HornSpeed", "y", "rad/s")
    d.signal_port("i", "output", "Current", "y", "A")
    d.signal_port("tau_m", "output", "MotorTorque", "y", "N*m")
    d.signal_port("tau_l", "output", "Transmit", "y", "N*m")
    d.signal_port("duty", "output", "PwmLimit", "y", "1")
    d.note("**Firmware (Position Control Mode).** duty = PGain (goal - encoder), PGain = kp_fw "
           "4096/(2 pi)/(256 885) [BAM]; clamped to the current-limit window "
           "(kt w +- R i_limit)/V_bus (BAM's limiter) and to +-100 % PWM. The goal arrives t_latency late.",
           0, -170, 900, 110)
    d.note("**Motor and gear (BAM XL330 M6 fit, output side).** H-bridge MTF (duty) -> winding R -> "
           "GY kt/N -> rotor I (armature/N^2) -> gear TF 1/N (N = 288.4) -> BAM M6 friction (load "
           "dependent, Stribeck) -> 2 deg backlash (smooth, no solver events) -> horn. The encoder reads the horn (after the play).",
           0, y2 + 300, 1100, 110)
    return {
        "format": "bgsim.subsystem",
        "name": "XL330",
        "description": (
            "Dynamixel XL330-M288-T in Position Control Mode: firmware P law to PWM with BAM's current "
            "limiter, DC motor (BAM M6 fit of Rhoban, the actuator microduck_rl trains against), "
            "gear 288.4:1, load-dependent Stribeck friction, gear backlash and command latency. "
            "Reads the globals kp_fw, i_limit, t_latency, k_motor, r_motor and armature."),
        "ports": d.ports,
        "diagram": d.document(),
        "pins": {"params": PINS_PARAMS, "starts": PINS_STARTS},
    }


PINS_PARAMS_RIGID = ["Friction/scale", "Friction/ws", "Latency/initial"]


def definition_rigid() -> dict:
    """library/XL330Rigid.bgsub.json: the XL330 for the robot that a policy drives (and an FMU runs).

    The same firmware, current limiter, winding and BAM M6 friction as `XL330`, with three
    differences, each one what the training simulation (BAM in mjlab) does too:

    * **rigid gear, no backlash.** The armature (rotor and gears reflected to the output) is not
      in the subsystem: the joint carries it (`Revolute3DRigid.Ja`), as MuJoCo's `armature`
      does. The motor torque kt i acts at the output; no rotor speed, no gear spring, no
      backlash state. (velstand was trained with 2 deg of backlash; see the README.)
    * **the encoder is the joint angle** (input `q`), so the joint's `q0` is the only start
      value of the angle; no integrating sensor duplicates it.
    * **the load torque the friction reads is sampled every 5 ms** (`LoadSample`, a ZOH of the
      torque delivered to the joint, kt i - tau_f), as BAM in mjlab reads the external torque of
      the previous physics step. This is what removes the algebraic loop of `XL330` (the friction
      read the torque it changes).

    The position gain is an input (`kp`, the Position P Gain register), because the robot sets
    it every control tick (200 walking, 160 standing). Reads the globals `i_limit` and
    `t_latency`.
    """
    d = _rigid_diagram(backlash=False)
    return {
        "format": "bgsim.subsystem",
        "name": "XL330Rigid",
        "description": (
            "Dynamixel XL330-M288-T for a robot model that runs in real time: the firmware P law with "
            "BAM's current limiter, the winding and the BAM M6 friction of XL330, with a rigid gear (the "
            "joint carries the armature), the joint angle as the encoder, the gain as an input and the "
            "friction's load torque sampled every 5 ms (no algebraic loop). Reads the globals k_motor, r_motor, "
            "i_limit and t_latency."),
        "ports": d.ports,
        "diagram": d.document(),
        "pins": {"params": PINS_PARAMS_RIGID, "starts": []},
    }


# ------------------------------------------------------------------ backlash as microduck_rl trains it

# [RL] add_backlash.py (microduck_rl 0daab16): every servo joint gets a passive hinge in series,
# range +-1 deg, armature 0.001, damping 0.01, frictionloss 0, solreflimit (0.01, 1),
# solimplimit (0.95, 0.999, 0.0001, 0.5, 2); the encoder reads through it.
PLAY = {"gap": math.radians(2.0), "jb": 0.001, "c": 0.01, "tc": 0.01, "zeta": 1.0,
        "dmin": 0.95, "dmax": 0.999, "width": 1.0e-4, "mid": 0.5, "power": 2.0}
PINS_PARAMS_BACKLASH = ["Friction/scale", "Friction/ws", "Latency/initial", "Backlash/gap", "Backlash/invw"]
PINS_STARTS_BACKLASH = ["Backlash/phi"]


def definition_backlash() -> dict:
    """library/XL330Backlash.bgsub.json: XL330Rigid with the gear play of microduck_rl.

    microduck_rl's backlash models (add_backlash.py, tasks/backlash.py, BacklashEncoderBamActuator)
    put an unactuated hinge after each servo joint: the servo joint is the motor output (BAM
    drives it, its armature is BAM's), the play hinge carries its own armature 0.001 kg m^2 and
    damping 0.01 N m s/rad and stops at +-1 deg through MuJoCo's soft limit; the link angle is
    the sum, and the firmware P law, the joint_pos and the joint_vel observations read the link.
    BAM's back-EMF and friction use the motor-side speed.

    Here: the motor junction carries the armature (`RotorInertia`, I = global `armature`), the
    motor torque, the BAM friction and the back-EMF speed; `Backlash` (library/MjBacklash.jl) is
    the play hinge with MuJoCo's limit law; the horn is the link. The joint (Revolute3DRigid) has
    Ja = 0. `Backlash/invw` is the play hinge's dof_invweight0 in the MuJoCo model (per joint).
    """
    d = _rigid_diagram(backlash=True)
    return {
        "format": "bgsim.subsystem",
        "name": "XL330Backlash",
        "description": (
            "XL330Rigid with the 2 deg gear play of microduck_rl's backlash models: the armature on the motor "
            "side, a play hinge (armature 0.001 kg m^2, damping 0.01 N m s/rad) with MuJoCo's soft limit at "
            "+-1 deg between the gear and the horn, the encoder on the horn. The joint carries no armature. "
            "Reads the globals k_motor, r_motor, armature, i_limit and t_latency."),
        "ports": d.ports,
        "diagram": d.document(),
        "pins": {"params": PINS_PARAMS_BACKLASH, "starts": PINS_STARTS_BACKLASH},
    }


def _rigid_diagram(backlash: bool):
    from diagram import Diagram

    d = Diagram()
    y0 = 0
    d.ref("Latency", "stdlib:continuous/TransportDelay", 80, y0, params={"initial": 0.0},
          constants={"delay_time": "t_latency", "sample_period": LATENCY_TICK})
    d.ref("GoalMux", "stdlib:continuous/Mux2", 220, y0 + 20)
    d.ref("Error", "stdlib:continuous/Sum", 340, y0 + 20, params={"signs": "[1.0, -1.0]"})
    d.ref("PGain", "stdlib:continuous/Product", 460, y0 + 20)
    d.ref("ErrorGain", "stdlib:continuous/Gain", 560, y0 + 20, params={"k": EG_EXPR})
    d.ref("Floor", "stdlib:continuous/Max", 680, y0 + 40)
    d.ref("Ceil", "stdlib:continuous/Min", 800, y0 + 40)
    d.ref("PwmLimit", "stdlib:continuous/Saturation", 920, y0 + 40,
          params={"lower": -MAX_PWM, "upper": MAX_PWM})
    y1 = y0 + 200
    d.ref("Emf", "stdlib:continuous/Gain", 340, y1, params={"k": "k_motor"})
    d.ref("EmfDuty", "stdlib:continuous/Divide", 460, y1)
    d.ref("RIlim", "stdlib:sources/Constant", 340, y1 + 100, params={"value": "r_motor*i_limit"})
    d.ref("Span", "stdlib:continuous/Divide", 460, y1 + 100)
    d.ref("HiMux", "stdlib:continuous/Mux2", 560, y1 - 20)
    d.ref("Hi", "stdlib:continuous/Sum", 660, y1 - 20, params={"signs": "[1.0, 1.0]"})
    d.ref("LoMux", "stdlib:continuous/Mux2", 560, y1 + 80)
    d.ref("Lo", "stdlib:continuous/Sum", 660, y1 + 80, params={"signs": "[1.0, -1.0]"})
    d.sig("Latency", "y", "GoalMux", "u1")
    d.sig("GoalMux", "y", "Error", "u")
    d.sig("Error", "y", "PGain", "u2")
    d.sig("PGain", "y", "ErrorGain", "u")
    d.sig("ErrorGain", "y", "Floor", "u1")
    d.sig("Lo", "y", "Floor", "u2")
    d.sig("Floor", "y", "Ceil", "u1")
    d.sig("Hi", "y", "Ceil", "u2")
    d.sig("Ceil", "y", "PwmLimit", "u")
    d.sig("Emf", "y", "EmfDuty", "u1")
    d.sig("RIlim", "y", "Span", "u1")
    d.sig("EmfDuty", "y", "HiMux", "u1")
    d.sig("Span", "y", "HiMux", "u2")
    d.sig("HiMux", "y", "Hi", "u")
    d.sig("EmfDuty", "y", "LoMux", "u1")
    d.sig("Span", "y", "LoMux", "u2")
    d.sig("LoMux", "y", "Lo", "u")
    # ---- power: supply -> H-bridge -> winding (R) -> GY (kt, at the output) -> output
    #      junction (friction) -> horn. No rotor, gear or backlash: the joint holds the armature.
    y2 = y0 + 480
    d.junction("Supply", "0", 80, y2)
    d.ref("VbusSense", "stdlib:bondgraph/De", 80, y2 + 110)
    d.ref("HBridge", "stdlib:bondgraph/MTF", 200, y2)
    d.junction("Winding", "1", 320, y2)
    d.ref("Rw", "stdlib:bondgraph/R", 280, y2 + 110, params={"r": "r_motor"})
    d.ref("Current", "stdlib:bondgraph/Df", 360, y2 + 110)
    d.ref("Motor", "project:MotorGY", 440, y2, params={"k": "k_motor"})
    # backlash: the motor side (Gear: armature, friction, back-EMF speed), the play hinge, the horn
    out = "Gear" if backlash else "Horn"
    if backlash:
        d.junction("Gear", "1", 600, y2)
        d.ref("RotorInertia", "stdlib:bondgraph/I", 560, y2 + 360, params={"i": "armature"})
        d.ref("GearSpeed", "stdlib:converters/SpeedSensor", 700, y2 + 130)
        d.ref("Backlash", "project:MjBacklash", 820, y2, params={k: PLAY[k] for k in ("gap", "jb", "c", "tc", "zeta",
                                                                                         "dmin", "dmax", "width", "mid", "power")})
        d.junction("Horn", "1", 1000, y2)
        d.ref("HornSpeed", "stdlib:converters/SpeedSensor", 1040, y2 + 130)
    else:
        d.junction("Horn", "1", 600, y2)
    d.ref("Friction", "project:BamFriction", 560, y2 + 130, params=friction_params())
    if not backlash:
        d.ref("HornSpeed", "stdlib:converters/SpeedSensor", 660, y2 + 130)
    d.ref("MotorTorque", "stdlib:continuous/Gain", 440, y2 + 200, params={"k": "k_motor"})
    d.ref("Transmit", "stdlib:continuous/Sum", 600, y2 + 280, params={"signs": "[1.0, -1.0]"})
    d.ref("TransmitMux", "stdlib:continuous/Mux2", 500, y2 + 280)
    d.ref("LoadSample", "stdlib:discrete/ZOH", 720, y2 + 280, constants={"sample_period": LATENCY_TICK})
    d.bond("Supply", None, "VbusSense", "p")
    d.bond("Supply", None, "HBridge", "p2")
    d.bond("HBridge", "p1", "Winding")
    d.bond("Winding", None, "Rw", "p")
    d.bond("Winding", None, "Current", "p")
    d.bond("Winding", None, "Motor", "e")
    d.bond("Motor", "m", out)
    d.bond(out, None, "Friction", "p")
    if backlash:
        d.bond("Gear", None, "RotorInertia", "p")
        d.bond("Gear", None, "GearSpeed", "a")
        d.bond("Gear", None, "Backlash", "a")
        d.bond("Horn", None, "Backlash", "b")
    d.bond("Horn", None, "HornSpeed", "a")
    d.sig("PwmLimit", "y", "HBridge", "u")
    d.sig("GearSpeed" if backlash else "HornSpeed", "y", "Emf", "u")
    d.sig("VbusSense", "y", "EmfDuty", "u2")
    d.sig("VbusSense", "y", "Span", "u2")
    d.sig("Current", "y", "MotorTorque", "u")
    d.sig("MotorTorque", "y", "Friction", "tau_m")
    d.sig("MotorTorque", "y", "TransmitMux", "u1")
    d.sig("Friction", "tau_f", "TransmitMux", "u2")
    d.sig("TransmitMux", "y", "Transmit", "u")
    d.sig("Transmit", "y", "LoadSample", "u")
    d.sig("LoadSample", "y", "Friction", "tau_l")
    # ---- ports
    d.signal_port("q_goal", "input", "Latency", "u", "rad")
    d.signal_port("kp", "input", "PGain", "u1", "1")
    d.signal_port("q", "input", "GoalMux", "u2", "rad")
    d.power_port("vbus", "Electrical", "Supply")
    d.power_port("horn", "Rotation", "Horn")
    d.signal_port("dq", "output", "HornSpeed", "y", "rad/s")
    d.signal_port("i", "output", "Current", "y", "A")
    d.signal_port("tau_m", "output", "MotorTorque", "y", "N*m")
    d.signal_port("tau_l", "output", "Transmit", "y", "N*m")
    d.signal_port("duty", "output", "PwmLimit", "y", "1")
    if backlash:
        d.signal_port("dq_gear", "output", "GearSpeed", "y", "rad/s")
    d.note("**Firmware (Position Control Mode).** duty = kp 4096/(2 pi)/(256 885) (goal - q), kp the "
           "Position P Gain register (an input: the robot changes it every tick); clamped to the "
           "current-limit window (kt w +- R i_limit)/V_bus [BAM] and to +-100 % PWM. The goal arrives "
           "t_latency late. q is the joint angle (the encoder).", 0, -170, 950, 110)
    if backlash:
        d.note("**Motor side, play hinge, horn (microduck_rl backlash models).** H-bridge MTF (duty) -> winding R "
               "-> GY kt -> gear (armature, BAM M6 friction, back-EMF speed) -> play hinge (2 deg, armature "
               "0.001 kg m^2, damping 0.01 N m s/rad, MuJoCo's soft limit: library/MjBacklash.jl) -> horn. The "
               "encoder q is the joint angle, after the play. The joint carries no armature. The friction reads "
               "kt i - tau_f sampled every 5 ms (LoadSample).", 0, y2 + 450, 1100, 130)
    else:
        d.note("**Motor at the output, rigid gear (BAM in mjlab).** H-bridge MTF (duty) -> winding R -> "
               "GY kt (output side) -> horn, with the BAM M6 friction. The armature is the joint's "
               "(Revolute3DRigid Ja). The friction reads the torque delivered to the joint sampled every "
               "5 ms (LoadSample), as BAM reads the previous physics step. No backlash.",
               0, y2 + 380, 1100, 110)
    return d


def fmtf(x: float) -> str:
    return repr(float(x))


# ------------------------------------------------------------------ reference simulator

def bam_friction(tau_m, tau_e, w, scale=1.0):
    """[BAM-CODE] bam/model.py compute_frictions for M6: (frictionloss, damping)."""
    b = BAM
    gt = abs(tau_e * b["load_friction_external"] - tau_m * b["load_friction_motor"])
    gts = abs(tau_e * b["load_friction_external_stribeck"] - tau_m * b["load_friction_motor_stribeck"])
    s = math.exp(-(abs(w / b["dtheta_stribeck"]) ** b["alpha"]))
    fl = b["friction_base"] + gt + s * b["friction_stribeck"] + gts * s
    if np.sign(tau_e) != np.sign(tau_m):
        if abs(tau_e) < abs(tau_m):
            fl += s * b["load_friction_external_quad"] * abs(tau_e) ** 2
        elif abs(tau_e) > abs(tau_m):
            fl += s * b["load_friction_motor_quad"] * abs(tau_m) ** 2
    return scale * fl, b["friction_viscous"]


def duty(q_goal, q, w, vin, kp=KP_FW, i_limit=I_LIMIT):
    """[BAM-CODE] VoltageControlledActuator.compute_control / vin."""
    d = (q_goal - q) * kp * ERROR_GAIN
    center, span = BAM["kt"] * w / vin, BAM["R"] * i_limit / vin
    d = min(max(d, center - span), center + span)
    return min(max(d, -MAX_PWM), MAX_PWM)


def motor_torque(d, w, vin):
    """[BAM-CODE] VoltageControlledActuator.compute_torque."""
    kt, r = BAM["kt"], BAM["R"]
    return kt * d * vin / r - kt**2 * w / r


def simulate_pendulum(goal, t_end, inertia, mgl, vin=V_NOMINAL, q0=0.0, latency=LATENCY,
                      dt=1e-5, kp=KP_FW, i_limit=I_LIMIT, every=100):
    """[BAM-CODE] bam/simulate.py Simulator.step on a pendulum (q = 0 hanging down), rigid gear,
    the goal delayed by `latency`. `goal(t)` is the commanded angle. Returns t, q, dq, tau_m."""
    q, w, t = q0, 0.0, 0.0
    jt = inertia + BAM["armature"]
    out = []
    n = int(round(t_end / dt))
    for k in range(n + 1):
        t = k * dt
        g = goal(t - latency) if t >= latency else goal(0.0)
        dd = duty(g, q, w, vin, kp, i_limit)
        tm = motor_torque(dd, w, vin)
        tb = -mgl * math.sin(q)
        fl, damp = bam_friction(tm, tb, w)
        net = tm + tb
        tau_stop = (jt / dt) * w + net
        net += -np.sign(tau_stop) * min(abs(tau_stop), fl + damp * abs(w))
        acc = net / jt
        if k % every == 0:
            out.append((t, q, w, tm))
        w += acc * dt
        q += w * dt + 0.5 * acc * dt * dt  # as bam/simulate.py (with the updated dq)
    a = np.array(out)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def report() -> None:
    kt, r = BAM["kt"], BAM["R"]
    print(f"error gain          {ERROR_GAIN:.6e} duty/(rad kp)")
    print(f"P stiffness kp=200  {KP_FW * ERROR_GAIN:.4f} duty/rad -> {kt * V_NOMINAL * KP_FW * ERROR_GAIN / r:.4f} N m/rad at {V_NOMINAL} V")
    print(f"stall torque        {kt * V_NOMINAL / r:.3f} N m (no limit), {kt * I_LIMIT:.3f} N m at {I_LIMIT} A")
    print(f"free speed          {V_NOMINAL / kt:.2f} rad/s at {V_NOMINAL} V")
    print(f"back-EMF damping    {kt**2 / r:.4f} N m s/rad")
    print(f"rotor inertia       {J_ROTOR:.4e} kg m^2 (armature {BAM['armature']:.4e})")
    print(f"motor constant      {K_MOTOR:.4e} N m/A at the rotor")


if __name__ == "__main__":
    report()
