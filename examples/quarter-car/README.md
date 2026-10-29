# quarter-car — a bond-graph quarter-car suspension with a table-driven road

The plan 9.4 quarter car: a 300 kg sprung mass on a 20 kN/m + 1500 N·s/m suspension, a
40 kg unsprung mass on a 200 kN/m one-sided tire, a ±0.08 m hard stop between them, and a
road that climbs a 5 cm plateau bump (0.1 s at +0.5 m/s at t = 0.5 s, then flat, then 0.1 s
at −0.5 m/s at t = 1.5 s). The continuous plant is a **bond graph** (D28); the only
non-bond-graph pieces are the signal sources (the `u = 1` constants on the two `MSe`
elements and the road table), the three flow sensors plus integrators that reconstruct the
positions for the plots and the checks (the D28 sensor exception), and a `Min` monitor used
by one check. The model runs for 4 s on a 1 ms output grid.

## Plant (bond graph)

| part | bond graph |
| --- | --- |
| sprung mass | 1-junction `SJ` with `IMs` (`I`, `i = 300 kg`) and the gravity `MSeGs` (`gain = 2943 N`, `u = 1`) |
| unsprung mass | 1-junction `UJ` with `IMu` (`I`, `i = 40 kg`) and `MSeGu` (`gain = 392.4 N`) |
| suspension | two-port `SpringDamper` `Susp` (`k = 20 kN/m`, `d = 1500 N·s/m`), `a` on `UJ` and `b` on `SJ` |
| hard stop | two-port `HardStop` `Stop` (`lower = −0.08 m`, `upper = +0.08 m`, `k = 1 MN/m`, `d = 2000 N·s/m`), `a` on `UJ`, `b` on `SJ` |
| tire | project `OneSidedSpring` `Tire` (`kt = 200 kN/m`), `a` on the road junction `RJ`, `b` on `UJ` |
| road | 1-junction `RJ` with the `VelocitySource` `RoadV` (flow fixed, `v = 1`) driven by the stdlib `TimeTable` `RoadProfile` |
| sensors | `SFlow`/`UFlow`/`RoadFlow` (`FlowSensor`) and `SInt`/`UInt`/`RoadInt` (`Integrator`) reconstruct `zs`, `zu`, `zr` |

With `zs`, `zu`, `zr` the absolute vertical positions (up positive, zero at static
equilibrium) and `vs`, `vu` their velocities, the graph is

```
MSeGs ─ SJ(1) ─ IMs(I, 300 kg) ─ SFlow
          │
          ├── Susp (SpringDamper 20 kN/m + 1500 N·s/m) ──┐
          ├── Stop (HardStop, free travel ±0.08 m) ──────┤  both span SJ ↔ UJ
          │                                              │
MSeGu ─ UJ(1) ─ IMu(I, 40 kg) ─ UFlow                  │
          │
          ├── Tire (OneSidedSpring 200 kN/m) ── RJ(1) ── RoadV ── RoadFlow
          │
RoadProfile ──(velocity table)──> RoadV
```

The two-port `SpringDamper`, `HardStop` and `OneSidedSpring` elements are drawn as a **C
and an R between two 1-junctions**: `ddt(x) = a.f − b.f` integrates the relative velocity,
and `a.e = k·x + d·(a.f − b.f)`, `b.e = −a.e` applies the equal and opposite force to the
two velocity nodes. That is the port form of a 0-junction force node with a `C` and an
`R` attached, with the J2.7f translation blocks supplying the two ports and the effort sign
(plan 9.4 explicitly asks for the `SpringDamper` and `HardStop`). The tire is the plan's
`OneSidedSpring`, copied from `stdlib:translation/Spring` into
`library/OneSidedSpring.jl` and edited so that `F = ifelse(x > 0, kt*x, 0)` — it pushes but
never pulls, which allows lift-off; its `F` output is recorded and fed to the
`TireNeg = min(F, 0)` check monitor.

The only stores on the graph are the two momenta (`IMs/P`, `IMu/P`), the suspension
relative displacement (`Susp/x`), the tire compression (`Tire/x`) and the hard-stop travel
(`Stop/x`); SCAP gives all of them integral causality, so the run reports no W201. The trip
through the road is `VelocitySource` (flow-out, fixed) → `RJ` 1-junction → `Tire`, exactly
the flow source of D8.

## Units and sign conventions

D8: in the `Translation` domain the **across variable is the flow `f` (velocity, m/s)** and
the **through variable is the effort `e` (force, N)**; every port takes power positive
*into* its element. The model is one-dimensional, up positive, with `z = 0` at static
equilibrium.

- Every bond is drawn **out of** a 1-junction into its element port, so the junction's
  effort equation is `Σ e_port = 0` and its flow equation is `f₁ = f₂ = …`. The `I`
  equation `ddt(P) = p.e` then gives `e_I = m·a`; a positive `MSe` effort is a force that
  accelerates the junction **downward**, which is why the two gravity gains are the
  positive weights `ms·g = 2943 N` and `mu·g = 392.4 N`, and why the suspension's
  `b.e = −Fs` appears as the upward force on the body.
- `Susp/x` is the **suspension compression from its free length**, positive when the wheel
  moves up relative to the body: `ddt(x) = a.f − b.f = vu − vs`. Its static value is
  `qs0 = ms·g/ks = 0.14715 m`, so `ks·qs0 = 2943 N` carries the sprung weight.
- `Stop/x` integrates the *same* relative velocity, but its start value is 0, so it is the
  **suspension travel from static ride height**; that is the quantity the plan limits to
  ±0.08 m. The constant offset between `Stop/x` and `Susp/x` is `qs0`.
- `Tire/x` is the tire compression from its free length, positive when the road moves up
  relative to the wheel (`ddt(x) = vroad − vu`); its static value is
  `qt0 = (ms+mu)·g/kt = 0.016677 m`, and `kt·qt0 = 3335.4 N` carries both masses.
- All energies and powers use the standard bond-graph sign: `P = e·f` into the element.

Parameters and units:

| symbol | value | unit | where |
| --- | --- | --- | --- |
| `ms` | 300 | kg | `IMs` `i` |
| `mu` | 40 | kg | `IMu` `i` |
| `ks` | 20 000 | N/m | `Susp` `k` |
| `cs` | 1 500 | N·s/m | `Susp` `d` |
| `kt` | 200 000 | N/m | `Tire` `kt` |
| hard stop | ±0.08 | m | `Stop` `lower`/`upper` |
| stop contact | 1·10⁶ / 2 000 | N/m, N·s/m | `Stop` `k`/`d` |
| `g` | 9.81 | m/s² | the two `MSe` gains and the static starts |
| `ms·g` | 2 943 | N | `MSeGs` `gain` |
| `mu·g` | 392.4 | N | `MSeGu` `gain` |
| `qs0` | 0.14715 | m | `Susp` start `x` |
| `qt0` | 0.016677 | m | `Tire` start `x` |

## Road input

`RoadProfile` is the stdlib `stdlib:sources/TimeTable`, a **hold** table (`method = 0`)
with `N = 13`, `t_start = 0.4` s and `sample_time = 0.1` s (the table length and the two
times are instance `constants`/parameters; a source block drives the plant only through
`RoadV`'s flow port):

```json
"block": { "ref": "stdlib:sources/TimeTable" },
"constants": { "N": "13" },
"params": {
  "t_start": "0.4", "sample_time": "0.1", "method": "0",
  "values": "[0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.5, 0.0]"
}
```

| interval | `v_road` |
| --- | --- |
| `t < 0.5` | 0 |
| `0.5 ≤ t < 0.6` | +0.5 m/s |
| `0.6 ≤ t < 1.5` | 0 (the 5 cm plateau) |
| `1.5 ≤ t < 1.6` | −0.5 m/s |
| `t ≥ 1.6` | 0 |

The four breakpoints 0.5/0.6/1.5/1.6 s are exactly the plan's table; the table's own
sample instants (every 0.1 s from 0.4 s) are where the condition-only callbacks land, so
the run lands on 13 sample instants (79 callback firings in total, well below the 10 000
event limit). `RoadInt` integrates the measured road flow (`RoadFlow/y`) to `zr`; it reads
0.05 m on [0.6, 1.5] s and returns to 0 (within 3·10⁻⁹ m) at t = 1.6 s.

**NOTES-6 fix.** Earlier versions of the block wrote its conditions as a normalised table
coordinate, `(t−t_start)/sample_time − k`. When a sample instant coincided with an output
grid time (`0.07/0.01 = 6.999999999999999`), the condition had no representable root, the
callback re-fired at every step and a two-node `TimeTable → Integrator` probe reached W206
at t = 1.2 s with 10 003 firings. The block now writes every condition in `t`
(`t >= t_start + k*sample_time`, `clamp(t − (t_start + k*sample_time), 0, sample_time)`),
whose roots are the sample instants themselves; the same probe reports 43 firings, no
diagnostics. This sample therefore uses the stdlib block directly. The plan's 3D variant
(body and wheel boxes, springs as scaled cylinders) is not included: like the other M2
samples this one is the 1D plant only.

## Design reference and results

`design/design.py` (a `uv` script with numpy) integrates the same equations independently
with RK4 at 1e-5 s and prints every value used below:

```
uv run examples/quarter-car/design/design.py
```

| quantity | design.py (RK4) | bond-graph run (4 s, 1 ms grid) |
| --- | --- | --- |
| static equilibrium | `qs0 = 0.147150 m`, `qt0 = 0.016677 m`, `Fs0 = 2943.0 N`, `Ft0 = 3335.4 N` | identical (holds for 0.5 s to < 10⁻⁶ m) |
| peak sprung displacement | 0.074654 m at 0.893 s | 0.0746537 m at 0.893 s |
| peak unsprung displacement | 0.052814 m at 0.809 s | 0.0528144 m at 0.809 s |
| suspension travel `Stop/x` | −0.036687 … +0.034440 m | −0.0366874 … +0.0344404 m |
| peak `|travel|` | 0.036687 m at 1.615 s | 0.0366874 m at 1.615 s |
| hard-stop contact | none (3.67 cm of the 8 cm free travel) | none (`Stop/a.e` ≡ 0) |
| tire force | 1673.245 … 4948.882 N | 1673.242 … 4948.880 N |
| body mode (free decay) | 1.211 Hz (period 0.8256 s) | 1.211 Hz (crossings at 2.1506 / 2.9762 s) |
| body mode (FFT, 1.8–4.0 s) | 1.2238 Hz | 1.2238 Hz (`fft_peak`) |
| wheel hop | 11.853 Hz (period 0.08437 s) | 11.852 Hz (crossings at 0.6689 / 0.7532 s) |
| wheel hop (FFT, 0.65–0.85 s) | 11.862 Hz | 11.846 Hz (`fft_peak`, 2 Hz high-pass) |
| linearised modes | 1.257 Hz (ζ 0.268), 11.633 Hz (ζ 0.262) | — |

The plan's targets are the **undamped** estimates `√(ks·kt/((ks+kt)·ms))/2π = 1.239 Hz`
and `√((ks+kt)/mu)/2π = 11.803 Hz`; the measured damped body mode is 2.3 % below 1.24 Hz
(1.3 % from the FFT) and the wheel hop 0.4 % above 11.8 Hz (0.4 % from the FFT), both well
inside the ±5 % bands. The tire force is never negative: the one-sided element makes it
exactly 0 at lift-off, and on this road it never gets closer than 1.673 kN to zero.

## Checks

`expected.json` has **33** checks (plan 9.4 plus the requested static/travel/tire checks),
all in the runner's kinds (including the new `fft_peak`):

- **Static equilibrium** (4): both masses stay within 10⁻⁶ m for t < 0.5 s; the suspension
  and tire preloads are 2943.0 N and 3335.4 N at t = 0.4 s.
- **Road input** (6): the two edges are +0.5 and −0.5 m/s, the position is 2.5 cm half way
  up and 5 cm on the plateau, and it returns to 0 at 1.6 s.
- **Sprung-mass response** (5): cursors at 0.6, 0.9, 1.5 and 2.0 s pin the rise, the peak
  (7.465 cm at 0.893 s) and the 1.8 cm rebound; a `max_abs` over [0.5, 1.6] pins the peak.
- **Unsprung-mass response** (3): cursors at 0.65 and 1.6 s and the 5.281 cm peak.
- **Suspension travel and hard stop** (4): the 3.669 cm peak, a `max_abs_le` bound of
  0.08 m, a cursor on the falling edge, and `Stop/a.e ≡ 0` (no contact on this input).
- **Tire force** (4): the 4.949 kN peak, the 4.394 kN value on the rise, the 1.673 kN
  minimum, and `max_abs_le` on `TireNeg = min(F, 0)` at 10⁻⁹ — the plan's "never negative".
- **Mode frequencies** (6): the runner's `fft_peak` kind takes the dominant frequency of
  the free decay `SInt/y` over [1.8, 4.0] s (1.224 Hz) and of the wheel-velocity ring-down
  `IMu/p.f` over [0.65, 0.85] s (11.846 Hz), both against the plan's 1.24 / 11.8 Hz with a
  ±5 % band. The four zero-crossing checks remain as an independent period measurement:
  the first two upward crossings of `IMu/p.f` give 11.85 Hz and the first two of `SInt/y`
  in the free decay give 1.211 Hz. `design.py` prints the same FFT values, the crossings
  and the linearised modes (1.257 Hz and 11.633 Hz undamped) independently.
- **`no_diagnostics`** (1): forbids `E901`, `E106`, `W201`, `W202`, `W205` and `W206`; the
  run reports no diagnostics at all (8 states, 68 equations, 79 condition-only firings at
  the table's sample instants, 5058 steps).

The run is read-only after copy: the whole example is a template.

## What to try

- Open the **Plots** tab: “Sprung mass, unsprung mass and road” shows the body overshooting
  the 5 cm plateau to 7.5 cm; “Suspension travel” stays inside the ±0.08 m stop; “Tire
  contact force” peaks at 4.95 kN and never reaches zero.
- Lower `Stop`'s `lower`/`upper` to ±0.02 m and rerun: the stop makes contact, `Stop/x`
  reaches ±0.02 and `Stop/a.e` becomes non-zero — the guard checks in `expected.json` then
  fail, which is the intended signal to update them.
- Raise `RoadProfile`'s bump: set `values` to `[0.0, 2.0, 0, …, 0, -2.0, 0.0]` (a 20 cm
  bump) to see lift-off: `Tire/F` reaches zero and `TireNeg/y` stays zero (the one-sided
  law), while the body response grows. A 1.0 m/s entry (a 10 cm bump) already drops the
  tire force to about 10 N without losing contact. Set `method` to 1 for a linear
  interpolation between the samples instead of the hold table.
- Change `Susp`'s `k` or `d` and rerun; `design/design.py` reproduces the new reference
  response and prints the new values.

## 3D view

`scenes/quarter-car.sdf` is a side view: the road block, the wheel and the car body, each on a vertical prismatic joint bound to `RoadInt/y`, `UInt/y` and `SInt/y` (metres from static equilibrium). The road bump lifts the wheel, and the body rides out the 1.2 Hz sprung-mass motion above it.
