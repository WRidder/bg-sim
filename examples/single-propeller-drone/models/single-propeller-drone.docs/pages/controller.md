# Control and design

The controller is a PX4-style cascade with a mixer for this vehicle: the roll and pitch moment
requests become a **cyclic motor torque**, the collective thrust becomes a **rotor speed**, and
there is no yaw channel.

| block | rate | role |
| --- | --- | --- |
| [Mission](block:Mission) `Waypoints` | 50 Hz | smooth 7th-order moves with velocity, acceleration and jerk; the land mode; the touchdown latch and the landed latch (from the foot load sensor), the thrust unload, disarm and motor stop |
| [Pos](block:Pos) `PosCtrl` | 50 Hz | position P, velocity PI with acceleration and drag feed-forward; thrust direction from $(a_x,a_y,g)$, limited to 0.20 rad; the jerk as a tilt-rate feed-forward; the **measured** heading in the desired attitude |
| [Att](block:Att) `AttCtrl` | 250 Hz | quaternion-error P on roll and pitch only |
| [Rate](block:Rate) `RateCtrl` | 400 Hz | PI on the body rates plus the gyroscopic feed-forward $(hq,-hp)$, $h=J_a\omega$; no integral on the ground |
| [Alloc](block:Alloc) `Alloc` | 400 Hz | $w_{\rm cmd}=\sqrt{F/k_T}$; cyclic amplitude $\lvert\tau\rvert/k_{M,est}$ up to 0.8 N m, phase $\operatorname{atan2}(\tau_y,\tau_x)$ |
| [Esc](block:Esc) `RotorEsc` | 400 Hz | rotor speed loop: acceleration-limited reference, drag and inertia feed-forward, PI; in landing mode the touchdown latch, the brake and the unload, limited to the yaw torque the measured foot loads hold |
| [Drive](block:Drive) `CyclicDrive` | continuous | current loop and cyclic modulation, output the inverter duty |

![Mission, attitude and tracking error](assets/405794422b18.png)

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

![Rotor speed, moment request, cyclic torque and the drive](assets/fc061f8f49dc.png)

![Yaw rate and the yaw torque balance](assets/6454d9081d38.png)

## Landing

The land mode descends from hover at 0.25 m/s, so the thrust carries the weight when the feet
touch the ground at 15.06 s. The fins carry the rotor drag in any state, so the only unbalanced
yaw torque on the body is the rotor's change of angular momentum. Any rotor speed lost while the
feet do not hold the body goes into its yaw, 0.109 rad/s per rad/s. The feet hold a yaw torque
only as a friction couple between two loaded feet; one foot alone holds none. The landing logic
reads one sensor, the foot loads of [Feet](block:Feet):

1. **Detection.** The impact lasts about 21 ms. The drive [Esc](block:Esc) samples the foot
   loads at 400 Hz, so it sees the impact about eight times; in landing mode
   ([Mission/land](signal:Mission/land)) it latches the touchdown on the first sample above
   2 N, at most 2.56 ms after the first contact. The [Mission](block:Mission) latches on its
   next 50 Hz tick from the sensor's held `touch` flag.
2. **Brake.** The drive caps its speed at 97 % of its reference at the latch and brakes to the
   cap at up to 4000 rad/s², never with more torque than half the friction its last load samples
   give. With the feet in the air it holds its speed.
3. **Ground.** The position loop holds its last thrust instead of reacting to the rebound of the
   feet. The horizontal position and attitude loops keep flying (integrators frozen): with
   $0.97^2$ of the weight still carried, the feet cannot hold a wind load, so the vehicle keeps
   its lean. The rebound comes back down in several small bounces over about 0.4 s, 1.5 mm
   high, with the feet off the ground for 0.13 s in total.
4. **Unload.** From the latch the thrust fraction falls along a smooth step over 1 s, and the
   drive scales its own cap with it, so the unload starts at the cap. The drive slows the rotor
   only with the torque that pairs of loaded feet hold ([Esc/t_hold](signal:Esc/t_hold)): on
   one foot or in the air the rotor speed stays, so a bounce stretches the unload and does not
   spin the body.
5. **Landed.** When the schedule has ended and the sensor has read more than half the weight
   for 5 ticks, the flight controller is off (16.16 s), and the motor stops 2 s later.

![Touchdown, disarm and run-down](assets/0e71c51e403c.png)

The raw yaw rate after the touchdown peaks at 0.15 rad/s. Most of that is the once-per-revolution
ripple of the cyclic torque against the rotor (up to 0.476 rad/s at full cyclic, zero mean), not
a spin: without it ([YawMean/y](signal:YawMean/y), a 25 ms lag used only as a read-out) the
yaw rate stays below 0.07 rad/s. `design.py` bounds what the landing can leave in calm air:
0.098 rad/s from the part of the brake before the first load sample, 0.208 rad/s if the brake
acts with one foot down (the body pivots about it), plus the ripple: 0.348 rad/s without the
ripple, 0.782 rad/s raw. A first version of this example read the rebound as a climb, cut the
thrust and slowed the rotor by 35 rad/s with the body in the air, which spun it to 3.27 rad/s.

### In wind

The wind sliders go to ±3 m/s; the landing is checked to 1 m/s (four check variants, wind along
±x and ±y). The vehicle leans 0.044 rad into a 1 m/s wind and arrives with about 0.91 rad/s of
yaw, and one foot touches first. That foot does not stop the arrival yaw, so it lasts about
70 ms longer than in calm air; from 0.1 s after the contact the raw yaw rate stays below
0.58 rad/s (0.33 without the ripple) at +1 m/s and below 0.78 rad/s (0.65) at −1 m/s, and the
vehicle ends upright with no spin. A foot that scrubs sideways while it carries load turns the
body through its friction; no rotor logic removes that. The calm bounds do not hold in wind: the
checks bound the yaw by the arrival yaw plus the one-foot brake (1.375 rad/s) and the height by
the lean geometry plus the hop (8.3 mm above the contact height; measured at most 3.2 mm).
At 2 m/s the vehicle bounces for over a second and is landed only at 18.1 s; at 3 m/s it tips
over.

![Touchdown in a 1 m/s wind along x: the four foot loads and the yaw torque the drive may use](assets/0114bbb51f23.png)

Limits: the mission flies one landing (its latches do not reset, there is no take-off or
go-around); the drive's latch resets when landing mode is off or the drive is disarmed; in
landing mode any touch above 2 N latches; the drive counts on a friction coefficient of 0.4
(the feet have 0.8).

## Sensors

[Imu](block:Imu) (`ImuSensor`, 500 Hz): gyro and accelerometer with biases, white noise and
Butterworth low-passes. The accelerometer sees the air loads and the contact force, never
gravity. [Mocap](block:Mocap) (100 Hz): position and velocity. [Beacon](block:Beacon)
(`IrBeacon`, 50 Hz): absolute heading. [Feet](block:Feet) (`FootSensor`, 400 Hz): the load in
each of the four legs with 0.03 N of white noise, their sum, and a `touch` flag (sum above 2 N,
held for 8 samples); only the landing logic reads it. [Nav](block:Nav) (`NavFilter`, 500 Hz) observes the tilt
through the velocity innovation, the heading through the beacon, and estimates the gyro bias and
the vertical accelerometer bias. A horizontal accelerometer bias looks exactly like a tilt. The
vehicle therefore leans by about $b/g$, and the position loop's integrator removes the drift.
