# The electric drive

    Battery -- 0 (bus) -- MachineR (modulated TF) -- 1 (rotor) -- elastic shaft -- 1 -- TF 1/7 -- 0 (differential) -- TF 2 -- RL, RR spin

| block | role |
| --- | --- |
| [Battery](block:Battery) | `TractionBattery`: open-circuit voltage from 340 V (empty) to 403 V (full), 60 mOhm, 100 Ah; the state is the charge |
| [MachineR](block:MachineR) | `TractionMachine`: the inverter and the motor as a power-conserving modulated transformer, rotor torque $u\,V$, bus current $u\,\omega$ |
| [MotorR](block:MotorR) | `EMotorControl`: the torque envelope, the accelerator, traction control, regeneration, and the modulus $u = \tau / V_{bus}$ |
| [RotorR](block:RotorR), [RotorRJ](block:RotorRJ), [RotorRDrag](block:RotorRDrag), [RotorRSpeed](block:RotorRSpeed) | the rotor's 1-junction, its inertia, its drag and the speed sensor the controller reads |
| [ShaftR](block:ShaftR) | the elastic drive shaft (1500 N m/rad, 8 N m s/rad) |
| [ReductionR](block:ReductionR), [DiffR](block:DiffR), [LsdR](block:LsdR) | the 7:1 reduction, the open differential (a 0-junction) and its viscous coupling |

The envelope is

$$T_{lim}(\omega) = \min\!\Big(T_{max},\ \frac{P_{max}}{|\omega|}\Big)\,\tfrac12\Big(1 - \tanh\frac{|\omega| - \omega_{max}}{\omega_c}\Big)$$

and the bus voltage at the commanded power $P = \tau\omega$ is the root of $V^2 - V_{oc} V + R P = 0$, so $u = \tau/V$ gives exactly the commanded torque with no algebraic loop.
