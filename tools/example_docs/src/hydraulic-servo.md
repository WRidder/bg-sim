@@ figures hydraulic-servo
{
  "diagram": {"kind": "diagram", "model": "hydraulic-servo"},
  "scene": {"kind": "scene", "model": "hydraulic-servo", "t": 0.5},
  "run": {
    "kind": "plot", "model": "hydraulic-servo", "xlim": [0, 1.5],
    "rows": [
      {"ylabel": "rod position [m]", "series": [{"signal": "XS/y", "label": "XS/y"}, {"signal": "XRef/y", "label": "XRef/y (reference)", "style": "--"}], "legend": true},
      {"ylabel": "chamber pressure [bar]", "series": [{"signal": "Cyl/pA", "label": "Cyl/pA (cap)", "scale": 1e-5}, {"signal": "Cyl/pB", "label": "Cyl/pB (annulus)", "scale": 1e-5}], "legend": true},
      {"ylabel": "spool command [-]", "series": [{"signal": "PID1/y", "label": "PID1/y", "color": "#1b9e77"}]}
    ]
  }
}
@@ page hydraulic-servo overview - | Overview
# Hydraulic position servo

A valve-controlled hydraulic servo (plan 9.6, milestone M2). A 100 bar supply and a 1 bar tank feed a 4/3 spool valve built from four variable orifices; the valve drives a single-rod [cylinder](block:Cyl) that moves a 50 kg mass with 500 N·s/m of damping. A 1 ms discrete [PID](block:PID1) turns the position error into the spool command. Everything except the position sensor and the sampled controller is a hydraulic/translation **bond graph** (D28).

![The model canvas|900](@fig:diagram)

Blocks of the loop:

| block | role |
| --- | --- |
| [PS](block:PS), [TK](block:TK) | pressure source (100 bar) and tank (1 bar); `One` drives the source input with a constant 1 |
| [Valve](block:Valve) | subsystem with four orifices in a Wheatstone bridge, ports P, T, A, B and one spool input |
| [Cyl](block:Cyl) | hydraulic cylinder, ports A, B and the rod |
| [Jrod](block:Jrod), [IM](block:IM), [RD](block:RD), [XS](block:XS) | translation 1-junction with the 50 kg mass, the 500 N·s/m damper and the position sensor |
| [XRef](block:XRef), [Err](block:Err), [PID1](block:PID1) | reference step, error node, discrete controller |
| [PSensA](block:PSensA), [PSensB](block:PSensB), [pAmin](block:pAmin), [pBmin](block:pBmin) | pressure taps and monitors of the checks |

## What to try

1. Press **Run** and plot [XS/y](signal:XS/y) together with [XRef/y](signal:XRef/y): the rod follows the 0.1 m step at 0.1 s.
2. Plot [Cyl/pA](signal:Cyl/pA) and [Cyl/pB](signal:Cyl/pB): the cap pressure dips to about 6 bar during the move and returns to the 33.7/67.3 bar trim.
3. Plot [PID1/y](signal:PID1/y): the spool is at -4.3e-5 before the step, saturates at +1 until about 0.166 s and then closes to the trim.
4. Raise `Kp` (for example to 25): the step saturates longer and the rod overshoots; lower it to 8 and the approach gets slower.
5. Set both cylinder start pressures back to 1e5 Pa and watch the W206 chatter described under [limitations](page:notes).

## 3D view

`scenes/hydraulic-servo.sdf` draws the translucent cylinder barrel, the piston with rod and the 50 kg load. The prismatic joint `stroke` follows [XS/y](signal:XS/y); the red tick marks the target position of the load. The picture is taken at 0.5 s, when the rod is at 0.0916 m.

![3D view at t = 0.5 s|500](@fig:scene)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
@@ page hydraulic-servo plant overview | Plant: valve, cylinder, load
# Plant

## Supply and valve

[PS](block:PS) is a `PressureSource` with `p` = 1e7 Pa; [TK](block:TK) a `Tank` at `p` = 1e5 Pa. The [Valve](block:Valve) subsystem holds four `VariableOrifice` elements around four hydraulic 0-junctions `JP`, `JT`, `JA`, `JB` (a common pressure on each rail, flows sum to zero):

| orifice | path | normalised area input |
| --- | --- | --- |
| `Valve/PA` | P to A | $\max(s, 0) + 10^{-4}$ |
| `Valve/BT` | B to T | the same as PA |
| `Valve/PB` | P to B | $\max(-s, 0) + 10^{-4}$ |
| `Valve/AT` | A to T | the same as PB |

with the spool command $s \in [-1, 1]$. All four orifices have `A` = $A_{max} = 10^{-5}\ \mathrm{m^2}$, `Cd` = 0.62, `rho` = 850 kg/m³ and `p_tr` = 1e5 Pa, so the open area is $A_{max}\max(\pm s, 0) + 10^{-9}\ \mathrm{m^2}$, the 10^-9 m² being the leakage area. The inline block `Valve/VDrive` splits the one spool input into the two normalised areas.

The orifices use the shipped regularised law

$$Q = C_d\,A\,\sqrt{\frac{2}{\rho}}\;\frac{\Delta p}{(\Delta p^2 + p_{tr}^2)^{1/4}},$$

which is linear for $|\Delta p| \ll p_{tr}$ and square-root for $|\Delta p| \gg p_{tr}$.

The four valve ports are exposed through series `FlowSensor` elements (`FSP`, `FST`, `FSA`, `FSB`, zero pressure drop) because a JSON subsystem power port must attach to a power port, not to a junction face (E102).

## Cylinder

`HydraulicCylinder` with piston area $A_p = 2\cdot10^{-3}\ \mathrm{m^2}$, annulus $A_r = 10^{-3}\ \mathrm{m^2}$, dead volumes $V_{0A} = V_{0B} = 5\cdot10^{-5}\ \mathrm{m^3}$, bulk modulus $\beta = 1.4\cdot10^9$ Pa and stroke $0.2$ m. Its chamber pressures are states:

$$\dot p_A = \frac{\beta\,(Q_A - A_p v)}{V_{0A} + A_p x}, \qquad \dot p_B = \frac{\beta\,(Q_B + A_r v)}{V_{0B} + A_r(\text{stroke} - x)}, \qquad F_{rod} = p_B A_r - p_A A_p .$$

Here $Q_A$, $Q_B$ are the volume flows into the chambers (the `A.f`, `B.f` of the cylinder) and $v$ is the rod speed. The rod effort is positive into the cylinder, so the load sees $-F_{rod} = p_A A_p - p_B A_r$.

## Load

The rod port connects to a translation 1-junction `Jrod` (common velocity $v$) with `IM` = 50 kg, `RD` = 500 N·s/m and the `PositionSensor` `XS`, which integrates the rod velocity (the D28 exception: a kinematic integrator):

$$m\,\dot v = p_A A_p - p_B A_r - c\,v, \qquad \dot x = v, \qquad m = 50\ \mathrm{kg},\ c = 500\ \mathrm{N\,s/m}.$$

## Units

| quantity | unit |
| --- | --- |
| pressure (`Cyl/pA`, `Cyl/pB`, `PSensA/y`, orifice `dp`) | Pa (1 bar = 1e5 Pa) |
| volume flow (orifice `Q`, `PS/a.f`) | m³/s |
| position, velocity (`XS/y`, `IM/p.f`) | m, m/s |
| force (`IM/p.e`, `RD/p.e`) | N |
| spool (`PID1/y`) and normalised area (`VDrive/ap`) | dimensionless |
@@ page hydraulic-servo controller overview | Controller
# Controller

[XRef](block:XRef) is a step from 0 to 0.1 m at $t = 0.1$ s. [Err](block:Err) is a two-input inline block $e = x_{ref} - x$ (the stdlib `Sum` takes one vector input). [PID1](block:PID1) is a `DiscretePID` at $T_s = 1\ \mathrm{ms}$, `method` 1 (backward), output clamped to $[-1, 1]$:

| parameter | value |
| --- | --- |
| `Kp` | 14 spool/m |
| `Ti` | 20 s, so $K_i = K_p/T_i = 0.7$ spool/(m·s) |
| `Td` | 0 (a PI: the 1 ms difference of a sampled position is too noisy, the valve characteristic already damps) |
| `lower`, `upper` | -1, +1 |

$$I_k = I_{k-1} + T_s e_k, \qquad s_k = \operatorname{clamp}\!\Big(K_p e_k + \frac{K_p}{T_i} I_k,\ -1,\ 1\Big),$$

with the block's anti-windup (the increment is taken back when the output saturates). The valve is saturated while the error exceeds $1/K_p = 71$ mm.

## Initial condition

Starting both chambers at the 1 bar tank pressure leaves the closed-centre valve (leakage only) unable to hold the 50 kg rod against the area difference: the rod runs away, the cap pressure falls through the tank pressure and the orifice sign switches chatter (W206 at the event limit). The model therefore starts at the valve's **no-load equilibrium**:

- `Cyl` starts at $p_A = 3.36667\cdot10^{6}$ Pa (33.667 bar) and $p_B = 6.73333\cdot10^{6}$ Pa (67.333 bar), the solution of $p_A A_p = p_B A_r$ and of the two leakage flow balances with the trim spool $s_0 = -4.25\cdot10^{-5}$;
- the PID integrator is preloaded with $I_0 = s_0 T_i/K_p = -6.07\cdot10^{-5}$ error-seconds, so the first tick already commands the trim.

This is a bumpless-start condition of the controller, not a change of the plant.
@@ page hydraulic-servo results overview | Results
# Results

![Rod position, chamber pressures and spool command|900](@fig:run)

## Measured numbers (README, `expected.json`)

| quantity | value |
| --- | --- |
| rod position at 0.3 / 0.5 s | 0.06945 / 0.09161 m |
| rod position at 0.9 s | 0.09982 m |
| rod position at 1.0 s | 0.10016 m (plan: 0.1 +- 0.002 m) |
| rod position at 1.5 s (peak 0.100525 m) | 0.10053 m |
| chamber A pressure, min / max | 6.13 / 92.58 bar |
| chamber B pressure, min / max | 22.89 / 67.33 bar |
| spool, min / peak | -4.28e-5 / +1.0 (saturated on the step) |
| piston speed, peak | 0.481 m/s |
| pump flow, peak | 9.22e-4 m³/s |
| run diagnostics | W202 only |

## What the 16 checks verify

- position: [XS/y](signal:XS/y) at 0.3 s (0.0694475, tolerance 0.002), at 1.0 s and 1.5 s (0.1 within 0.002 m);
- pressures: [PSensA/y](signal:PSensA/y) and [PSensB/y](signal:PSensB/y) at most 100.5 bar; the monitors [pAmin/y](signal:pAmin/y) and [pBmin/y](signal:pBmin/y) ($\min(p, 0)$) stay below 1 Pa, so both chambers stay at or above 0 bar;
- spool: $\max|s| = 1.0$ (the clamp is reached) and $|s| \le 1$ everywhere;
- flow sanity: piston speed at most 0.6 m/s, pump flow [PS/a.f](signal:PS/a.f) at most 1e-3 m³/s, orifice flows [Valve/PA/Q](signal:Valve/PA/Q) and [Valve/BT/Q](signal:Valve/BT/Q) at most 1e-3 m³/s;
- the two pressure taps agree with the chamber states [Cyl/pA](signal:Cyl/pA), [Cyl/pB](signal:Cyl/pB) to 1e-6 Pa;
- no E901, E101, E102, E103, E106 or W206.

The response is monotone: the valve saturates until about 0.166 s, then closes as the rod approaches the reference.
@@ page hydraulic-servo notes overview | Notes and limitations
# Notes and limitations

- **W202 is expected and allowed.** The message "algebraic loop through AT, BT, FST" (and analogous ones at the other rails) is the causality pass's view of the series `FlowSensor` that exposes a rail as a subsystem power port. The rail pressure is in fact fixed by the tank through the sensor, and the DAE solves without an iteration failure.
- **Deviations from a literal plan 9.6 transcription.** The sub-spool area law uses the smooth $\max(u, 0) \approx \tfrac12\left(u + \sqrt{u^2 + 10^{-12}}\right)$ so the closed-centre spool does not sit on a kink (difference below 1e-6 in spool, 5e-12 m² in area). `Err` and `VDrive` are inline glue blocks, not plant physics. The initial pressures and the preloaded integrator are not specified by the plan.
- The closed-loop bandwidth is limited by the hydraulic resonance and the 1 ms sample: the valve is strongly oversized for the load.
