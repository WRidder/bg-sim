# flex-torsion — two disks on a flexible shaft

Two steel disks on a slender aluminium shaft hang from a bearing. The shaft is a `FlexibleBeam3D` with three torsion modes and no bending modes. A 1 N·m motor torque pulse of 0.1 s on the upper disk (at t = 0.05 s) sets the pair spinning and twisting against each other. The lower disk is free.

```
World ─ Bearing (Revolute3D, motor torque) ─ Disk1 ─ Weld1 ─ Mount ─ Shaft (FlexibleBeam3D, nt = 3) ─ Weld2 ─ Disk2
```

The disks are welded to the shaft by stiff compliant joints (a `Revolute3D` whose drive holds a stiff `TorsionSpring` against a `FixedShaft`), so the disk inertias stay integral-causal next to the beam's inertia. `Mount` turns the bearing's z axis into the beam's x axis (end A at the top, x down the shaft).

## 3D view

| binding | signal |
| --- | --- |
| `link:disk1` pose | `PDisk1/g` |
| `link:shaft` pose | `Shaft/pose` (the beam's reference frame, end A) |
| `link:disk2` pose | `PDisk2/g` |
| `visual:shaft_rod` deformation | torsion, clamped-free, beam axis `+z`, length 1 m, signals `Shaft/eta_t[1..3]` |

The shaft is drawn with a 12 mm radius (the real shaft is 6 mm) so its twist stripes are easy to see. The largest twist is about 0.27 rad (15°).

## Numbers

| quantity | value |
| --- | --- |
| shaft d, L, G = E/(2(1+ν)) | 6 mm, 1 m, 26.3 GPa |
| shaft stiffness k = G I_p / L, inertia ρ I_p L | 3.348 N·m/rad, 3.435e-7 kg·m² |
| disk m, J (axial) | 3.157 kg, 0.010101 kg·m² |
| μ = J_disk / (ρ I_p L) | 29404 |
| exact first torsional frequency | 25.7475 rad/s (4.0978 Hz) |
| massless-shaft limit sqrt(k (J1+J2)/(J1 J2)) | 25.7475 rad/s |
| Ritz eigenvalue of the model's basis, nt = 1 / 2 / 3 | 28.598 / 27.131 / 26.655 rad/s (+11.07 % / +5.37 % / +3.53 %) |
| FFT of `Shaft/twist` (simulation, nt = 3) | 4.24214 Hz (Ritz 4.24230 Hz) |

### The exact frequency

With the torsion wave speed c = sqrt(G/ρ), a shaft θ(s,t) = (a cos(ωs/c) + b sin(ωs/c)) e^{iωt} and the end conditions G I_p θ'(0) = −ω² J1 θ(0) and G I_p θ'(L) = ω² J2 θ(L) give, with z = ωL/c and μ_i = J_i/(ρ I_p L),

    (μ1 + μ2) z cos z + (1 − μ1 μ2 z²) sin z = 0.

For μ → ∞, z is small: sin z ≈ z and cos z ≈ 1. Then (μ1 + μ2) z² ≈ μ1 μ2 z⁴, so ω² = k (J1 + J2)/(J1 J2), the two-inertia oscillator.

### Why 3 modes are 3.5 % stiff

The model's basis is the rigid rotation of the frame plus nt clamped-free torsion modes ψ_n = √2 sin((2n−1)π s/2L). With a heavy disk at B, the first mode is almost a linear twist along the shaft. A sine series with ψ_n'(L) = 0 converges slowly to that shape: the static twist under an end torque reaches 81 % / 90 % / 93 % of T L/(G I_p) with 1 / 2 / 3 modes. The simulation reproduces the Ritz eigenvalue of that basis (to 4e-5). The distance to the exact root is the truncation error of the assumed-modes method, not of the integration. For heavy end bodies, a static-correction or Craig–Bampton basis would converge faster.

## Checks (`expected.json`)

- no E101/E102/W201/W202 diagnostics; all scene bindings resolve
- FFT peak of `Shaft/twist` against the Ritz frequency (0.5 %)
- FFT peak of `Shaft/twist` against the exact root (4 %)
- the largest twist is 0.27 rad (5 %)

## Files

| file | content |
| --- | --- |
| `design/build.py` | uv script: writes the model, scene and `expected.json`, and prints the reference frequencies |
| `models/flex-torsion.bgmodel.json` | the model |
| `models/flex-torsion.docs` | the model documentation |
| `scenes/flex-torsion.sdf` | frame, disks and the twisting shaft |

Rebuild with `uv run examples/flex-torsion/design/build.py`; check with `uv run examples/run_checks.py --only flex-torsion`. The settings use `Rodas5P`: the torsion modes of the shaft itself reach about 24 000 rad/s.
