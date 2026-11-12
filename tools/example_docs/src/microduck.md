@@ figures @project
{
  "bench": {"kind": "diagram", "model": "xl330-step"}
}
@@ page @project robot - | The microduck and its XL330 servos
# The microduck and its XL330 servos

The **microduck** of Pollen Robotics is a 25 cm, 0.74 kg biped with 15 Dynamixel XL330-M288-T servos. Its walking policies are trained in MuJoCo (microduck_rl) against **BAM**, Rhoban's identified model of the XL330. This example rebuilds that actuator as a bond graph and puts it into the robot:

| model | what |
| --- | --- |
| [Servo step on the bench](model:xl330-step) | one XL330 swings the 100 g test arm of microduck_rl, against the BAM simulator |
| [Torque-speed curve](model:xl330-torque-speed) | one XL330 driven by a speed source, against the analytic curve |
| [Robot on a stand](model:microduck-hang) | the 14-joint robot held by the trunk, the legs stepping to a squat pose |
| [Robot holding HOME](model:microduck-stand) | the robot on the floor with the servos holding the STAND pose and no policy |
| Rigid servo on the bench (`xl330-rigid-step`) | the bench with `XL330Rigid`, the servo of the policy robot |
| Rigid servo torque-speed (`xl330-rigid-torque-speed`) | the torque-speed curve of `XL330Rigid` |
| Robot for a policy (`microduck-policy`) | the robot the walking policy drives in the browser demo, exported as an FMU |

The servo is the **library subsystem** `XL330` (`library/XL330.bgsub.json`). It is drawn once and placed once per joint: one instance on each bench and 14 in each robot, all on the battery bus. A second subsystem, `XL330Rigid`, keeps the firmware, the winding and the friction but drops the gear play, as the training simulation does; it is the servo of the robot that the published walking policy drives. Each instance can set its own P gain, friction scale, rotor inertia, backlash and initial angle (the subsystem's pins), as the domain randomisation of training does.

![The bench model: goal, supply, one XL330 instance and the pendulum arm|900](@fig:bench)

## Inside the XL330

- **Firmware (Position Control Mode).** The goal waits `t_latency` (20 ms) in a delay line. The P law turns the angle error into a PWM duty, $d = k_{p} \frac{4096}{2\pi} \frac{e}{256 \cdot 885}$, with I = D = 0 as on the robot. BAM's current limiter clamps the duty to the window $(k_t\omega \pm R\, i_\text{limit})/V$, and the PWM limit clamps it to $\pm 1$.
- **Motor and gear.** An `MTF` H-bridge (modulus = duty) takes power from the bus. A winding `R` and an `EMConverter` drive the rotor `I`, and a gear `TF` of 1/288.4 leads to the output. Every value is the BAM M6 fit: $k_t$ and $R$ at the output, and the armature reflected to the rotor.
- **Friction.** `BamFriction` is a nonlinear `R` with the M6 law: a load-dependent Coulomb budget that grows with the motor torque and the external torque, a Stribeck part near rest, and viscous friction.
- **Backlash.** `SmoothBacklash` gives 2° of play between the gear output and the horn. The encoder reads the horn, so the P law sees the play, as on the real servo.

Continue with [parameters and sources](page:parameters) and [limits](page:limits).
@@ page @project parameters robot | Parameters and sources
# Parameters and sources

The README of the example has the full table, with a status (sourced, assumed or modelling choice) for every number. `design/xl330.py` and `design/robot.py` hold the numbers.

- **Sourced.** Rhoban BAM `xl330/m6.json`, at the commit microduck_rl pins: $k_t$ = 0.3660 N·m/A, $R$ = 2.811 Ω, armature 1.808e-3 kg·m², and the M6 friction terms. From BAM's `XL330Actuator`: the P-gain divisor 256, the PWM limit 885 and the current limit 1.75 A. From the ROBOTIS e-manual: gear 288.4 and 4096 counts/rev. From microduck: the P gain 200, I = D = 0, a 2S Li-ion pack (6.6 to 8.2 V) and the HOME pose. From microduck_rl: the latency range of 15 to 30 ms, 2° of backlash, the friction and armature randomisation, the MJCF masses and inertias, the soles and the foot friction 1.0.
- **Assumed.** The latency is 20 ms, inside the training range. The gear tooth stiffness is 100 N·m/rad and its damping 0.1 N·m·s/rad. The battery resistance is 0.1 Ω and the bus capacitance 1 mF. The contact stiffness and damping are also assumed.
- **Derived.** The P stiffness is 0.554 N·m/rad at 7.4 V and kp 200, the same as the MJCF position actuators (kp 0.55). The stall torque is 0.641 N·m at 1.75 A, and the free speed 20.2 rad/s.
@@ page @project limits robot | Limits
# Limits

The goal is a model in which a policy behaves as it does on the real robot. **That transfer is not shown here.** The checks cover the actuator and the body without a policy. The limits, most important first:

1. **No real robot.** Nothing here is checked against hardware. The published walking policy runs on the exported `microduck-policy` FMU in the browser demo; that shows what the policy does on this model, not that it would transfer. At zero command it stands (10 s, at most 2.24° of tilt). At half forward (0.2 m/s asked) it shifts its weight and stands. At full forward (0.4 m/s asked) it walks, at about half that speed and curving right (1.8 m in 10 s, heading turned 56°), without falling. One run each, in this model only.
2. **Differences from the training simulator** (mjlab with BAM), each of which can change a gait: no backlash (velstand was trained with 2° of play in every joint, `XL330Rigid` has none, to keep the model real-time); a fixed 20 ms latency where training randomises 15 to 30 ms; an ideal supply; the deploy action scale 0.9 where training used 1.0; no one-step lag of the observed joint velocities; a flat floor; this model's contact law, four points per sole; friction smoothed instead of BAM's.
3. **Current limit.** Training and this model use BAM's 1.75 A window. The robot's impact-guard firmware limits the current to 1.0 A, derates the PWM with speed and brakes; none of that is modelled.
4. **Two BAM fits disagree**, by 6 % in $k_t$, 11 % in $R$ and 13 % in the armature. The newer fit is not the one the policies were trained with.
5. **Latency** is assumed (20 ms). The newer BAM fit identifies 10 ms.
6. **Backlash and gear stiffness** are training assumptions and guesses.
7. **Firmware** is modelled as a continuous law: no control period, and no encoder or PWM quantisation.
8. **Friction** is regularised: a held joint creeps slowly instead of sticking. Its external torque is the transmitted gear torque, where BAM uses gravity.
9. **No winding inductance and no heating.** The 8.2 V pack is above the servo's 6 V rating, as on the robot.
10. **Contacts.** Each sole has four contact points. In the policy robot the trunk, the head and the shins have frictionless bumper points too, so a fall lands; in the others nothing else touches the ground.
@@ figures xl330-step
{
  "diagram": {"kind": "diagram", "model": "xl330-step"},
  "run": {
    "kind": "plot", "model": "xl330-step",
    "rows": [
      {"ylabel": "angle [rad]", "series": [{"signal": "Goal/y", "label": "goal"}, {"signal": "Servo/Encoder/y", "label": "encoder"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "Servo/Current/y", "label": "Servo/Current/y", "color": "#d95f02"}], "hlines": [{"y": 1.75, "label": "i_limit 1.75 A"}, {"y": -1.75, "label": ""}]},
      {"ylabel": "torque [N m]", "series": [{"signal": "Servo/MotorTorque/y", "label": "motor kt i"}, {"signal": "Servo/Transmit/y", "label": "to the arm"}, {"signal": "Servo/Friction/tau_f", "label": "friction"}], "legend": true}
    ]
  }
}
@@ page xl330-step overview - | Overview
# XL330 on the bench

One [XL330](block:Servo) swings the 100 g test arm of microduck_rl (the arm's centre of mass is 96.6 mm from the axis). The [goal](block:Goal) steps from 0 to 1 rad at 0.1 s and back at 0.9 s. The [supply](block:Supply) is 7.4 V. The arm is a `Revolute3D` joint `J` with a rigid body `B`, so gravity pulls it back to hanging.

![Diagram|800](@fig:diagram)

This instance pins the backlash to 0, because the BAM simulator it is checked against has a rigid gear.

## Run it

1. Press **Run** and plot [Servo/Encoder/y](signal:Servo/Encoder/y) against the [goal](signal:Goal/y). The arm starts moving 20 ms after the goal: that is the firmware latency.
2. Change the global `kp_fw` to 50, the limp gain of the robot. The arm stops well short of 1 rad.
3. Set `v_bat` to 6.6 V (an empty pack): the P stiffness falls with the voltage.

See [Results](page:results).
@@ page xl330-step results overview | Results
# Results

![Goal and encoder, winding current, torques|900](@fig:run)

During the swing up the current peaks at 1.46 A, just under the 1.75 A limit: at kp 200 an error of 1 rad asks for 58 % PWM. Near the goal, the P law and gravity balance: the encoder holds 0.910 rad, short of 1 rad, with a holding torque of 0.050 N·m.

## Checks against the BAM simulator

`design/xl330.py` ports BAM's `simulate.py` (the M6 friction with its stopping logic, a rigid gear, the same latency, a time step of 10 µs). On this bench:

| quantity | BAM simulator | bg-sim |
| --- | --- | --- |
| angle at 0.3 s | 0.7691 rad | 0.7750 rad |
| angle held at the goal (0.5 s) | 0.9084 rad | 0.9102 rad |
| holding torque at 0.5 s | 0.0508 N·m | 0.0499 N·m |
| angle at 1.0 s (falling back) | 0.5913 rad | 0.5755 rad |
| rest angle after the return | -0.01736 rad | -0.0172 rad |

The largest difference is 16 mrad, during the fast swings. The delay line samples every 5 ms and ramps a goal step over one tick, half a tick early. The rest angles agree to 0.2 mrad, which is a test of the friction budget. `expected.json` checks nine encoder angles within 0.02 rad, the rest angle within 2 mrad and the holding torque within 5 mN·m.
@@ figures xl330-torque-speed
{
  "run": {
    "kind": "plot", "model": "xl330-torque-speed", "xlim": [0.5, 8.0],
    "rows": [
      {"ylabel": "horn speed [rad/s]", "series": [{"signal": "Servo/HornSpeed/y", "label": "horn speed"}]},
      {"ylabel": "torque [N m]", "series": [{"signal": "Servo/MotorTorque/y", "label": "motor kt i"}, {"signal": "Servo/Transmit/y", "label": "at the horn"}, {"signal": "Servo/Friction/tau_f", "label": "friction"}], "legend": true},
      {"ylabel": "current [A], duty", "series": [{"signal": "Servo/Current/y", "label": "current"}, {"signal": "Servo/PwmLimit/y", "label": "duty"}], "legend": true}
    ]
  }
}
@@ page xl330-torque-speed overview - | Overview
# Torque-speed curve of the XL330

A dynamometer (an [MSf](block:Dyno) driven by a [ramp](block:SpeedRamp)) turns the horn of one [XL330](block:Servo) from -8 to 20 rad/s. The [goal](block:Goal) is far ahead, so the firmware asks for full PWM all the time. The torque at the horn, [Servo/Transmit/y](signal:Servo/Transmit/y), traces the servo's torque-speed curve:

- up to 6.8 rad/s, the **current limit**: the duty follows the upper edge of BAM's window, the current stays at 1.75 A, and the motor torque at $k_t \cdot 1.75 = 0.641$ N·m;
- above it, the **back-EMF line** at full PWM, $k_t (V - k_t \omega)/R$, down to the free speed $V/k_t = 20.2$ rad/s;
- minus the friction: the load-dependent M6 budget, large near rest (the Stribeck part), plus the viscous part.

Try `i_limit` = 1.0 A, the limit of the impact-guard firmware on the robot, and `v_bat` between 6.6 and 8.2 V.
@@ page xl330-torque-speed results overview | Results
# Results

![Speed, torques, current and duty during the ramp|900](@fig:run)

`design/torque_speed.py` computes the curve on paper. The duty is $\min(1, (k_t\omega + R\, i_\text{limit})/V)$, and the horn torque is $k_t i$ minus the M6 friction, with the external torque solved by fixed-point iteration, minus the armature torque of the ramp:

| horn speed | analytic | bg-sim |
| --- | --- | --- |
| -6 rad/s | 0.8411 N·m | 0.8410 N·m |
| 1 rad/s | 0.4134 N·m | 0.4137 N·m |
| 5 rad/s | 0.4308 N·m | 0.4309 N·m |
| 10 rad/s | 0.2914 N·m | 0.2916 N·m |
| 18 rad/s | -0.0310 N·m | -0.0308 N·m |

`expected.json` checks eleven speeds within 0.5 mN·m. The differences come from the smoothed kinks of the friction law. It also checks that the current is 1.75 A on the flat part and never above it.

Against the direction of rotation (negative speeds), the friction and the motor torque add up at the horn: the servo brakes with more than its stall torque.
@@ figures microduck-hang
{
  "run": {
    "kind": "plot", "model": "microduck-hang", "xlim": [0, 1.2],
    "rows": [
      {"ylabel": "left leg [rad]", "series": [{"signal": "Goal_left_hip_pitch/y", "label": "hip pitch goal", "style": "--"}, {"signal": "left_hip_pitch/Encoder/y", "label": "hip pitch"}, {"signal": "Goal_left_knee/y", "label": "knee goal", "style": "--"}, {"signal": "left_knee/Encoder/y", "label": "knee"}, {"signal": "Goal_left_ankle/y", "label": "ankle goal", "style": "--"}, {"signal": "left_ankle/Encoder/y", "label": "ankle"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "left_hip_pitch/Current/y", "label": "hip pitch"}, {"signal": "left_knee/Current/y", "label": "knee"}, {"signal": "left_ankle/Current/y", "label": "ankle"}, {"signal": "BatCurrent/y", "label": "battery"}], "legend": true}
    ]
  }
}
@@ page microduck-hang overview - | Overview
# The microduck on a stand

The robot hangs by its trunk, the way a real robot is brought up. Its 15 bodies come from the microduck_rl MJCF, with 14 `Revolute3D` joints. One [XL330](block:left_knee) instance per joint is named after the joint. Every `vbus` port sits on one battery bus: a [battery](block:Battery) behind a [resistance](block:Rbat), and a [bus capacitor](block:Cbus).

At 0.2 s the hip-pitch, knee and ankle goals step from HOME to a pose that would lower a standing trunk by 15 mm (inverse kinematics in `design/robot.py`). The other joints hold HOME.

What to watch:

- the firmware **latency**: [left_knee/Latency/y](signal:left_knee/Latency/y) steps 20 ms after the goal;
- the **P gain**: the knee draws at most 0.87 A, so at kp 200 the gain, not the 1.75 A limit, sets the speed of the move;
- the **backlash**: [left_knee/Backlash/phi](signal:left_knee/Backlash/phi) sits on one flank (+1°) under the weight of the shank;
- the **gravity sag**: every joint ends short of its goal.

Raise `kp_fw` and the move gets faster; lower `i_limit` to 1.0 A and the limit starts to matter.
@@ page microduck-hang results overview | Results
# Results

![Left leg goals and encoders, motor and battery currents|900](@fig:run)

## The quasi-static reference

With the trunk held, each joint settles where the P law balances gravity: $K (q_\text{goal} - q) + \tau_g(q) = 0$, with $K$ = 0.5544 N·m/rad. `design/robot.py` (`hang_reference`) computes the gravity torques $\tau_g = -\partial U/\partial q$ from the MJCF bodies. A joint can also stop anywhere inside its friction budget at rest, which is a band of $\pm F/K$ (15 to 35 mrad here).

| joint | goal | reference | bg-sim at 1.2 s | band |
| --- | --- | --- | --- | --- |
| left hip pitch | -0.1510 | -0.1717 | -0.1914 | ±0.024 |
| left knee | 0.5811 | 0.5552 | 0.5377 | ±0.026 |
| left ankle | 0.7321 | 0.7353 | 0.7198 | ±0.018 |
| left hip roll | -0.0873 | -0.1400 | -0.1185 | ±0.035 |

Every leg joint stops 15 to 20 mrad short of the reference, on the side it came from, as a joint stopped by its friction does. `expected.json` checks nine joints before the step and at the end, each within its band plus 5 mrad. It also checks the time at which the knee goal crosses half-way through the delay line ($0.2 + 0.02 - 0.0025$ s) and the current bound.
@@ figures microduck-stand
{
  "run": {
    "kind": "plot", "model": "microduck-stand", "xlim": [0, 1.3],
    "rows": [
      {"ylabel": "trunk quaternion", "series": [{"signal": "Free/pose[1]", "label": "w"}, {"signal": "Free/pose[3]", "label": "y (pitch)"}], "hlines": [{"y": 0.9397, "label": "40 deg tilt"}], "legend": true},
      {"ylabel": "foot forces [N]", "series": [{"signal": "FootL1/f_n", "label": "left toe out"}, {"signal": "FootL2/f_n", "label": "left toe in"}, {"signal": "FootL3/f_n", "label": "left heel in"}, {"signal": "FootL4/f_n", "label": "left heel out"}], "legend": true},
      {"ylabel": "left leg [rad]", "series": [{"signal": "left_hip_pitch/Encoder/y", "label": "hip pitch"}, {"signal": "left_knee/Encoder/y", "label": "knee"}, {"signal": "left_ankle/Encoder/y", "label": "ankle"}], "legend": true}
    ]
  }
}
@@ page microduck-stand overview - | Overview
# The microduck holding HOME

The robot is released 0.1 mm above the floor in the STAND pose, on a free joint ([Free](block:Free)). Each sole has four contact points with friction 1.0. The 14 servos hold the HOME goals at kp 200, and **no policy runs**.

The robot first settles into its gear play and its P stiffness: the knees bend, and the weight moves from the heels to the toes. Then it tips forward. HOME at walking gain is balanced only by a policy that keeps balancing it. The microduck design notes report the same from their own simulation: "a robot holding it on the floor tips past 40° within a second or two". Here the trunk passes 40° at 1.14 s.

Only the soles touch the ground, so the run ends at 1.3 s, before the head would hit the floor.

Try a higher `kp_fw` and see how long the robot stays up. A run takes a few minutes.
@@ page microduck-stand results overview | Results
# Results

![Trunk attitude, left foot forces and left leg joints|900](@fig:run)

- In the first 0.3 s the trunk drops 1.7 mm. The joints take up their backlash (±1°), the knee shows the largest sag, and the heels carry more than the toes. The centre of mass is 0.6 mm ahead of the trunk origin, which is 12 mm from the heel edge and 25 mm from the toe edge.
- The knees keep bending forward, and the load moves onto the toes.
- The pitch then grows faster and faster: the trunk is at 25° at 1.0 s and 53° at 1.2 s.

`expected.json` checks the 40° crossing against the design notes' "within a second or two" (1.5 ± 0.5 s).
