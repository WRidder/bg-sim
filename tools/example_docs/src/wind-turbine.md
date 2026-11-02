@@ figures @project
{
  "diagram": {"kind": "diagram", "model": "wind-turbine-step"},
  "scene": {"kind": "scene", "model": "wind-turbine-step", "t": 200.0, "zoom": 1},
  "curve": {
    "kind": "plot", "model": "wind-turbine-steady", "xlabel": "wind [m/s]",
    "rows": [
      {"ylabel": "power [MW]", "x": "Wind/y", "xlabel": "wind [m/s]", "series": [{"signal": "ElecPower/y", "label": "electrical power"}], "hlines": [{"y": 5.0, "label": "5 MW"}]},
      {"ylabel": "rotor [rpm]", "x": "Wind/y", "xlabel": "wind [m/s]", "series": [{"signal": "RotorRPM/y", "label": "rotor speed"}], "hlines": [{"y": 12.1, "label": "12.1 rpm"}]},
      {"ylabel": "pitch [deg]", "x": "Wind/y", "xlabel": "wind [m/s]", "series": [{"signal": "Aero/beta_deg", "label": "pitch"}]},
      {"ylabel": "thrust [kN]", "x": "Wind/y", "xlabel": "wind [m/s]", "series": [{"signal": "ThrustkN/y", "label": "thrust"}]}
    ]
  }
}
@@ page @project turbine - | The NREL 5 MW turbine
# The NREL 5 MW reference turbine

This example models the NREL 5 MW reference wind turbine of Jonkman, Butterfield, Musial and Scott, *Definition of a 5-MW Reference Wind Turbine for Offshore System Development* (NREL/TP-500-38060, 2009). It covers the rotor's aerodynamics, the drivetrain, the tower's first fore-aft mode and the report's baseline controller.

| property | value | source |
| --- | --- | --- |
| rotor | 3 blades, 126 m diameter, hub at 90 m | Table 1-1 |
| operating range | cut-in 3 m/s, rated 11.4 m/s, cut-out 25 m/s; 6.9 to 12.1 rpm | Table 1-1 |
| rotor inertia | 38,759,228 kg m² | section 7.3 |
| generator inertia | 534.116 kg m² (high-speed shaft) | chapter 5 |
| gearbox | 97 : 1 | chapter 5 |
| shaft | 867,637,000 N m/rad, 6,215,000 N m s/rad (low-speed-shaft equivalents) | chapter 5 |
| generator | 94.4 % efficient: 5.29661 MW mechanical for 5 MW electrical | chapter 5 |
| tower | first fore-aft mode 0.324 Hz (FAST), 1 % damping | Table 9-1, chapter 6 |

![The model canvas|900](@fig:diagram)

![The 3D scene: the tower, the nacelle and the rotor; the wind arrow scales with the wind speed and the blade tip colours with the pitch|600](@fig:scene)

## The bond graph

The drivetrain is a rotational bond graph:
- `Rotor` 1-junction: the rotor inertia and the aerodynamic torque (an MSe);
- `Shaft` 0-junction: its twist rate loads the shaft's C and R;
- `Gearbox`: a TF of 97;
- `Gen` 1-junction: the generator inertia and the generator, an MSe that absorbs the converter's torque.

The tower is a translational 1-junction with the modal mass, stiffness and damping of its first fore-aft mode. The thrust (an MSe) drives it.

The aerodynamic block `RotorAero` reads the rotor speed and the nacelle velocity. Two stdlib `Lookup2D` blocks hold the BEM tables:

$$\lambda = \frac{\Omega R}{v_{rel}}, \qquad v_{rel} = v - \dot x, \qquad T_a = \frac{\tfrac12 \rho \pi R^2 C_p(\lambda, \beta)\, v_{rel}^3}{\Omega}, \qquad T = \tfrac12 \rho \pi R^2 C_t(\lambda, \beta)\, v_{rel}^2$$

The nacelle velocity in $v_{rel}$ is the aerodynamic damping of the tower: a nacelle moving downwind sees less wind and less thrust.

## The tables

`design/bem.py` computes $C_p$ and $C_t$ by blade-element momentum theory. It uses the report's 17 blade elements (Table 3-1) and its airfoil polars (Appendix B), with these corrections:
- Prandtl tip and hub losses;
- the Buhl high-induction correction;
- the 2.5° precone and the 5° shaft tilt.

The peak is $C_p$ = 0.4855 at $\lambda$ = 7.70, against the report's 0.482 at 7.55.

## The tower

`design/tower.py` is a finite-element model of the report's tower:
- a steel tube 87.6 m high, from 6 m to 3.87 m in diameter;
- 347 t of steel;
- the rotor and nacelle on top as one rigid body of 350 t.

Its first mode is 0.3216 Hz, between the report's FAST (0.3240 Hz) and ADAMS (0.3195 Hz) values. The modal mass is 442,803 kg and the stiffness 1.808 MN/m, normalised to the tower-top deflection.

Continue with [the controller](project:controller) and [the validation](project:validation).
@@ page @project controller turbine | The baseline controller
# The baseline controller

The controller is the report's chapter 7, as in its DISCON source (Appendix C). It works on the generator speed, low-pass filtered at 0.25 Hz.

**Generator torque** (`VSTorque`):

| region | generator speed | torque |
| --- | --- | --- |
| 1 | below 670 rpm | 0 |
| 1½ | 670 to 871 rpm | linear up to the region-2 curve |
| 2 | 871 rpm to the 2½ line | $K\omega^2$, K = 0.0255764 N m/rpm² (the optimal tip-speed ratio) |
| 2½ | up to 1161.963 rpm | the line of an induction machine with 10 % slip |
| 3 | from 1161.963 rpm, or pitch ≥ 1° | $P/\omega$ with P = 5.29661 MW |

**Pitch** (`PitchPI`): a PI on the speed error to 1173.7 rpm.

$$\beta_{cmd} = GK\,(K_P\, e + K_I \textstyle\int e\, dt), \qquad GK = \frac{1}{1 + \beta / 6.302336°}$$

The gains are $K_P$ = 0.01882681 s and $K_I$ = 0.008068634. The integrator is clamped to the pitch limits, as in DISCON.

**Actuators** (`RateLimitedLag`): the pitch is a 50 ms lag with the 8°/s rate limit. The converter's torque loop is a 50 ms lag with the 15 kN m/s rate limit.

Differences from DISCON:
- the controller is continuous, not discrete;
- the gain correction reads the measured pitch, not the last command;
- the actuators have a small lag (DISCON's FAST model has an ideal pitch).
@@ page @project validation turbine | Validation
# Validation

![The quasi-steady power curve of wind-turbine-steady|900](@fig:curve)

**Steady states.** The checks run `wind-turbine-steady` with a constant wind at 5, 8, 10, 11, 12, 14, 18 and 25 m/s. Each run checks:
- the rotor speed, the generator torque, the power, the thrust and the tower deflection against `design/design.py`, which runs the same controller law and tables in numpy;
- in region 3, the pitch against the report's Table 7-1.

| wind [m/s] | pitch here [deg] | Table 7-1 [deg] |
| --- | --- | --- |
| 12 | 3.91 | 3.83 |
| 14 | 8.62 | 8.70 |
| 18 | 14.85 | 14.92 |
| 25 | 22.97 | 23.47 |

Rated power is 5.000 MW from 11.3 m/s up.

**Modes.**
- The drivetrain torsion mode is 2.223 Hz with 5 % damping, the two-inertia formula $\omega = \sqrt{k(1/J_r + 1/(N^2 J_g))}$.
- The tower mode is 0.32 Hz. It is about 5 % damped in operation: 1 % structural plus the rotor's aerodynamic damping.
- [wind-turbine-open-loop](model:wind-turbine-open-loop) reads both from ring-downs, and [wind-turbine-turbulent](model:wind-turbine-turbulent) from the spectrum.

The report's drivetrain mode (0.62 Hz) involves the blades' edgewise bending, which this rigid-rotor model leaves out.

**Energy.** The port-power ledger of every model closes:
- the Tellegen residual is zero to round-off;
- the kinetic and elastic energy changes by the work of the aerodynamic torque, the thrust and the generator, minus the damping.
@@ figures wind-turbine-steady
{
  "diagram": {"kind": "diagram", "model": "wind-turbine-steady"},
  "run": {
    "kind": "plot", "model": "wind-turbine-steady", "xlim": [0, 1160],
    "rows": [
      {"ylabel": "wind [m/s]", "series": [{"signal": "Wind/y", "label": "wind"}]},
      {"ylabel": "power [MW]", "series": [{"signal": "ElecPower/y", "label": "electrical power"}]},
      {"ylabel": "rpm, deg", "series": [{"signal": "RotorRPM/y", "label": "rotor speed [rpm]"}, {"signal": "Aero/beta_deg", "label": "pitch [deg]"}], "legend": true}
    ]
  }
}
@@ page wind-turbine-steady overview - | Overview
# Power curve

The NREL 5 MW turbine with its baseline controller on a slow wind ramp from 4 to 25 m/s (0.02 m/s per second). The turbine passes through its operating points almost in equilibrium, so the run traces the power curve. See [the turbine](project:turbine) for the model.

![The model canvas|900](@fig:diagram)

![The ramp|900](@fig:run)

## What you see

- Below rated (11.3 m/s), [Torque](block:Torque) holds the optimal tip-speed ratio: [Aero/lambda](signal:Aero/lambda) stays at 7.58 and [Cp/y](signal:Cp/y) at 0.485, while the power grows with $v^3$.
- From rated on, [PitchCtrl](block:PitchCtrl) pitches the blades ([Aero/beta_deg](signal:Aero/beta_deg)) to hold 12.1 rpm and [ElecPower/y](signal:ElecPower/y) at 5 MW. The thrust ([ThrustkN/y](signal:ThrustkN/y)) peaks at rated and falls above it.

## What to try

- Set `v_end` equal to `v_start` on the dashboard for one steady operating point.
- Plot [ElecPower/y](signal:ElecPower/y) over [Wind/y](signal:Wind/y) (the saved plot "Power curve").

## Key parameters

`v_start`, `v_end`, `t_ramp` and `ramp_time` set the ramp. The turbine globals (`J_rotor`, `k_shaft`, `m_tower`, ...) are shared by all models.
@@ figures wind-turbine-step
{
  "diagram": {"kind": "diagram", "model": "wind-turbine-step"},
  "run": {
    "kind": "plot", "model": "wind-turbine-step", "xlim": [0, 420],
    "rows": [
      {"ylabel": "wind [m/s]", "series": [{"signal": "Wind/y", "label": "wind"}]},
      {"ylabel": "rotor [rpm]", "series": [{"signal": "RotorRPM/y", "label": "rotor speed"}], "hlines": [{"y": 12.1, "label": "rated"}]},
      {"ylabel": "pitch [deg]", "series": [{"signal": "Aero/beta_deg", "label": "pitch"}]},
      {"ylabel": "power [MW]", "series": [{"signal": "ElecPower/y", "label": "electrical power"}]},
      {"ylabel": "tower [m]", "series": [{"signal": "TowerSpring/q", "label": "tower-top deflection"}]}
    ]
  }
}
@@ page wind-turbine-step overview - | Overview
# Wind steps across rated

The wind steps every 60 s: 10, 12, 14, 18, 14, 12 and 10 m/s. See [the turbine](project:turbine) and [the controller](project:controller).

![The step responses|900](@fig:run)

## What you see

- At 10 m/s the turbine is in region 2. The step to 12 m/s takes it to rated: [Torque/region](signal:Torque/region) switches to 3 and the pitch starts to act.
- Each step up overspeeds the rotor ([RotorRPM/y](signal:RotorRPM/y)) for a few seconds until the pitch PI has caught up. The power follows the speed, because the torque law holds constant power, not constant torque.
- The thrust step sets the tower swinging at 0.32 Hz ([TowerSpring/q](signal:TowerSpring/q)). The aerodynamic damping stops it within a few cycles.

## What to try

- Lower the PI gain `kp` on the dashboard and compare the overspeed after the step to 18 m/s.
- Move `v_low` below 8 m/s to see region 2 and region 1½.

![The model canvas|900](@fig:diagram)
@@ figures wind-turbine-gust
{
  "scene": {"kind": "scene", "model": "wind-turbine-gust", "t": 26.0, "zoom": 1},
  "run": {
    "kind": "plot", "model": "wind-turbine-gust", "xlim": [10, 60],
    "rows": [
      {"ylabel": "wind [m/s]", "series": [{"signal": "Wind/y", "label": "wind"}, {"signal": "Aero/v_rel", "label": "relative to the nacelle"}], "legend": true},
      {"ylabel": "rotor [rpm]", "series": [{"signal": "RotorRPM/y", "label": "rotor speed"}]},
      {"ylabel": "pitch [deg]", "series": [{"signal": "Aero/beta_deg", "label": "pitch"}, {"signal": "PitchCmdDeg/y", "label": "command", "style": "--"}], "legend": true},
      {"ylabel": "power [MW]", "series": [{"signal": "ElecPower/y", "label": "electrical power"}]},
      {"ylabel": "thrust [kN]", "series": [{"signal": "ThrustkN/y", "label": "thrust"}]}
    ]
  }
}
@@ page wind-turbine-gust overview - | Overview
# Extreme operating gust

The IEC 61400-1 extreme operating gust on a mean wind of 12 m/s, just above rated. The gust magnitude is class IB for this rotor, 5.2 m/s. The wind first dips by 1.4 m/s, then rises 3.8 m/s above the mean within 5 s, and dips again. [Gust](block:Gust) is the gust shape. See [the controller](project:controller).

![The gust|900](@fig:run)

## What you see

- In the dip the speed falls below rated, and the torque law drops back to region 2½ ([Torque/region](signal:Torque/region)).
- In the rise the rotor overspeeds while the pitch ([Aero/beta_deg](signal:Aero/beta_deg)) follows its command ([PitchCmdDeg/y](signal:PitchCmdDeg/y)).
- The thrust peak pushes the tower; [Aero/v_rel](signal:Aero/v_rel) shows the nacelle's motion in the wind the rotor sees.

## What to try

- Set `v_hub` to 9 m/s: below rated there is no pitch action, and the rotor speeds up with the gust.
- Set `v_hub` to 20 m/s: the pitch is large and the turbine reacts much more quietly.

## 3D view

The rotor turns at its real speed. The tower's sway is drawn 20 times larger than it is. The wind arrow grows with the wind.

![3D view during the gust|600](@fig:scene)
@@ figures wind-turbine-turbulent
{
  "run": {
    "kind": "plot", "model": "wind-turbine-turbulent", "xlim": [0, 600],
    "rows": [
      {"ylabel": "wind [m/s]", "series": [{"signal": "Wind/y", "label": "wind"}]},
      {"ylabel": "pitch [deg]", "series": [{"signal": "Aero/beta_deg", "label": "pitch"}]},
      {"ylabel": "rotor [rpm]", "series": [{"signal": "RotorRPM/y", "label": "rotor speed"}]},
      {"ylabel": "power [MW]", "series": [{"signal": "ElecPower/y", "label": "electrical power"}]},
      {"ylabel": "tower [m]", "series": [{"signal": "TowerSpring/q", "label": "tower-top deflection"}]}
    ]
  }
}
@@ page wind-turbine-turbulent overview - | Overview
# Turbulent wind at 18 m/s

Ten minutes of seeded turbulence at 18 m/s, with the IEC class-B standard deviation of 2.67 m/s. The turbulence is band-limited white noise ([WhiteNoise](block:WhiteNoise)) through a first-order filter ([Turbulence](block:Turbulence)). Its time constant is the Kaimal length scale over the wind speed, 18.9 s. It is one point of wind, a simple stand-in for a full turbulence field.

![Ten minutes of turbulence|900](@fig:run)

## What you see

- The pitch ([Aero/beta_deg](signal:Aero/beta_deg)) works all the time to hold 12.1 rpm.
- The power follows the rotor speed within a few percent.
- The tower-top deflection ([TowerSpring/q](signal:TowerSpring/q)) follows the thrust with its 0.32 Hz mode on top. The shaft twist ([ShaftC/q](signal:ShaftC/q)) rings at the 2.22 Hz drivetrain mode. The checks find both peaks in the spectra.

## What to try

- Change the global `seed` for another realisation, or `v_mean` for another wind.
@@ figures wind-turbine-open-loop
{
  "run": {
    "kind": "plot", "model": "wind-turbine-open-loop", "xlim": [0, 320],
    "rows": [
      {"ylabel": "tower [m]", "xlim": [0, 40], "series": [{"signal": "TowerSpring/q", "label": "tower-top deflection"}]},
      {"ylabel": "twist [mrad]", "xlim": [118, 126], "series": [{"signal": "ShaftC/q", "label": "shaft twist", "scale": 1000}]},
      {"ylabel": "rotor [rpm]", "series": [{"signal": "RotorRPM/y", "label": "rotor speed"}]},
      {"ylabel": "lambda", "series": [{"signal": "Aero/lambda", "label": "tip-speed ratio"}]}
    ]
  }
}
@@ page wind-turbine-open-loop overview - | Overview
# Open loop: the aerodynamics and the modes

The turbine at 8 m/s with a fixed pitch ([PitchFixed](block:PitchFixed), 0°) and a fixed generator torque ([TorqueCmd](block:TorqueCmd)), with no controller. It starts in the region-2 steady state of `design/design.py`. See [the turbine](project:turbine).

![Ring-downs and the torque step|900](@fig:run)

## What you see

- **Tower.** The tower is released undeflected. It rings about its static deflection under the thrust (0.213 m) at 0.322 Hz. The damping ratio is 4.8 %: 1 % structural, the rest the rotor's aerodynamic damping through [Aero/v_rel](signal:Aero/v_rel).
- **Drivetrain.** At 120 s the generator torque steps up by 5 %. The shaft twist ([ShaftC/q](signal:ShaftC/q)) rings at 2.22 Hz with 5 % damping.
- **Rotor.** The rotor then slows to a new equilibrium, 8.70 rpm at a tip-speed ratio of 7.17, where the aerodynamic torque matches the new generator torque.

The checks compare each of these with the linearised plant and the steady states of `design/design.py`.

## What to try

- Set `dtq` to −0.1: the rotor speeds up to a higher tip-speed ratio.
- Raise `v_ol`: the tower's aerodynamic damping grows with the wind.
