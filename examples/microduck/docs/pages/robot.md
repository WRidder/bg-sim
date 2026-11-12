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

![The bench model: goal, supply, one XL330 instance and the pendulum arm|900](assets/849b29ce6920.png)

## Inside the XL330

- **Firmware (Position Control Mode).** The goal waits `t_latency` (20 ms) in a delay line. The P law turns the angle error into a PWM duty, $d = k_{p} \frac{4096}{2\pi} \frac{e}{256 \cdot 885}$, with I = D = 0 as on the robot. BAM's current limiter clamps the duty to the window $(k_t\omega \pm R\, i_\text{limit})/V$, and the PWM limit clamps it to $\pm 1$.
- **Motor and gear.** An `MTF` H-bridge (modulus = duty) takes power from the bus. A winding `R` and an `EMConverter` drive the rotor `I`, and a gear `TF` of 1/288.4 leads to the output. Every value is the BAM M6 fit: $k_t$ and $R$ at the output, and the armature reflected to the rotor.
- **Friction.** `BamFriction` is a nonlinear `R` with the M6 law: a load-dependent Coulomb budget that grows with the motor torque and the external torque, a Stribeck part near rest, and viscous friction.
- **Backlash.** `SmoothBacklash` gives 2° of play between the gear output and the horn. The encoder reads the horn, so the P law sees the play, as on the real servo.

Continue with [parameters and sources](page:parameters) and [limits](page:limits).
