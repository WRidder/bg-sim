"""The acceptance checks of the microduck example (expected.json), from independent references:

* xl330-step: the BAM identification simulator ported in xl330.py (simulate_pendulum), on the
  same bench arm and goal pulse.
* xl330-torque-speed: the analytic torque-speed curve of torque_speed.py.
* microduck-hang: the TransportDelay timing (exact), the BAM current-limit bound and the
  quasi-static gravity sag of robot.py (hang_reference) with the BAM friction band.
* microduck-stand: the microduck design notes (docs/design/robotd-design.md, section 2.4.2): HOME
  held at walking gain on the floor "tips past 40 deg within a second or two" in their simulation.

Written by build_model.py; nothing here reads a bgsim run.
"""

from __future__ import annotations

import math

import numpy as np

import robot as rb
import xl330 as xl

STEP_TIMES = [0.15, 0.2, 0.3, 0.5, 0.85, 0.95, 1.0, 1.1, 1.5]
HANG_JOINTS = ["left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle", "right_hip_pitch", "right_knee",
               "right_ankle", "neck_pitch", "head_pitch"]
DIAG = {"kind": "no_diagnostics", "codes": ["W201", "E106"],
        "note": "no causality conflicts. W202 (algebraic loops through Backlash/Transmit and Motor/Rw in "
                "every XL330) is expected: the friction reads the transmitted torque and the motor current"}


def step_checks() -> list[dict]:
    import compare_bench

    t, q, _, tm = compare_bench.reference()
    out = []
    for tt in STEP_TIMES:
        out.append({"kind": "cursor_value", "signal": "Servo/Encoder/y", "t": tt, "value": float(np.interp(tt, t, q)),
                    "abs": 0.02,
                    "note": "BAM identification simulator (design/xl330.py simulate_pendulum, the M6 XL330 fit "
                            "microduck_rl trains with). 0.02 rad: the delay line ramps a goal step over its 5 ms "
                            "tick, centred 2.5 ms early (TransportDelay), which moves the fast swings by up to 16 mrad"})
    out.append({"kind": "final_value", "signal": "Servo/Encoder/y", "t": 1.6, "value": float(q[-1]), "abs": 0.002,
                "note": "rest angle after the return: P gain against gravity inside the friction budget (BAM simulator)"})
    out.append({"kind": "cursor_value", "signal": "Servo/MotorTorque/y", "t": 0.5, "value": float(np.interp(0.5, t, tm)),
                "abs": 0.005, "note": "holding torque of the arm at the 1 rad goal (BAM simulator)"})
    out.append(DIAG)
    return out


def torque_speed_checks() -> list[dict]:
    import torque_speed as ts

    out = []
    for w in ts.SPEEDS:
        tm, tl, i = ts.horn_torque(w)
        out.append({"kind": "cursor_value", "signal": "Servo/Transmit/y", "t": ts.time_of(w), "value": tl, "abs": 5e-4,
                    "note": f"horn torque at {w:g} rad/s: min(1, (kt w + R i_limit)/V) duty, kt i minus the M6 "
                            "friction and the armature torque (design/torque_speed.py); 0.5 mN m for the smoothed kinks"})
    tm, _, i = ts.horn_torque(3.0)
    out.append({"kind": "cursor_value", "signal": "Servo/Current/y", "t": ts.time_of(3.0), "value": i, "rtol": 1e-4,
                "note": "the current-limit window holds the winding current at i_limit = 1.75 A (BAM XL330Actuator)"})
    out.append({"kind": "max_abs_le", "signal": "Servo/Current/y", "value": xl.I_LIMIT + 1e-6,
                "note": "BAM's limiter: the duty never lets the current exceed i_limit"})
    out.append(DIAG)
    return out


DIAG_RIGID = {"kind": "no_diagnostics", "codes": ["W202", "E106"],
              "note": "no algebraic loop and no causality conflict: XL330Rigid reads the friction's load torque "
                      "sampled every 5 ms. W201 is expected: the rigid joint's hard constraints put the link "
                      "inertia in derivative causality (Revolute3DRigid)"}


def rigid_step_checks() -> list[dict]:
    """XL330Rigid on the same bench against the same BAM simulator, with the same tolerances: the
    BAM simulator has a rigid gear too, and the armature is the joint's (Revolute3DRigid.Ja)."""
    out = []
    for c in step_checks():
        if c["kind"] == "no_diagnostics":
            out.append(DIAG_RIGID)
            continue
        c = dict(c)
        if c["signal"] == "Servo/Encoder/y":
            c["signal"] = "J/qout"
        out.append(c)
    return out


def rigid_torque_speed_checks() -> list[dict]:
    """XL330Rigid on the dynamometer: the analytic curve without the armature torque of the ramp
    (the joint carries the armature, and the dynamometer drives the horn directly)."""
    import build_model as bm
    import torque_speed as ts

    out = []
    for w in ts.SPEEDS:
        tm, tl, i = ts.horn_torque(w)
        tl += xl.BAM["armature"] * bm.SPEED_RAMP["slope"]
        out.append({"kind": "cursor_value", "signal": "Servo/Transmit/y", "t": ts.time_of(w), "value": tl, "abs": 5e-4,
                    "note": f"torque delivered at {w:g} rad/s: as xl330-torque-speed plus the armature torque "
                            "(armature x 4 rad/s^2, which XL330Rigid leaves to the joint); 0.5 mN m as there"})
    tm, _, i = ts.horn_torque(3.0)
    out.append({"kind": "cursor_value", "signal": "Servo/Current/y", "t": ts.time_of(3.0), "value": i, "rtol": 1e-4,
                "note": "the current-limit window holds the winding current at i_limit = 1.75 A (BAM XL330Actuator)"})
    out.append({"kind": "max_abs_le", "signal": "Servo/Current/y", "value": xl.I_LIMIT + 1e-6,
                "note": "BAM's limiter: the duty never lets the current exceed i_limit"})
    out.append(DIAG_RIGID)
    return out


DIAG_BACKLASH = {"kind": "no_diagnostics", "codes": ["W202", "E106"],
                 "note": "no algebraic loop and no causality conflict (XL330Backlash samples the friction's load "
                         "torque as XL330Rigid does). W201 is expected: the joint's hard constraints put the link "
                         "inertia in derivative causality"}

# Times at which the play rests on a flank or overshoots it (|d play/dt| small or the stop's impact
# well past), where the play angle is a property of the stop and not of the free-play phase.
BACKLASH_PLAY_TIMES = {
    "xl330-backlash-step": [0.15, 0.3, 0.9, 1.05, 1.2],
    "xl330-backlash-reversal": [0.175, 0.225, 0.375, 0.425, 0.7, 0.875, 0.925],
}
BACKLASH_ENC_TIMES = {
    "xl330-backlash-step": STEP_TIMES,
    "xl330-backlash-reversal": [0.2, 0.3, 0.4, 0.5, 0.65, 0.7, 0.8, 0.9, 1.0],
}
BACKLASH_ENC_TOL = {"xl330-backlash-step": 0.02, "xl330-backlash-reversal": 0.01}
BACKLASH_OVERTRAVEL = {"xl330-backlash-step": (0.13, 0.2), "xl330-backlash-reversal": (0.15, 0.2)}


def backlash_checks(name: str) -> list[dict]:
    """XL330Backlash (MjBacklash: microduck_rl's play hinge with MuJoCo's soft limit) on the bench
    against MuJoCo itself running the same bench (design/backlash_bench.py, stored in
    design/backlash_reference.json). bg-sim's play angle Servo/Backlash/phi is gear minus horn,
    MuJoCo's play hinge horn minus gear."""
    from backlash_bench import load_reference

    r = load_reference()["models"][name]
    t = r["t"]
    src = ("MuJoCo running the microduck_rl play hinge (add_backlash.py: +-1 deg, armature 0.001, damping 0.01, "
           "solreflimit 0.01 1, solimplimit 0.95 0.999 0.0001 0.5 2) with the BAM actuator each 0.5 ms step "
           "(design/backlash_bench.py)")
    out = []
    tol = BACKLASH_ENC_TOL[name]
    for tt in BACKLASH_ENC_TIMES[name]:
        out.append({"kind": "cursor_value", "signal": "J/qout", "t": tt, "value": float(np.interp(tt, t, r["q"])),
                    "abs": tol,
                    "note": f"encoder angle (horn, through the play), {src}. {tol:g} rad: as xl330-rigid-step, the "
                            "delay line ramps a goal step over its 5 ms tick and the friction rows of MuJoCo stick "
                            "a few mrad apart from bg-sim's friction law"})
    if name == "xl330-backlash-step":
        out.append({"kind": "final_value", "signal": "J/qout", "t": float(t[-1]), "value": float(r["q"][-1]),
                    "abs": 0.002, "note": f"rest angle after the return, {src}"})
    for tt in BACKLASH_PLAY_TIMES[name]:
        out.append({"kind": "cursor_value", "signal": "Servo/Backlash/phi", "t": tt,
                    "value": -float(np.interp(tt, t, r["q_play"])), "abs": 1e-3,
                    "note": f"play angle on or past a flank (the flanks are at +-{xl.PLAY['gap'] / 2:.5f} rad), {src}; "
                            "1 mrad, a twentieth of the play"})
    a, b = BACKLASH_OVERTRAVEL[name]
    w = (t >= a) & (t <= b)
    peak = float(np.max(np.abs(r["q_play"][w])))
    out.append({"kind": "max_abs_le", "signal": "Servo/Backlash/phi", "from_t": a, "to_t": b, "value": peak + 5e-4,
                "note": f"the first impact on the flank overshoots it by {(peak - xl.PLAY['gap'] / 2) * 1e3:.1f} mrad in "
                        f"MuJoCo (soft limit, time constant 10 ms), {src}; bg-sim may not overshoot by more than 0.5 mrad "
                        "beyond that"})
    out.append(DIAG_BACKLASH)
    return out


def hang_checks() -> list[dict]:
    home = rb.HOME
    low = rb.hang_goal_pose()
    pre = rb.hang_reference(home)
    post = rb.hang_reference(low)
    t_mid = rb.HANG_STEP + xl.LATENCY - xl.LATENCY_TICK / 2
    out = [{"kind": "zero_crossing", "signal": "left_knee/Latency/y", "level": (home["left_knee"] + low["left_knee"]) / 2,
            "direction": "up", "n": 1, "value": t_mid, "abs": 1e-4,
            "note": "the knee goal steps at 0.2 s and reaches the firmware t_latency = 20 ms later, ramped over the "
                    "5 ms tick of the delay line (half-way at 0.2 + 0.02 - 0.0025 s)"},
           {"kind": "max_abs_le", "signal": "left_knee/Current/y", "value": xl.I_LIMIT + 1e-6,
            "note": "BAM's current-limit window bounds the winding current by i_limit = 1.75 A"}]
    for label, t, ref, goal in (("before the step", 0.19, pre, home), ("at the end", rb.HANG_T_END, post, low)):
        for j in HANG_JOINTS:
            r = ref[j]
            out.append({"kind": "cursor_value", "signal": f"{j}/Encoder/y", "t": t, "value": r["q"],
                        "abs": round(r["band"] + 0.005, 4),
                        "note": f"{label}: quasi-static encoder angle, goal {goal[j]:.4f} plus gravity torque "
                                f"{r['tau_g']:.4f} N m over the P stiffness {rb.p_stiffness():.4f} N m/rad "
                                "(design/robot.py hang_reference); the tolerance is the BAM friction band at "
                                "rest plus 5 mrad"})
    out.append(DIAG)
    return out


def stand_checks() -> list[dict]:
    return [
        {"kind": "zero_crossing", "signal": "Free/pose[1]", "level": math.cos(math.radians(20.0)), "direction": "down",
         "n": 1, "value": 1.5, "abs": 0.5,
         "note": "the trunk quaternion w falls below cos(20 deg): the robot has tipped 40 deg. microduck "
                 "docs/design/robotd-design.md 2.4.2: HOME held at walking gain on the floor 'tips past 40 deg "
                 "within a second or two' in simulation (measured here 1.14 s)"},
        DIAG,
    ]


def policy_checks() -> list[dict]:
    """microduck-policy run by itself (its scripted targets, no policy): physics, not behaviour."""
    weight = rb.mass() * rb.G0
    t_mid = rb.POLICY_STEP + xl.LATENCY - xl.LATENCY_TICK / 2
    out = []
    for side in ("left", "right"):
        out.append({"kind": "cursor_value", "signal": f"{side}_foot_contact/u", "t": 0.25, "value": weight / 2, "rtol": 0.01,
                    "note": f"standing still at HOME, each sole carries half the weight m g = {weight:.4f} N "
                            "(the robot is symmetric; the slow forward tip changes this by well under 1 %)"})
    out += [
        {"kind": "max_abs_le", "signal": "gravity_y/u", "value": 1e-3,
         "note": "left-right symmetry: the projected gravity has no sideways part while both legs do the same"},
        {"kind": "zero_crossing", "signal": "left_knee/Latency/y",
         "level": (rb.HOME["left_knee"] + rb.policy_target_pose()["left_knee"]) / 2, "direction": "up", "n": 1,
         "value": t_mid, "abs": 1e-4,
         "note": f"the knee target steps at {rb.POLICY_STEP:g} s and reaches the firmware t_latency = 20 ms later, ramped "
                 "over the 5 ms tick of the delay line"},
        {"kind": "max_abs_le", "signal": "left_knee/Current/y", "value": xl.I_LIMIT + 1e-6,
         "note": "BAM's current-limit window bounds the winding current by i_limit = 1.75 A"},
        DIAG_RIGID,
    ]
    return out


def policy_backlash_checks() -> list[dict]:
    """microduck-policy-backlash by itself: the checks of microduck-policy (the play does not change
    them) and the play: every joint's stays within its stops plus MuJoCo's impact overshoot, and the
    loaded knees rest on a flank."""
    gap2 = xl.PLAY["gap"] / 2
    out = [c for c in policy_checks() if c["kind"] != "no_diagnostics"]
    for j in rb.JOINTS:
        out.append({"kind": "max_abs_le", "signal": f"{j}/Backlash/phi", "value": round(gap2 + 0.006, 6),
                    "note": "the play stays within its stops (+-1 deg) plus the overshoot of MuJoCo's soft limit, about the "
                            "arriving play rate times tc/e (5.3 mrad on the bench, design/backlash_bench.py); 6 mrad"})
    for side, sign in (("left", -1.0), ("right", 1.0)):
        out.append({"kind": "cursor_value", "signal": f"{side}_knee/Backlash/phi", "t": 0.25, "value": sign * gap2, "abs": 5e-4,
                    "note": "standing at HOME the knee carries the body and its play rests on a flank (MuJoCo's soft limit "
                            "lets a load of a few tenths of a N m sink it by about 0.1 mrad); the knee axes "
                            "are mirrored left to right"})
    out.append(DIAG_BACKLASH)
    return out


def expected() -> dict:
    out = _expected()
    import scene

    for name in scene.SCENE_OF:  # every link of the robot's scene follows its body's pose band
        out["models"][name]["checks"].insert(0, {"kind": "scene_bindings", "note": "every link of the scene follows the world pose of its body frame"})
    return out


def _expected() -> dict:
    return {
        "project": "microduck",
        "description": "The XL330 actuator on its bench against the BAM simulator and the analytic torque-speed "
                       "curve; the robot held by the trunk against the quasi-static gravity sag; the robot on "
                       "the floor against the tipping time reported by the microduck design notes.",
        "models": {
            "xl330-step": {"checks": step_checks()},
            "xl330-torque-speed": {"checks": torque_speed_checks()},
            "microduck-hang": {"checks": hang_checks()},
            "microduck-stand": {"checks": stand_checks()},
            "xl330-rigid-step": {"checks": rigid_step_checks()},
            "xl330-rigid-torque-speed": {"checks": rigid_torque_speed_checks()},
            "microduck-policy": {"checks": policy_checks()},
            "xl330-backlash-step": {"checks": backlash_checks("xl330-backlash-step")},
            "xl330-backlash-reversal": {"checks": backlash_checks("xl330-backlash-reversal")},
            # about 4.5 min of simulation for its 0.6 s (with other jobs running, 6.4 min)
            "microduck-policy-backlash": {"checks": policy_backlash_checks(), "run_timeout": 1200},
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(expected(), indent=1))
