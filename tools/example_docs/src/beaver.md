@@ figures beaver-modes
{
  "diagram": {"kind": "diagram", "model": "beaver-modes"},
  "scene": {"kind": "scene", "model": "beaver-modes", "t": 4.0, "zoom": 16},
  "run": {
    "kind": "plot", "model": "beaver-modes", "xlim": [0, 60],
    "rows": [
      {"ylabel": "V [m/s]", "series": [{"signal": "Phugoid/Air/V", "label": "Phugoid"}], "legend": true},
      {"ylabel": "alpha [deg]", "xlim": [0, 6], "series": [{"signal": "ShortPeriod/Air/alpha_deg", "label": "ShortPeriod"}], "legend": true},
      {"ylabel": "beta [deg]", "series": [{"signal": "DutchRoll/Air/beta_deg", "label": "DutchRoll"}], "legend": true},
      {"ylabel": "phi [deg]", "series": [{"signal": "Roll/Air/phi_deg", "label": "Roll"}, {"signal": "Spiral/Air/phi_deg", "label": "Spiral"}], "legend": true}
    ]
  }
}
@@ page beaver-modes overview - | Overview
# Beaver modes

The de Havilland DHC-2 'Beaver' of the TU Delft *Flight Dynamics and Control* toolbox (FDC, M. O. Rauw), on the aerodynamic and engine model that Tjee & Mulder identified from flight tests. Five aircraft are trimmed at the thesis' point, 45 m/s at 6000 ft with the flaps up and the engine at 1800 rpm. Each is released on one eigenvector of the coupled linear model.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Phugoid](block:Phugoid), [ShortPeriod](block:ShortPeriod), [DutchRoll](block:DutchRoll), [Roll](block:Roll), [Spiral](block:Spiral) | one airframe each, an instance of the library subsystem `BeaverAirframe`: rigid body, air data, aerodynamics, propulsion, wrench, drivetrain |
| [Trim_de](block:Trim_de) ... [Trim_pz](block:Trim_pz) | the FDC trim: elevator, ailerons, rudder, flaps, rpm, manifold pressure |
| [GrowRoll](block:GrowRoll), [GrowSpiral](block:GrowSpiral) | $\lambda = \dot\phi/\phi$: on a real mode this is the eigenvalue |

## What to try

1. Press **Run**. The phugoid swings with a 23.7 s period, the short period dies out within 2 s, and the Dutch roll within about 6 s.
2. Plot [GrowRoll/lambda](signal:GrowRoll/lambda) and [GrowSpiral/lambda](signal:GrowSpiral/lambda): they read $-5.133$ and $-0.0429$ 1/s.
3. Switch the **drivetrain** on with the dashboard slider. The modes hardly change: the shaft dynamics are fast and well damped.

## 3D view

The view keeps the phugoid aircraft (yellow) framed; the others fly 25 m to the sides. The floor is a reference plane 150 m below. The dots behind each aircraft are its path over the last few seconds, and the propellers turn at 1/20 of their speed.

![3D view at t = 4 s|600](@fig:scene)

Continue with [the airframe](page:airframe) and [the results](page:results).
@@ page beaver-modes airframe overview | The airframe
# The airframe

## Rigid body

The mass is 2288.231 kg, with $I_x = 5368.39$, $I_y = 6928.93$, $I_z = 11\,158.75$ and $J_{xz} = 117.64$ kg m². The product of inertia tilts the principal axes by 1.16° about y. The stdlib `RigidBody3D` sits on the principal axes, and a `FixedTransform3DNeutral` (the Mount) carries the wrench from the geometric body frame to them.

## Coefficients and wrench

`BeaverAirData` gives the airspeed, $\alpha$, $\beta$, the body rates, the Euler angles and the FDC atmosphere, with the gravity falling off with altitude. `BeaverAero` holds the polynomial model of Tjee & Mulder. For example:

$$C_Z = C_{Z_0} + C_{Z_\alpha}\alpha + C_{Z_{\alpha^3}}\alpha^3 + C_{Z_q}\frac{q\bar c}{V} + C_{Z_{\delta_e}}\delta_e + C_{Z_{\delta_e\beta^2}}\delta_e\beta^2 + C_{Z_{\delta_f}}\delta_f + C_{Z_{\alpha\delta_f}}\alpha\delta_f$$

`BeaverPropulsion` adds the forces and moments of engine operation. They are polynomials in the dimensionless pressure rise over the propeller,

$$\Delta p_t = 0.08696 + 191.18\,\frac{P}{\tfrac12\rho V^3}.$$

`BeaverWrench` turns them into the six inputs of the wrench source on the body. It also applies FDC's two corrections: the gravity at altitude, and the side force of $\dot\beta$.

## Drivetrain

The engine and the propeller are a rotational bond graph on a 1-junction, the crank:

| element | role |
| --- | --- |
| an MSe | the engine torque $P(p_z, n, \rho)/\omega$ |
| an I | the crank and propeller inertia |
| a second MSe | the torque of the constant-speed propeller, from its governor |
| a speed sensor | the shaft speed |

The global `drivetrain` selects the thrust power: 0 is the source's algebraic power at the prescribed rpm (exact FDC), 1 is the shaft power of the bond graph.
@@ page beaver-modes results airframe | Results
# Results

![The five modes|900](@fig:run)

| mode | bg-sim (fit or growth rate) | coupled linear model | THESIS Table 5-3 (decoupled) |
| --- | --- | --- | --- |
| phugoid | damping fit of [Phugoid/Air/V](signal:Phugoid/Air/V) | $-0.01757 \pm 0.2651j$ | $-0.01614 \pm 0.2631j$ |
| short period | fit of [ShortPeriod/Air/alpha_deg](signal:ShortPeriod/Air/alpha_deg) | $-2.1584 \pm 2.4207j$ | $-2.1606 \pm 2.4112j$ |
| Dutch roll | fit of [DutchRoll/Air/beta_deg](signal:DutchRoll/Air/beta_deg) | $-0.4791 \pm 0.9662j$ | $-0.4770 \pm 0.9763j$ |
| roll | [GrowRoll/lambda](signal:GrowRoll/lambda) | $-5.1332$ | $-5.1351$ |
| spiral | [GrowSpiral/lambda](signal:GrowSpiral/lambda) | $-0.04289$ | $-0.04573$ |

The decoupled 4-state modes of the reference reproduce Table 5-3 and FDC's own linear model. The coupled model includes the strong longitudinal-lateral cross-coupling of the Beaver, which comes from the propeller's slipstream; that is what the nonlinear aircraft does. The thesis' lateral modes differ in the third digit because the 1993 model applied the $\dot\beta$ correction with the opposite sign (the README explains it). The README also lists the trim against Table 5-1 and the linearisation against FDC's A and B matrices.
@@ figures beaver-steps
{
  "diagram": {"kind": "diagram", "model": "beaver-steps"},
  "scene": {"kind": "scene", "model": "beaver-steps", "t": 20.0, "zoom": 16},
  "run": {
    "kind": "plot", "model": "beaver-steps", "xlim": [0, 60],
    "rows": [
      {"ylabel": "V [m/s]", "series": [{"signal": "Elevator/Air/V", "label": "Elevator"}, {"signal": "Flap/Air/V", "label": "Flap"}, {"signal": "Rpm/Air/V", "label": "Rpm"}, {"signal": "Manifold/Air/V", "label": "Manifold"}], "legend": true},
      {"ylabel": "beta [deg]", "series": [{"signal": "Aileron/Air/beta_deg", "label": "Aileron"}, {"signal": "Rudder/Air/beta_deg", "label": "Rudder"}], "legend": true},
      {"ylabel": "phi [deg]", "series": [{"signal": "Aileron/Air/phi_deg", "label": "Aileron"}, {"signal": "Rudder/Air/phi_deg", "label": "Rudder"}, {"signal": "Flap/Air/phi_deg", "label": "Flap"}, {"signal": "Manifold/Air/phi_deg", "label": "Manifold"}], "legend": true}
    ]
  }
}
@@ page beaver-steps overview - | Overview
# Beaver control steps

Six Beavers start at the FDC trim (45 m/s, 6000 ft), and each gets one of the inputs of the thesis' figures 5-2 to 5-7:

| aircraft | input |
| --- | --- |
| [Elevator](block:Elevator), [Aileron](block:Aileron), [Rudder](block:Rudder) | a 3° block for 2 s, from 1 s |
| [Flap](block:Flap) | 3° of flap in 3 s |
| [Rpm](block:Rpm) | +200 rpm in 4 s |
| [Manifold](block:Manifold) | +2 inch Hg of manifold pressure in 2 s |

![The model canvas|900](@fig:diagram)

The responses show the cross-coupling the thesis points out: the elevator block also yaws and rolls the aircraft, the phugoid follows the aileron and rudder inputs, and flaps or power make the aircraft roll (the slipstream's rolling moment grows with $\alpha^2 \Delta p_t$).

![Responses|900](@fig:run)

## What to try

1. Change the sizes of the inputs with the sliders.
2. Switch the **drivetrain** on. The shaft of the Rpm aircraft now lags the rpm command, with the governor's 2 rad/s, ζ 0.7 loop, instead of following it exactly.

![3D view at t = 20 s|600](@fig:scene)
@@ figures beaver-sim
{
  "diagram": {"kind": "diagram", "model": "beaver-sim"},
  "scene": {"kind": "scene", "model": "beaver-sim", "t": 45.0, "zoom": 18},
  "run": {
    "kind": "plot", "model": "beaver-sim", "xlim": [0, 150],
    "rows": [
      {"ylabel": "H [m]", "series": [{"signal": "Beaver/Air/H", "label": "altitude"}, {"signal": "h_ref_m/y", "label": "reference"}], "legend": true},
      {"ylabel": "[deg]", "series": [{"signal": "Beaver/Air/psi_deg", "label": "heading"}, {"signal": "Beaver/Air/phi_deg", "label": "bank"}, {"signal": "Beaver/Air/theta_deg", "label": "pitch"}], "legend": true},
      {"ylabel": "V [m/s]", "series": [{"signal": "Beaver/Air/V", "label": "airspeed"}]},
      {"ylabel": "rpm", "series": [{"signal": "Beaver/Engine/n_shaft", "label": "shaft"}, {"signal": "Controls/n", "label": "lever"}], "legend": true}
    ]
  }
}
@@ page beaver-sim overview - | Overview
# The flyable Beaver

The FDC Beaver with the bond-graph drivetrain on, cockpit controls and the FDC autopilot. Its inputs and outputs are export markers, so it exports as an FMU for a flight-simulator host.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [Beaver](block:Beaver) | the airframe subsystem, with wind inputs |
| [Controls](block:Controls) | the cockpit: column, pedals, flaps, elevator trim, manifold pressure, rpm lever; travel limits |
| [PitchAP](block:PitchAP) | the pitch attitude hold (PAH) and the altitude hold (ALH) |
| [RollAP](block:RollAP) | the roll attitude hold (RAH), the heading hold (HH) and the turn coordinator |
| [ElevServo](block:ElevServo), [AilServo](block:AilServo), [RudServo](block:RudServo) | the autopilot servos: a 0.09 s lag with the airspeed-dependent gain of FDC's actuator and cable models |
| `col_pitch` ... `wind_d` | the FMU inputs (`ExportInputPass`): they pass the demo stimulus through in BG-Sim |

## The demo

1. At 5 s: climb power (25 inch Hg, 2000 rpm), and the attitude hold 4° up.
2. At 30 s: the heading hold turns the aircraft to 090 at the 30° bank limit.
3. At 70 s: the altitude hold captures 150 m above the start.
4. At 85 s: the power goes back to the trim setting.

![The demo|900](@fig:run)

## What to try

- Move the climb, heading and altitude sliders.
- Set the pitch or roll autopilot to 0 and fly the column pulses by hand.
- Switch the **drivetrain** off: the rpm then follows the lever exactly, as in the source.

The elevator, ailerons, flaps and rudder move in the 3D view, and the propeller turns at 1/20 of the shaft speed.

![3D view at t = 45 s, in the turn|600](@fig:scene)
