# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Reference calculations of the `van-der-pol` example (independent of bgsim).

    uv run examples/van-der-pol/design/design.py

Writes `design/design.json`: every number the models, the checks, the README and the docs use.
Then `uv run examples/van-der-pol/design/build_model.py` writes the models and `expected.json`.

1. The textbook equation  x'' - mu (1 - x^2) x' + x = 0  (' = d/dtau):
   the limit cycle by shooting on the section x = 0, x' > 0 (period, amplitude, peak x'), the
   averaging-theory amplitude 2, the small-mu period 2 pi (1 + mu^2/16) and the relaxation period
   (3 - 2 ln 2) mu + 3 a mu^(-1/3) (a = 2.33811, the first zero of Ai(-z)), and the runs from
   (x, x') = (0.5, 0) that the bgsim model repeats.
2. The tunnel-diode oscillator: a parallel LC tank on a tunnel diode biased in its negative-
   resistance region, i_D = -a v + b v^3 about the bias point. C v' = -i_L + a v - b v^3 and
   L i_L' = v map onto the textbook form with
       w0 = 1/sqrt(L C),  mu = a sqrt(L/C),  x = v/A,  A = sqrt(a/(3 b)),  tau = w0 t.
   Integrated here in SI units (not in the scaled form), then scaled and compared.
3. The belt-driven oscillator: a mass on a spring rides a belt at v_b; the friction force of the
   belt on the mass is F(w), w = v_b - x' the slip. Expanding F about v_b (an inflection point of
   the curve) to third order gives Rayleigh's equation m x'' - alpha x' + beta x'^3 + k (x - x_s) = 0;
   its derivative is Van der Pol in the velocity:
       w0 = sqrt(k/m),  mu = alpha/sqrt(k m),  x_vdp = x'/V,  V = sqrt(alpha/(3 beta)).
   Integrated in SI units with the cubic fit and with the full Stribeck curve.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.special import ai_zeros

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- textbook
MUS = [0.1, 1.0, 5.0, 20.0]
X0, Y0 = 0.5, 0.0          # start of every run, in textbook units
TAU_END = 200.0            # length of the textbook runs (and of the scaled physical runs)
AIRY = float(-ai_zeros(1)[0][0])   # 2.338107410459767

# --------------------------------------------------------------------------- tunnel diode
# A germanium tunnel diode of the 4.7 mA class (illustrative, rounded values): peak 4.7 mA at
# 65 mV, valley 0.6 mA at 355 mV. The cubic i(v) = I0 - a u + b u^3 (u = v - V0) has its maximum
# at the peak and its minimum at the valley when V0 is the midpoint, A = (V_v - V_p)/2 and
# I_p - I_v = (4/3) a A.
I_P, V_P = 4.7e-3, 0.065
I_V, V_V = 0.6e-3, 0.355
F0_E = 10.0e6              # Hz, tank resonance 1/(2 pi sqrt(L C))
MU_E = 1.0                 # default mu of the circuit (the dashboard slider)
MU_E_EXTRA = [0.2, 5.0]    # two more dashboard settings, checked as override runs
T_END_E = 32.0 / F0_E      # 32 tank periods = 64 pi in tau

# --------------------------------------------------------------------------- belt
M_M = 1.0                  # kg
K_M = 100.0                # N/m
G0 = 9.81
F_N = 40.0                 # N, normal force (the block's weight and a spring-loaded pressure pad)
MU_C = 0.30                # Coulomb (kinetic) friction coefficient
MU_S = 0.45                # static friction coefficient
V_S = 0.10                 # m/s, Stribeck velocity of the Gaussian curve exp(-(w/v_s)^2)
MU_M = 0.5                 # mu of the belt oscillator; sets the viscous coefficient sigma
V_EPS = 1.0e-3             # m/s, regularisation of sign(w) in the Stribeck block (never active)
T_END_M = 40.0             # s, 400 rad of tau at w0 = 10 rad/s


def vdp_rhs(_t, s, mu):
    x, y = s
    return [y, mu * (1.0 - x * x) * y - x]


def solve(rhs, span, s0, args=(), method="DOP853", **kw):
    kw.setdefault("rtol", 1e-12)
    kw.setdefault("atol", 1e-12)
    return solve_ivp(rhs, span, s0, method=method, args=args, dense_output=True, **kw)


def method_for(mu: float) -> str:
    return "Radau" if mu >= 5.0 else "DOP853"


def up_cross(_t, s, *_):
    return s[0]


up_cross.direction = 1.0


def peak(_t, s, *_):
    return s[1]


peak.direction = -1.0


def limit_cycle(mu: float) -> dict:
    """Shooting on x = 0, x' > 0: iterate the return map to its fixed point."""
    m = method_for(mu)
    y = 2.0
    t_max = 1.5 * max(t_small(mu), t_relax(mu))
    period = 0.0
    for _ in range(400):
        sol = solve_ivp(vdp_rhs, (0.0, t_max), [0.0, y], method=m, args=(mu,), rtol=1e-13, atol=1e-13,
                        events=[up_cross])
        # skip the start itself (x = 0): the first crossing after t = 0 closes the cycle
        k = next(i for i, t in enumerate(sol.t_events[0]) if t > 1e-6)
        period = float(sol.t_events[0][k])
        y_new = float(sol.y_events[0][k][1])
        done = abs(y_new - y) < 1e-12 * max(1.0, abs(y))
        y = y_new
        if done:
            break
    sol = solve(vdp_rhs, (0.0, period), [0.0, y], args=(mu,), method=m, rtol=1e-13, atol=1e-13,
                events=[peak])
    amp = float(sol.y_events[0][0][0])
    tt = np.linspace(0.0, period, 400001)
    xx, yy = sol.sol(tt)
    g = xx * xx - xx ** 4 / 3.0
    i_sup = float(np.trapezoid(np.maximum(g, 0.0), tt))
    i_abs = float(np.trapezoid(np.maximum(-g, 0.0), tt))
    return {"mu": mu, "period": period, "amplitude": amp, "y_peak": float(np.max(yy)), "y_section": y,
            # integrals over one cycle of the scaled diode/contact power shape x^2 - x^4/3 (tau units)
            "I_sup": i_sup, "I_abs": i_abs, "I_net": float(np.trapezoid(g, tt))}


def t_small(mu: float) -> float:
    return 2.0 * math.pi * (1.0 + mu * mu / 16.0)


def t_relax(mu: float) -> float:
    return (3.0 - 2.0 * math.log(2.0)) * mu + 3.0 * AIRY * mu ** (-1.0 / 3.0)


def crossings(sol_t_events) -> list[float]:
    return [float(t) for t in sol_t_events if t > 1e-12]


def run_textbook(mu: float) -> dict:
    sol = solve(vdp_rhs, (0.0, TAU_END), [X0, Y0], args=(mu,), method=method_for(mu), rtol=1e-12,
                atol=1e-13, events=[up_cross, peak])
    ups = crossings(sol.t_events[0])
    peaks = [float(s[0]) for s in sol.y_events[1]]
    x_end, y_end = sol.sol(TAU_END)
    n = len(ups) - 1           # the last full cycle: up-crossings n and n + 1 (1-based)
    return {"mu": mu, "up": ups, "n_last": n, "period_last": ups[-1] - ups[-2],
            "amp_last": peaks[-1], "x_end": float(x_end), "y_end": float(y_end),
            "max_abs_x_late": float(np.max(np.abs(sol.sol(np.linspace(TAU_END / 2, TAU_END, 200001))[0])))}


# --------------------------------------------------------------------------- circuit


def circuit(mu: float) -> dict:
    v0_bias = 0.5 * (V_P + V_V)
    i0_bias = 0.5 * (I_P + I_V)
    amp_scale = 0.5 * (V_V - V_P)
    a = 3.0 * (I_P - I_V) / (4.0 * amp_scale)
    b = a / (3.0 * amp_scale ** 2)
    w0 = 2.0 * math.pi * F0_E
    z0 = mu / a                       # tank characteristic impedance sqrt(L/C)
    L = z0 / w0
    C = 1.0 / (z0 * w0)
    v0 = amp_scale * X0
    il0 = a * v0 - b * v0 ** 3        # the start current that makes i_C(0) = 0, so x'(0) = 0

    def rhs(_t, s):
        v, il = s
        return [(-il + a * v - b * v ** 3) / C, v / L]

    def ev_up(_t, s):
        return s[0]

    ev_up.direction = 1.0

    def ev_peak(_t, s):
        v, il = s
        return -il + a * v - b * v ** 3   # i_C = C dv/dt

    ev_peak.direction = -1.0
    sol = solve_ivp(rhs, (0.0, T_END_E), [v0, il0], method=method_for(mu), dense_output=True,
                    rtol=1e-12, atol=[1e-15, 1e-17], events=[ev_up, ev_peak])
    ups = crossings(sol.t_events[0])
    peaks = [float(s[0]) for s in sol.y_events[1]]
    period = ups[-1] - ups[-2]
    # scaled comparison against the textbook run in tau = w0 t
    ref = solve(vdp_rhs, (0.0, w0 * T_END_E), [X0, Y0], args=(mu,), method=method_for(mu), rtol=1e-12,
                atol=1e-13)
    tt = np.linspace(0.0, T_END_E, 20001)
    v, il = sol.sol(tt)
    x_phys = v / amp_scale
    y_phys = (-il + a * v - b * v ** 3) / (w0 * C * amp_scale)
    xr, yr = ref.sol(w0 * tt)
    lc = limit_cycle(mu)
    e_scale = mu * C * amp_scale ** 2   # a A^2 / w0
    return {
        "mu": mu, "V_bias": v0_bias, "I_bias": i0_bias, "A": amp_scale, "a": a, "b": b, "w0": w0,
        "f0": F0_E, "Z0": z0, "L": L, "C": C, "R_neg": -1.0 / a, "v0": v0, "iL0": il0, "t_end": T_END_E,
        "up": ups, "n_last": len(ups) - 1, "period": period, "freq": 1.0 / period,
        "period_cycle": lc["period"] / w0, "freq_cycle": w0 / lc["period"],
        "v_amp": peaks[-1], "v_amp_cycle": lc["amplitude"] * amp_scale,
        "v_end": float(sol.sol(T_END_E)[0]),
        "scaled_vs_textbook_x": float(np.max(np.abs(x_phys - xr))),
        "scaled_vs_textbook_y": float(np.max(np.abs(y_phys - yr))),
        "E_sup_cycle": e_scale * lc["I_sup"], "E_abs_cycle": e_scale * lc["I_abs"],
        "E_net_cycle": e_scale * lc["I_net"],
        "E_tank0": 0.5 * C * v0 ** 2 + 0.5 * L * il0 ** 2,
        "i_D_peak": float(np.max(np.abs(-a * v + b * v ** 3))),
    }


# --------------------------------------------------------------------------- belt


def belt() -> dict:
    s_i = 1.0 / math.sqrt(2.0)              # inflection of exp(-s^2)
    v_b = V_S * s_i
    dmu = MU_S - MU_C
    e = math.exp(-0.5)
    alpha_f = F_N * dmu * math.sqrt(2.0) * e / V_S          # -dF/dw of the Gaussian part at v_b
    beta = F_N * dmu * 4.0 * math.sqrt(2.0) * e / (6.0 * V_S ** 3)   # F'''(v_b)/6
    w0 = math.sqrt(K_M / M_M)
    alpha = MU_M * math.sqrt(K_M * M_M)                   # net falling slope of the curve at v_b
    sigma = alpha_f - alpha                               # viscous friction coefficient
    F0 = F_N * (MU_C + dmu * e) + sigma * v_b
    x_s = F0 / K_M
    V = math.sqrt(alpha / (3.0 * beta))
    xd0 = V * X0

    def f_cubic(w):
        d = w - v_b
        return F0 - alpha * d + beta * d ** 3

    def f_stribeck(w):
        return F_N * (MU_C + dmu * np.exp(-(w / V_S) ** 2)) * np.tanh(w / V_EPS) + sigma * w

    out = {"m": M_M, "k": K_M, "F_n": F_N, "mu_c": MU_C, "mu_s": MU_S, "v_s": V_S, "v_eps": V_EPS,
           "mu": MU_M, "v_b": v_b, "alpha_f": alpha_f, "alpha": alpha, "sigma": sigma, "beta": beta,
           "F0": F0, "x_s": x_s, "w0": w0, "f0": w0 / (2 * math.pi), "V": V, "xd0": xd0, "t_end": T_END_M,
           "zeta_passive": sigma / (2.0 * math.sqrt(K_M * M_M)),
           "F_static": F_N * MU_S, "F_at_vb_stribeck": float(f_stribeck(v_b))}
    lc = limit_cycle(MU_M)
    for name, law in (("cubic", f_cubic), ("stribeck", f_stribeck)):
        def rhs(_t, s, law=law):
            x, xd = s
            return [xd, (law(v_b - xd) - K_M * x) / M_M]

        def ev_up(_t, s):
            return s[1]

        ev_up.direction = 1.0

        def ev_peak(_t, s, law=law):
            x, xd = s
            return law(v_b - xd) - K_M * x

        ev_peak.direction = -1.0
        sol = solve_ivp(rhs, (0.0, T_END_M), [x_s, xd0], method="DOP853", dense_output=True, rtol=1e-12,
                        atol=1e-14, events=[ev_up, ev_peak])
        ups = crossings(sol.t_events[0])
        peaks = [float(s[1]) for s in sol.y_events[1]]
        tt = np.linspace(T_END_M / 2, T_END_M, 200001)
        x, xd = sol.sol(tt)
        r = {"up": ups, "n_last": len(ups) - 1, "period": ups[-1] - ups[-2], "xd_amp": peaks[-1],
             "x_max": float(np.max(x)), "x_min": float(np.min(x)), "x_mean": float(0.5 * (np.max(x) + np.min(x))),
             "slip_min": float(np.min(v_b - xd)), "xd_end": float(sol.sol(T_END_M)[1])}
        if name == "cubic":
            ref = solve(vdp_rhs, (0.0, w0 * T_END_M), [X0, MU_M * (X0 - X0 ** 3 / 3.0)], args=(MU_M,))
            t2 = np.linspace(0.0, T_END_M, 20001)
            x2, xd2 = sol.sol(t2)
            xr, yr = ref.sol(w0 * t2)
            r["scaled_vs_textbook_x"] = float(np.max(np.abs(xd2 / V - xr)))
            ydd = (f_cubic(v_b - xd2) - K_M * x2) / M_M
            r["scaled_vs_textbook_y"] = float(np.max(np.abs(ydd / (w0 * V) - yr)))
        out[name] = r
    e_scale = MU_M * M_M * V ** 2       # alpha V^2 / w0
    out["period_cycle"] = lc["period"] / w0
    out["xd_amp_cycle"] = lc["amplitude"] * V
    out["E_sup_cycle"] = e_scale * lc["I_sup"]
    out["E_abs_cycle"] = e_scale * lc["I_abs"]
    out["x_amp_estimate"] = 2.0 * V / w0
    return out


def main() -> None:
    cycles = {f"{mu:g}": limit_cycle(mu) for mu in MUS + [MU_E] + MU_E_EXTRA + [MU_M]}
    textbook = {}
    for mu in MUS:
        c = cycles[f"{mu:g}"]
        r = run_textbook(mu)
        r.pop("up")
        textbook[f"{mu:g}"] = {**r, "cycle": c, "T_small": t_small(mu), "T_relax": t_relax(mu),
                               "err_small": t_small(mu) / c["period"] - 1.0,
                               "err_relax": t_relax(mu) / c["period"] - 1.0}
    circ = {f"{mu:g}": circuit(mu) for mu in [MU_E] + MU_E_EXTRA}
    for c in circ.values():
        c.pop("up")
    bl = belt()
    for k in ("cubic", "stribeck"):
        bl[k].pop("up")
    design = {
        "x0": X0, "y0": Y0, "tau_end": TAU_END, "airy": AIRY,
        "textbook": textbook, "cycles": cycles, "circuit": circ, "circuit_default": f"{MU_E:g}",
        "diode": {"I_p": I_P, "V_p": V_P, "I_v": I_V, "V_v": V_V},
        "belt": bl,
    }
    (HERE / "design.json").write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8", newline="\n")

    print("limit cycles (textbook units)")
    print(f"{'mu':>6} {'T':>12} {'2pi(1+mu^2/16)':>15} {'relax':>10} {'amp':>10} {'peak xd':>9}")
    for k, c in cycles.items():
        print(f"{c['mu']:6g} {c['period']:12.8f} {t_small(c['mu']):15.6f} {t_relax(c['mu']):10.4f} "
              f"{c['amplitude']:10.7f} {c['y_peak']:9.4f}  I_net {c['I_net']:.2e}")
    for k, c in circ.items():
        print(f"circuit mu={k}: L={c['L'] * 1e9:.2f} nH C={c['C'] * 1e12:.2f} pF a={c['a'] * 1e3:.4f} mS "
              f"b={c['b']:.5f} A/V^3 A={c['A'] * 1e3:.1f} mV  f={c['freq'] / 1e6:.6f} MHz "
              f"v_amp={c['v_amp'] * 1e3:.4f} mV  scaled-vs-textbook {c['scaled_vs_textbook_x']:.2e} "
              f"{c['scaled_vs_textbook_y']:.2e}  E_sup/cycle {c['E_sup_cycle']:.4e} J")
    print(f"belt: v_b={bl['v_b']:.5f} alpha_f={bl['alpha_f']:.4f} sigma={bl['sigma']:.4f} beta={bl['beta']:.3f} "
          f"F0={bl['F0']:.4f} x_s={bl['x_s']:.5f} V={bl['V']:.5f} zeta_passive={bl['zeta_passive']:.3f}")
    for k in ("cubic", "stribeck"):
        r = bl[k]
        print(f"  {k}: T={r['period']:.8f} s xd_amp={r['xd_amp']:.6f} slip_min={r['slip_min']:.5f} "
              f"x in [{r['x_min']:.5f}, {r['x_max']:.5f}]"
              + (f" scaled-vs-textbook {r['scaled_vs_textbook_x']:.2e} {r['scaled_vs_textbook_y']:.2e}"
                 if k == "cubic" else ""))
    print(f"  cycle: T={bl['period_cycle']:.8f} xd_amp={bl['xd_amp_cycle']:.6f}")


if __name__ == "__main__":
    main()
