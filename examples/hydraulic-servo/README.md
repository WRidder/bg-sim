# Hydraulic servo (plan 9.6, milestone M2)

A valve-controlled hydraulic position servo: a 100 bar supply and a 1 bar tank feed a
4/3 spool valve built from four variable orifices, which drive a single-rod
`HydraulicCylinder` loaded by a 50 kg mass and a 500 N·s/m damper. A 1 ms discrete PID
turns the position error into the spool command. Everything except the sensor and the
sampled controller is a hydraulic/translation bond graph (D28).

## Topology

```
 100 bar ── PS ──► P ─┐                      ┌─ A ──► Cylinder.A ─┐
                      │  PA        B ── BT ─┤                   ├─ rod ── 1-junction ── I(50 kg)
   Valve subsystem:   ├─ (P→A)     (B→T) ───┤                   │                       R(500 N·s/m)
   four VariableOrifice  (P→B)     (A→T) ───┤                   │                       PositionSensor
   1 bar ── TK ─────► T ─┘                      └─ B ──► Cylinder.B ─┘
```

* **Supply/return.** `PS` is a `PressureSource` with `p = 1e7 Pa` (100 bar) driven by a
  constant 1; `TK` is a `Tank` at `p = 1e5 Pa` (1 bar).
* **Valve (subsystem).** Four `VariableOrifice` elements in a Wheatstone bridge around
  four hydraulic 0-junctions `JP`, `JT`, `JA`, `JB` (effort = pressure is equal on a rail,
  flows sum to zero):
  - `PA`: P → A, area `A_max·max(spool, 0) + A_leak`
  - `BT`: B → T, the same area
  - `PB`: P → B, area `A_max·max(−spool, 0) + A_leak`
  - `AT`: A → T, the same area
  with `A_max = 1e-5 m^2`, `A_leak = 1e-9 m^2`, `Cd = 0.62`, `rho = 850 kg/m³`,
  `p_tr = 1e5 Pa`. The orifices use the shipped regularized law
  `Q = Cd·A·√(2/ρ)·Δp / (Δp² + p_tr²)^(1/4)`, which is linear for `|Δp| ≪ p_tr` and
  square-root for `|Δp| ≫ p_tr`.
  The `VariableOrifice` input is a *normalized* area: with `A = A_max`, passing
  `u = max(±spool, 0) + 1e-4` gives exactly the plan's area, because
  `A_max·1e-4 = 1e-9 m²`. The valve's `u` port is one signal input; the internal
  `VDrive` block splits it into the two normalized areas (`ap`, `an`).
  The four power ports `P`, `T`, `A`, `B` are exposed through series `FlowSensor`
  elements (zero pressure drop), because a JSON subsystem power port has to attach to a
  power port — a junction face is rejected (E102). The sensor's `y` is the port flow.
* **Cylinder.** `HydraulicCylinder`: piston area `Ap = 2e-3 m²`, annulus
  `Ar = 1e-3 m²`, dead volumes `V0A = V0B = 5e-5 m³` (plus the swept volume), bulk
  modulus `beta = 1.4e9 Pa`, stroke 0.2 m. Its equations are
  `ddt(pA) = β(A.f − Ap·v)/(V0A + Ap·x)`, `ddt(pB) = β(B.f + Ar·v)/(V0B + Ar·(stroke − x))`
  and `rod.e = pB·Ar − pA·Ap`.
* **Rod.** A translation 1-junction carries `I(50 kg)`, `R(500 N·s/m)` and a
  `PositionSensor` (the sensor is the D28 exception: a kinematic integrator of the rod
  velocity). `rod.f` is the extension rate; the cylinder effort `rod.e` is positive into
  the cylinder, so the mass sees `−rod.e = pA·Ap − pB·Ar`.
* **Controller.** `DiscretePID` at `Ts = 1 ms` (`method = "backward"`), error
  `e = x_ref − x` from a two-input inline `ErrorSum`, output clamped to `[−1, 1]` and fed
  to the valve `u`. The reference is a `Step` from 0 to 0.1 m at `t = 0.1 s`.
  Gains: **Kp = 14 spool/m, Ti = 20 s, Td = 0** (`Ki = Kp/Ti = 0.7
  spool/(m·s)`). `Td = 0` makes it a PI: the 1 ms difference of the sampled position is
  too noisy, and the valve's flow/pressure characteristic already provides the damping.

### Units

| Quantity | Unit |
| --- | --- |
| pressure (`PS`, `Cyl/pA`, `Cyl/pB`, orifice `dp`) | Pa (bar = 1e5 Pa) |
| volume flow (`*_f`, orifice `Q`, `PS/a.f`) | m³/s |
| area (`A`, `Ap`, `Ar`) | m² |
| position / velocity (`XS/y`, `IM/p.f`, `rod.f`) | m, m/s |
| force (`rod.e`, `IM/p.e`, `RD/p.e`) | N |
| mass / damping (`I`, `R`) | kg, N·s/m |
| spool (`PID1/y`) and normalized area (`VDrive/ap`) | dimensionless |

### Initial condition and why it is not "everything at tank pressure"

The plan fixes the plant parameters but not the initial pressures. Starting both
chambers at the 1 bar tank pressure leaves the closed-centre valve (leakage only) unable
to hold the 50 kg rod against the piston/annulus area difference: the rod runs away, the
cap chamber pressure falls through the tank pressure and the `VariableOrifice` sign
switches chatter (W206 at the event limit). The model therefore starts at the valve's
**no-load equilibrium**, `pA = 33.667 bar`, `pB = 67.333 bar`, which is the solution of
`pA·Ap = pB·Ar` and of the two leakage flow balances with the trim spool
`spool₀ = −4.25e-5`; the PID integrator is preloaded with
`i₀ = spool₀·Ti/Kp = −6.07e-5` error-seconds so the first tick already commands the trim.
This is a controller bumpless-start condition, not a plant change.

## Measured results (t_end = 1.5 s, `expected.json`)

| Quantity | Measured |
| --- | --- |
| rod position at 0.3 / 0.5 s | 0.06945 / 0.09161 m |
| rod position at 0.9 s | 0.09982 m |
| rod position at 1.0 s | **0.10016 m** (plan: 0.1 ± 0.002) |
| rod position at 1.5 s (peak 0.100525) | 0.10053 m |
| chamber A pressure, min / max | 6.13 / **92.58 bar** |
| chamber B pressure, min / max | 22.89 / 67.33 bar |
| spool, min / peak | −4.28e-5 / **+1.0** (saturated on the step) |
| piston speed, peak | 0.481 m/s |
| pump flow, peak | 9.22e-4 m³/s |
| `PA` / `BT` orifice flow, peak | 9.22e-4 / 7.75e-4 m³/s |
| run diagnostics | W202 only (see below) |

The response is monotone: the valve saturates at +1 from the step until about 0.166 s
(the position error stays above `1/Kp = 71 mm` for that long), then closes as the rod
approaches the reference, and the 6 bar cap pressure and 23 bar annulus pressure stay well
inside `[0, 100.5] bar` throughout.

## Checks (`expected.json`)

`uv run examples/run_checks.py` runs the model through the real worker. The 16 checks are:

* position: `XS/y` at 0.3 s (mid-move), at **1.0 s within ±0.002 m** (plan 9.6) and at
  1.5 s (it holds);
* pressures: `PSensA/y` and `PSensB/y` ≤ 100.5 bar, and the `pAmin`/`pBmin` monitors
  (`min(p, 0)`) ≤ 1 Pa, i.e. both chambers stay ≥ 0 bar;
* spool: `max|PID1/y| = 1.0` (the ±1 clamp is reached) and `|PID1/y| ≤ 1` everywhere;
* flow sanity: piston speed ≤ 0.6 m/s, pump flow ≤ 1e-3 m³/s, `PA` and `BT` orifice flows
  ≤ 1e-3 m³/s;
* the two pressure taps agree with the chamber states to 1e-6 Pa;
* no `E901`/`E101`/`E102`/`E103`/`E106`/`W206`.

`W202` is expected and allowed: "algebraic loop through AT, BT, FST" (and the analogous
chains at the other rails). It is the causality pass's view of the series `FlowSensor`
that exposes a rail as a subsystem power port; the rail pressure is in fact fixed by the
tank through that sensor, and the DAE solves without an iteration failure.

## What to try

1. Open `hydraulic-servo`, press **Run**, and plot `XS/y` with `XRef/y`: the rod tracks
   the 0.1 m step at 0.1 s and settles in about 0.6 s.
2. Plot `Cyl/pA` and `Cyl/pB` (or the `PSensA/y`/`PSensB/y` taps): the cap pressure dips
   to 6 bar during the move and returns to the 33.7/67.3 bar trim.
3. Plot `PID1/y`: the spool is at −4.3e-5 before the step, saturates at +1 for about
   66 ms, then closes to the trim.
4. Raise `Kp` (e.g. 25) and run again: the step saturates longer and the rod overshoots;
   lower it to 8 and the approach gets slower. The valve is strongly oversized for the
   load, so the closed-loop bandwidth is limited by the hydraulic resonance and the 1 ms
   sample.
5. Set the cylinder starts back to both 1e5 Pa and watch the W206 chatter: this is the
   closed-centre/area-asymmetry problem described above.

## Deviations from a literal plan 9.6 transcription

* The sub-spool area law uses a smooth `max`, `0.5·(u + √(u² + 1e-12))` instead of
  `max(u, 0)`, so the closed-centre spool does not sit on a non-smooth kink; the
  difference is below 1e-6 in spool (5e-12 m² in area). The two-input `ErrorSum` and the
  valve's `VDrive` are inline blocks: the stdlib `Sum` takes a single vector input, and a
  subsystem has only one spool input that has to fan out to four orifices. They are
  controller/valve-drive glue, not plant physics.
* The rail power ports use series `FlowSensor` elements (with the resulting W202
  warning) because a JSON subsystem cannot expose a junction as a power port.
* The initial pressures and the preloaded integrator are set as described above; the
  plan does not specify them.
* The 3D cylinder/rod binding is the M5 part of plan 9.6 and is not included here.

## 3D view

`scenes/hydraulic-servo.sdf` draws the cylinder barrel (translucent), the piston with its rod and the 50 kg load. The prismatic joint `stroke` follows the rod position `XS/y`, so the 0.1 m reference step at 0.1 s is a visible slide; the red tick marks the target position of the load.
