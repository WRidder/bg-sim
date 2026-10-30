@@ figures quarter-car
{
  "diagram": {"kind": "diagram", "model": "quarter-car"},
  "scene": {"kind": "scene", "model": "quarter-car", "t": 0.9},
  "run": {
    "kind": "plot", "model": "quarter-car", "xlim": [0, 4],
    "rows": [
      {"ylabel": "position [cm]", "series": [{"signal": "RoadInt/y", "label": "road RoadInt/y", "scale": 100, "style": "--", "color": "#888888"}, {"signal": "UInt/y", "label": "wheel UInt/y", "scale": 100}, {"signal": "SInt/y", "label": "body SInt/y", "scale": 100}], "legend": true},
      {"ylabel": "suspension travel [cm]", "series": [{"signal": "Stop/x", "label": "Stop/x", "scale": 100}], "hlines": [{"y": 8, "label": "hard stop +-8 cm"}, {"y": -8}], "legend": true},
      {"ylabel": "tire force [kN]", "series": [{"signal": "Tire/F", "label": "Tire/F", "scale": 0.001, "color": "#1b9e77"}]}
    ]
  }
}
@@ page quarter-car overview - | Overview
# Quarter-car suspension

The plan 9.4 quarter car: a 300 kg sprung mass on a 20 kN/m and 1500 N·s/m suspension, a 40 kg unsprung mass on a 200 kN/m **one-sided tire**, a $\pm 0.08$ m hard stop between the masses, and a road that climbs a 5 cm plateau bump (0.1 s at +0.5 m/s from $t = 0.5$ s, flat, then 0.1 s at -0.5 m/s from $t = 1.5$ s). The continuous plant is a **bond graph** (D28); the only non-bond-graph pieces are the signal sources, three flow sensors with integrators that reconstruct the positions for plots and checks (the D28 sensor exception) and a `Min` monitor used by one check. The run lasts 4 s on a 1 ms grid (4001 points).

![The model canvas|900](@fig:diagram)

## What to try

- **Plots** tab: "Sprung mass, unsprung mass and road" ([SInt/y](signal:SInt/y), [UInt/y](signal:UInt/y), [RoadInt/y](signal:RoadInt/y)) shows the body overshooting the 5 cm plateau to 7.5 cm; "Suspension travel" ([Stop/x](signal:Stop/x)) stays inside the 8 cm stop; "Tire contact force" ([Tire/F](signal:Tire/F)) peaks at 4.95 kN and never reaches zero.
- Lower the limits of [Stop](block:Stop) to $\pm 0.02$ m and rerun: the stop makes contact, `Stop/x` reaches $\pm 0.02$ and `Stop/a.e` becomes non-zero. The guard checks in `expected.json` then fail, which is the intended signal to update them.
- Make the road bump bigger: set `values` of [RoadProfile](block:RoadProfile) to `[0.0, 2.0, 0, ..., 0, -2.0, 0.0]` (a 20 cm bump) to see lift-off: `Tire/F` reaches zero and `TireNeg/y` stays zero. A 1.0 m/s entry (a 10 cm bump) already drops the tire force to about 10 N without losing contact. Set `method` to 1 for linear interpolation instead of the hold table.
- Change `k` or `d` of [Susp](block:Susp) and rerun.

## 3D view

`scenes/quarter-car.sdf` is a side view: the road block, the wheel and the car body, each on a vertical prismatic joint bound to [RoadInt/y](signal:RoadInt/y), [UInt/y](signal:UInt/y) and [SInt/y](signal:SInt/y) (metres from static equilibrium). The picture is taken at 0.9 s, near the peak of the body.

![3D view at t = 0.9 s|500](@fig:scene)

Continue with [the plant](page:plant) and [the results](page:results).
@@ page quarter-car plant overview | Plant and road
# Plant (bond graph)

| part | bond graph |
| --- | --- |
| sprung mass | 1-junction [SJ](block:SJ) with `I` [IMs](block:IMs) (300 kg) and gravity [MSeGs](block:MSeGs) (2943 N, input `One` = 1) |
| unsprung mass | 1-junction [UJ](block:UJ) with `I` [IMu](block:IMu) (40 kg) and [MSeGu](block:MSeGu) (392.4 N) |
| suspension | two-port `SpringDamper` [Susp](block:Susp) ($k$ = 20 kN/m, $d$ = 1500 N·s/m), `a` on `UJ`, `b` on `SJ` |
| hard stop | two-port `HardStop` [Stop](block:Stop) (lower $-0.08$ m, upper $+0.08$ m, $k$ = 1 MN/m, $d$ = 2000 N·s/m) between the same junctions |
| tire | project `OneSidedSpring` [Tire](block:Tire) ($k_t$ = 200 kN/m), `a` on the road junction [RJ](block:RJ), `b` on `UJ` |
| road | 1-junction `RJ` with the `VelocitySource` [RoadV](block:RoadV) (flow fixed), driven by the stdlib `TimeTable` [RoadProfile](block:RoadProfile) |
| sensors | [SFlow](block:SFlow), [UFlow](block:UFlow), [RoadFlow](block:RoadFlow) with integrators [SInt](block:SInt), [UInt](block:UInt), [RoadInt](block:RoadInt) reconstruct $z_s$, $z_u$, $z_r$ |

The two-port spring elements are drawn as a C and an R between two 1-junctions: the state integrates the relative velocity, $\dot x = a.f - b.f$, and the force $a.e = k\,x + d\,(a.f - b.f)$ is applied equally and oppositely to the two velocity nodes. The tire is `stdlib:translation/Spring` copied into `library/OneSidedSpring.jl` with $F = \mathrm{ifelse}(x > 0,\ k_t x,\ 0)$: it pushes but never pulls, which allows lift-off. [TireNeg](block:TireNeg) $= \min(F, 0)$ is the check monitor.

## Equations

With the absolute vertical positions $z_s, z_u, z_r$ (up positive, zero at static equilibrium) the model integrates

$$m_s\,\ddot z_s = -m_s g + F_s + F_h, \qquad m_u\,\ddot z_u = -m_u g - F_s - F_h + F_t,$$

$$F_s = k_s\,q_s + c_s\,(\dot z_u - \dot z_s), \quad q_s = q_{s0} + (z_u - z_s), \qquad F_t = \begin{cases} k_t\,x_t & x_t > 0 \\ 0 & \text{otherwise} \end{cases}, \quad x_t = q_{t0} + (z_r - z_u),$$

with $F_h$ the hard-stop contact force (zero inside $\pm 0.08$ m of travel), and the static compressions

$$q_{s0} = \frac{m_s g}{k_s} = 0.14715\ \mathrm{m}, \qquad q_{t0} = \frac{(m_s + m_u)\,g}{k_t} = 0.016677\ \mathrm{m}.$$

## Signs and units

In the translation domain the across variable is the flow (velocity, m/s) and the through variable the effort (force, N); every port takes power positive into its element. The model is one-dimensional, up positive. Every bond is drawn out of a 1-junction into its element port, so a positive `MSe` effort accelerates the junction downward: the gravity gains are the positive weights $m_s g = 2943$ N and $m_u g = 392.4$ N.

- `Susp/x` is the suspension compression from its free length; static value $q_{s0}$, so $k_s q_{s0} = 2943$ N carries the sprung weight.
- `Stop/x` integrates the same relative velocity but starts at 0: it is the **travel from static ride height**, the quantity limited to $\pm 0.08$ m.
- `Tire/x` is the tire compression from its free length; static value $q_{t0}$, so $k_t q_{t0} = 3335.4$ N carries both masses.

| symbol | value | block parameter |
| --- | --- | --- |
| $m_s$, $m_u$ | 300, 40 kg | `IMs.i`, `IMu.i` |
| $k_s$, $c_s$ | 20000 N/m, 1500 N·s/m | `Susp.k`, `Susp.d` |
| $k_t$ | 200000 N/m | `Tire.kt` |
| hard stop | $\pm 0.08$ m, 1e6 N/m, 2000 N·s/m | `Stop` |
| starts | 0.14715 m, 0.016677 m | `Susp.x`, `Tire.x` |

## Road input

[RoadProfile](block:RoadProfile) is a hold table (`method` 0) with `N` = 13, `t_start` = 0.4 s, `sample_time` = 0.1 s and `values` = [0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, -0.5, 0]:

| interval | road velocity |
| --- | --- |
| $t < 0.5$ | 0 |
| $0.5 \le t < 0.6$ | +0.5 m/s |
| $0.6 \le t < 1.5$ | 0 (the 5 cm plateau) |
| $1.5 \le t < 1.6$ | -0.5 m/s |
| $t \ge 1.6$ | 0 |

`RoadInt` integrates the measured road flow to $z_r$: 0.05 m on $[0.6, 1.5]$ s, returning to 0 (within 3e-9 m) at 1.6 s. The table's own sample instants every 0.1 s are where the condition-only callbacks land (79 firings in all, far below the event limit).
@@ page quarter-car results overview | Results and checks
# Results and checks

![Positions, suspension travel and tire force|900](@fig:run)

`design/design.py` integrates the same equations independently with RK4 at 1e-5 s. Values from the README:

| quantity | design.py (RK4) | bond graph run |
| --- | --- | --- |
| peak sprung displacement | 0.074654 m at 0.893 s | 0.0746537 m at 0.893 s |
| peak unsprung displacement | 0.052814 m at 0.809 s | 0.0528144 m at 0.809 s |
| suspension travel `Stop/x` | -0.036687 to +0.034440 m | -0.0366874 to +0.0344404 m |
| hard-stop contact | none (3.67 cm of 8 cm) | none (`Stop/a.e` is 0) |
| tire force | 1673.245 to 4948.882 N | 1673.242 to 4948.880 N |
| body mode (free decay) | 1.211 Hz | 1.211 Hz |
| body mode (FFT, 1.8 to 4.0 s) | 1.2238 Hz | 1.2238 Hz |
| wheel hop | 11.853 Hz | 11.852 Hz |
| wheel hop (FFT, 0.65 to 0.85 s) | 11.862 Hz | 11.846 Hz |
| linearised undamped modes | 1.257 Hz ($\zeta$ 0.268), 11.633 Hz ($\zeta$ 0.262) | |

The plan's targets are the undamped estimates

$$f_{body} = \frac{1}{2\pi}\sqrt{\frac{k_s k_t}{(k_s + k_t)\,m_s}} = 1.239\ \mathrm{Hz}, \qquad f_{hop} = \frac{1}{2\pi}\sqrt{\frac{k_s + k_t}{m_u}} = 11.803\ \mathrm{Hz}.$$

The measured damped body mode is 2.3 % below 1.24 Hz (1.3 % from the FFT) and the wheel hop 0.4 % above 11.8 Hz, both inside the plan's $\pm 5$ % bands. The tire force is never negative: it never gets closer than 1.673 kN to zero on this road.

## Acceptance checks (33 in `expected.json`)

- static equilibrium: both masses stay within 1e-6 m for $t < 0.5$ s; spring preloads 2943.0 N and 3335.4 N;
- road: edges +0.5 and -0.5 m/s, position 2.5 cm half way up, 5 cm on the plateau, back to 0 at 1.6 s;
- sprung-mass response: cursors at 0.6, 0.9, 1.5 and 2.0 s and the peak 7.465 cm at 0.893 s ([SInt/y](signal:SInt/y)); unsprung mass: cursors and the 5.281 cm peak ([UInt/y](signal:UInt/y));
- travel and stop: peak 3.669 cm, bound 0.08 m and `Stop/a.e` identically 0;
- tire force [Tire/F](signal:Tire/F): peak 4.949 kN, minimum 1.673 kN and [TireNeg/y](signal:TireNeg/y) below 1e-9 (the plan's "never negative");
- mode frequencies: `fft_peak` of [SInt/y](signal:SInt/y) over $[1.8, 4.0]$ s (1.224 Hz) and of [IMu/p.f](signal:IMu/p.f) over $[0.65, 0.85]$ s (11.846 Hz) against 1.24 and 11.8 Hz with a 5 % band, plus four zero-crossing period checks;
- no E901, E106, W201, W202, W205 or W206 (8 states, 68 equations, 5058 steps).

## Note on the road table

An earlier version of the `TimeTable` block wrote its conditions as a normalised table coordinate and could re-fire at every step when a sample instant coincided with an output grid time (NOTES-6). The block now writes every condition in $t$, whose roots are the sample instants, so this sample uses the stdlib block directly. The plan's 3D variant with spring cylinders is not included.
