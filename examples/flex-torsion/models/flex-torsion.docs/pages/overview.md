# Two disks on a flexible shaft

Two steel disks (m = 3.157 kg, axial inertia J = 0.010101 kg·m²) sit on a slender aluminium shaft (d = 6 mm, L = 1 m) that hangs from a bearing. [Motor](block:Motor) gives the upper disk a 1 N·m torque pulse of 0.1 s, driven by [Pulse](block:Pulse). The disks then spin and twist against each other.

## The model

- [Bearing](block:Bearing) is a `Revolute3D` about the world z axis. Its drive takes the motor torque.
- [Disk1](block:Disk1) and [Disk2](block:Disk2) are `RigidBody3D` blocks.
- [Shaft](block:Shaft) is a `FlexibleBeam3D` with three torsion modes (`nt = 3`) and no bending modes (`ny = nz = 0`). Its material is E = 70 GPa, ν = 0.33, ρ = 2700 kg/m³, with a modal damping ζ_t = 0.002. The beam includes its own mass and inertia.
- [Weld1](block:Weld1) and [Weld2](block:Weld2) attach the disks to the shaft ends. Each is a stiff, compliant revolute joint whose drive holds a stiff torsion spring against ground. A rigid weld would put the disk inertias in derivative causality next to the beam's inertia.
- [Mount](block:Mount) turns the bearing frame so that the beam's x axis (from end A to end B) points down the shaft.

## Equations of the shaft

The shaft's torsion is θ(s,t) = θ_frame(t) + Σ ψ_n(s) η_t,n(t), with the clamped-free shapes ψ_n(s) = √2 sin((2n−1)π s / 2L). The modal stiffness is k_n = G I_p ((2n−1)π/2)² / L, and the modal mass is ρ I_p L. The end torques enter through the end twists ψ_n(0) = 0 and ψ_n(L) = √2 (−1)^{n+1}.

## The exact answer

With the wave speed c = sqrt(G/ρ), z = ωL/c and μ_i = J_i/(ρ I_p L), the shaft with end inertias has

$$(\mu_1+\mu_2)\,z\cos z + (1-\mu_1\mu_2 z^2)\sin z = 0 .$$

Here μ = 29404, so the first root is very close to the massless-shaft limit

$$\omega^2 = k\,\frac{J_1+J_2}{J_1 J_2},\qquad k = \frac{G I_p}{L} = 3.348\ \mathrm{N\,m/rad}.$$

Both give 25.7475 rad/s (4.098 Hz).

## What the run shows

- [Shaft/twist](signal:Shaft/twist) is the twist of end B relative to end A. It rings at 4.242 Hz. That is the Ritz eigenvalue of the model's basis (26.655 rad/s), 3.5 % above the exact root. With 1 / 2 / 3 modes the error is 11.1 % / 5.4 % / 3.5 %: a sine series with zero end slope converges slowly to the nearly linear twist of a shaft between two heavy disks.
- [Shaft/eta_t[1]](signal:Shaft/eta_t[1]), [Shaft/eta_t[2]](signal:Shaft/eta_t[2]) and [Shaft/eta_t[3]](signal:Shaft/eta_t[3]) are the modal coordinates (rad). They drive the deformation of the shaft in the 3D view. [Shaft/f_t[1]](signal:Shaft/f_t[1]) is the first torsion mode's clamped-free frequency in Hz (the shaft alone, without the disks).
- [Bearing/qout](signal:Bearing/qout) is the upper disk's angle. After the pulse, the pair keeps turning at a mean speed of T·Δt/(J1 + J2).

In the 3D view, the shaft is drawn thicker than it really is so that its stripes show the twist (about 15° at the peak).
