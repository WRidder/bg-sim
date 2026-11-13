# One motor, one propeller, no servos

A conventional multirotor needs one motor per rotor, and a helicopter needs servos for every
tilt. This vehicle has **one motor** and **one propeller**, and still controls roll and pitch.
The motor controller modulates the torque once per revolution:

$$\tau_m(t)=\tau_{\mathrm{base}}+c_x\cos\psi+c_y\sin\psi .$$

The rotor speeds up and slows down within each turn. The two blades sit on **lag-pitch
hinges**: when the hub accelerates, the blades lag, and the skewed hinges turn the lag into
pitch, up on one blade and down on the other. The blade with more pitch makes more lift, so the
rotor exerts a hub moment on the body. The model computes that moment from the rotor's own
state, the torque that accelerates it, $\tau_{net}=\tau_m-Q=J_a\dot W$:

$$M_x=2k_M\,\tau_{net}\cos\psi,\qquad M_y=2k_M\,\tau_{net}\sin\psi .$$

A once-per-revolution torque gives the mean moment $k_M(c_x,c_y)$ plus a ripple at twice the
rotor frequency. The amplitude of $(c_x,c_y)$ sets the size of the moment, and its phase sets
the direction. $k_M=0.25$ is an assumed value; there is no bench data for it.

There is no third actuator, so **yaw cannot be commanded**. The four red fins sit in the rotor
slipstream. The slipstream carries the angular momentum the rotor torque puts into it (the
swirl), and the fins, lifting surfaces at a fixed incidence, turn that swirl into a torque that
opposes the motor reaction. The incidence is chosen so the two balance at hover. Both scale with
the rotor speed squared, so they balance at every speed. The fins also damp the yaw rate, but
nothing holds a heading. The real vehicle therefore uses an IR beacon for its heading estimate:
a magnetometer cannot compete with the motor current.

The example follows
[`jyjblrd/single-propeller-drone`](https://github.com/jyjblrd/single-propeller-drone) and its
ArduPilot `MCOUT` / moteus `mcout` firmware: the flight controller runs the attitude loops and
the motor controller adds the phase-locked cyclic torque from its encoder.

![The model canvas](assets/f88750202992.png)

The two models are:

| model | what it is |
| --- | --- |
| `single-propeller-drone` | 20 s: released in hover at 1.32 m (a hand launch, no take-off), two 1.5 m legs, the land mode, touchdown, disarm and run-down |
| `single-propeller-drone-hover` | 8 s: released in hover with a yaw kick and a roll kick, then a 1 m lateral step |

Start with the [flight model](model:single-propeller-drone) or the
[hover and passive-yaw model](model:single-propeller-drone-hover).
