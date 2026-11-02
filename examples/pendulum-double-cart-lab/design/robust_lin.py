"""Linear models, analysis and the balance-controller structure of the robust classical designs (plan C1).

Used by `design/robust_c1.py` (the designs and their verification) and `design/robust_ctrl.py` (the
controllers on the robustness harness). No script of its own.

Models. `lin_cont(p)` is the twin of `lablib` for the parameter set p linearised at the upright with the
Coulomb friction, ripple and cogging removed (the smooth Coulomb law has no meaningful linearisation at zero
speed; it is left to the harness): z = [x, th1, th2, v, w1, w2], input the motor voltage, plus the tip force.
`truth_dt(p)` is its 1 kHz sampled form with what the harness puts between the command and the plant: the
whole-sample delay of p (the command computed at sample k acts from k + delay) and the armature lag
L_m / R_m (the plant sees its mean over each sample), with the measured positions y = [x, th1, th2]. With
`belt=True` the belt (k_belt, d_belt) joins the motor and the cart (two masses, as `lablib.belt_poles`) and
the motor encoder measures the motor side.

Controller structure (the firmware's): an observer on the nominal sampled model that predicts with the
command it applied `d_obs` samples ago (the EKF of `lablib.setup`, d_obs = 2, its linearised steady-state
gain by default) and the state feedback u = -K [x_hat; u_{k-1}; u_{k-2}] (6 state gains and two gains on its
own last commands, a delay predictor; zero for the nominal LQR). `ObserverCtrl.lti()` is this as a discrete LTI
controller y -> u for the analysis; `robust_ctrl.py` runs it on the harness (EKF or linear observer).

Analysis. Closed loops of a truth and a controller (`closed_loop`), spectral radius, H2, a gridded H-infinity
norm, the input loop (`loop_at_input`: disk margin, gain / phase / delay margins), and the LFT of the
parameter box for the mu-analysis (`build_lft`, `mu_bounds`).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import scipy.linalg as sla

import lablib as lb

TS = lb.TS
P_NOM = lb.nominal()
SPEC = lb.spec()
NO_COULOMB = {"tc_joint1": 0.0, "tc_joint2": 0.0, "tc_carriage": 0.0, "tc_motor": 0.0, "ripple_rel": 0.0, "cogging": 0.0}
# the measured relative joint angles of the encoders: [x, th1, th2 - th1] = T [x, th1, th2]
T_REL = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, -1.0, 1.0]])


# ----------------------------------------------------------------------------- plant models
_LIN: dict = {}


def lin_cont(p: dict):
    """Continuous linearisation at the upright: A (6x6), B (6x1, per volt), Bf (6x1, per newton of tip push)."""
    key = tuple(sorted((k, float(v)) for k, v in p.items()))
    if key not in _LIN:
        rig, alpha = lb.twin_rig(p | NO_COULOMB)
        plant = lb.LabPlant(rig, alpha)
        A, B = (np.array(m, float) for m in plant.lin_fn(np.zeros(6), 0.0))
        f0 = np.array(plant.f(np.zeros(6), 0.0, 0.0)).ravel()
        Bf = np.array(plant.f(np.zeros(6), 0.0, 1.0)).ravel() - f0
        if len(_LIN) > 512:
            _LIN.clear()
        _LIN[key] = (A, B.reshape(6, 1), Bf.reshape(6, 1))
    return _LIN[key]


def belt_cont(p: dict):
    """The 8-state linearisation with the belt: [x, th1, th2, v, w1, w2, xm, vm], xm the motor-side belt end
    (m at the cart). Returns A, B (per volt), Bf (tip push) and the measured-position map C (y = [xm, th1, th2])."""
    import dataclasses as dc
    P = lb.design_plant(p)
    d = lb.drive(p)
    dyn = lb.cp.Dynamics(dc.replace(P, J_m=0.0, b_m=0.0, k_t=1e-12))
    A6, _ = dyn.lin(np.zeros(6))
    A6 = np.array(A6, float)
    M = np.array(dyn.M(np.zeros(6)), float)
    bF = np.concatenate([np.zeros(3), np.linalg.solve(M, [1.0, 0.0, 0.0])])
    f0 = np.array(dyn.f(np.zeros(6), 0.0, 0.0)).ravel()
    bT = np.array(dyn.f(np.zeros(6), 0.0, 1.0)).ravel() - f0
    k, c = p["k_belt"], p["d_belt"]
    A = np.zeros((8, 8))
    A[:6, :6] = A6
    A[:6, :] += np.outer(bF, np.r_[-k, 0, 0, -c, 0, 0, k, c])
    A[6, 7] = 1.0
    A[7, :] = np.r_[k, 0, 0, c, 0, 0, -k, -c - d["beta_m"]] / d["m_rot"]
    B = np.zeros((8, 1))
    B[7, 0] = d["alpha"] / d["m_rot"]
    Bf = np.zeros((8, 1))
    Bf[:6, 0] = bT
    C = np.zeros((3, 8))
    C[0, 6], C[1, 1], C[2, 2] = 1.0, 1.0, 1.0
    return A, B, Bf, C


def zoh(A, B, ts: float = TS):
    n, m = A.shape[0], B.shape[1]
    M = sla.expm(np.block([[A, B], [np.zeros((m, n + m))]]) * ts)
    return M[:n, :n], M[:n, n:]


@dataclasses.dataclass
class LTI:
    """Discrete state space x+ = A x + B u, y = C x + D u (sampling time TS)."""
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: np.ndarray

    @property
    def n(self):
        return self.A.shape[0]


@dataclasses.dataclass
class Truth:
    """The sampled truth: state s = [plant (6 or 8), lag uf, the commands u_{k-1} .. u_{k-d}], input the command
    u, disturbances w = [tip push (N), voltage disturbance at the drive (V)], measured y = [x, th1, th2]."""
    A: np.ndarray
    Bu: np.ndarray
    Bw: np.ndarray
    Cy: np.ndarray
    Cx: np.ndarray       # the plant's own 6 design states z (x, th1, th2, v, w1, w2) from s
    Cv: np.ndarray       # the voltage at the plant (the mean over the sample) as a row on [s; u]
    nx: int
    delay: int


def truth_dt(p: dict, belt: bool = False, delay: int | None = None, lag: bool = True) -> Truth:
    if belt:
        A, B, Bf, C = belt_cont(p)
    else:
        A, B, Bf = lin_cont(p)
        C = np.zeros((3, 6))
        C[0, 0], C[1, 1], C[2, 2] = 1.0, 1.0, 1.0
    nx = A.shape[0]
    Ad, BB = zoh(A, np.hstack([B, Bf]))
    Bd, Bfd = BB[:, :1], BB[:, 1:]
    d = int(p["delay"] if delay is None else delay)
    tau = p["L_m"] / p["R_m"] if lag else 0.0
    if tau > 0:
        ea = math.exp(-TS / tau)
        wa = 1.0 - tau / TS * (1.0 - ea)
    else:
        ea, wa = 0.0, 1.0
    n = nx + 1 + d
    # applied command a = u_{k-d}: a row on [s; u]
    a = np.zeros(n + 1)
    if d == 0:
        a[n] = 1.0
    else:
        a[nx + 1 + d - 1] = 1.0
    v = wa * a
    v[nx] += 1.0 - wa                    # mean voltage over the sample
    At = np.zeros((n, n))
    Bu = np.zeros((n, 1))
    At[:nx, :nx] = Ad
    At[:nx, :] += Bd @ v[None, :n]
    Bu[:nx, 0] += Bd[:, 0] * v[n]
    # lag state
    At[nx, :] += ea * np.eye(n)[nx] + (1 - ea) * a[:n]
    Bu[nx, 0] += (1 - ea) * a[n]
    # delay line
    if d >= 1:
        Bu[nx + 1, 0] = 1.0
        for j in range(1, d):
            At[nx + 1 + j, nx + j] = 1.0
    Bw = np.zeros((n, 2))
    Bw[:nx, 0] = Bfd[:, 0]
    Bw[:nx, 1] = Bd[:, 0]
    Cy = np.zeros((3, n))
    Cy[:, :nx] = C
    Cx = np.zeros((6, n))
    Cx[:, :6] = np.eye(6)
    return Truth(A=At, Bu=Bu, Bw=Bw, Cy=Cy, Cx=Cx, Cv=v, nx=nx, delay=d)


# ----------------------------------------------------------------------------- the controller structure
def ekf_gain(p_nom: dict = P_NOM, q_acc=None, r_meas=None) -> np.ndarray:
    """Steady-state gain L (6x3, on [x, th1, th2 - th1]) of the firmware EKF at the upright (lablib.setup:
    process noise q_acc as random accelerations, measurement noise from the encoder resolution and noise)."""
    A, B, _ = lin_cont(p_nom)
    Ad, _ = zoh(A, B)
    q_acc = tuple(q_acc or lb.EKF_Q)
    if r_meas is None:
        res_q = 2 * math.pi / 2 ** int(p_nom["joint_bits"])
        nq = math.radians(p_nom["joint_noise"])
        r_meas = [p_nom["base_res"] ** 2 / 12 + p_nom["base_noise"] ** 2] + [res_q**2 / 12 + nq**2] * 2
    qv = np.array([q_acc[0], q_acc[1], q_acc[1]]) * TS
    Q = np.diag(np.concatenate([(0.5 * qv * TS) ** 2, qv**2]))
    R = np.diag(r_meas)
    H = np.zeros((3, 6))
    H[:, :3] = T_REL
    Pm = sla.solve_discrete_are(Ad.T, H.T, Q, R)
    return Pm @ H.T @ np.linalg.inv(H @ Pm @ H.T + R)


@dataclasses.dataclass
class ObserverCtrl:
    """u_k = -K [x_hat_k; u_{k-1}; u_{k-2}] with the predictor-corrector observer
    x_hat_k = (I - L H)(Ad x_hat_{k-1} + Bd u_{k-1-d_obs}) + L y_rel_k  (y_rel = [x, th1, th2 - th1])."""
    K: np.ndarray            # (8,) or (6,)
    L: np.ndarray            # (6, 3)
    d_obs: int = 2
    p_nom: dict | None = None

    def k8(self):
        k = np.asarray(self.K, float).ravel()
        return np.concatenate([k, np.zeros(8 - len(k))])

    def model(self):
        A, B, _ = lin_cont(self.p_nom or P_NOM)
        return zoh(A, B)

    def lti(self) -> LTI:
        """Controller state xi = [x_hat_{k-1} (6), u_{k-1}, .., u_{k-m}], m = max(d_obs + 1, 2); input y = [x, th1, th2]."""
        Ad, Bd = self.model()
        H = np.zeros((3, 6))
        H[:, :3] = T_REL
        m = max(self.d_obs + 1, 2)
        n = 6 + m
        k = self.k8()
        IL = np.eye(6) - self.L @ H
        # x_hat_k = IL Ad x_hat + IL Bd u_{k-1-d} + L T y   (u_{k-1-d} = xi[6 + d])
        Xx = np.zeros((6, n))
        Xx[:, :6] = IL @ Ad
        Xx[:, 6 + self.d_obs] += IL @ Bd[:, 0]
        Xy = self.L @ T_REL
        # u = -k_x x_hat_k - k1 u_{k-1} - k2 u_{k-2}
        Uc = -k[:6] @ Xx
        Uc[6] -= k[6]
        Uc[7] -= k[7]
        Ud = -k[:6] @ Xy
        A = np.zeros((n, n))
        B = np.zeros((n, 3))
        A[:6] = Xx
        B[:6] = Xy
        A[6] = Uc
        B[6] = Ud
        for j in range(1, m):
            A[6 + j, 6 + j - 1] = 1.0
        return LTI(A=A, B=B, C=Uc[None, :], D=Ud[None, :])


def nominal_lqr() -> np.ndarray:
    import json
    return np.array(json.loads((lb.HERE / "design.json").read_text(encoding="utf-8"))["Klqr"], float)


# ----------------------------------------------------------------------------- closed loops
@dataclasses.dataclass
class CL:
    A: np.ndarray
    B: np.ndarray     # inputs [w (tip push, drive disturbance), n (3 measurement noise)]
    C: np.ndarray     # outputs [z (6 design states), u]
    D: np.ndarray


def closed_loop(T: Truth, K: LTI) -> CL:
    nt, nk = T.A.shape[0], K.n
    A = np.block([[T.A + T.Bu @ K.D @ T.Cy, T.Bu @ K.C], [K.B @ T.Cy, K.A]])
    B = np.block([[T.Bw, T.Bu @ K.D], [np.zeros((nk, 2)), K.B]])
    C = np.block([[T.Cx, np.zeros((6, nk))], [K.D @ T.Cy, K.C]])
    D = np.block([[np.zeros((6, 5))], [np.zeros((1, 2)), K.D]])
    return CL(A, B, C, D)


def rho(cl) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(cl.A))))


def h2(cl, Wz=None, Ww=None) -> float:
    """H2 norm (discrete) of Wz T Ww; inf if unstable."""
    if rho(cl) >= 1.0:
        return math.inf
    B = cl.B if Ww is None else cl.B @ Ww
    C = cl.C if Wz is None else Wz @ cl.C
    D = cl.D if Ww is None else cl.D @ Ww
    D = D if Wz is None else Wz @ D
    W = sla.solve_discrete_lyapunov(cl.A, B @ B.T)
    return float(math.sqrt(max(np.trace(C @ W @ C.T + D @ D.T), 0.0)))


def grid(n: int = 160, lo: float = 0.05) -> np.ndarray:
    return np.geomspace(lo, 0.999 * math.pi / TS, n)


def freqresp(A, B, C, D, w) -> np.ndarray:
    """(nw, ny, nu) frequency response at z = exp(j w TS)."""
    z = np.exp(1j * w * TS)
    n = A.shape[0]
    M = z[:, None, None] * np.eye(n)[None] - A[None]
    X = np.linalg.solve(M, np.broadcast_to(B, (len(w),) + B.shape))
    return C[None] @ X + D[None]


def hinf(cl, Wz=None, Ww=None, w=None) -> float:
    if rho(cl) >= 1.0:
        return math.inf
    w = grid() if w is None else w
    B = cl.B if Ww is None else cl.B @ Ww
    D = cl.D if Ww is None else cl.D @ Ww
    C = cl.C if Wz is None else Wz @ cl.C
    D = D if Wz is None else Wz @ D
    G = freqresp(cl.A, B, C, D, w)
    return float(np.max(np.linalg.norm(G, 2, axis=(1, 2))))


def loop_at_input(T: Truth, K: LTI, w=None) -> dict:
    """The loop broken at the command: L = -K G (negative-feedback convention). Disk margin (balanced, sigma
    = 0), gain margins, phase margin, delay margin (continuous equivalent, min over the crossovers) and the
    integer-sample delay margin."""
    w = grid(2000) if w is None else w
    G = freqresp(T.A, T.Bu, T.Cy, np.zeros((3, 1)), w)[:, :, 0]          # (nw, 3)
    Kf = freqresp(K.A, K.B, K.C, K.D, w)[:, 0, :]                        # (nw, 3)
    L = -np.sum(Kf * G, axis=1)
    S = 1.0 / (1.0 + L)
    alpha = 1.0 / float(np.max(np.abs(S - 0.5)))
    out = {"disk_alpha": alpha, "disk_gm": [(2 - alpha) / (2 + alpha) if alpha < 2 else 0.0,
                                            (2 + alpha) / (2 - alpha) if alpha < 2 else math.inf],
           "disk_pm_deg": math.degrees(2 * math.atan(alpha / 2)), "S_peak": float(np.max(np.abs(S)))}
    mag = np.abs(L)
    ph = np.angle(L)
    pm, dm, wc = [], [], []
    for i in np.where(np.diff(np.sign(mag - 1.0)) != 0)[0]:
        a = (1.0 - mag[i]) / (mag[i + 1] - mag[i])
        wi = w[i] + a * (w[i + 1] - w[i])
        phi = ph[i] + a * (np.angle(L[i + 1] / L[i]))
        m = math.degrees(math.remainder(phi - math.pi, 2 * math.pi))      # phase above -180
        pm.append(m)
        wc.append(wi)
        dm.append(math.radians(m) / wi if m > 0 else 0.0)
    gms = []
    for i in np.where(np.diff(np.sign(np.sin(ph))) != 0)[0]:
        if np.cos(ph[i]) < 0:            # crossing of the negative real axis
            gms.append(1.0 / mag[i])
    out |= {"pm_deg": min(pm, key=abs) if pm else None, "crossovers_rad_s": wc, "pms_deg": pm,
            "delay_margin_ms": 1000 * min(dm) if dm else None,
            "gm_low": max([g for g in gms if g < 1], default=None), "gm_high": min([g for g in gms if g > 1], default=None)}
    return out


def delay_margin_samples(p: dict, K: LTI, belt: bool = False, max_extra: int = 40) -> int:
    """Extra whole samples of delay (beyond p's) the loop tolerates (stays stable)."""
    d0 = int(p["delay"])
    for e in range(1, max_extra + 1):
        if rho(closed_loop(truth_dt(p, belt=belt, delay=d0 + e), K)) >= 1.0:
            return e - 1
    return max_extra


# ----------------------------------------------------------------------------- the parameter box
UNCERTAIN = [k for k, v in SPEC.items() if v["min"] != v["max"] and v["group"] in ("mass", "drive", "fbase", "fjoint", "cable")
             and k not in ("k_belt", "d_belt", "tc_joint1", "tc_joint2", "tc_carriage", "tc_motor", "eps_joint", "eps_base")]


def center() -> dict:
    """The box centre (delay at its nominal 2 samples)."""
    p = dict(P_NOM)
    for k in UNCERTAIN:
        p[k] = 0.5 * (SPEC[k]["min"] + SPEC[k]["max"])
    return p


def at(delta: dict, base: dict | None = None) -> dict:
    """The parameter set at normalised deviations delta[k] in [-1, 1] from the box centre."""
    p = dict(base or center())
    for k, d in delta.items():
        lo, hi = SPEC[k]["min"], SPEC[k]["max"]
        p[k] = 0.5 * (lo + hi) + 0.5 * d * (hi - lo)
    return p


def sensitivities(base: dict | None = None):
    """Per uncertain parameter: the half-range central difference of the sampled core [Ad Bd Bfd]."""
    base = base or center()
    out = {}
    for k in UNCERTAIN:
        mm = []
        for s in (-1.0, 1.0):
            A, B, Bf = lin_cont(at({k: s}, base))
            Ad, BB = zoh(A, np.hstack([B, Bf]))
            mm.append(np.hstack([Ad, BB[:, :1]]))
        out[k] = 0.5 * (mm[1] - mm[0])
    return out


@dataclasses.dataclass
class LFT:
    """The generalised plant of the box: x+ = A x + B1 p + B2 w + B3 u, q = C1 x + D11 p + D13 u,
    z = C2 x + D23 u, y = C3 x. Blocks: `blocks` = [(kind, size)], kind 'r' (repeated real scalar) or 'c'
    (complex scalar); then the performance channels w -> z."""
    A: np.ndarray
    B1: np.ndarray
    B2: np.ndarray
    B3: np.ndarray
    C1: np.ndarray
    D11: np.ndarray
    D13: np.ndarray
    C2: np.ndarray
    D23: np.ndarray
    C3: np.ndarray
    blocks: list
    names: list
    nw: int
    nz: int
    wn: np.ndarray


def build_lft(params: list[str] | None = None, wm=(1.1, 0.03), wz=None, ww=None, tol: float = 1e-3) -> LFT:
    """LFT of the parameter box around its centre: each uncertain parameter a real scalar delta in [-1, 1]
    (affine in the sampled core [Ad Bd Bfd], rank-reduced by SVD), the delay 1..2 samples, the armature lag and
    unmodelled dynamics as a complex multiplicative uncertainty at the drive, weight Wm(z) = wm[0] (1 - z^-1) +
    wm[1] (|1 - z^-1| = |z - 1| is the relative error of 1 sample less delay). Performance: w = Ww [tip push,
    drive disturbance, 3 noise], z = Wz [x, th1, th2, u]."""
    base = center()
    T = truth_dt(base, delay=2)
    nx, n = T.nx, T.A.shape[0]
    sens = sensitivities(base)
    params = params or list(sens)
    Ls, Rs, blocks, names = [], [], [], []
    for k in params:
        U, s, Vt = np.linalg.svd(sens[k])
        r = int(np.sum(s > tol * max(s[0], 1e-300))) if s[0] > 1e-12 else 0
        if r == 0:
            continue
        Ls.append(U[:, :r] * s[:r])
        Rs.append(Vt[:r])
        blocks.append(("r", r))
        names.append(k)
    # the multiplicative weight state m = v_{k-1} (the voltage at the plant one sample earlier)
    # augmented state [s (n), m]
    N = n + 1
    A = np.zeros((N, N))
    A[:n, :n] = T.A
    B3 = np.zeros((N, 1))
    B3[:n] = T.Bu
    v_s, v_u = T.Cv[:n], T.Cv[n]
    A[n, :n] = v_s
    B3[n, 0] = v_u
    # real parameter channels: q_i = R_i [x; v; f] with v the plant voltage; p_i enters x+ through L_i
    nr = sum(b[1] for b in blocks)
    np_ = nr + 1
    B1 = np.zeros((N, np_))
    C1 = np.zeros((np_, N))
    D11 = np.zeros((np_, np_))
    D13 = np.zeros((np_, 1))
    B2 = np.zeros((N, 5))
    B2[:n, :2] = T.Bw
    i = 0
    for Li, Ri in zip(Ls, Rs):
        r = Ri.shape[0]
        B1[:nx, i:i + r] = Li
        # [x; v; f]: x = s[:nx]; v = Cv [s; u] + p_c; f = w0 (the push, unweighted)
        C1[i:i + r, :nx] = Ri[:, :nx]
        C1[i:i + r, :n] += np.outer(Ri[:, nx], v_s)
        D13[i:i + r, 0] = Ri[:, nx] * v_u
        D11[i:i + r, nr] = Ri[:, nx]           # the complex perturbation adds to v
        i += r
    # complex channel: q_c = Wm v = wm0 (v - v_{k-1}) + wm1 v ; p_c adds to the plant voltage
    B1[:nx, nr] = truth_dt(base, delay=0, lag=False).Bw[:nx, 1]      # Bd (voltage at the plant)
    C1[nr, :n] = (wm[0] + wm[1]) * v_s
    C1[nr, n] = -wm[0]
    D13[nr, 0] = (wm[0] + wm[1]) * v_u
    blocks = blocks + [("c", 1)]
    names = names + ["drive (delay, lag, unmodelled)"]
    # performance: z = Wz [x, th1, th2, u], w = Ww [f, d, n1..3]
    wz = np.diag(wz if wz is not None else [1 / 0.3, 1 / math.radians(2.0), 1 / math.radians(2.0), 1 / 12.0])
    ww = np.diag(ww if ww is not None else [0.2, 0.3, 1e-5, 1e-3, 1e-3])
    C2 = np.zeros((4, N))
    C2[:3, :3] = np.eye(3)
    D23 = np.zeros((4, 1))
    D23[3, 0] = 1.0
    C2 = wz @ C2
    D23 = wz @ D23
    B2 = B2 @ ww
    C3 = np.zeros((3, N))
    C3[:, :n] = T.Cy
    # the noise enters y: handled in lft_close through B2's last three columns (y = C3 x + n)
    return LFT(A=A, B1=B1, B2=B2, B3=B3, C1=C1, D11=D11, D13=D13, C2=C2, D23=D23, C3=C3,
               blocks=blocks, names=names, nw=5, nz=4, wn=np.diag(ww)[2:5].copy())


def lft_matrices(G: LFT, K: LTI) -> LTI:
    """Closed loop [p, w] -> [q, z]; the noise adds to y (y = C3 x + diag(G.wn) w[2:5])."""
    wn = G.wn
    N, nk = G.A.shape[0], K.n
    npp = G.B1.shape[1]
    En = np.zeros((3, G.nw))
    En[:, 2:5] = np.diag(wn)
    B2 = G.B2.copy()
    B2[:, 2:5] = 0.0
    # u = Kc xi + Kd (C3 x + En w)
    A = np.block([[G.A + G.B3 @ K.D @ G.C3, G.B3 @ K.C], [K.B @ G.C3, K.A]])
    B = np.block([[G.B1, B2 + G.B3 @ K.D @ En], [np.zeros((nk, npp)), K.B @ En]])
    C = np.block([[G.C1 + G.D13 @ K.D @ G.C3, G.D13 @ K.C], [G.C2 + G.D23 @ K.D @ G.C3, G.D23 @ K.C]])
    D = np.block([[G.D11, G.D13 @ K.D @ En], [np.zeros((G.nz, npp)), G.D23 @ K.D @ En]])
    return LTI(A=A, B=B, C=C, D=D)


# ----------------------------------------------------------------------------- mu bounds
def _blocks_full(G: LFT, rp: bool):
    bl = list(G.blocks)
    if rp:
        bl.append(("p", (G.nw, G.nz)))
    return bl


def block_index(blocks) -> np.ndarray:
    """Block number of every row / column of a square M with the block structure `blocks`."""
    out = []
    for j, (kind, size) in enumerate(blocks):
        out += [j] * int(size)
    return np.array(out)


def mu_upper_complex(M: np.ndarray, blocks, x0=None, return_x: bool = False):
    """Complex-mu upper bound inf_D sigma(D M D^-1), D = diag(exp(x_j) I) per block (repeated real scalars
    treated as complex repeated scalars with a scalar scaling, a conservative bound): L-BFGS on log D with
    the exact gradient sigma (|u_j|^2 - |v_j|^2) of the largest singular triple."""
    from scipy.optimize import minimize
    bi = block_index(blocks)
    nb = len(blocks)
    if M.shape[0] != M.shape[1] or len(bi) != M.shape[0]:
        raise ValueError("square M with the block structure expected")

    def f(xr):
        x = np.concatenate([xr, [0.0]])
        d = np.exp(x[bi])
        Ms = (d[:, None] * M) / d[None, :]
        U, s, Vh = np.linalg.svd(Ms)
        u, v = np.abs(U[:, 0]) ** 2, np.abs(Vh[0]) ** 2
        g = s[0] * np.bincount(bi, weights=u - v, minlength=nb)
        return float(s[0]), g[:-1]

    if nb <= 1:
        val = f(np.zeros(0))[0]
        return (val, np.zeros(0)) if return_x else val
    x0 = np.zeros(nb - 1) if x0 is None else np.asarray(x0, float)
    r = minimize(f, x0, jac=True, method="L-BFGS-B", bounds=[(-25, 25)] * (nb - 1),
                 options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-9})
    f0 = f(x0)[0]
    val, x = (r.fun, r.x) if r.fun <= f0 else (f0, x0)
    return (float(val), x) if return_x else float(val)


def mu_upper_mixed(M: np.ndarray, blocks, hi: float | None = None, tol: float = 2e-3):
    """Mixed-mu upper bound (real repeated scalars with full D_i and G_i scalings, complex scalars with d,
    the performance block with d I): the smallest beta with an LMI M* D M + j (G M - M* G) - beta^2 D < 0,
    by bisection (cvxpy, Clarabel)."""
    import cvxpy as cp
    hi = hi or mu_upper_complex(M, blocks) * 1.001 + 1e-9
    lo = 0.0
    n_in = M.shape[1]
    # square M: blocks are square except the performance block (nw x nz): pad to square with zeros
    nout = M.shape[0]
    N = max(n_in, nout)
    if n_in != nout:
        raise ValueError("square M expected (pad the performance block)")
    Ds, Gs, parts = [], [], []
    i = 0
    for kind, size in blocks:
        if kind == "r":
            D = cp.Variable((size, size), hermitian=True)
            Gv = cp.Variable((size, size), hermitian=True)
            Ds.append(D)
            Gs.append(Gv)
            parts.append(("r", i, size, D, Gv))
            i += size
        else:
            s = size if kind == "c" else size[0]
            d = cp.Variable(nonneg=True)
            parts.append(("c", i, s, d, None))
            i += s

    def blk(which):
        mats = []
        for kind, i0, s, D, Gv in parts:
            if kind == "r":
                mats.append(D if which == "D" else Gv)
            else:
                mats.append(D * np.eye(s) if which == "D" else np.zeros((s, s)))
        return cp.bmat([[mats[a] if a == b else np.zeros((parts[a][2], parts[b][2])) for b in range(len(parts))]
                        for a in range(len(parts))])

    Dm, Gm = blk("D"), blk("G")
    Mh = M.conj().T
    beta2 = cp.Parameter(nonneg=True)
    lhs = Mh @ Dm @ M + 1j * (Gm @ M - Mh @ Gm) - beta2 * Dm
    lhs = 0.5 * (lhs + lhs.H)
    cons = [lhs << -1e-9 * np.eye(N), Dm >> 1e-6 * np.eye(N), cp.real(cp.trace(Dm)) == N]
    prob = cp.Problem(cp.Minimize(0), cons)

    def feasible(b):
        beta2.value = b * b
        try:
            prob.solve(solver="CLARABEL")
        except Exception:
            return False
        return prob.status in ("optimal", "optimal_inaccurate")

    if not feasible(hi):
        return hi
    while hi - lo > tol * max(hi, 1e-6):
        mid = 0.5 * (lo + hi)
        if feasible(mid):
            hi = mid
        else:
            lo = mid
    return hi


def pad_rp(Mw: np.ndarray, G: LFT) -> tuple[np.ndarray, list]:
    """The RP matrix with the performance block made square (max(nw, nz) with zero padding) and its blocks."""
    npp = Mw.shape[1] - G.nw
    nq = Mw.shape[0] - G.nz
    s = max(G.nw, G.nz)
    M = np.zeros((nq + s, npp + s), complex)
    M[:nq, :npp] = Mw[:nq, :npp]
    M[:nq, npp:npp + G.nw] = Mw[:nq, npp:]
    M[nq:nq + G.nz, :npp] = Mw[nq:, :npp]
    M[nq:nq + G.nz, npp:npp + G.nw] = Mw[nq:, npp:]
    return M, list(G.blocks) + [("c", s)]


def mu_analysis(G: LFT, K: LTI, w=None, mixed: bool = True, n_mixed: int = 40) -> dict:
    """Robust stability (the Delta blocks) and robust performance (plus a full complex performance block,
    here bounded with a scalar scaling) of the closed loop over the frequency grid: the complex-mu upper bound
    (real parameters treated as complex) at every frequency and the mixed-mu upper bound (D, G scalings) at
    `n_mixed` frequencies around the peaks. Also the nominal performance (the w -> z H-infinity norm)."""
    w = grid(120) if w is None else w
    Mcl = lft_matrices(G, K)
    if rho(Mcl) >= 1.0:
        return {"stable": False}
    F = freqresp(Mcl.A, Mcl.B, Mcl.C, Mcl.D, w)
    npp = G.B1.shape[1]
    nq = npp
    rs_c, rp_c, npf = [], [], []
    xs = xp = None
    for Fk in F:
        Mrs = Fk[:nq, :npp]
        v, xs = mu_upper_complex(Mrs, G.blocks, xs, return_x=True)
        rs_c.append(v)
        Mrp, brp = pad_rp(Fk, G)
        v, xp = mu_upper_complex(Mrp, brp, xp, return_x=True)
        rp_c.append(v)
        npf.append(float(np.linalg.norm(Fk[nq:, npp:], 2)))
    rs_c, rp_c = np.array(rs_c), np.array(rp_c)
    out = {"stable": True, "w": w.tolist(), "rs_complex": rs_c.tolist(), "rp_complex": rp_c.tolist(), "np": npf,
           "rs_complex_peak": float(rs_c.max()), "rs_complex_w": float(w[rs_c.argmax()]),
           "rp_complex_peak": float(rp_c.max()), "rp_complex_w": float(w[rp_c.argmax()]),
           "np_peak": float(max(npf))}
    if mixed:
        sel = sorted(set(np.argsort(-rs_c)[: n_mixed // 2].tolist() + np.argsort(-rp_c)[: n_mixed // 2].tolist()))
        rs_m, rp_m = {}, {}
        for k in sel:
            Fk = F[k]
            rs_m[k] = mu_upper_mixed(Fk[:nq, :npp], G.blocks, hi=rs_c[k] * 1.001 + 1e-9)
            Mrp, brp = pad_rp(Fk, G)
            rp_m[k] = mu_upper_mixed(Mrp, brp, hi=rp_c[k] * 1.001 + 1e-9)
        out["rs_mixed_peak"] = float(max(rs_m.values()))
        out["rs_mixed_w"] = float(w[max(rs_m, key=rs_m.get)])
        out["rp_mixed_peak"] = float(max(rp_m.values()))
        out["rp_mixed_w"] = float(w[max(rp_m, key=rp_m.get)])
        out["mixed_at"] = {str(round(float(w[k]), 4)): [round(rs_m[k], 4), round(rp_m[k], 4)] for k in sel}
    return out
