# Control and design

The controller is a PX4-style cascade with a mixer for this vehicle: the roll and pitch moment
requests become a **cyclic motor torque**, the collective thrust becomes a **rotor speed**, and
there is no yaw channel.

| block | rate | role |
| --- | --- | --- |
| [Mission](block:Mission) `Waypoints` | 50 Hz | smooth 7th-order moves with velocity, acceleration and jerk; the land mode; the touchdown latch (from the peak hold), the thrust unload, disarm and motor stop |
| [Pos](block:Pos) `PosCtrl` | 50 Hz | position P, velocity PI with acceleration and drag feed-forward; thrust direction from $(a_x,a_y,g)$, limited to 0.20 rad; the jerk as a tilt-rate feed-forward; the **measured** heading in the desired attitude |
| [Att](block:Att) `AttCtrl` | 250 Hz | quaternion-error P on roll and pitch only |
| [Rate](block:Rate) `RateCtrl` | 400 Hz | PI on the body rates plus the gyroscopic feed-forward $(hq,-hp)$, $h=J_a\omega$ |
| [Alloc](block:Alloc) `Alloc` | 400 Hz | $w_{\rm cmd}=\sqrt{F/k_T}$; cyclic amplitude $\lvert\tau\rvert/k_{M,est}$ up to 0.8 N m, phase $\operatorname{atan2}(\tau_y,\tau_x)$ |
| [Esc](block:Esc) `RotorEsc` | 400 Hz | rotor speed loop: acceleration-limited reference, drag and inertia feed-forward, PI; the touchdown brake |
| [Drive](block:Drive) `CyclicDrive` | continuous | current loop and cyclic modulation, output the inverter duty |

![Mission, attitude and tracking error](assets/ee66674fa573.png)

## The gyroscopic plant

At hover the rotor carries $h=J_a\omega_0=0.189$ N m s. A body torque mostly **precesses** the
body about the other axis; without control the body nutates at $h/\sqrt{J_xJ_y}=12.94$ rad/s
(2.06 Hz). The rate loop cancels the coupling with the feed-forward $(hq,-hp)$ and closes a PI
on a bare inertia per axis, crossover 20 rad/s. `design.py` checks both: the coupled two-axis
attitude and rate loops have a minimum damping of 0.691 with the feed-forward and 0.360 without.
The outer gains (attitude 5 /s, velocity $K_v=2$, $K_i=0.8$, position $K_p=0.6$) come from a
linear one-axis model with the loop delays, minimum damping 0.717.

## The swashplateless gain

The allocation inverts its own fixed estimate $k_{M,est}=0.25$; the plant gain is the global
`cyclic_gain`. A different value is a real model mismatch that the rate loop has to absorb. The
cyclic limit 0.8 N m is a hub-moment limit of 0.2 N m, which is also the rate loop's moment
limit.

## Fins and passive yaw

At hover the fin torque equals the rotor drag, $Q_0=0.3052$ N m. A body yaw rate changes the
fins' angle of attack, which gives the yaw damping $D=0.00410$ N m s/rad. Because the speed loop
holds the rotor's speed relative to the body, the rotor follows the body's yaw, and the time
constant is $(J_z+J_a)/D=0.870$ s. Four identical fins at 90° prefer no heading: a crossflow
changes the yaw torque only at second order, by 0.85 mN m at 1 m/s. The position controller
builds the desired attitude with the measured heading, so roll and pitch go in the right world
direction whatever the heading is. In a steady descent the mass flow through the disc drops, the
swirl grows, and the model's body yaws at a steady 0.859 rad/s (at 0.25 m/s).

That descent yaw rate is a property of the model's assumptions, not a prediction for the real
vehicle. The swirl uses the descent speed in the mass flow, but the thrust and drag laws
$T=k_TW^2$, $Q=k_QW^2$ ignore the inflow. The 0.859 rad/s needs a torque imbalance of only
$D\cdot 0.859=3.5$ mN m, 1.15 % of $Q_0$. In the descent the flow through the disc drops by
1.5 % (from 8.41 to 8.29 m/s). A real propeller's $k_T$ and $k_Q$ change by an amount of the
same order, so the real rate could be quite different. The check
only shows that the model agrees with its Python twin in `design.py`.

![Rotor speed, moment request, cyclic torque and the drive](assets/e160bdfddb08.png)

![Yaw rate and the yaw torque balance](assets/bd7e3faa9c68.png)

## Landing

The land mode descends from hover at 0.25 m/s, so the thrust carries the weight when the feet
touch the ground at 15.06 s. The fins carry the rotor drag in any state, so the only unbalanced
yaw torque on the body is the rotor's change of angular momentum. Any rotor speed lost while the
feet do not hold the body goes into its yaw, 0.109 rad/s per rad/s. The touchdown therefore runs
in three stages:

1. **Impact.** The 85 N impact lasts a few milliseconds and falls between two ticks of the
   controllers. [Aero](block:Aero) holds its peak (`Aero/fc_max`). The drive
   [Esc](block:Esc) reads the peak at its next 400 Hz tick and brakes the rotor to 97 % of its
   speed while the feet are still pressed and their friction holds the braking reaction.
2. **Hold.** The [Mission](block:Mission) latches the touchdown on its next 50 Hz tick. The
   position loop holds its last thrust instead of reacting to the rebound of the feet, and the
   drive keeps the rotor at its cap. With $0.97^2$ of the weight carried, the rebound ends in a
   hop of 1.5 mm at a constant rotor speed. The rate loop only damps while the feet are on the
   ground.
3. **Unload.** After 0.3 s the thrust comes off along a smooth step over 1 s. The rotor slows
   gently while the feet carry little, and faster as they take the weight, so their friction
   always holds the rotor's deceleration torque. Then the flight controller is off, and the
   motor stops 2 s later.

The impact's friction stops the 0.84 rad/s descent yaw within 5 ms. From then on to rest, the
yaw rate stays below 0.14 rad/s. `design.py` bounds what the landing can leave: 4.2 rad/s of the brake
may fall outside the part of the impact that holds it, which allows at most 0.457 rad/s. Before
this sequence, the 50 Hz mission missed the impact and latched the touchdown 0.2 s late. In
between, the vertical loop read the rebound as a climb and cut the thrust, and the rotor lost
35 rad/s with the body in the air, which spun the body to 3.27 rad/s.

![Touchdown, disarm and run-down](assets/57c04f9835eb.png)

## Sensors

[Imu](block:Imu) (`ImuSensor`, 500 Hz): gyro and accelerometer with biases, white noise and
Butterworth low-passes. The accelerometer sees the air loads and the contact force, never
gravity. [Mocap](block:Mocap) (100 Hz): position and velocity. [Beacon](block:Beacon)
(`IrBeacon`, 50 Hz): absolute heading. [Nav](block:Nav) (`NavFilter`, 500 Hz) observes the tilt
through the velocity innovation, the heading through the beacon, and estimates the gyro bias and
the vertical accelerometer bias. A horizontal accelerometer bias looks exactly like a tilt. The
vehicle therefore leans by about $b/g$, and the position loop's integrator removes the drift.
