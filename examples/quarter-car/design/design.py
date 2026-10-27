# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Reference integration for the `quarter-car` sample (plan 9.4).

The plant in ``models/quarter-car.bgmodel.json`` is a two-degree-of-freedom bond graph:

* sprung mass ``ms`` on the 1-junction ``SJ`` (``IMs``, an ``I`` element);
* unsprung mass ``mu`` on the 1-junction ``UJ`` (``IMu``);
* suspension ``ks`` in parallel with ``cs`` (``SpringDamper``) between the two junctions;
* a hard stop at +/-0.08 m of travel (``HardStop``), same two junctions;
* a one-sided tire ``kt`` (``OneSidedSpring``, ``F = ifelse(x > 0, kt*x, 0)``) between the
  road 1-junction ``RJ`` and ``UJ``;
* gravity as the two ``MSe`` preloads (``ms*g`` and ``mu*g``) plus the static spring
  compression starts, so t = 0 is the static equilibrium;
* the road as a ``VelocitySource`` driven by the stdlib ``TimeTable``: a 0.1 s hold table
  from t = 0.4 s with +0.5 m/s for 0.1 s at t = 0.5 s and -0.5 m/s for 0.1 s at
  t = 1.5 s, i.e. a 5 cm plateau bump.

Written in absolute vertical coordinates (up positive) with the static equilibrium at
z = 0, the equations this script integrates are

    qs = qs0 + (zu - zs)                         suspension compression from free length
    Fs = ks*qs + cs*(vu - vs)                    suspension force (up on the body)
    Fh = hard-stop contact force from (zu - zs)  (0 inside +/-0.08 m of travel)
    xt = qt0 + (zr - zu)                         tire compression from free length
    Ft = kt*xt if xt > 0 else 0                  one-sided tire force (up on the wheel)
    ms*as = -ms*g + Fs + Fh
    mu*au = -mu*g - Fs - Fh + Ft

with ``qs0 = ms*g/ks`` and ``qt0 = (ms + mu)*g/kt``.  A fourth state integrates the road
velocity to ``zr``; the bond graph reconstructs zs, zu and zr with FlowSensors and
Integrators (the D28 sensor exception), so the recorded positions are these states.

The script prints the values ``expected.json`` checks: the static equilibrium, the peak
sprung/unsprung displacement and suspension travel, the tire-force bounds, the body-mode
and wheel-hop periods from zero crossings, the dominant frequencies from an FFT of the
free decay / ring-down (the same windows as the runner's ``fft_peak`` checks), and the
cursor values.  It also prints the undamped modal frequencies from the linearised system
for comparison with plan 9.4's 1.24 Hz and 11.8 Hz.

Run it with ``uv run examples/quarter-car/design/design.py``.
"""

from __future__ import annotations

import math

import numpy as np

#: Plant parameters, identical to the model document.
MS = 300.0         # kg      sprung mass
MU = 40.0          # kg      unsprung mass
KS = 20_000.0      # N/m     suspension stiffness
CS = 1_500.0       # N*s/m   suspension damping
KT = 200_000.0     # N/m     tire stiffness
G = 9.81           # m/s^2
KH = 1.0e6         # N/m     hard-stop contact stiffness
DH = 2_000.0       # N*s/m   hard-stop contact damping
STOP = 0.08        # m       free suspension travel either side of equilibrium
T_END = 4.0        # s       run length
POINTS = 4_001      # 1 ms output grid

QS0 = MS * G / KS               # 0.14715 m static suspension compression
QT0 = (MS + MU) * G / KT        # 0.016677 m static tire compression


def road_velocity(t: float) -> float:
    """The RoadProfile table: a 5 cm plateau bump between 0.5 s and 1.6 s."""
    if 0.5 <= t < 0.6:
        return 0.5
    if 1.5 <= t < 1.6:
        return -0.5
    return 0.0


def derivatives(t: float, y: np.ndarray) -> np.ndarray:
    """The right-hand side in the state order ``[zs, vs, zu, vu, zr]``."""
    zs, vs, zu, vu, zr = y
    compression = zu - zs
    force_s = KS * (QS0 + compression) + CS * (vu - vs)
    if compression > STOP:
        force_h = KH * (compression - STOP) + DH * (vu - vs)
    elif compression < -STOP:
        force_h = KH * (compression + STOP) + DH * (vu - vs)
    else:
        force_h = 0.0
    extension = QT0 + (zr - zu)
    force_t = KT * extension if extension > 0.0 else 0.0
    return np.array(
        [
            vs,
            (-MS * G + force_s + force_h) / MS,
            vu,
            (-MU * G - force_s - force_h + force_t) / MU,
            road_velocity(t),
        ]
    )


def integrate(h: float = 1e-5) -> dict[str, np.ndarray]:
    """Classical RK4 on the 1 ms output grid (the substeps are ``h``)."""
    steps = int(round(T_END / h))
    substeps = max(1, int(round(1e-3 / h)))
    out = np.empty((steps // substeps + 1, 10))
    y = np.zeros(5)
    t = 0.0
    row = 0
    for i in range(steps + 1):
        zs, vs, zu, vu, zr = y
        compression = zu - zs
        force_s = KS * (QS0 + compression) + CS * (vu - vs)
        extension = QT0 + (zr - zu)
        force_t = KT * extension if extension > 0.0 else 0.0
        if i % substeps == 0:
            out[row] = (t, zs, vs, zu, vu, zr, compression, force_s, force_t,
                        road_velocity(t))
            row += 1
        k1 = derivatives(t, y)
        k2 = derivatives(t + h / 2, y + h / 2 * k1)
        k3 = derivatives(t + h / 2, y + h / 2 * k2)
        k4 = derivatives(t + h, y + h * k3)
        y = y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t = (i + 1) * h
    return {
        "t": out[:row, 0], "zs": out[:row, 1], "vs": out[:row, 2],
        "zu": out[:row, 3], "vu": out[:row, 4], "zr": out[:row, 5],
        "comp": out[:row, 6], "fs": out[:row, 7], "ft": out[:row, 8],
        "vroad": out[:row, 9],
    }


def crossings(t: np.ndarray, values: np.ndarray, level: float = 0.0,
              direction: str = "up") -> list[float]:
    """The linearly interpolated crossings of ``level`` in the given direction."""
    found: list[float] = []
    for i in range(t.size - 1):
        a = float(values[i]) - level
        b = float(values[i + 1]) - level
        if direction == "up" and a < 0.0 <= b:
            found.append(float(t[i] + (t[i + 1] - t[i]) * (-a) / (b - a)))
        elif direction == "down" and a > 0.0 >= b:
            found.append(float(t[i] + (t[i + 1] - t[i]) * a / (a - b)))
    return found


def modes() -> list[tuple[float, float]]:
    """The damped natural frequencies (Hz) and damping ratios of the linearised plant."""
    mass = np.diag([MS, MU])
    stiffness = np.array([[KS, -KS], [-KS, KS + KT]])
    damping = np.array([[CS, -CS], [-CS, CS]])
    zero = np.zeros((2, 2))
    identity = np.eye(2)
    companion = np.block([[zero, identity],
                          [-np.linalg.solve(mass, stiffness), -np.linalg.solve(mass, damping)]])
    result: list[tuple[float, float]] = []
    for value in np.linalg.eigvals(companion):
        if value.imag >= 0.0:
            omega = abs(value)
            result.append((omega / (2.0 * math.pi), -value.real / omega))
    return sorted(result)


def fft_peak(t: np.ndarray, values: np.ndarray, t0: float, t1: float,
             band: tuple[float, float] | None = None,
             highpass_hz: float = 0.0) -> float:
    """The dominant frequency of ``values`` over ``[t0, t1]`` (the runner's ``fft_peak``).

    Removes a linear trend, optionally a centered moving-average high-pass (for the
    decaying wheel-hop envelope), applies a Hann taper, zero-pads the FFT and fits a
    parabola through the three samples around the peak.
    """
    mask = (t >= t0) & (t <= t1)
    window_t = t[mask]
    samples = values[mask]
    dt = float(np.median(np.diff(window_t)))
    positions = np.arange(samples.size, dtype=float)
    slope, offset = np.polyfit(positions, samples, 1)
    residual = samples - (slope * positions + offset)
    if highpass_hz > 0.0:
        width = max(2, int(round(1.0 / (dt * highpass_hz))))
        pad = width // 2
        padded = np.pad(residual, (pad, pad), mode="edge")
        residual = residual - np.convolve(padded, np.ones(width) / width,
                                          mode="valid")[: samples.size]
    tapered = residual * np.hanning(samples.size)
    size = 1 << int(np.ceil(np.log2(max(4 * samples.size, 1024))))
    spectrum = np.abs(np.fft.rfft(tapered, n=size))
    frequencies = np.fft.rfftfreq(size, d=dt)
    candidates = np.ones(frequencies.size, dtype=bool)
    candidates[0] = False
    if band is not None:
        candidates &= (frequencies >= band[0]) & (frequencies <= band[1])
    peak = int(np.flatnonzero(candidates)[int(np.argmax(spectrum[candidates]))])
    frequency = float(frequencies[peak])
    if 0 < peak < spectrum.size - 1:
        left, middle, right = (float(np.log(spectrum[peak + k] + 1e-300))
                               for k in (-1, 0, 1))
        curvature = left - 2.0 * middle + right
        if curvature < 0.0:
            fraction = 0.5 * (left - right) / curvature
            if abs(fraction) <= 0.5:
                frequency += fraction * float(frequencies[1] - frequencies[0])
    return frequency


def main() -> None:
    print(f"static equilibrium: qs0 = {QS0:.6f} m, qt0 = {QT0:.6f} m, "
          f"Fs0 = {KS * QS0:.3f} N, Ft0 = {KT * QT0:.3f} N")
    print(f"check: Fs0 = ms*g = {MS * G:.3f} N, Ft0 = (ms+mu)*g = {(MS + MU) * G:.3f} N")
    print(f"undamped estimates: body {math.sqrt(KS * KT / (KS + KT) / MS) / (2 * math.pi):.3f} Hz, "
          f"wheel hop {math.sqrt((KS + KT) / MU) / (2 * math.pi):.3f} Hz")
    for frequency, damping in modes():
        print(f"linear mode: {frequency:.3f} Hz, zeta = {damping:.4f}")

    data = integrate()
    t = data["t"]
    zs, zu, comp, ft = data["zs"], data["zu"], data["comp"], data["ft"]
    print(f"\ntravel from equilibrium (comp): [{comp.min():+.6f}, {comp.max():+.6f}] m "
          f"(hard stop at +/-{STOP:g} m: "
          f"{'contact' if np.abs(comp).max() > STOP else 'no contact'})")
    print(f"peak sprung displacement: {np.abs(zs).max():.6f} m at t = "
          f"{t[int(np.argmax(np.abs(zs)))]:.3f} s")
    print(f"peak unsprung displacement: {np.abs(zu).max():.6f} m at t = "
          f"{t[int(np.argmax(np.abs(zu)))]:.3f} s")
    print(f"tire force: [{ft.min():.3f}, {ft.max():.3f}] N "
          f"(never negative: {bool((ft >= 0.0).all())})")

    wheel = [c for c in crossings(t, data["vu"], 0.0, "up") if c > 0.5]
    body = [c for c in crossings(t, zs, 0.0, "up") if c > 1.6]
    travel = [c for c in crossings(t, comp, 0.0, "up") if c > 1.6]
    print("\nwheel velocity (up) crossings:", ", ".join(f"{c:.6f}" for c in wheel[:4]))
    if len(wheel) >= 2:
        period = wheel[1] - wheel[0]
        print(f"  wheel-hop period {period:.6f} s -> {1.0 / period:.3f} Hz "
              f"(plan 11.8 Hz, {abs(1 / period - 11.8) / 11.8 * 100:.2f} % off)")
    print("body displacement (up) crossings:", ", ".join(f"{c:.6f}" for c in body[:4]))
    if len(body) >= 2:
        period = body[1] - body[0]
        print(f"  body period {period:.6f} s -> {1.0 / period:.3f} Hz "
              f"(plan 1.24 Hz, {abs(1 / period - 1.24) / 1.24 * 100:.2f} % off)")
    print("suspension travel (up) crossings:", ", ".join(f"{c:.6f}" for c in travel[:4]))

    body_fft = fft_peak(t, zs, 1.8, 4.0, band=(0.5, 2.5))
    wheel_fft = fft_peak(t, data["vu"], 0.65, 0.85, band=(8.0, 16.0), highpass_hz=2.0)
    print("\nFFT of the free decay / ring-down (plan 9.4):")
    print(f"  body SInt [1.8, 4.0] s: {body_fft:.4f} Hz "
          f"(plan 1.24 Hz, {abs(body_fft - 1.24) / 1.24 * 100:.2f} % off)")
    print(f"  wheel IMu/p.f [0.65, 0.85] s: {wheel_fft:.4f} Hz "
          f"(plan 11.8 Hz, {abs(wheel_fft - 11.8) / 11.8 * 100:.2f} % off)")

    print("\ncursor values:")
    for cursor in (0.0, 0.4, 0.5, 0.55, 0.6, 0.65, 0.8, 0.9, 1.0, 1.5, 1.6, 2.0, 3.0, 4.0):
        index = int(np.argmin(np.abs(t - cursor)))
        print(f"  t = {cursor:4.2f} s  zs = {zs[index]:+.6f} m  zu = {zu[index]:+.6f} m  "
              f"zr = {data['zr'][index]:.6f} m  travel = {comp[index]:+.6f} m  "
              f"Ft = {ft[index]:8.3f} N  Fs = {data['fs'][index]:8.3f} N")


if __name__ == "__main__":
    main()
