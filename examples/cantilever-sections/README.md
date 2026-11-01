# cantilever-sections — round bar, square bar and I-beam under one tip force

Three 2 m steel cantilevers of the same mass per metre, clamped side by side to one wall: a solid round bar, a solid square bar and an IPE 100 I-beam on its strong axis. One downward tip force loads all three: a constant force (step or ramp), a sine, both, or a frequency sweep, chosen on the dashboard. The 3D view bends the beams and colours them by the bending stress of their outer fibre, so the section shape's effect on deflection, stress and dynamics shows at a glance.

## Sections: the same mass

The I-beam is an IPE 100 (EN 10365: h = 100, b = 55, tw = 4.1, tf = 5.7 mm) without its root fillets, bent about its strong axis (web vertical, load in the web plane). The two bars get the I-beam's area, so all three weigh 7.774 kg/m (15.55 kg per beam). With equal mass, the comparison shows what the shape alone does: it puts the material far from the neutral axis.

| | round bar | square bar | IPE 100 |
| --- | --- | --- | --- |
| size | d = 35.51 mm | a = 31.47 mm | 100 x 55 x 4.1 / 5.7 mm |
| area A | 9.903 cm² | 9.903 cm² | 9.903 cm² (catalogue with fillets: 10.3) |
| second moment I | 7.803 cm⁴ | 8.172 cm⁴ | 163.32 cm⁴ (catalogue: 171) |
| section modulus W = I/c | 4.395 cm³ | 5.194 cm³ | 32.665 cm³ |
| I relative to the round bar | 1 | 1.047 | **20.93** |
| f1 / f2 / f3 | 6.423 / 40.25 / 112.7 Hz | 6.573 / 41.19 / 115.3 Hz | 29.39 / 184.2 / 515.6 Hz |

All section values are global parameters of the model (Model > Global parameters): the I-beam's `h`, `b`, `tw`, `tf`, the bars derived from its area (`d_rod = sqrt(4 A_ipe / Pi)`, `a_sq = sqrt(A_ipe)`). Steel: E = 210 GPa, ρ = 7850 kg/m³, yield strength fy = 235 MPa (S235). Damping ratio ζ = 0.02 on every mode.

## The model

```
            ┌─► MSe ── ModalCantilever "Round"   (A_rod, I_rod, c = d/2)
 TipLoad ───┼─► MSe ── ModalCantilever "Square"  (A_sq,  I_sq,  c = a/2)
  (F, down) └─► MSe ── ModalCantilever "IPE"     (A_ipe, I_ipe, c = h/2)
```

Two project blocks (`library/`):

- **`TipLoad`**: the force from `t0` = 0.2 s on. `mode` 0 constant `F0` (a step, or a ramp over `t_ramp`), 1 sine `Fa sin(2 pi f (t - t0))`, 2 both, 3 a linear sweep from `f_start` to `f_end` over `T_sweep`. Defaults: F0 = 250 N, Fa = 10 N, f = 6.4233 Hz (the round bar's f1), sweep 2 to 40 Hz in 10 s.
- **`ModalCantilever`**: a clamped-free Euler–Bernoulli beam by the assumed-modes method with three modes, the modal bond graph of the example **cantilever-modes** (one 1-junction with I, C and R per mode, coupled to the tip 0-junction by a TF of modulus φ_n(L) = +2, −2, +2), with the same mode shapes and normalisation as the library's `FlexibleBeam3D` and the viewer.

The tip port is a translational bond: the `MSe` sets the force, the beam answers with the tip velocity.

## Derivation

Deflection w(s, t) = Σ φ_n(s) η_n(t) with φ_n = cosh βs − cos βs − σ_n (sinh βs − sin βs), β = λ_n/L, λ = 1.8751, 4.6941, 7.8548 (roots of 1 + cos λ cosh λ = 0), normalised so that (1/L) ∫ φ_n² ds = 1. Each mode is a damped oscillator

    m η_n'' + 2 ζ ω_n m η_n' + k_n η_n = φ_n(L) F + m g0 a_n,   m = ρ A L,   k_n = λ_n⁴ E I / L³,

with a_n = (1/L) ∫ φ_n ds (the own weight, off by default: `g0` = 0). Then

- **eigenfrequencies** f_n = (λ_n² / 2π) sqrt(E I / (ρ A L⁴)): exact for the first three modes;
- **tip deflection** w = Σ φ_n(L) η_n. Statically 12 Σ 1/λ_n⁴ = 99.86 % of the Euler–Bernoulli F L³ / (3 E I);
- **root bending moment** from the equilibrium of the whole beam (force summation):

      M(0) = F L + ρ A g0 L² / 2 − ρ A ∫ s w'' ds = F L + m g0 L/2 − m L Σ b_n η_n'',   b_n = (1/L²) ∫ s φ_n ds,

  exact in the static limit (M = F L) and fast-converging in dynamics, because only the inertia of the modes enters. The block also gives `M_modal` = E I w''(0) = (2 E I / L²) Σ λ_n² η_n, the moment from the modal curvature: a slowly converging, alternating series, 4 F L (1/λ1² − 1/λ2² + 1/λ3²) = 1.0210 F L statically with three modes;
- **stress** σ = M c / I = M / W at the outer fibre at the wall, **utilisation** |σ| / fy.

A step force overshoots: the tip swings to 1 + exp(−ζπ / sqrt(1 − ζ²)) = 1.94 times its static deflection (one mode; 1.904 with all modes). The root moment overshoots more, to 2.21 F L: at the wall the inertia of the higher modes adds to the first mode's swing (the three-mode model and the finite element model with all modes agree to 0.1 %). A sine at frequency f gives the steady amplitude Σ φ_n(L)² Fa / (k_n sqrt((1 − r_n²)² + (2 ζ r_n)²)), r_n = f / f_n: 1/(2ζ) = 25 times the static deflection at resonance.

## Results

Independent references (`design/reference.py`, numpy/scipy, no BG-Sim code): the sections from their rectangles with the parallel-axis theorem, the Euler–Bernoulli formulas, the eigenvalues from the characteristic equation (brentq), and a finite element model of each beam (60 Hermite elements, consistent mass, every mode damped by ζ) for the step response and the frequency response.

F0 = 250 N step at 0.2 s (the default run), values at 10 s:

| | round bar | square bar | IPE 100 |
| --- | --- | --- | --- |
| tip deflection F L³/(3 E I) | 40.682 mm | 38.848 mm | 1.944 mm |
| root moment F L | 500 N m | 500 N m | 500 N m |
| stress F L / W | 113.76 MPa | 96.27 MPa | 15.31 MPa |
| utilisation | 0.484 | 0.410 | 0.065 |
| largest deflection after the step (FE) | 77.47 mm | 73.97 mm | 3.701 mm |
| largest root moment after the step (FE, all modes) | 1104 N m = 2.21 F L | 1104 N m | 1104 N m |
| peak utilisation after the step | **1.07** | 0.90 | 0.14 |

Sine, steady state (FE frequency response):

| case | round bar | square bar | IPE 100 |
| --- | --- | --- | --- |
| 50 N at 4 Hz: tip amplitude | 13.13 mm (x1.61) | 12.20 mm (x1.57) | 0.396 mm (x1.02) |
| 50 N at 4 Hz: stress amplitude | 39.09 MPa | 32.09 MPa | 3.13 MPa |
| 10 N at 6.4233 Hz (round f1): tip amplitude | 39.49 mm (x24.3) | 25.32 mm (x16.3) | 0.0815 mm (x1.05) |
| 10 N at 6.4233 Hz: stress amplitude | 129.5 MPa | 73.06 MPa | 0.647 MPa |

At resonance a 10 N force stresses the round bar more than the 250 N static load. The square bar, whose f1 is only 2.3 % higher, is already off its resonance peak (its half-power band is 2ζ f = 0.26 Hz wide). The I-beam does not notice: its first mode is at 29.4 Hz.

`expected.json` runs the model five times (the default and four run overrides, as the dashboard would) with 70 checks, plus the docs check. The default run checks, per beam, the settled tip deflection against F L³/(3 E I) (0.2 %), the root moment, stress and utilisation (0.1 %), `M_modal` against 1.0210 F L, f1 and f2 against the characteristic equation, the largest deflection after the step against the finite element step response (0.5 %), the largest root moment and utilisation after the step of the two bars against it (2 %), the ring-down frequency (FFT, 1 %) against f1, and the stiffness ratios w_round / w_IPE = I_IPE / I_round = 20.93 and w_square / w_IPE = 19.99. The `-sine` (50 N, 4 Hz) and `-resonance` (10 N at the round bar's f1) runs check the steady tip, moment and stress amplitudes over 10 to 12 s against the finite element frequency response (1 %), `-weight` the deflection and moment with the own weight added (q = ρ A g = 76.26 N/m: w = F L³/(3 E I) + q L⁴/(8 E I), M = F L + q L²/2), and `-sweep` the sweep.

## 3D view

The scene (`scenes/cantilever-sections.sdf`) has the wall, a steel plate for each beam and the three beams at 1.2 m, round bar on the left, I-beam on the right. Every beam visual has a deformation binding (`bending-y`, `clamped-free`, the beam's `eta[1..3]`, beam y pointing down) with a strain colouring on `coolwarm` from −fy/E to +fy/E: the strain is a magnitude, so an unstressed beam is grey and a beam at first yield dark red (the stress is E times the strain).

- The I-beam is three boxes. Its two flange bindings set the **neutral axis** of the whole section (`"neutral": [±(h − tf)/2, 0]` in the beam mapping), so the flanges turn about the web's axis and their strain colour is the h/2 outer-fibre strain. The web's own outer fibre is at h/2 − tf, so it colours 11 % lighter, as it should.
- The colour is the three-mode curvature, which at the wall overshoots the true static strain by 2.1 % (`M_modal`, above); the readouts use the equilibrium moment.
- The deflection is drawn **x10 (exaggerated)** when the view opens (`"exaggeration": 10`); the view's deformation control offers x1 (true scale) to x1000 and marks every factor above x1. The colours always use the true strain. The round bar's true static deflection is 41 mm, 2 % of its length.
- The scene draws the default sections. Changing `h`, `b`, `tw` or `tf` changes the model but not the drawing.

## Dashboard

The load mode (select), `F0`, the ramp time, the sine amplitude and frequency, the damping ratio and the own weight (`g0`: 0 or 9.81); value cards for the tip deflection (mm) and the root stress (MPa) of each beam, utilisation gauges (good up to 0.6, warn to 1, bad above), and plots of deflection, stress, utilisation and force. Things to try:

- the step: on the overshoot, 250 N takes the round bar past the yield stress (utilisation 1.07; the model stays elastic). Set a ramp time of 1 s: the overshoot is gone;
- the sine at 6.42 Hz (the default frequency), then 6.57 Hz (the square bar's), then 29.4 Hz (the I-beam's; raise the amplitude);
- the sweep (set `t_end` to `T_sweep` or more): each beam rings when the sweep passes its first mode;
- the own weight: the bars sag 9.3 mm more, the I-beam 0.44 mm.

## Files

| file | content |
| --- | --- |
| `design/reference.py` | the independent references (uv, numpy, scipy); writes `design/reference.json` |
| `design/build.py` | writes the model, the scene, `expected.json` and the project file from `reference.json` |
| `library/ModalCantilever.jl`, `library/TipLoad.jl` | the beam and the load |
| `models/cantilever-sections.bgmodel.json` | the model with its globals, bindings and dashboard |
| `models/cantilever-sections.docs` | the model documentation (built by `tools/example_docs`) |

Rebuild with `uv run examples/cantilever-sections/design/reference.py` and `uv run examples/cantilever-sections/design/build.py`; check with `uv run examples/run_checks.py --only cantilever-sections`.

## Limitations

- Linear Euler–Bernoulli beams: no shear deformation or rotary inertia (Timoshenko). For these slender beams (L/h = 20 for the I-beam) the shear flexibility of the IPE adds about 1 % to its static deflection and lowers f1 by about 0.5 %; for the higher modes the error grows.
- Small deflections: no geometric stiffening, no foreshortening.
- No lateral-torsional buckling of the I-beam: its elastic buckling load as a 2 m cantilever with the load at the shear centre is about 5 kN (4.013 sqrt(E Iz G J) / L², warping neglected; a load on the top flange lowers it), far above the loads here. No local buckling, no plasticity: above a utilisation of 1 the model stays elastic.
- Three modes per beam: the stress at the wall from the equilibrium moment is exact statically; the deflection is 99.86 % of the exact static value.
- Bending in the vertical plane only: no torsion, no out-of-plane bending, the load acts at the shear centre.
