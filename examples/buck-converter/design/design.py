# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design of the `buck-converter` sample.

The plant is the averaged synchronous buck converter in continuous conduction

    L di/dt = Vin*d - v - R_L*i
    C dv/dt = i - v/R_load - i_load

with the switch modelled as an ideal, power-conserving transformer of modulus `d` (the
models use the bond-graph `MTF`): the switch-node voltage is `d*Vin` and the input current
`d*i`.  There is no diode, no discontinuous conduction, no capacitor ESR and no switch
on-resistance; the only loss is the inductor resistance `R_L`.  The controller is the
stdlib `PID` block plus the duty feed-forward `d_ff = Vref/Vin`:

    u = clamp(d_ff + pid, 0, 1),
    pid = clamp(Kp*e + (Kp/Ti)*xi + N*(e - xd), -1, 1),
    dxi/dt = e/Ti + (pid - v)/sqrt(Ti*Td),   dxd/dt = (e - xd)*N/Td,

with `e = Vref_f - v` and a 1 ms set-point filter `Vref_f`.  The block is not in textbook
form: its integral gain is `Kp/Ti^2` (so the script passes `Ti = sqrt(Kp/Ki)`), its
derivative path is `Td*s/(1 + s*Td/N)` (derivative gain `Td` itself, not `Kp*Td`), and its
high-frequency gain is `Kp + N`.

The script prints the loop margins, the averaged closed-loop reference, the switching
ripple and the steady-state power balance at the check window, and writes
`design/design.json`, which `design/build_model.py` puts into the two models.

Run it with ``uv run examples/buck-converter/design/design.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
OUT = HERE / "design.json"

#: Power stage.
VIN = 12.0          # V   nominal input
VIN_STEP = 15.0     # V   input after the line step
L = 470e-6          # H
C = 470e-6          # F
R_L = 0.1           # Ohm series resistance of the inductor
R_LOAD = 5.0        # Ohm nominal load (1 A at 5 V)
I_LOAD_STEP = 1.0   # A   extra load current after the step
F_SW = 20e3         # Hz  switching frequency
VREF = 5.0          # V
T_LOAD = 0.020      # s
T_LINE = 0.030      # s
T_END = 0.050       # s

#: Controller.  Kp = 0.2, Ki = 100 1/s, Td = 0.2 ms, derivative filter N = 5.
KP = 0.2
KI = 100.0
TD = 2.0e-4
N = 5.0
TAU_F = 1.0e-3
TI = float(np.sqrt(KP / KI))   # the PID block's Ti (its integral gain is Kp/Ti^2)


def plant_tf(vin: float = VIN, r: float = R_LOAD) -> signal.TransferFunction:
    """Control-to-output voltage of the averaged buck at the nominal operating point.

    With the inductor resistance the DC gain is `Vin/(1 + R_L/r)`, not `Vin`.
    """
    return signal.TransferFunction([vin], [L * C, L / r + R_L * C, 1.0 + R_L / r])


def pid_tf(kp: float = KP, td: float = TD, n: float = N) -> signal.TransferFunction:
    """The PID block's transfer function, including the derivative filter.

    `C(s) = Kp + (Kp/Ti^2)/s + Td*s/(1 + s*Td/N)` with the model's fixed `Ti`, so the
    integral gain scales with `kp` exactly as it does when `PID1.Kp` is changed in the model.
    """
    ki = kp / TI**2
    num = [kp + n, kp * n / td + ki, ki * n / td]
    den = [1.0, n / td, 0.0]
    return signal.TransferFunction(num, den)


def margins(kp: float = KP, td: float = TD, n: float = N,
            vin: float = VIN, r: float = R_LOAD) -> tuple[float, float]:
    """Last unity-gain crossover [Hz] and its phase margin [deg]."""
    controller = pid_tf(kp, td, n)
    plant = plant_tf(vin, r)
    num = np.polymul(controller.num, plant.num)
    den = np.polymul(controller.den, plant.den)
    w = np.logspace(-1.0, 6.0, 200_000)
    _, h = signal.freqs(num, den, w)
    mag = np.abs(h)
    phase = np.unwrap(np.angle(h)) * 180.0 / np.pi
    crossings = np.where(np.diff(np.sign(mag - 1.0)))[0]
    if crossings.size == 0:
        raise SystemExit("the loop never crosses unity gain")
    i = crossings[-1]
    log_mag = np.log(mag[i : i + 2])
    log_w = np.log(w[i : i + 2])
    wc = np.exp(np.interp(0.0, log_mag[::-1], log_w[::-1]))
    return float(wc / (2.0 * np.pi)), float(180.0 + np.interp(wc, w, phase))


def steady_state(vin: float, i_out: float, ripple: bool) -> dict[str, float]:
    """Steady state of the synchronous buck at `Vref`, input `vin`, load current `i_out`.

    The averaged law gives `d*vin = Vref + R_L*i_out`; the switched inductor current is a
    triangle of `dI = vin*d*(1 - d)/(L*f_sw)` around `i_out`, the output ripple is
    `dI/(8*f_sw*C)` (no ESR), and the inductor loss is `R_L*(i_out^2 + dI^2/12)`.
    """
    d = (VREF + R_L * i_out) / vin
    d_i = vin * d * (1.0 - d) / (L * F_SW)
    d_v = d_i / (8.0 * F_SW * C)
    p_out = VREF * i_out
    p_rl = R_L * (i_out**2 + (d_i**2 / 12.0 if ripple else 0.0))
    p_in = p_out + p_rl
    return {
        "duty": d, "ripple_i_pp": d_i, "ripple_v_pp": d_v,
        "i_in": p_in / vin, "p_in": p_in, "p_out": p_out, "p_rl": p_rl,
        "efficiency": p_out / p_in,
    }


def simulate() -> dict[str, float]:
    """The averaged closed loop with the PID, feed-forward, limits and both steps."""

    def vin(t: float) -> float:
        return VIN_STEP if t >= T_LINE else VIN

    def iload(t: float) -> float:
        return I_LOAD_STEP if t >= T_LOAD else 0.0

    def rhs(t: float, x: np.ndarray) -> list[float]:
        i, v, xi, xd, vf = x
        e = vf - v
        pid = KP * e + (KP / TI) * xi + N * (e - xd)
        pid = float(np.clip(pid, -1.0, 1.0))
        duty = float(np.clip(vf / vin(t) + pid, 0.0, 1.0))
        return [
            (vin(t) * duty - v - R_L * i) / L,
            (i - v / R_LOAD - iload(t)) / C,
            e / TI + (pid - (KP * e + (KP / TI) * xi + N * (e - xd))) / np.sqrt(TI * TD),
            (e - xd) * N / TD,
            (VREF - vf) / TAU_F,
        ]

    sol = solve_ivp(
        rhs, [0.0, T_END], [0.0, 0.0, 0.0, 0.0, 0.0],
        max_step=2e-6, rtol=1e-9, atol=1e-11, dense_output=True,
    )
    t = np.linspace(0.0, T_END, 100_001)
    i, v, xi, xd, vf = sol.sol(t)
    e = vf - v
    pid = np.clip(KP * e + (KP / TI) * xi + N * (e - xd), -1.0, 1.0)
    duty = np.clip(vf / np.where(t >= T_LINE, VIN_STEP, VIN) + pid, 0.0, 1.0)

    pre = (t >= 0.015) & (t <= 0.0195)
    load = (t >= T_LOAD) & (t <= 0.028)
    line = (t >= T_LINE) & (t <= 0.040)
    post = t >= 0.040
    below = np.where(v >= 0.99 * VREF)[0]
    rise = float(t[below[0]]) if below.size else float("nan")
    # 2 % settling after the load step, ignoring the line step that follows
    settle_after_load = None
    idx = np.where((t >= T_LOAD) & (t <= T_LINE))[0]
    for j in idx:
        if np.all(np.abs(v[j:][t[j:] <= T_LINE] - VREF) < 0.02 * VREF):
            settle_after_load = float(t[j] - T_LOAD)
            break
    load_peak = int(np.argmax(np.where(load, i, -np.inf)))
    vin_t = np.where(t >= T_LINE, VIN_STEP, VIN)
    p_in = vin_t * duty * i
    p_out = v * (v / R_LOAD + np.where(t >= T_LOAD, I_LOAD_STEP, 0.0))

    def window_mean(y: np.ndarray) -> float:
        return float(np.trapezoid(y[post], t[post]) / (T_END - 0.040))

    return {
        "final_v": float(v[-1]),
        "final_i": float(i[-1]),
        "final_duty": float(duty[-1]),
        "final_iin": float(duty[-1] * i[-1]),
        "final_pin": float(p_in[-1]),
        "final_pout": float(p_out[-1]),
        "final_efficiency": float(p_out[-1] / p_in[-1]),
        "mean_v_40_50": window_mean(v),
        "mean_i_40_50": window_mean(i),
        "mean_pin_40_50": window_mean(p_in),
        "mean_pout_40_50": window_mean(p_out),
        "peak_v": float(v.max()),
        "pre_load_v": float(np.interp(0.015, t, v)),
        "pre_load_error": float(np.abs(v[pre] - VREF).max()),
        "load_min_v": float(v[load].min()),
        "load_max_v": float(v[load].max()),
        "load_max_i": float(i[load_peak]),
        "load_max_i_t": float(t[load_peak]),
        "line_min_v": float(v[line].min()),
        "line_max_v": float(v[line].max()),
        "post_line_error": float(np.abs(v[post] - VREF).max()),
        "rise_time": rise,
        "settle_after_load": settle_after_load,
        "max_i": float(i.max()),
        "max_i_t": float(t[int(np.argmax(i))]),
        "max_duty": float(duty.max()),
        "max_duty_t": float(t[int(np.argmax(duty))]),
        "startup_max_duty": float(duty[t <= 0.002].max()),
        "min_duty": float(duty.min()),
    }


def main() -> None:
    wc, pm = margins()
    sim = simulate()
    w0 = 1.0 / np.sqrt(L * C)
    lc = {
        "f0_hz": float(w0 / (2.0 * np.pi)),
        "q_without_rl": float(R_LOAD * np.sqrt(C / L)),
        "q_with_rl": float(np.sqrt(L * C * (1.0 + R_L / R_LOAD)) / (L / R_LOAD + R_L * C)),
    }
    sensitivity = {}
    for label, kwargs in (("nominal", {}), ("Kp 0.4", {"kp": 0.4}), ("Kp 0.05", {"kp": 0.05}),
                          ("Td 0.1 ms", {"td": 1e-4}), ("Td 0.4 ms", {"td": 4e-4}),
                          ("N 2.5", {"n": 2.5}), ("N 10", {"n": 10.0})):
        f, m = margins(**kwargs)
        sensitivity[label] = {"crossover_hz": f, "phase_margin_deg": m}
    window = {
        "averaged": steady_state(VIN_STEP, VREF / R_LOAD + I_LOAD_STEP, ripple=False),
        "switched": steady_state(VIN_STEP, VREF / R_LOAD + I_LOAD_STEP, ripple=True),
    }
    data = {
        "description": "Averaged buck converter with a PID voltage-mode compensator and duty feed-forward.",
        "plant": {
            "Vin": VIN, "Vin_step": VIN_STEP, "L": L, "C": C, "R_L": R_L,
            "R_load": R_LOAD, "I_load_step": I_LOAD_STEP,
            "f_sw": F_SW, "Vref": VREF, "t_load": T_LOAD, "t_line": T_LINE, "t_end": T_END,
        },
        "lc": lc,
        "controller": {
            "Kp": KP, "Ki": KI, "Ti": TI, "Td": TD, "N": N, "tau_filter": TAU_F,
            "derivative_filter_hz": float(N / TD / (2.0 * np.pi)),
            "high_frequency_gain": KP + N,
            "crossover_hz": wc, "phase_margin_deg": pm,
            "sensitivity": sensitivity,
        },
        "reference": sim,
        "steady_state_15V_2A": window,
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"plant: Vin {VIN}->{VIN_STEP} V, L {L * 1e6:.0f} uH, C {C * 1e6:.0f} uF, "
          f"R_L {R_L} Ohm, load {R_LOAD} Ohm + {I_LOAD_STEP} A step, f_sw {F_SW / 1e3:.0f} kHz")
    print(f"LC corner {lc['f0_hz']:.1f} Hz, Q {lc['q_without_rl']:.2f} without R_L, "
          f"{lc['q_with_rl']:.2f} with R_L")
    print(f"controller: Kp {KP}, Ki {KI}, Td {TD * 1e6:.0f} us, N {N}, Ti {TI:.8f} s, "
          f"derivative filter {N / TD / (2 * np.pi):.0f} Hz, HF gain {KP + N}")
    print(f"loop: crossover {wc:.1f} Hz, phase margin {pm:.1f} deg")
    for label, value in sensitivity.items():
        print(f"  {label:10s} crossover {value['crossover_hz']:7.1f} Hz, "
              f"phase margin {value['phase_margin_deg']:5.1f} deg")
    print("averaged reference:")
    for key, value in sim.items():
        print(f"  {key:20s} {value:.9g}")
    for kind, values in window.items():
        print(f"steady state at 15 V, 2 A ({kind}): " +
              ", ".join(f"{k} {v:.6g}" for k, v in values.items()))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
