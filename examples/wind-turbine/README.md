# Wind turbine (NREL 5 MW)

The NREL 5 MW reference wind turbine, its drivetrain, its tower's first fore-aft mode and its baseline controller, as a rotational and a translational bond graph. The rotor's aerodynamics are two modulated sources fed by Cp and Ct tables that `design/bem.py` computes with blade-element momentum theory from the report's blade and airfoil data.

Reference: J. Jonkman, S. Butterfield, W. Musial and G. Scott, *Definition of a 5-MW Reference Wind Turbine for Offshore System Development*, NREL/TP-500-38060, National Renewable Energy Laboratory, February 2009 (public, <https://www.nrel.gov/docs/fy09osti/38060.pdf>). Section and table numbers below refer to it.

## Models

| model | what it shows |
| --- | --- |
| `wind-turbine-steady` | A slow wind ramp from 4 to 25 m/s (0.02 m/s per s): the quasi-steady power curve, rotor speed and pitch. With `v_end = v_start` it is one operating point; `expected.json` runs it that way at 8 wind speeds. |
| `wind-turbine-step` | Wind steps every 60 s: 10, 12, 14, 18, 14, 12, 10 m/s. The torque law hands over to the pitch PI at rated, and the rotor overspeeds briefly after each step up. |
| `wind-turbine-gust` | The IEC 61400-1 extreme operating gust (class IB) on 12 m/s: a dip, a rise of 3.8 m/s within 5 s and a second dip. |
| `wind-turbine-turbulent` | 600 s of seeded turbulence at 18 m/s: pitch activity, the tower swaying at its 0.32 Hz mode and the shaft ringing at 2.2 Hz. |
| `wind-turbine-open-loop` | Fixed pitch and fixed generator torque at 8 m/s, which checks the aerodynamics: the tower released undeflected rings down with aerodynamic damping, and a 5 % torque step rings the drivetrain. |

All five share one plant, one scene (`scenes/wind-turbine.sdf`) and the same globals for the turbine's data.

## The bond graph

**Drivetrain (rotation).**
* `Rotor` 1-junction: the rotor inertia `RotorInertia` (I, 38,759,228 kg m², section 7.3) and the aerodynamic torque `AeroTorque` (MSe).
* `Shaft` 0-junction: the shaft torque. Its twist rate (the `Twist` 1-junction) loads the shaft stiffness `ShaftC` (C, 1/867,637,000 rad/(N m)) and the damping `ShaftR` (R, 6,215,000 N m s/rad). Both are low-speed-shaft equivalents (chapter 5).
* `Gearbox`: a TF of 97.
* `Gen` 1-junction: the generator inertia `GenInertia` (I, 534.116 kg m²) and the generator `Generator`, an MSe that absorbs the converter's torque.

**Tower (translation).** The `Nacelle` 1-junction holds the first fore-aft mode as one degree of freedom, the tower-top deflection:
* the modal mass `TowerMass` (I), the stiffness `TowerSpring` (C) and the damping `TowerDamper` (R, 1 % of critical, chapter 6);
* the thrust `Thrust` (MSe).

**Aerodynamics.**
* `RotorAero` computes the tip-speed ratio λ = ΩR/v_rel and the pitch in degrees. The two stdlib `Lookup2D` blocks `Cp` and `Ct` read the BEM tables at (λ, β).
* `RotorAero` then gives `Ta = ½ρπR² Cp v_rel³ / Ω` and `T = ½ρπR² Ct v_rel²`.
* The wind the rotor sees is `v_rel = v − ẋ`, where ẋ is the nacelle velocity from `NacelleVel`. This feedback is the aerodynamic damping of the tower.

**Controller** (chapter 7 and the DISCON source of Appendix C).
* `SpeedFilter`: a stdlib FirstOrder at 0.25 Hz on the generator speed.
* `Torque` (VSTorque): the generator-torque law.
  * region 1½: from 670 to 871 rpm;
  * region 2: `K ω²` with K = 0.0255764 N m/rpm²;
  * region 2½: the 10 % slip line;
  * region 3: constant power, 5.29661 MW mechanical, once the speed reaches 99 % of rated or the pitch reaches 1°.
* `PitchCtrl` (PitchPI): the collective-pitch PI.
  * KP = 0.01882681 s and KI = 0.008068634 at zero pitch;
  * the gain correction `GK = 1/(1 + β/6.302336°)`;
  * the integrator is clamped as in DISCON.
* `PitchAct` and `Converter` (both RateLimitedLag): the pitch actuator (8°/s) and the converter's torque loop (15 kN m/s). Each is a 50 ms lag inside its rate limit.

`ElecPower` is the electrical power in MW, 0.944 × torque × generator speed.

**Custom blocks** (`library/`). They are signal blocks only; all the energy storage and transfer is in stdlib bond-graph elements.

| block | why it is a custom block |
| --- | --- |
| `RotorAero` | the aerodynamic law: Ta and T from the table values, with floors at standstill |
| `VSTorque` | the five-region torque law of DISCON, a piecewise law with derived constants |
| `PitchPI` | the gain-scheduled PI with DISCON's integrator clamp |
| `RateLimitedLag` | a lag with a rate limit; the stdlib RateLimiter has a fixed 1 s time constant inside its band |
| `GustEOG` | the IEC extreme operating gust shape |

## Design scripts

```
uv run examples/wind-turbine/design/design.py        # BEM tables, tower mode, steady states -> design.json
uv run examples/wind-turbine/design/build_model.py   # models, scene, expected.json
```

* `design/nrel5mw.py`: the report's numbers, each with its section.
* `design/bem.py`: steady BEM on the 17 blade elements of Table 3-1, with the polars of Appendix B (`design/airfoils/*.csv`).
  * Prandtl tip and hub losses, the Buhl high-induction correction and tangential induction;
  * the 2.5° precone and the 5° shaft tilt;
  * Ning's guaranteed-convergence residual, solved with Brent's method.
  * The tables cover λ = 2 to 16 (step 0.5) and β = −1 to 27° (step 1°).
* `design/tower.py`: a 60-element Euler-Bernoulli model of the chapter-6 tower.
  * The tower tapers from 6 m to 3.87 m in diameter and from 35.1 mm to 24.7 mm in wall thickness, with E = 210 GPa and 8500 kg/m³. Its mass is 347,373 kg (the report gives 347,460).
  * The rotor and nacelle sit on top as one rigid body: 350 t, with the centre of mass 1.95 m above the tower top and a nodding inertia of 23.9e6 kg m².
  * The first mode, normalised to a unit tower-top deflection, gives the modal mass, stiffness and damping.
* `design/design.py`: the closed-loop steady states. It uses the same torque law, the same PI equilibrium and the same bilinear table lookup in numpy. It also linearises the open-loop plant to give its modes, and computes the two-inertia drivetrain frequency.

## Validation

### Cp peak

| | BEM (`design/bem.py`) | report (section 7.3) |
| --- | --- | --- |
| peak Cp, β = 0 | 0.4855 at λ = 7.70 | 0.482 at λ = 7.55 |
| Cp at λ = 7.55 | 0.4853 | 0.482 |

The BEM leaves out the tower, the wind shear and the blades' flexibility, so its rotor is 0.7 % better than FAST's.

### Steady states (closed loop)

The bg-sim values are the final values of the 8 `wind-turbine-steady-*` scenarios. Each starts 3 % below the design rotor speed and 1° below the design pitch, and runs 250 to 400 s.

| wind [m/s] | region | rotor speed [rpm] | pitch [deg] | Table 7-1 pitch [deg] | generator torque [N m] | electrical power [MW] | thrust [kN] |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 1.5 | 7.505 | 0 | | 5,597 | 0.403 | 172.9 |
| 8 | 2 | 9.189 | 0 | | 20,320 | 1.790 | 385.4 |
| 10 | 2 | 11.486 | 0 | | 31,749 | 3.497 | 602.2 |
| 11 | 2.5 | 11.903 | 0 | | 40,502 | 4.623 | 701.3 |
| 12 | 3 | 12.100 | 3.91 | 3.83 | 43,094 | 5.000 | 587.5 |
| 14 | 3 | 12.100 | 8.62 | 8.70 | 43,094 | 5.000 | 458.9 |
| 18 | 3 | 12.100 | 14.85 | 14.92 | 43,094 | 5.000 | 350.9 |
| 25 | 3 | 12.100 | 22.97 | 23.47 | 43,094 | 5.000 | 277.7 |

The bg-sim values match `design/design.py` (the same law in numpy) to better than 1e-5 relative; the
checks allow 0.2 % to 0.5 %. The report's rotor speed is 12.1 rpm throughout region 3, and Figure
9-1 shows about 9.2 rpm at 8 m/s and 11.5 rpm at 10 m/s, as here.

* **Rated wind.** It is 11.30 m/s here; the report gives 11.4 m/s. With this rotor the controller reaches 5 MW at 12.1 rpm already at 11.3 m/s, so at 11.4 m/s it pitches by 1.2°.
* **Region-3 pitch.** It agrees with Table 7-1 within 0.15° up to 20 m/s. It is 0.25° to 0.5° lower from 21 to 25 m/s, where the flexible blades of FAST twist and bend.
* **Power.** It is 5.000 MW electrical in region 3.

### Modes

| mode | analytic or design | bg-sim | report |
| --- | --- | --- | --- |
| drivetrain torsion | 2.2227 Hz, ζ 0.050 (two inertias: √(k (1/J_r + 1/(97² J_g))) = 13.965 rad/s) | open loop at 8 m/s (ring-down fit): 13.977 rad/s, ζ 0.051; turbulent run (spectrum peak): 2.13 Hz | 0.62 Hz (Table 9-1, with flexible blades: the blades' edgewise motion lowers it) |
| tower fore-aft | 0.3216 Hz (`tower.py`), ζ 0.048 in operation at 8 m/s (1 % structural + aerodynamic) | open loop at 8 m/s (ring-down fit): 2.023 rad/s = 0.3220 Hz, ζ 0.048 (linearised: 0.0484); turbulent run: 0.326 Hz | 0.3240 Hz FAST, 0.3195 Hz ADAMS (Table 9-1) |

* The rigid-blade drivetrain cannot reproduce the report's 0.62 Hz drivetrain mode: that mode is coupled to the blades' edgewise bending. The report's shaft damping of 6,215,000 N m s/rad was chosen for 5 % critical damping of the rigid two-inertia system, which `design.py` confirms (ζ = 0.0500).
* The checks read the tower and drivetrain modes from the open-loop ring-downs (a `damping` fit) and from the turbulent run (`fft_peak`).

### Energy

Every model has an `energy_ledger` check.
* The Tellegen residual of the port powers is zero to round-off.
* The stored energy (½P²/I of the three inertias and ½kq² of the shaft and the tower spring) changes by the work of the aerodynamic torque, the thrust and the generator, minus the damping.
* The storage balance holds to 1e-4 of the throughput in the steady, gust and open-loop runs and to 1e-3 in the step and turbulent runs, where the trapezoid rule over the output grid limits the integration of the faster transients.

## Wind

* **Ramp** and **steps**: stdlib `Ramp` and `TimeTable` (hold).
* **Gust**: `GustEOG`, the IEC 61400-1 ed. 3 extreme operating gust.
  * Its shape is `−0.37 V_gust sin(3πt/T)(1 − cos(2πt/T))` over T = 10.5 s.
  * Its magnitude is `V_gust = 3.3 σ1/(1 + 0.1 D/Λ1)`, with σ1 = 0.14 (0.75 V_hub + 5.6) (class B) and Λ1 = 42 m.
* **Turbulence**: seeded stdlib `BandLimitedWhiteNoise` (held every 0.25 s) through a first-order filter, which makes an Ornstein-Uhlenbeck process.
  * The standard deviation is the IEC class-B σ (2.67 m/s at 18 m/s).
  * The time constant is L/V with the Kaimal integral length L = 8.1 Λ1 = 340.2 m.
  * Its spectrum has the Kaimal level at low frequency and falls as f⁻² above 0.01 Hz, where the Kaimal spectrum falls as f^(−5/3).
  * It is one point of wind, with no rotor averaging and no shear. It is a simple stand-in for TurbSim, not a substitute.

## Simplifications

* **Rigid blades and tower top.** Only the tower's first fore-aft mode is flexible: no blade modes, no side-side mode and no tower torsion.
* **No yaw, no shear, no tower shadow.** The rotor axis is horizontal in the dynamics. The precone and tilt are only in the tables.
* **Thrust at the tower top.** The thrust acts at the tower top (generalised force T × 1), not at the hub 2.4 m higher, and without the rotor's weight moment.
* **Quasi-steady aerodynamics.** No dynamic inflow and no dynamic stall, so the aerodynamic torque responds instantly to the wind and the pitch.
* **Continuous controller.** DISCON is discrete, while this controller is continuous.
  * Its gain scheduling reads the measured pitch instead of the last command.
  * The pitch actuator is a 50 ms lag with the 8°/s limit; the report's FAST model uses an ideal pitch.
  * The generator torque has the same lag with the 15 kN m/s limit.
* **Electrical side.** Mechanical losses are not modelled. The electrical power is 0.944 × the mechanical power, as the report's generator efficiency.

## 3D view

The turbine stands at full scale in a field, with the wind blowing towards +x.
* The nacelle is yawed into the wind.
* The rotor turns at its real speed.
* The tower tilts about its base by 20 × its fore-aft deflection over its height, so the nacelle's motion is visible.
* The wind arrow upwind of the rotor scales and colours with the wind speed.
* One blade tip is coloured by the pitch.

## Sources and licence

* Turbine, tower, drivetrain and controller data: NREL/TP-500-38060 (a US government work, public).
* Airfoil polars (`design/airfoils/*.csv`): the report's AeroDyn tables (Appendix B), originally from the DOWEC project and corrected by J. Jonkman for rotational stall delay and with the Viterna method. They are taken from the OpenFAST regression-test repository, <https://github.com/OpenFAST/r-test> (`glue-codes/openfast/5MW_Baseline/Airfoils`, Apache License 2.0), and converted to CSV (alpha, cl, cd) without changing a value.
* BEM solution method: S. A. Ning, "A simple solution method for the blade element momentum equations with guaranteed convergence", *Wind Energy* 17 (2014) 1327-1345.
* Gust and turbulence parameters: IEC 61400-1 ed. 3 (2005), the normal turbulence model and the extreme operating gust.

## What to try

* `wind-turbine-steady`: run it and look at the power curve (power over the wind). Set `v_start = v_end` for one operating point.
* `wind-turbine-step`: lower `kp` on the dashboard and see the overspeed after the 14 to 18 m/s step grow.
* `wind-turbine-gust`: move `v_hub` below rated (9 m/s): there is no pitch action, so the rotor speeds up with the gust.
* `wind-turbine-turbulent`: change the `seed` or `v_mean` and compare the pitch activity.
* `wind-turbine-open-loop`: set `dtq` to −0.1 and watch the rotor speed up to a higher tip-speed ratio.
