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
