# The bond graph

## Drive

The winding is the dq model in the amplitude-invariant frame, as an equivalent DC circuit:

- [Uq](block:Uq) is an `MSe` driven by the current loop's $u_q$.
- [Rw](block:Rw) and [Lw](block:Lw) are $R/1.5$ and $L/1.5$.
- [EMF](block:EMF) is a gyrator with the modulus $p\lambda = k_{t,q}/1.5$.

The flow is $i_e = 1.5\, i_q$, so $u_q i_e$ is the electrical power, and $k_{t,q} = k_{t,rms}/\sqrt2 = 0.171$ N·m/A.

The mechanical path runs from [Rotor](block:Rotor) ($J_m = J_{out}/N^2$) and the motor-side friction [FricIn](block:FricIn) through [Gear](block:Gear) (TF $1/N$) to a 0-junction. That junction carries the gear compliance [GearSpring](block:GearSpring). After it come the output bearing friction [FricOut](block:FricOut) and the arm joint [J1](block:J1).

**Gear spring.** The backlash is a smooth dead zone, with no `abs`/`max` kink and no tangent at zero:

$$D(\varphi) = s(\varphi - b) - s(-\varphi - b),\qquad s(x) = \tfrac12\big(x + \sqrt{x^2 + \varepsilon^2}\big)$$

$b$ is half of the 13′ backlash. The torque is a hardening spring plus contact damping that vanishes in the gap:

$$\tau = k_3 D - (k_3 - k_1)\, D_k \tanh(D/D_k) + d\,\dot\varphi\, D'(\varphi)$$

**Friction.** All friction is Coulomb, Stribeck and viscous, with a smooth sign:

$$\tau_f = \big(F_c + (F_s - F_c)\,e^{-(w/v_s)^2}\big)\tanh(w/v_\varepsilon) + F_v w$$

## Mechanics

The mechanics is the spatial multibond bond graph of the Quanser model:

- `Revolute3D` joints [J1](block:J1), [J2](block:J2) and [J3](block:J3) with $10^6$ compliance;
- `RigidBody3D` composite bodies [Arm](block:Arm), [Link1](block:Link1) and [Link2](block:Link2). Each combines its tube, shaft, bearing housing and AS5048 board with its own COM and inertia.

The passive joints have bearing friction ([FricJ2](block:FricJ2), [FricJ3](block:FricJ3)).

## Drive firmware and sensors

- **Current loop.** [CurrentLoop](block:CurrentLoop) is the continuous equivalent `ALCurrentLoopC` of the 16 kHz digital PI.
  - It keeps the zero on the winding pole, the 26.3 V clamp ($0.95\,V_{dc}/\sqrt3$), anti-windup and the 1.5-period delay as a lag.
  - The digital loop itself (`ALCurrentLoop`) runs in the current-step identification.
  - The continuous form is used here because a 16 kHz held output would record 32 000 event rows per simulated second.
- **Drive loop.** [DriveLoop](block:DriveLoop) runs at 4 kHz.
  - In CST it passes the target torque to the current loop: $i_{ref} = \tau/(N k_{t,q})$, clamped at the 68 N·m acceleration torque (44.2 A).
  - In CSV it runs a speed PI.
- **Drive encoders.** [MotorEnc](block:MotorEnc) and [OutputEnc](block:OutputEnc) are 20-bit encoders, read in the 1 kHz cycle.
- **AS5048 encoders.** [Enc1A](block:Enc1A), [Enc1B](block:Enc1B), [Enc2A](block:Enc2A) and [Enc2B](block:Enc2B) are the two chains on the two joints. Each reading:
  - is taken at the angle $\theta - w\,\mathrm{lat}$, where lat is 0.19 ms over SPI and 0.44 ms over I2C;
  - adds the INL as two harmonics, plus 0.06° rms noise from a seeded `Noise` block;
  - is quantised to 14 bit, modulo one turn.
