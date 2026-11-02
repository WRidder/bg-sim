"""The double-cart lab rig: its parameters (`realism.json`), the design model, the twin and the firmware replica.

`realism.json` is the single source of the rig. This module turns one parameter set (`nominal()` or
`sample(rng)`) into

- `design_plant(p)`: the `cartpend.Plant` of `examples/pendulum-double-cart/design/` (the design model,
  the trajectory optimisation, the TVLQR, the LQR and the bond-graph generator `cartmodel.py`), with the
  link masses, centres of mass and inertias lumped from the parts list (`link_props`);
- `twin_rig(p)`: the `quadlib.Rig` of `examples/quad-pendulum/design/quadlib.py` with the realism terms
  (smooth Coulomb friction per joint and on the cart, cable springs and dampers, commutation ripple and
  cogging), and `LabPlant`, the quadlib Lagrangian twin with the voltage-driven DC motor;
- `setup(p, effects, ...)`: the truth twin and the firmware-replica options of one parameter set, the lab
  counterpart of `quadlib.realistic_setup` (sensors: quantised, noisy encoders; loop: whole-sample delay and
  the armature current lag; rates from filtered differences or an EKF; Coulomb compensation of the cart);
- `firmware(tab, **kw)`: the replica of `library/DoubleCartLabCtrl.jl` (quadlib.Firmware with the
  time-based catch of cartpend.py).

The design model and the twin are the same mechanism (checked by `check_twin`): states
z = [x, th1, th2, xd, w1, w2] with absolute link angles from the upward vertical, input the motor voltage V,
cart force F = alpha V - beta xd (armature inductance neglected, rotor inertia reflected onto the cart).
The twin is belt-rigid; the belt is in the bond graph (and checked on the linearisation by `belt_poles`).
"""

from __future__ import annotations

import dataclasses
import math
import sys
from pathlib import Path

import casadi as ca
import numpy as np

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parents[1]
# appended, not prepended: both folders have their own design.py (and the quad a screen.py)
sys.path.append(str(EXAMPLES / "pendulum-double-cart" / "design"))
sys.path.append(str(EXAMPLES / "quad-pendulum" / "design"))

import cartpend as cp  # noqa: E402
import quadlib as ql  # noqa: E402

REALISM = HERE / "realism.json"
KIND = "lab"
TS = 1e-3
EFFECTS = ("mass", "drive", "fbase", "fjoint", "cable", "sensor", "loop", "ripple")
# EKF process noise (random accelerations: cart m/s^2, links rad/s^2), see screen.py
EKF_Q = (1.0, 10.0)


# ----------------------------------------------------------------------------- parameter sets
def spec() -> dict:
    return ql.load_realism(REALISM)["rigs"][KIND]["params"]


def nominal() -> dict:
    return ql.realism_nominal(KIND, REALISM)


def sample(rng: np.random.Generator) -> dict:
    return ql.sample_realism(KIND, rng, REALISM)


def groups() -> dict:
    """{effect: [parameter names]} from the 'group' of every parameter."""
    out: dict = {}
    for k, v in spec().items():
        out.setdefault(v["group"], []).append(k)
    return out


# switched off, these parameters are zero (they do not exist in the design model); every other parameter of
# an effect that is off is set to its nominal value
_ZERO_OFF = {"fbase": ("tc_carriage", "tc_motor"), "fjoint": ("tc_joint1", "tc_joint2"),
             "cable": ("k_cable", "k_cable_base"), "ripple": ("ripple_rel", "cogging")}


def effects_only(p: dict, effects=EFFECTS) -> dict:
    """`p` with the effects not in `effects` back at the design model: nominal values, and no Coulomb friction,
    cable springs or ripple. With no effect on, the twin is the design model."""
    nom = nominal()
    q = dict(p)
    for eff, names in groups().items():
        if eff in effects or eff in ("sensor", "loop", "rail", "disturbance"):
            continue
        for k in names:
            q[k] = 0.0 if k in _ZERO_OFF.get(eff, ()) else nom[k]
    return q


# ----------------------------------------------------------------------------- the links
def link_parts(p: dict) -> list:
    """Per link the parts as (mass kg, position along the link from its pivot m, own inertia about the part's
    centre of mass kg m^2): the tube (thin-walled cylinder, its own COM shifted by com_shift L), the hub at the
    pivot with the encoder magnet, link 1's head (joint-2 bearing block and encoder board) at its tip and the
    joint-2 cable along it, link 2's tip cap. Hubs, head and cap are small cubes (J = m s^2 / 6)."""
    L1, L2 = p["L1"], p["L2"]
    ro = p["tube_od"] / 2
    ri = ro - p["tube_wall"]

    def tube(m, L, shift):
        return (m, L * (0.5 + shift), m * (L * L / 12 + (ro * ro + ri * ri) / 4))

    def cube(m, x, s):
        return (m, x, m * s * s / 6)

    mc = p["rho_cable"] * L1
    link1 = [tube(p["m_tube1"], L1, p["com_shift1"]), cube(p["m_hub1"], 0.0, p["s_hub"]), (p["m_enc_magnet"], 0.0, 0.0),
             cube(p["m_head1"], L1, p["s_head"]), (p["m_enc_board"], L1, 0.0), (mc, L1 / 2, mc * L1 * L1 / 12)]
    link2 = [tube(p["m_tube2"], L2, p["com_shift2"]), cube(p["m_hub2"], 0.0, p["s_hub"]), (p["m_enc_magnet"], 0.0, 0.0),
             cube(p["m_tip2"], L2, p["s_tip"])]
    return [link1, link2]


def link_props(p: dict) -> tuple[list, list, list]:
    """Mass, centre of mass from the pivot and inertia about the centre of mass of each link (parallel axes)."""
    m, c, J = [], [], []
    for parts in link_parts(p):
        mt = sum(a for a, _, _ in parts)
        ct = sum(a * x for a, x, _ in parts) / mt
        m.append(round(mt, 12))
        c.append(round(ct, 12))
        J.append(round(sum(j + a * (x - ct) ** 2 for a, x, j in parts), 15))
    return m, c, J


# ----------------------------------------------------------------------------- the drive
def drive(p: dict) -> dict:
    """Motor seen from the cart: n = N/r (motor rad per m), force per volt alpha, back-EMF and bearing damping
    beta_m, reflected rotor mass m_rot, Coulomb force of the motor tc_m."""
    n = p["N_gear"] / p["r_pulley"]
    return {"n": n, "alpha": p["k_t"] * n / p["R_m"], "beta_m": (p["k_t"] ** 2 / p["R_m"] + p["b_motor"]) * n * n,
            "m_rot": p["J_m"] * n * n, "tc_m": p["tc_motor"] * n}


def current(p: dict, V, xd):
    """Armature current (A) for the terminal voltage V and the cart speed xd (quasi-static, L_m neglected)."""
    n = p["N_gear"] / p["r_pulley"]
    return (np.asarray(V) - p["k_t"] * n * np.asarray(xd)) / p["R_m"]


# ----------------------------------------------------------------------------- design model
def design_plant(p: dict, name: str = "PendulumDoubleCartLab") -> cp.Plant:
    """The design model (and the bond graph) of the parameter set: masses and inertias lumped, viscous friction
    of the joints (with the cable drag across joint 1), the carriage and the cable chain; no Coulomb friction,
    cable springs or ripple (they are left to the feedback and screened on the twin)."""
    m, c, J = link_props(p)
    return cp.Plant(
        name=name, L=[p["L1"], p["L2"]], m=m, c=c, J=J,
        b=[p["b_joint1"] + p["b_cable"], p["b_joint2"]],
        m_cart=p["m_cart"], J_cart=p["J_cart"],
        R_m=p["R_m"], L_m=p["L_m"], k_t=p["k_t"], J_m=p["J_m"], b_m=p["b_motor"], N=p["N_gear"], r=p["r_pulley"],
        u_max=p["u_max"], x_rail=p["x_rail"], k_belt=p["k_belt"], d_belt=p["d_belt"],
        b_cart=p["b_carriage"] + p["b_cable_base"], k_stop=p["k_stop"], d_stop=p["d_stop"],
    )


# ----------------------------------------------------------------------------- the twin
class LabPlant(ql.Plant):
    """The quadlib cart twin with the voltage-driven DC motor: the input is the terminal voltage V, the force on
    the cart alpha V (1 + ripple sin(n_r th_m)) + cogging sin(n_c th_m), th_m = (N/r) x the motor angle; the
    back-EMF and the bearing loss are viscous damping on the cart (in b_base), the rotor inertia is in m_base."""

    def __init__(self, rig: ql.Rig, alpha: float):
        self.alpha = alpha
        super().__init__(rig)

    def actuator(self, u, s):
        R = self.rig
        f = self.alpha * u
        if R.ripple_rel == 0.0 and R.cogging == 0.0:
            return f
        th = R.motor_per_base * s
        return f * (1 + R.ripple_rel * ca.sin(R.ripple_n * th)) + R.cogging * ca.sin(R.cogging_n * th)


def twin_rig(p: dict) -> tuple[ql.Rig, float]:
    """The quadlib Rig of the parameter set (all realism terms of `p`) and the force per volt alpha."""
    m, c, J = link_props(p)
    d = drive(p)
    rig = ql.Rig(
        kind="cart", L=[p["L1"], p["L2"]], m=m, c_eq=c, J_eq=J,
        b_joint=[p["b_joint1"], p["b_joint2"]], tc_joint=[p["tc_joint1"], p["tc_joint2"]], eps_joint=p["eps_joint"],
        m_base=p["m_cart"] + d["m_rot"], b_base=d["beta_m"] + p["b_carriage"],
        tc_base=p["tc_carriage"] + d["tc_m"], eps_base=p["eps_base"],
        k_cable=[p["k_cable"], 0.0], b_cable=[p["b_cable"], 0.0],
        k_cable_base=p["k_cable_base"], b_cable_base=p["b_cable_base"],
        ripple_rel=p["ripple_rel"], ripple_n=p["ripple_per_rev"], cogging=p["cogging"], cogging_n=p["cogging_per_rev"],
        motor_per_base=d["n"], u_max=p["u_max"], slew=1e12, s_max=p["x_rail"], J_cart=p["J_cart"],
    )
    return rig, d["alpha"]


_PLANTS: dict = {}


def plant_of(rig: ql.Rig, alpha: float, sub: int = 8):
    """Cached (LabPlant, RK4 sample step with `sub` substeps)."""
    key = (repr(dataclasses.asdict(rig)), alpha, sub)
    if key not in _PLANTS:
        if len(_PLANTS) > 64:
            _PLANTS.clear()
        plant = LabPlant(rig, alpha)
        _PLANTS[key] = (plant, plant.steps(TS, sub)[0])
    return _PLANTS[key]


def twin(p: dict, sub: int = 8):
    rig, alpha = twin_rig(p)
    return plant_of(rig, alpha, sub)


# ----------------------------------------------------------------------------- firmware replica
def firmware(tab: cp.Tables, **kw) -> ql.Firmware:
    """The replica of the 1 kHz firmware (`library/DoubleCartLabCtrl.jl`, written by cartpend.write_controller):
    hold, feed-forward + TVLQR from the 10 ms tables, the time-based catch at tau = T_s (catch_lead 0, no catch
    region), the discrete LQR, the clamp; no slew limit. `kw`: the quadlib.Firmware options (delay, sensors,
    estimator, compensation, balance_only)."""
    nx = len(tab.Klqr)
    base = dict(t_on=tab.t_on, t_s=tab.T_s, dt_tab=float(tab.tk[1] - tab.tk[0]), tab_x=np.array(tab.xs),
                tab_u=np.array(tab.uff), tab_k=np.array(tab.Ks), k_lqr=np.array(tab.Klqr), p_catch=np.zeros((nx, nx)),
                catch_tol=math.inf, catch_lead=0.0, u_max=tab.u_max, slew=1e12, res_s=nominal()["base_res"],
                res_q=2 * math.pi / 2**14, tau_f=0.002)
    return ql.Firmware(**(base | kw))


def setup(p: dict, effects=EFFECTS, estimator: str = "diff", ekf_q=None, comp: float = 0.0, seed: int = 0,
          sub: int = 8) -> ql.Realistic:
    """The truth twin and the firmware-replica options of the parameter set `p` with the effects `effects` on
    (the lab counterpart of quadlib.realistic_setup):

    - sensor: quantised, noisy encoders (quadlib.sensor_options); off: exact positions and rates (or exact
      positions through the EKF);
    - loop: the whole-sample delay and the armature current lag tau = L_m / R_m (`tau_act` of closed_loop);
    - estimator "diff" (filtered differences, tau_f of the Firmware) or "ekf": an EKF on the nominal twin with
      its Coulomb friction (calibrated) and without ripple, process noise `ekf_q` (default EKF_Q), measurement
      noise from the encoder resolution and noise, designed for the nominal delay;
    - comp: Coulomb compensation of the cart, the fraction `comp` of the nominal Coulomb force, in volts.

    The firmware's own model knowledge (observer, EKF delay, compensation) is the nominal parameter set.
    Use with `firmware(tab, **setup.fw_kw)` and `quadlib.closed_loop(setup.step, fw, x0, t_end, tau_act=setup.tau_act)`."""
    q = effects_only(p, effects)
    rig, alpha = twin_rig(q)
    plant, step = plant_of(rig, alpha, sub)
    on = set(effects)
    nom = nominal()
    kw: dict = {}
    if "sensor" in on:
        so = ql.sensor_options("cart", q)
        kw |= {k: so[k] for k in ("quant", "res_q", "noise_q", "res_s", "noise_s")}
    elif estimator == "ekf":
        kw |= {"quant": True, "res_q": 1e-12, "res_s": 1e-12}
    if "loop" in on:
        kw["delay"] = int(q["delay"])
    if estimator == "ekf":
        obs, alpha_o = twin_rig(nom | {"ripple_rel": 0.0, "cogging": 0.0})
        res_q, res_s = kw.get("res_q", 1e-9), kw.get("res_s", 1e-9)
        r_meas = tuple([max(res_s**2 / 12 + kw.get("noise_s", 0.0) ** 2, 1e-12)]
                       + [max(res_q**2 / 12 + kw.get("noise_q", 0.0) ** 2, 1e-12)] * rig.n)
        q_acc = tuple(ekf_q or EKF_Q)
        kw["estimator"] = "ekf"
        kw["ekf"] = _ekf(obs, alpha_o, q_acc, r_meas)
        kw["ekf_delay"] = int(nom["delay"]) if "loop" in on else 0
    kw["seed"] = int(seed)
    if comp:
        dn = drive(nom)
        kw["fc_base"] = comp * (nom["tc_carriage"] + dn["tc_m"]) / dn["alpha"]     # volts
        kw["fc_eps"] = 2.0 * nom["eps_base"]
    return ql.Realistic(p=q, truth=rig, plant=plant, step=step, fw_kw=kw,
                        tau_act=q["L_m"] / q["R_m"] if "loop" in on else 0.0)


_EKFS: dict = {}


def _ekf(rig, alpha, q_acc, r_meas) -> ql.EKF:
    key = (repr(dataclasses.asdict(rig)), alpha, q_acc, r_meas)
    if key not in _EKFS:
        _EKFS[key] = ql.EKF(LabPlant(rig, alpha), q_acc, r_meas)
    return _EKFS[key]


# ----------------------------------------------------------------------------- checks
def check_twin(p: dict | None = None, n: int = 20, seed: int = 0) -> float:
    """Largest relative difference of the state derivative of the design model (cartpend.Dynamics) and the
    twin with no realism term (LabPlant), over random states and voltages."""
    p = effects_only(p or nominal(), ())
    dyn = cp.Dynamics(design_plant(p))
    plant, _ = twin(p)
    rng = np.random.default_rng(seed)
    err = 0.0
    for _ in range(n):
        z = rng.normal(size=6) * [0.3, 2.0, 2.0, 1.0, 5.0, 5.0]
        V = float(rng.normal() * 10)
        a, b = dyn(z, V), plant.rhs(z, V)
        err = max(err, float(np.max(np.abs(a - b)) / max(1.0, np.max(np.abs(a)))))
    return err


def belt_poles(p: dict, k_lqr, delay: int = 0) -> np.ndarray:
    """Closed-loop poles (continuous equivalents, 1/s) of the discrete LQR on the sampled linearisation with the
    belt: the motor (rotor reflected, m_rot, back-EMF) and the cart are two masses joined by k_belt, d_belt; the
    firmware reads the cart and the joints (z of the rigid model, with x the cart), plus `delay` samples."""
    import scipy.linalg as sla
    P = design_plant(p)
    d = drive(p)
    # the links and the cart without the motor (its back-EMF and rotor move to the motor side of the belt)
    dyn = cp.Dynamics(dataclasses.replace(P, J_m=0.0, b_m=0.0, k_t=1e-12))
    A6, _ = dyn.lin(np.zeros(6))
    bF = np.concatenate([np.zeros(3), np.linalg.solve(np.array(dyn.M(np.zeros(6))), [1.0, 0.0, 0.0])])  # unit cart force
    # augmented state [z (6), xm, vm]: xm motor-side belt end (m at the cart), F_belt = k (xm - x) + d (vm - v)
    k, c = p["k_belt"], p["d_belt"]
    A = np.zeros((8, 8))
    A[:6, :6] = A6
    A[:6, :] += np.outer(bF, np.r_[-k, 0, 0, -c, 0, 0, k, c])
    A[6, 7] = 1.0
    A[7, :] = np.r_[k, 0, 0, c, 0, 0, -k, -c - d["beta_m"]] / d["m_rot"]
    B = np.zeros((8, 1))
    B[7, 0] = d["alpha"] / d["m_rot"]
    n = 8
    M = sla.expm(np.block([[A, B], [np.zeros((1, n + 1))]]) * TS)
    Ad, Bd = M[:n, :n], M[:n, n:]
    K = np.zeros((1, n))
    K[0, :6] = k_lqr
    if delay == 0:
        Acl = Ad - Bd @ K
    else:
        N = n + delay
        Acl = np.zeros((N, N))
        Acl[:n, :n] = Ad
        Acl[:n, n + delay - 1:n + delay] = Bd
        Acl[n, :n] = -K
        for i in range(1, delay):
            Acl[n + i, n + i - 1] = 1.0
    ev = np.linalg.eigvals(Acl).astype(complex)
    return np.log(ev) / TS
