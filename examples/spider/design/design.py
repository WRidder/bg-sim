# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Reference values of the T8X spider example (`design.json`).

Everything here is computed from `data.py` with an independent implementation: the leg is a
rotation-matrix chain (not the closed-form expressions of the Julia blocks), derivatives are
finite differences, and the walk path integrates the command profile. Nothing here runs the
model. `build_model.py` reads `design.json` for the derived plant data (joint inertias, the
composite body, the equilibrium start) and for the check references.

    uv run examples/spider/design/design.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import data as d

W = d.M_TOTAL * d.G0                       # N, total weight


# ----------------------------------------------------------------------------- leg chain
def rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


LINKS = (("coxa", d.M_COXA, d.J_COXA, d.A_COXA),
         ("femur", d.M_FEMUR, d.J_FEMUR, d.B_FEMUR),
         ("tibia", d.M_TIBIA, d.J_TIBIA, d.C_TIBIA))


def chain(i: int, q) -> dict:
    """Frames of leg i at joint angles q, in the body frame (the chain of the 3D scene).

    hip = T(h) Rz(yaw), C1 = Rz(q1), F2 = T(a,0,0) Rx90, C2 = Rz(q2), F3 = T(b,0,0), C3 = Rz(q3),
    foot = T(c,0,0). Returns the link frames (origin, rotation), the link centres, the joint
    axes and the foot point.
    """
    hx, hy, hz, yaw = d.HIPS[i]
    q1, q2, q3 = q
    o1 = np.array([hx, hy, hz])
    r1 = rz(yaw + q1)
    o2 = o1 + r1 @ np.array([d.A_COXA, 0.0, 0.0])
    r2 = r1 @ rx(math.pi / 2.0) @ rz(q2)
    o3 = o2 + r2 @ np.array([d.B_FEMUR, 0.0, 0.0])
    r3 = r2 @ rz(q3)
    foot = o3 + r3 @ np.array([d.C_TIBIA, 0.0, 0.0])
    frames = [(o1, r1), (o2, r2), (o3, r3)]
    centres = [o + r @ np.array([0.5 * length, 0.0, 0.0])
               for (o, r), (_n, _m, _j, length) in zip(frames, LINKS)]
    axes = [(o1, r1[:, 2]), (o2, r2[:, 2]), (o3, r3[:, 2])]
    return {"frames": frames, "centres": centres, "axes": axes, "foot": foot}


def foot_jacobian(i: int, q, h: float = 1e-7) -> np.ndarray:
    """d foot / d q (body frame), central differences."""
    jac = np.zeros((3, 3))
    for j in range(3):
        qp, qm = list(q), list(q)
        qp[j] += h
        qm[j] -= h
        jac[:, j] = (chain(i, qp)["foot"] - chain(i, qm)["foot"]) / (2.0 * h)
    return jac


def gravity_torques(i: int, q, gvec=(0.0, 0.0, -d.G0), h: float = 1e-7) -> np.ndarray:
    """Generalised gravity force of the three links, -dV/dq, V = -sum m g . r_centre."""
    g = np.array(gvec)

    def pot(qq):
        return -sum(m * float(g @ c) for (_n, m, _j, _l), c in zip(LINKS, chain(i, qq)["centres"]))

    out = np.zeros(3)
    for j in range(3):
        qp, qm = list(q), list(q)
        qp[j] += h
        qm[j] -= h
        out[j] = -(pot(qp) - pot(qm)) / (2.0 * h)
    return out


def joint_inertias(i: int, q, h: float = 1e-7) -> list[float]:
    """Diagonal of the leg's mass matrix (relative to the body) at q.

    M_jj = sum over the links distal to joint j of m |d c / d q_j|^2 + a_j^T R J R^T a_j, with
    the link centre velocity by finite differences and a_j the joint axis.
    """
    out = []
    ch = chain(i, q)
    for j in range(3):
        qp, qm = list(q), list(q)
        qp[j] += h
        qm[j] -= h
        cp, cm = chain(i, qp)["centres"], chain(i, qm)["centres"]
        mjj = 0.0
        axis = ch["axes"][j][1]
        for k, (_n, m, jl, _l) in enumerate(LINKS):
            v = (cp[k] - cm[k]) / (2.0 * h)
            mjj += m * float(v @ v)
            if k >= j:
                rk = ch["frames"][k][1]
                mjj += float(axis @ (rk @ np.diag(jl) @ rk.T) @ axis)
        out.append(mjj)
    return out


def contact_force(x: float) -> float:
    return d.CONTACT["k"] * x * math.sqrt(x / d.CONTACT["xref"])


def contact_penetration(force: float) -> float:
    """x for force = k x sqrt(x/xref), solved in closed form."""
    return (force / d.CONTACT["k"] * math.sqrt(d.CONTACT["xref"])) ** (2.0 / 3.0)


def contact_stiffness(force: float) -> float:
    """dF/dx of the Hertz law at a given load: 1.5 F / x."""
    return 1.5 * force / contact_penetration(force)


# ----------------------------------------------------------------------------- statics
def static_leg(i: int, force: float, qcmd) -> dict:
    """Leg i carrying a vertical foot force `force` (N) on level ground, the servo at qcmd.

    Joint equilibrium of the model's joint equation at rest:
        kp (qcmd - q) + tau_g(q) + J(q)^T (0, 0, F) = 0
    solved by Newton for all three q. Returns q, the servo torques kp (qcmd - q), the foot
    point in the body frame and the vertical foot compliance of the servo.
    """
    kp = np.array(d.KP)
    q = np.array(qcmd, dtype=float)
    f = np.array([0.0, 0.0, force])
    for _ in range(50):
        res = kp * (np.array(qcmd) - q) + gravity_torques(i, q) + foot_jacobian(i, q).T @ f
        jac = np.zeros((3, 3))
        for j in range(3):
            dq = np.zeros(3)
            dq[j] = 1e-6
            rp = kp * (np.array(qcmd) - (q + dq)) + gravity_torques(i, q + dq) + foot_jacobian(i, q + dq).T @ f
            jac[:, j] = (rp - res) / 1e-6
        step = np.linalg.solve(jac, -res)
        q = q + step
        if np.max(np.abs(step)) < 1e-13:
            break
    jf = foot_jacobian(i, q)
    stiff = np.diag(kp) - np.array([[(gravity_torques(i, q + e * 1e-6)[r] - gravity_torques(i, q - e * 1e-6)[r]) / 2e-6
                                     for e in np.eye(3)] for r in range(3)])
    compliance = jf @ np.linalg.solve(stiff, jf.T)
    return {"q": q, "tau": kp * (np.array(qcmd) - q), "foot": chain(i, q)["foot"],
            "c_servo_z": float(compliance[2, 2])}


def stance_static() -> dict:
    """The robot standing on eight feet, all joints commanded to the IK of the nominal foot."""
    f8 = W / 8.0
    legs = [static_leg(i, f8, d.Q0[i]) for i in range(8)]
    pen = contact_penetration(f8)
    z_body = [-pen - leg["foot"][2] for leg in legs]
    assert max(z_body) - min(z_body) < 1e-9, z_body
    k_servo = 1.0 / legs[0]["c_servo_z"]
    k_cont = contact_stiffness(f8)
    k_foot = 1.0 / (1.0 / k_servo + 1.0 / k_cont)
    return {"legs": legs, "penetration": pen, "z_body": z_body[0], "k_servo": k_servo,
            "k_contact": k_cont, "k_foot": k_foot}


# ----------------------------------------------------------------------------- composite body
def composite_body() -> dict:
    """The body plus the eight legs locked in the nominal stance, about the body origin."""
    m = d.M_BODY
    first = np.zeros(3)
    jo = np.diag(d.J_BODY).astype(float)
    leg_j = np.zeros((3, 3))
    for i in range(8):
        ch = chain(i, d.Q0[i])
        for (_n, ml, jl, _l), c, (_o, r) in zip(LINKS, ch["centres"], ch["frames"]):
            m += ml
            first += ml * c
            jl_o = r @ np.diag(jl) @ r.T + ml * (float(c @ c) * np.eye(3) - np.outer(c, c))
            jo += jl_o
            leg_j += jl_o
    return {"m": m, "com": first / m, "J_origin": jo, "J_legs": leg_j}


# ----------------------------------------------------------------------------- gait profile
def gait_profile(s: float, z_unload: float, beta: float = d.DUTY,
                 lift: float = d.LIFT) -> tuple[float, float]:
    """Foot command at phase s: normalised position along the stride (+1 front .. -1 rear)
    and the height above the stance height (m).

    Stance, s in [0, beta): constant velocity from +1 to -1; height z_unload (2 s/beta - 1)^8
    (the load hand-over ramp). Swing, u = (s - beta)/(1 - beta): a cubic Hermite from -1 back
    to +1 whose end slopes equal the stance slope, height z_unload + lift 16 u^2 (1 - u)^2 +
    m u (1 - u) with m = 16 z_unload (1 - beta)/beta (the ramp's slope), so position and
    velocity are continuous at both switches.
    """
    if s < beta:
        return 1.0 - 2.0 * s / beta, z_unload * (2.0 * s / beta - 1.0) ** 8
    u = (s - beta) / (1.0 - beta)
    m = -2.0 * (1.0 - beta) / beta
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    mz = 16.0 * z_unload * (1.0 - beta) / beta
    return (-h00 + h01 + m * (h10 + h11),
            z_unload + lift * 16.0 * u * u * (1.0 - u) ** 2 + mz * u * (1.0 - u))


# ----------------------------------------------------------------------------- command path
T_TABLE = np.arange(9) * 2.0
VX_TABLE = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.3, 0.3, 1.0, 1.0]) * d.V_WALK
VY_TABLE = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]) * d.V_CRAB
WZ_TABLE = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0]) * d.W_TURN


def command_path(t_end: float = 16.0, n: int = 160001) -> dict:
    """The body path the commands ask for: the TimeTable profile (linear between the 2 s
    samples) times the gait's ramp 1 - exp(-t/ramp_t), integrated in the body frame."""
    t = np.linspace(0.0, t_end, n)
    ramp = 1.0 - np.exp(-t / d.RAMP_T)
    vx = np.interp(t, T_TABLE, VX_TABLE) * ramp
    vy = np.interp(t, T_TABLE, VY_TABLE) * ramp
    wz = np.interp(t, T_TABLE, WZ_TABLE) * ramp

    def cumtrapz(y):
        return np.concatenate(([0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))))

    yaw = cumtrapz(wz)
    x = cumtrapz(vx * np.cos(yaw) - vy * np.sin(yaw))
    y = cumtrapz(vx * np.sin(yaw) + vy * np.cos(yaw))
    length = cumtrapz(np.hypot(vx, vy))
    return {"t": t, "x": x, "y": y, "yaw": yaw, "length": length, "vx": vx}


# ----------------------------------------------------------------------------- roll dynamics
def roll_model(k_att: float, st: dict, comp: dict, tau_att: float = d.TAU_ATT) -> dict:
    """Linear roll model of the reduced plant about the stance (vertical directions only).

    Per foot: the femur coordinate (inertia I2), the servo spring kp and the back-EMF/gear
    damping between the joint and its command, the command filter tau_s, and the contact
    (Hertz stiffness and Hunt-Crossley damping at the static load) between the foot and the
    ground. The body roll inertia is the composite J_xx, and the body receives only the
    contact forces (the reduction of the model). The attitude loop adds k_att * roll_f * ny to
    each foot command, roll_f being the roll through a first-order filter tau_att. The
    lateral friction of the feet is left out.
    """
    i2 = st["I"][1]
    jz = st["jz2"]
    kp = d.KP[1]
    bq = d.B_EMF + d.B_JOINT[1] + d.KD[1]
    kc = st["k_contact"]
    cc = W / 8.0 * d.CONTACT["c"]
    jxx = comp["J_origin"][0, 0]
    ny = d.NY
    n = 3 + 3 * 8                      # phi, phidot, roll_f, then (dq, dqdot, qf) per foot
    a = np.zeros((n, n))
    a[0, 1] = 1.0
    if tau_att > 0.0 and k_att != 0.0:
        a[2, 0] = 1.0 / tau_att
        a[2, 2] = -1.0 / tau_att
        src_att = 2
    else:
        a[2, 2] = -1.0e6               # no loop: the filter state is decoupled
        src_att = 0
    for k in range(8):
        iq, iv, iff = 3 + 3 * k, 4 + 3 * k, 5 + 3 * k
        # foot height z = ny phi + jz dq; contact force F = -kc z - cc zdot
        a[iq, iv] = 1.0
        # I2 dq'' = kp (qf - dq) - bq dq' + jz F
        a[iv, iff] += kp / i2
        a[iv, iq] += -kp / i2 - jz * kc * jz / i2
        a[iv, iv] += -bq / i2 - jz * cc * jz / i2
        a[iv, 0] += -jz * kc * ny[k] / i2
        a[iv, 1] += -jz * cc * ny[k] / i2
        # tau_s qf' = k_att ny roll_f / jz - qf
        a[iff, iff] = -1.0 / d.TAU_S
        a[iff, src_att] = k_att * ny[k] / jz / d.TAU_S
        # Jxx phi'' = sum ny F
        a[1, 0] += -ny[k] * kc * ny[k] / jxx
        a[1, 1] += -ny[k] * cc * ny[k] / jxx
        a[1, iq] += -ny[k] * kc * jz / jxx
        a[1, iv] += -ny[k] * cc * jz / jxx
    ev = np.linalg.eigvals(a)
    slow = ev[np.argmax(ev.real)]
    k_roll = (1.0 + k_att) * st["k_foot"] * sum(v * v for v in ny)
    return {"sigma": -float(slow.real), "omega": float(abs(slow.imag)), "k_roll": k_roll}


# ----------------------------------------------------------------------------- neglected terms
def swing_reactions(z_unload: float, i: int = 0, n: int = 4001) -> dict:
    """What the signal-coupled leg leaves out during one swing of leg i at the walk command:
    the inertial force of the moving link masses (relative to the body) and the reaction of
    the coxa servo (I1 q1''), both not applied to the body in the model."""
    beta, period = d.DUTY, d.T_GAIT
    amp = d.V_WALK * beta * period / 2.0
    s = np.linspace(beta, 1.0, n)
    dt = (s[1] - s[0]) * period
    pts, q1s = [], []
    for sv in s:
        xn, zn = gait_profile(min(sv, 1.0 - 1e-12), z_unload)
        foot = (d.FOOT[i][0] + amp * xn, d.FOOT[i][1], -d.H_STAND + zn)
        q = d.leg_ik(foot, d.HIPS[i][:3], d.HIPS[i][3])[:3]
        ch = chain(i, q)
        pts.append(sum(m * c for (_n, m, _j, _l), c in zip(LINKS, ch["centres"])))
        q1s.append(q[0])
    pts, q1s = np.array(pts), np.array(q1s)
    acc = np.gradient(np.gradient(pts, dt, axis=0), dt, axis=0)
    q1dd = np.gradient(np.gradient(q1s, dt), dt)
    inert = joint_inertias(i, d.Q0[i])
    return {"peak_inertial_force": float(np.max(np.linalg.norm(acc, axis=1))),
            "peak_coxa_reaction": float(inert[0] * np.max(np.abs(q1dd)))}


def main() -> None:
    st = stance_static()
    comp = composite_body()
    leg0 = st["legs"][0]
    inertia = joint_inertias(0, d.Q0[0])
    for i in range(1, 8):
        assert np.allclose(joint_inertias(i, d.Q0[i]), inertia, rtol=1e-6), i
        assert np.allclose(st["legs"][i]["q"], leg0["q"], atol=1e-9), i
    st["I"] = inertia
    st["jz2"] = float(foot_jacobian(0, leg0["q"])[2, 1])
    q0 = [[math.degrees(v) for v in leg] for leg in d.Q0]
    fk_err = []
    for i in range(8):
        p = chain(i, d.Q0[i])["foot"]
        f = d.leg_fk(*d.Q0[i], d.HIPS[i][:3], d.HIPS[i][3])
        fk_err.append(float(np.max(np.abs(p - np.array(f)))))

    # the four-foot phase of the tetrapod: one group carries the weight
    f4 = W / 4.0
    leg4 = static_leg(0, f4, d.Q0[0])
    sag8 = d.H_STAND - st["z_body"]
    z_body4 = -contact_penetration(f4) - leg4["foot"][2]
    sag4 = d.H_STAND - z_body4

    def free_foot_z(zc: float) -> float:
        """World height of an unloaded foot commanded to z = -h + zc (body frame) while the
        body is at its four-foot height: the leg sags under its own weight."""
        foot = (d.FOOT[0][0], d.FOOT[0][1], -d.H_STAND + zc)
        qc = d.leg_ik(foot, d.HIPS[0][:3], d.HIPS[0][3])[:3]
        return z_body4 + static_leg(0, 0.0, qc)["foot"][2]

    # z_unload: the height above the stance height at which the unloaded foot just touches
    # the floor while the other group carries the body, so touchdown and liftoff happen at
    # zero load and the double-support ramps move the load (bisection on free_foot_z = 0)
    lo, hi = 0.0, 0.02
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if free_foot_z(mid) < 0.0 else (lo, mid)
    z_unload = 0.5 * (lo + hi)
    zc_apex = gait_profile(d.DUTY + 0.5 * (1.0 - d.DUTY), z_unload)[1]
    apex_world = free_foot_z(zc_apex)
    # the command's vertical acceleration at the apex, and the peak reduction a first-order
    # filter tau_s gives there, |z''| tau_s^2 / 2
    du = 1e-4
    zpp = (gait_profile(d.DUTY + (0.5 + du) * (1 - d.DUTY), z_unload)[1]
           - 2 * zc_apex + gait_profile(d.DUTY + (0.5 - du) * (1 - d.DUTY), z_unload)[1]) \
        / (du * (1 - d.DUTY) * d.T_GAIT) ** 2
    filter_drop = 0.5 * abs(zpp) * d.TAU_S ** 2

    path = command_path()
    k_end = -1
    roll = {f"{k:g}": roll_model(k, st, comp) for k in (0.0, 0.5, 1.0, 2.0)}
    roll_old_sign = {f"{k:g}": roll_model(-k, st, comp) for k in (0.5, 1.0, 1.5)}
    react = swing_reactions(z_unload)

    # floor: the path's bounding box plus the leg span and a margin
    span = 0.30
    floor = {"x": [float(path["x"].min()) - span, float(path["x"].max()) + span],
             "y": [float(path["y"].min()) - span, float(path["y"].max()) + span]}

    out = {
        "mass": d.M_TOTAL,
        "weight": W,
        "static_foot_force": W / 8.0,
        "static_contact_penetration": st["penetration"],
        "leg_lengths": [d.A_COXA, d.B_FEMUR, d.C_TIBIA],
        "foot_radius": d.FOOT_R,
        "q0_deg": q0,
        "fk_matrix_max_error": max(fk_err),
        "joint_inertias": inertia,
        "joint_inertia_note": "diagonal of the leg mass matrix at the nominal pose, links only (no rotor)",
        "composite_body": {"m": comp["m"], "com": comp["com"].tolist(),
                           "J_origin_diag": np.diag(comp["J_origin"]).tolist(),
                           "J_origin_offdiag_max": float(np.max(np.abs(comp["J_origin"] - np.diag(np.diag(comp["J_origin"]))))),
                           "J_legs_diag": np.diag(comp["J_legs"]).tolist(),
                           "body_only": {"m": d.M_BODY, "J": d.J_BODY}},
        "stand": {
            "q_static": leg0["q"].tolist(),
            "q_cmd": list(d.Q0[0]),
            "tau_static": leg0["tau"].tolist(),
            "body_height": st["z_body"],
            "sag": sag8,
            "servo_sag": sag8 - st["penetration"],
            "k_servo_vertical": st["k_servo"],
            "k_contact": st["k_contact"],
            "k_foot": st["k_foot"],
        },
        "four_foot": {"foot_force": f4, "tau_static": leg4["tau"].tolist(), "sag": sag4},
        "gait": {
            "duty_command": d.DUTY,
            "stride_amplitude": d.V_WALK * d.DUTY * d.T_GAIT / 2.0,
            "stance_foot_speed": d.V_WALK,
            "z_unload": z_unload,
            "mean_feet_down": 8.0 * d.DUTY,
            "apex_command": zc_apex,
            "apex_world": apex_world,
            "apex_filter_drop": filter_drop,
            "swing_time": (1.0 - d.DUTY) * d.T_GAIT,
        },
        "walk_path": {"x16": float(path["x"][k_end]), "y16": float(path["y"][k_end]),
                      "yaw16_deg": math.degrees(float(path["yaw"][k_end])),
                      "length16": float(path["length"][k_end]),
                      "x_range": [float(path["x"].min()), float(path["x"].max())],
                      "y_range": [float(path["y"].min()), float(path["y"].max())],
                      "mean_vx_14p4_16": float(np.mean(path["vx"][path["t"] >= 14.4]))},
        "floor": floor,
        "roll": {"k_att_used": d.K_ATT, "tau_att": d.TAU_ATT, "by_k_att": roll,
                 "old_sign_by_k_att": roll_old_sign,
                 "k_att_1_unfiltered": roll_model(1.0, st, comp, 0.0)},
        "neglected": {"swing_inertial_force_per_leg": react["peak_inertial_force"],
                      "coxa_reaction_torque_per_leg": react["peak_coxa_reaction"],
                      "eight_coxa_I1": 8.0 * inertia[0]},
        "servo": {"tau_stall": d.TAU_STALL, "w_noload": d.W_NOLOAD, "b_emf": d.B_EMF,
                  "kp": d.KP_SERVO},
        "gait_period": d.T_GAIT,
        "walk_speed_command": d.V_WALK,
        "turn_rate_command_deg": math.degrees(d.W_TURN),
        "contact_stiffness": d.CONTACT["k"],
    }
    path_out = Path(__file__).resolve().parent / "design.json"
    with open(path_out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(json.dumps({k: v for k, v in out.items() if k != "q0_deg"}, indent=2))


if __name__ == "__main__":
    main()
