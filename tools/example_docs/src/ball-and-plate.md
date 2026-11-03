@@ figures @project
{
  "scene": {"kind": "scene", "model": "ball-and-plate-track", "t": 14.0, "zoom": 3},
  "diagram": {"kind": "diagram", "model": "ball-and-plate-pid"}
}
@@ page @project rig - | The ball-and-plate rig
# The ball-and-plate rig

A **1 inch steel ball** (67 g) rolls on a **0.35 m acrylic plate**. The plate sits on a gimbal and two
rotary servos tilt it through cranks and push rods, one per axis. An overhead camera finds the ball
at **30 frames/s, one frame late**. The layout is that of the Quanser 2 DOF Ball Balancer: two SRV02
servos beside a plate on a 2 DOF gimbal, with an overhead camera.

![The rig in the 3D view: base, servos with cranks and push rods, the plate with its grid and the two reference paths, the steel ball with its painted bands and the red target ring|700](@fig:scene)

| part | value | source |
| --- | --- | --- |
| ball | r = 12.7 mm, 67.0 g, solid (J = 2/5 m r²) | chrome steel, 7810 kg/m³ |
| plate | 0.35 m × 0.35 m × 6 mm acrylic, 0.875 kg, centre of mass on the gimbal centre 0.16 m above the base | PMMA, 1190 kg/m³ |
| servo | R = 2.6 Ω, L = 0.18 mH, k_t = k_m = 7.68e-3, gearbox 70:1, J_eq = 2.08e-3 kg m², B_eq = 0.015 N m s/rad, 4096 counts/rev | SRV02 User Manual, Table 5 |
| linkage | crank 25.4 mm, lever 0.16 m: sin α = ρ sin θ, ρ = 0.159 | Sidi et al. 2024, eq. 8 |
| camera | 0.625 mm per pixel, 30 frames/s, one frame of latency, 0.3 mm noise | Quanser product page; latency and noise assumed |
| drive | ±10 V, 0.05 V dead band | dead band assumed |
| contact | Hunt-Crossley, μ = 0.4, rolling resistance crr = 0.002 | assumed |

## The bond graph

The plant is the same bond graph in every model:

- **Plate.** A `RigidBody3D` on a `Universal3D` gimbal. The first axis is world y, the second the
  plate's x axis.
- **Ball.** A free `RigidBody3D` with its `PoseIntegrator3D`. The inertia factor is the model global
  `k_ball`: 0.4 for the solid ball, 2/3 for a hollow one.
- **Contact.** The two bodies meet in `RollingSphere`, a contact between two bodies. The plate feels
  the ball, and the plate's rotation rate and angular acceleration enter the ball's motion.
- **Servos.** Each servo is `MSe` → electrical 1-junction (`R`, `I`) → `GY` → gearbox `TF` →
  output-shaft 1-junction (`I`, `R`, `AngleSensor`) → crank `MTF` → push-rod compliance (a `C`/`R`
  pair on a 0-junction) → gimbal drive. The modulus of the `MTF` is the crank kinematics
  dα/dθ = ρ cos θ/√(1 − ρ² sin² θ), computed by `CrankLinkage`.

![The PID model: plant, servos, camera chains, controllers, task and push|900](@fig:diagram)

## The control loops

The **firmware** of each servo runs at 500 Hz: an encoder, a PD on the encoder angle (50 rad/s,
damping 0.8) and a dead band. The **outer loop** runs at the camera's 30 Hz and gives the servo
angle set-points. The **camera** chain is the ball's world position plus seeded noise, rounded to
the pixel and delayed by one frame.

- **Cascaded PID** (`PlatePID`): Kp = 3.6 rad/m, Ki = 0.72, Kd = 2.52, with a filtered derivative on
  the measurement and conditional integration. A grid search in `design/design.py` picked these
  gains: overshoot at most 8 %, stable with 2 frames of delay, then the shortest settling time.
- **LQR + Kalman** (`PlateLQG`): a steady-state Kalman filter on [x, v, θ, ω, last camera
  reading], fed by the camera and the encoder. It estimates where the ball is now, not where the
  camera saw it. An LQR with integral action and a reference feed-forward follows: the plate angle
  comes from the reference's acceleration and jerk.

## Comparison

| | PID | LQR + Kalman |
| --- | --- | --- |
| x step 0.1 m, rig (design) | settling 1.65 s (1.37), overshoot 0.8 % (1.9 %) | settling 1.97 s (1.6), overshoot 1.4 % (1.5 %) |
| 1 s set-point filter | settling 2.2 s | settling 0.92 s |
| 0.6 N push | peak 61 mm | peak 46 mm |
| circle 0.08 m, RMS per axis | 40 mm | 1.9 mm |
| figure-8, RMS per axis | 40 mm | 1.8 mm |
| 6 frames (200 ms) of camera delay | overshoot 24 %, settling 4.1 s | overshoot 8.8 %, settling 2.7 s |

The PID settles a hard step a little faster. The LQR copes better with delay. With its
feed-forward, the LQR tracks moving references 20 times more closely. The remaining 2 mm come from
the rolling resistance, which the feed-forward does not model. Without it, the rig tracks the
circle to 0.2 mm, as the linear design predicts.

The models: [free roll](model:ball-and-plate-free), [swinging plate](model:ball-and-plate-swing),
[PID](model:ball-and-plate-pid), [LQR](model:ball-and-plate-lqr), [tracking](model:ball-and-plate-track).
@@ figures ball-and-plate-free
{
  "roll": {
    "kind": "plot", "model": "ball-and-plate-free", "xlim": [0, 2],
    "rows": [
      {"ylabel": "x on the plate [m]", "series": [{"signal": "Contact/u1", "label": "Contact/u1"}], "hlines": [{"y": 0.0, "label": "centre: 1.5663 s analytic"}], "legend": true},
      {"ylabel": "energy [J]", "series": [{"signal": "Energy/Ek", "label": "kinetic"}, {"signal": "Energy/Ekrot", "label": "rotational (2/7)", "style": "--"}], "legend": true},
      {"ylabel": "slip [mm/s]", "series": [{"signal": "Contact/slip", "label": "Contact/slip", "scale": 1000}]}
    ]
  }
}
@@ page ball-and-plate-free overview - | What you're looking at
# Free roll on a tilted plate

**Scenario.** The servos are replaced by stiff `C`/`R` locks on the gimbal drives
([SpringX](block:SpringX), [DamperX](block:DamperX)), which hold the plate at **1°** about y. The
spring of the X lock starts preloaded with the ball's weight torque. The ball is released at rest
**0.15 m** from the centre, uphill.

**What it checks.**

- **Roll time.** A rolling solid sphere accelerates at a = 5/7 g sin α = 0.12229 m/s², so it
  reaches the centre after **1.5663 s**. The model ([Contact/u1](signal:Contact/u1)) gives
  1.5662 s.
- **Rotational energy.** It is 2/7 of the kinetic energy
  ([Energy/Ekrot](signal:Energy/Ekrot) / [Energy/Ek](signal:Energy/Ek)).
- **No slip.** The slip ([Contact/slip](signal:Contact/slip)) creeps at only 1.25e-5 m/s, the
  regularisation of the friction.
- **Energy book.** [Energy/Ebal](signal:Energy/Ebal) (stored energy plus the contact losses) stays
  constant to 2e-9 J.
- **Hollow ball.** The check run with `k_ball` = 2/3 gives 3/5 g sin α and a time of 1.7089 s.

![Free roll: position, kinetic energy and slip|900](@fig:roll)

**What to try.** On the dashboard:

- Set the ball inertia to 0.667, a hollow ball of the same mass, and it rolls slower.
- Raise the rolling resistance to 0.02 and the ball barely moves: a ball rests on a tilt smaller
  than crr.

The rig: [the ball-and-plate rig](project:rig).
@@ figures ball-and-plate-swing
{
  "swing": {
    "kind": "plot", "model": "ball-and-plate-swing", "xlim": [0, 4],
    "rows": [
      {"ylabel": "plate angle [deg]", "series": [{"signal": "Gimbal/q1out", "label": "alpha", "scale": 57.29577951308232}]},
      {"ylabel": "x [m]", "series": [{"signal": "Contact/u1", "label": "full 3D rolling"}, {"signal": "LinX/y", "label": "linearised 5/7 g sin(alpha)", "style": "--"}], "legend": true},
      {"ylabel": "normal force [N]", "series": [{"signal": "Contact/f_n", "label": "Contact/f_n"}]}
    ]
  }
}
@@ page ball-and-plate-swing overview - | What you're looking at
# The swinging plate: what the linear model leaves out

**Scenario.** An `MSf` drives the plate through a stiff lock spring
([Shaker](block:Shaker), [ShakerRate](block:ShakerRate)), so the plate angle swings as
α = −2° cos(2π · 2 Hz · t). The ball starts at rest **0.10 m** from the axis.

**The two answers.** The signal chain [LinX](block:LinX) integrates the textbook model
x'' = 5/7 g sin α of the same plate angle. Its mean is zero, so in that model the ball just jiggles
around 0.10 m. The bond graph contains the plate's rotation, and the ball drifts outwards by
**59 mm in 4 s** ([Drift/y](signal:Drift/y)). This is the centrifugal term x α̇² of the full
equation

ẍ = 5/7 (g sin α + x α̇² − (h + 2r/5) α̈),

which `design/design.py` integrates for the ball centre h = 15.7 mm above the axis. The drift
agrees with that equation to **0.1 %** at 1, 2, 3 and 4 s. The plate's angular acceleration also
modulates the normal force by ±0.05 N ([Contact/f_n](signal:Contact/f_n)).

![Plate angle, both positions and the normal force|900](@fig:swing)

The rig: [the ball-and-plate rig](project:rig).
@@ figures ball-and-plate-pid
{
  "steps": {
    "kind": "plot", "model": "ball-and-plate-pid", "xlim": [0, 20],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "PoseBall/g[5]", "label": "x"}, {"signal": "Task/xd", "label": "x set-point", "style": "--"}, {"signal": "PoseBall/g[6]", "label": "y"}, {"signal": "Task/yd", "label": "y set-point", "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "plate angle [deg]", "series": [{"signal": "Gimbal/q1out", "label": "about y", "scale": 57.29577951308232}, {"signal": "Gimbal/q2out", "label": "about x", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"},
      {"ylabel": "servo voltage [V]", "series": [{"signal": "ServoX/V", "label": "X"}, {"signal": "ServoY/V", "label": "Y"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page ball-and-plate-pid overview - | What you're looking at
# Cascaded PID

**Scenario.** The ball starts at rest on the level plate at the centre. The set-points are:

- x to **0.10 m** at 1 s;
- y to **0.08 m** at 6 s;
- both back to the centre at 11 s;
- a **0.6 N, 50 ms** push in y at 15 s ([Push](block:Push)).

**The loops.** [PIDX](block:PIDX) and [PIDY](block:PIDY) run at 30 Hz on the camera reading
([FrameX/y](signal:FrameX/y), one frame old) and give the servo set-points. [ServoX](block:ServoX)
and [ServoY](block:ServoY) close the 500 Hz servo loops on the encoders.

**Against the design.** The x step settles (±2 mm) in **1.65 s** with **0.8 %** overshoot. The
linear design in `design/design.py` gives 1.37 s and 1.9 %. The rig adds the dead band, the pixel
rounding, the camera noise and the rolling resistance. The resistance lets the ball rest on a tilt
of up to 0.002 rad, so the ball stops within about 1 mm and the integral removes the rest. The push
moves the ball by 61 mm, and it is back within 4 mm 5 s later.

![Steps and push: position, plate angles and servo voltages|900](@fig:steps)

**What to try.** Lower Kp on the dashboard. Switch the task to the circle or the figure-8: without
feed-forward the PID lags about 40 mm behind. Set the push to 1.2 N. Set the ball inertia to 0.667,
a hollow ball, which accelerates 16 % less per plate angle.

The rig and the comparison with the LQR: [the ball-and-plate rig](project:rig).
@@ figures ball-and-plate-lqr
{
  "steps": {
    "kind": "plot", "model": "ball-and-plate-lqr", "xlim": [0, 20],
    "rows": [
      {"ylabel": "position [m]", "series": [{"signal": "PoseBall/g[5]", "label": "x"}, {"signal": "Task/xd", "label": "x set-point", "style": "--"}, {"signal": "PoseBall/g[6]", "label": "y"}, {"signal": "Task/yd", "label": "y set-point", "style": "--"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "x [mm] near the step", "series": [{"signal": "PoseBall/g[5]", "label": "true x", "scale": 1000}, {"signal": "LQGX/xhat", "label": "Kalman estimate", "scale": 1000, "style": "--"}, {"signal": "FrameX/y", "label": "camera", "scale": 1000, "style": ":"}], "legend": true, "legend_loc": "right"},
      {"ylabel": "normal force [N]", "series": [{"signal": "Contact/f_n", "label": "Contact/f_n"}]}
    ]
  },
  "zoom": {
    "kind": "plot", "model": "ball-and-plate-lqr", "xlim": [1.0, 2.0],
    "rows": [
      {"ylabel": "x [mm]", "series": [{"signal": "PoseBall/g[5]", "label": "true x", "scale": 1000}, {"signal": "LQGX/xhat", "label": "Kalman estimate (now)", "scale": 1000, "style": "--"}, {"signal": "FrameX/y", "label": "camera (one frame old)", "scale": 1000, "style": ":"}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page ball-and-plate-lqr overview - | What you're looking at
# LQR with a Kalman filter

**Scenario.** The same scenario as the PID model: steps at 1 s, 6 s and 11 s, and a push at 15 s.

**The controller.** [LQGX](block:LQGX) and [LQGY](block:LQGY) each hold a steady-state Kalman
filter. Its model knows that the camera ([FrameX/y](signal:FrameX/y)) is one frame late, so the
estimate [LQGX/xhat](signal:LQGX/xhat) is where the ball is now. An LQR with integral action and
anti-windup follows the filter. All gains come from `design/design.py`.

**Against the design.** The x step settles in **1.97 s** with **1.4 %** overshoot; the design
gives 1.6 s and 1.5 %. The integral is slow (50 s), so the ball first stops within about 2 mm,
where the rolling resistance holds it. The push moves the ball by only 46 mm (PID: 61 mm). In the
design, the LQR tolerates 8 frames of camera delay and the PID 7. On the rig with 6 frames, the LQR
overshoots by 9 % and the PID by 24 %.

**The hop.** At 11 s both set-points jump back while the ball is 0.1 m off the axis. The LQR
commands a 0.6 rad servo step, and the plate edge drops faster than gravity can follow. The ball
leaves the plate for about 20 ms: [Contact/f_n](signal:Contact/f_n) reads zero, and the ball slips
briefly on landing. Set the **set-point filter** on the dashboard to 1 s and the hop goes away. With
the feed-forward riding on the filtered reference, the steps then settle in 0.9 s.

![Steps, the Kalman estimate and the normal force|900](@fig:steps)

![Between 1 and 2 s: the camera lags one frame, the estimate does not|900](@fig:zoom)

The rig and the comparison: [the ball-and-plate rig](project:rig).
@@ figures ball-and-plate-track
{
  "xy": {
    "kind": "plot", "model": "ball-and-plate-track", "xlim": [-0.13, 0.13], "xlabel": "x [m]",
    "rows": [
      {"ylabel": "y [m]", "x": "PoseBall/g[5]", "series": [{"signal": "PoseBall/g[6]", "label": "ball"}, {"signal": "Task/yd", "label": "reference (against the ball's x)", "style": "--"}], "legend": true}
    ]
  },
  "err": {
    "kind": "plot", "model": "ball-and-plate-track", "xlim": [0, 30],
    "rows": [
      {"ylabel": "error [mm]", "series": [{"signal": "LQGX/err", "label": "x (estimate)", "scale": 1000}, {"signal": "LQGY/err", "label": "y (estimate)", "scale": 1000}], "legend": true, "legend_loc": "right"},
      {"ylabel": "plate angle [deg]", "series": [{"signal": "Gimbal/q1out", "label": "about y", "scale": 57.29577951308232}, {"signal": "Gimbal/q2out", "label": "about x", "scale": 57.29577951308232}], "legend": true, "legend_loc": "right"}
    ]
  }
}
@@ page ball-and-plate-track overview - | What you're looking at
# Tracking a figure-8

**Scenario.** The LQR with the Kalman filter follows a **figure-8** ([Task](block:Task), task 3):
x = 0.10 sin(ωt), y = 0.06 sin(2ωt), with an 8 s period. The path grows from the centre over
3 s. Task 2 is a **circle** of radius 0.08 m and period 6 s.

**Feed-forward.** The task block also outputs the reference's velocity, acceleration and jerk. The
controller tilts the plate to the angle that gives the reference acceleration (a/K_bb), plus the
servo lag (τ_s ω) and the ball's weight on the servo. Feedback only corrects what is left.

**Result.** After the growth phase, the RMS error is **1.9 mm in x and 1.7 mm in y**. For the
circle it is 1.8 and 1.9 mm. Most of that comes from the rolling resistance, which the feed-forward
does not know about. A check run without it reaches **0.2 mm**, the value of the linear design. The
PID without feed-forward lags about 40 mm on both paths.

![The figure-8 on the plate (XY)|600](@fig:xy)

![Tracking error and plate angles|900](@fig:err)

**What to try.** Switch the task to the circle. Set the ball inertia to 0.667: the feed-forward
assumes a solid ball, so the plate tilts too little and the error grows. Use the **3D view** to
watch the red target ring and the ball.

The rig and the comparison: [the ball-and-plate rig](project:rig).
