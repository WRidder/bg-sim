@@ figures cessna-open-loop
{
  "diagram": {"kind": "diagram", "model": "cessna-open-loop"},
  "scene": {"kind": "scene", "model": "cessna-open-loop", "t": 4.0, "zoom": 9},
  "long": {
    "kind": "plot", "model": "cessna-open-loop", "xlim": [0, 60],
    "rows": [
      {"ylabel": "alpha [deg]", "xlim": [0, 5], "series": [{"signal": "SP/Air/alpha_deg", "label": "short period"}]},
      {"ylabel": "airspeed [m/s]", "series": [{"signal": "Ph/Air/vt", "label": "phugoid"}]},
      {"ylabel": "altitude [m]", "series": [{"signal": "Ph/Air/h", "label": "phugoid"}]}
    ]
  },
  "lat": {
    "kind": "plot", "model": "cessna-open-loop", "xlim": [0, 12],
    "rows": [
      {"ylabel": "beta [deg]", "series": [{"signal": "DR/Air/beta_deg", "label": "dutch roll"}]},
      {"ylabel": "bank [rad]", "series": [{"signal": "Ro/Air/phi", "label": "roll mode"}, {"signal": "Sl/Air/phi", "label": "spiral"}], "legend": true},
      {"ylabel": "roll rate [1/s]", "xlim": [0, 1.0], "ylim": [-6.5, 0.0], "series": [{"signal": "RateRo/lambda", "label": "roll mode"}],
       "hlines": [{"y": -5.5735, "label": "eigenvalue -5.57"}], "legend": true},
      {"ylabel": "spiral rate [1/s]", "ylim": [-0.015, 0.0], "series": [{"signal": "RateSl/lambda", "label": "spiral"}],
       "hlines": [{"y": -0.010686, "label": "eigenvalue -0.0107"}], "legend": true}
    ]
  }
}
@@ page cessna-open-loop overview - | Overview
# Cessna 172 open loop

A Cessna 172P built from the data of JSBSim's c172p, released on each of its five rigid-body modes. Five copies of the aircraft are trimmed in level flight at 100 KTAS and 5000 ft. Each starts displaced along the eigenvector of one mode of the linearised aircraft: the short period (1 deg of alpha), the phugoid (2 m/s of speed), the dutch roll (1 deg of sideslip), the roll mode (2 deg of bank) and the spiral (5 deg of bank).

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [SP](block:SP), [Ph](block:Ph), [DR](block:DR), [Ro](block:Ro), [Sl](block:Sl) | one aircraft each (a subsystem): the airframe, the engine and propeller, the aerodynamics and the controls held at the trim |
| [RateRo](block:RateRo), [RateSl](block:RateSl) | $\lambda = \dot\phi/\phi$ of the bank angle: on a real mode this is its eigenvalue |

## What to try

1. Press **Run**. The short period dies out in about a second. The phugoid trades speed for height with a 25 s period. The dutch roll rings for about 10 s.
2. Plot [RateRo/lambda](signal:RateRo/lambda). It reads the roll-mode eigenvalue, $-5.57$ 1/s, while the bank decays.
3. The spiral is stable but slow: half the bank is gone after about 65 s.

## 3D view

The five aircraft fly side by side over a striped reference floor. The ailerons, elevator, rudder and flaps are separate meshes on their hinge lines, and the propeller turns at the engine's speed. Picture at 4 s:

![3D view at t = 4 s|600](@fig:scene)

Continue with [the aircraft](page:aircraft) and [the results](page:results).
@@ page cessna-open-loop aircraft overview | The aircraft
# The aircraft

## Airframe and forces

The airframe is the stdlib `RigidBody3D` on a `Free3D` joint, with a mass of 1088.6 kg (2400 lb). Its inertia is c172p's empty tensor plus its point masses. Two kinds of force enter it as `ExternalWrenchSpatial` modulated sources:

- `C172Aero`: the aerodynamic wrench, the c172p build-up of lift, drag, side force and the three moments;
- `Propeller`: the thrust and torque at the hub.

The aerodynamic build-up includes:

- the flap and ground-effect tables;
- the rate and alpha-dot terms;
- a stall hysteresis on the lift.

`C172AirData` computes the inputs of the build-up from the body pose and twist:

$$\alpha = \arctan\frac{w}{\sqrt{u^2 + V_f^2}}, \qquad \beta = \arctan\frac{v}{\sqrt{u^2 + w^2 + V_f^2}}, \qquad \bar q = \tfrac12 \rho V^2$$

Here $V_f = 1$ m/s keeps both angles finite at standstill.

## Engine and propeller

The engine and propeller form a rotational bond graph. Its one inertia is a `Rotor3D` (the crankshaft and the propeller, 2.26 kg m²), mounted on the airframe, so its gyroscopic moment and torque reaction act on the body. On its 1-junction sit two elements.

The first is `PistonEngine`, a modulated effort source: JSBSim's FGPiston model of the 160 hp Lycoming O-320. Its torque comes from the manifold pressure (a lagged state), the air mass flow and the mixture efficiency, minus the pumping and friction losses.

The second is `Propeller`, a resistance whose torque and thrust are

$$\tau = C_P(J)\,\frac{\rho n^2 D^5}{2\pi}, \qquad T = C_T(J)\,\rho n^2 D^4, \qquad J = \frac{u}{n D}$$

with the 75-inch fixed-pitch propeller's tables. These are JSBSim's prop_75in2f with a correction that is not JSBSim data: at low advance ratio $C_T$ is raised (by 46 % at $J = 0$) and $C_P$ lowered (by 15 %), fading out by $J = 0.725$, a fit to the POH's static rpm, climb and take-off (the example's README, "The propeller fit"). Cruise and maximum speed keep the JSBSim tables.

## Validation source

`design/c172_ref.py` is an independent numpy implementation of the same physics. `design/c172_lin.py` trims and linearises it. Its modes are the expected values of the next page.
@@ page cessna-open-loop results aircraft | Results
# Results

![Longitudinal modes|900](@fig:long)

![Lateral modes and the mode rates|900](@fig:lat)

| mode | scipy (linearised) | bg-sim (fitted on the nonlinear run) |
| --- | --- | --- |
| short period | $\zeta$ 0.604, $\omega_n$ 5.96 rad/s | 0.602, 5.97 |
| phugoid | $\zeta$ 0.085, period 24.9 s | 0.085, $\omega_n$ 0.2535 |
| dutch roll | $\zeta$ 0.183, $\omega_n$ 2.16 rad/s | 0.183, 2.158 |
| roll | $-5.57$ 1/s | [RateRo/lambda](signal:RateRo/lambda) $-5.573$ at 0.3 s |
| spiral | $-0.0107$ 1/s | [RateSl/lambda](signal:RateSl/lambda) $-0.0107$ at 0 s |

The damping fits fit a damped sinusoid to the signal (the run-check kind `damping`). The curves agree with the nonlinear scipy run to between 1e-8 and 1e-12 at every checked instant.

The spiral's rate wanders between $-0.008$ and $-0.011$ 1/s after the start (over 120 s). The 5 deg bank also excites the phugoid, which modulates the speed and so the spiral's rate.
@@ figures cessna-sim
{
  "diagram": {"kind": "diagram", "model": "cessna-sim"},
  "scene": {"kind": "scene", "model": "cessna-sim", "t": 30.0, "zoom": 17},
  "run": {
    "kind": "plot", "model": "cessna-sim", "xlim": [0, 120],
    "rows": [
      {"ylabel": "KIAS", "series": [{"signal": "Status/kias", "label": "indicated airspeed"}], "hlines": [{"y": 45.0, "label": "rotate 45 KCAS"}, {"y": 75.0, "label": "climb 75"}]},
      {"ylabel": "height [ft]", "series": [{"signal": "Status/agl_ft", "label": "above the runway"}], "hlines": [{"y": 50.0, "label": "50 ft"}]},
      {"ylabel": "wheel load [N]", "xlim": [0, 45], "series": [{"signal": "C172/Contact_nose/fn", "label": "nose"}, {"signal": "C172/Contact_left/fn", "label": "left"}, {"signal": "C172/Contact_right/fn", "label": "right"}], "legend": true},
      {"ylabel": "attitude [deg]", "series": [{"signal": "Status/theta_deg", "label": "pitch"}, {"signal": "Status/phi_deg", "label": "bank"}], "legend": true},
      {"ylabel": "rpm", "series": [{"signal": "C172/Engine/n_rpm", "label": "engine"}]}
    ]
  }
}
@@ page cessna-sim overview - | Overview
# Cessna 172 simulator model

The flyable Cessna 172P, standing on runway 36 with the engine at idle and flaps 10. Pressing **Run** starts a scripted take-off ([Demo](block:Demo)):

1. full power, with the nose wheel holding the centre line;
2. rotation at 45 KCAS;
3. a climb at 75 KCAS, with the flaps up at 65 ft;
4. a turn to the east at 75 s.

The same model is the FMU of the flight simulator `apps/cessna-sim`.

![The model canvas|900](@fig:diagram)

| block | role |
| --- | --- |
| [C172](block:C172) | the aircraft (a subsystem): the airframe, three landing-gear legs, the engine and propeller, the aerodynamics, the flaps |
| [Demo](block:Demo) | the scripted pilot; in the FMU the host's pilot replaces it |
| [AP](block:AP) | the autopilot: a wing leveller or heading hold, and altitude hold, adding to the yoke |
| [Status](block:Status) | what the instruments show: KIAS, vertical speed, slip, turn rate, the on-ground flag |

## What to try

1. Press **Run** and watch the [wheel loads](signal:C172/Contact_nose/fn): the nose wheel unloads at rotation, then the mains at lift-off.
2. Use the dashboard sliders to override the pilot: the yoke, pedals, throttle, mixture, flap detent, trim and toe brakes.
3. Switch the autopilot on with its sliders: the roll mode, the heading bug, altitude hold.

## 3D view

The airfield has runway 36, a taxiway, an apron, a hangar, a tower and a windsock. The control surfaces, the flaps, the steered nose wheel and the propeller move. Picture at 30 s, climbing out at 25 ft:

![3D view at t = 30 s|600](@fig:scene)

Continue with [the landing gear](page:gear), [the results](page:results) and [the FMU](page:fmu).
@@ page cessna-sim gear overview | Landing gear
# Landing gear

Each leg (nose, left, right) is a `GearContact`: a power-conserving modulated transformer between the airframe's multibond and three translational bonds, one per contact direction.

| direction | flow | elements on its 1-junction |
| --- | --- | --- |
| runway normal | the penetration rate of the contact point | `StrutSpring` (C) and `StrutDamper` (R): c172p's strut coefficients, with a smooth unloading |
| along the wheel | the rolling speed | `WheelFriction` (R): the rolling resistance plus the toe brake (main wheels) |
| across the wheel | the side-slip speed | `WheelSide` (R): the cornering force from JSBSim's magic formula of the slip angle |

The nose wheel's rolling direction is turned by the steering angle, 10 deg at full pedal. The transformer keeps

$$p.e \cdot p.f + n.e\, n.f + x.e\, x.f + y.e\, y.f = 0$$

so the gear only exchanges energy with its elements: the springs store it, the dampers, the tyres and the brakes dissipate it.

At rest the CG sits 1.2546 m above the runway, with the nose-up attitude of the tricycle gear. The model's start globals hold this equilibrium, computed by `design/perf.py` (`ground_state`).
@@ page cessna-sim results gear | Results
# Results

![The demo run|900](@fig:run)

| check | bg-sim | reference |
| --- | --- | --- |
| on the runway until rotation (14 s) | CG height 1.2546 to 1.2725 m | |
| 50 ft above the runway | 37.0 s, 2657 ft from brake release | scipy reference 37.0 s |
| [Status/kias](signal:Status/kias) at 60 s, 100 s | 77.3, 77.3 kt | scipy within 1e-6 kt |
| bank in the turn | at most 18.9 deg | limit 20 deg |
| heading hold (60 deg) and altitude hold (1000 m) | within 2.6 m | `cessna-sim-autopilot` |
| full-throttle climb at the best-rate speed (84 KCAS), 300 m | 703 fpm | POH 700 fpm at sea level (rtol 0.05) |
| full throttle at 8000 ft | 124.1 KTAS | POH 120 KTAS at 75 % power |

The climb matches the handbook because the propeller's low-speed thrust and power tables are fitted to it (the engine keeps its rated 160 hp). With JSBSim's own propeller tables the model climbed at 583 fpm here and needed 1492 ft of ground roll instead of the POH's 892 (now 855). The demo pilot does not fly the POH's short-field technique, so its 50 ft point is not the POH's 1628 ft. The example's README has the comparison with the POH and the fit.
@@ page cessna-sim fmu overview | The FMU
# The FMU

`examples/export_cessna.jl` exports this model with the host interface:

- 16 inputs, `ExportInputPass` markers: the yoke, the pedals, the throttle, the mixture, the flap detent, the trim, the two toe brakes, the autopilot modes, the heading bug and altitude, and the wind;
- 38 outputs, `ExportOutput` markers: the pose, the instruments, the engine, the surfaces, the wheel loads;
- 20 parameters: the start state, set together from a trim or the runway equilibrium.

The analysis picks RK4 at 2.5 ms, 2 substeps per 5 ms communication step. A step takes about 10 µs, with no allocation after instantiate.

`examples/export_cessna_check.py` drives the FMU in fmpy through a take-off roll, a braked run-up and nose-wheel steering in a crosswind, and compares every output with bg-sim:

- every output agrees to about 1e-4 of its peak;
- the exception is the stall flag, whose threshold switch the FMU evaluates once per step.

The host `apps/cessna-sim` flies the FMU. It is a Panda3D world with an airfield and has three cameras (chase, cockpit, tower) and a six-pack panel. Input comes from the keyboard, a joystick, pedals or a throttle quadrant.
