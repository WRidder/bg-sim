@@ figures cantilever-sections
{
  "diagram": {"kind": "diagram", "model": "cantilever-sections"},
  "scene": {"kind": "scene", "model": "cantilever-sections", "t": 0.28, "zoom": 5},
  "scene-static": {"kind": "scene", "model": "cantilever-sections", "t": 9.9, "zoom": 5},
  "step": {
    "kind": "plot", "model": "cantilever-sections", "xlim": [0, 3],
    "rows": [
      {"ylabel": "tip deflection [mm]", "series": [{"signal": "Round/w_mm", "label": "round bar"}, {"signal": "Square/w_mm", "label": "square bar"}, {"signal": "IPE/w_mm", "label": "IPE 100"}],
       "hlines": [{"y": 40.682, "label": "F L^3/(3 E I), round"}], "legend": true},
      {"ylabel": "root stress [MPa]", "series": [{"signal": "Round/sigma_MPa", "label": "round bar"}, {"signal": "Square/sigma_MPa", "label": "square bar"}, {"signal": "IPE/sigma_MPa", "label": "IPE 100"}],
       "hlines": [{"y": 235, "label": "fy = 235 MPa"}], "legend": true}
    ]
  },
  "resonance": {
    "kind": "plot", "model": "cantilever-sections", "settings": {"t_end": 12.0, "output": {"points": 24001}},
    "overrides": {"Load/mode": 1, "Load/Fa": 10.0, "Load/f": 6.423258},
    "xlim": [0, 12],
    "rows": [
      {"ylabel": "tip deflection [mm]", "series": [{"signal": "Round/w_mm", "label": "round bar"}, {"signal": "Square/w_mm", "label": "square bar"}, {"signal": "IPE/w_mm", "label": "IPE 100"}], "legend": true},
      {"ylabel": "tip force [N]", "series": [{"signal": "Load/F", "label": "10 N at 6.42 Hz", "color": "#444444"}]}
    ]
  },
  "sweep": {
    "kind": "plot", "model": "cantilever-sections", "settings": {"t_end": 10.0},
    "overrides": {"Load/mode": 3, "Load/Fa": 10.0},
    "xlim": [0, 10], "xlabel": "t [s] (the sweep runs 2 to 40 Hz from 0.2 to 10.2 s)",
    "rows": [
      {"ylabel": "tip deflection [mm]", "series": [{"signal": "Round/w_mm", "label": "round bar"}, {"signal": "Square/w_mm", "label": "square bar"}], "legend": true},
      {"ylabel": "IPE 100 tip [mm]", "series": [{"signal": "IPE/w_mm", "label": "IPE 100", "color": "#1b9e77"}]}
    ]
  }
}
@@ page cantilever-sections overview - | Overview
# Three sections, one tip force

Three 2 m steel cantilevers of the **same mass per metre** (7.774 kg/m) are clamped to one wall: a solid round bar, a solid square bar and an **IPE 100** I-beam on its strong axis. One downward tip force loads all three. The shape alone decides how far each bends, how hard it is stressed and how fast it vibrates.

![The three beams at the first peak after the 250 N step (deflection drawn x10, colour: bending stress, grey 0, dark red at yield)|900](@fig:scene)

![Diagram: the load, three effort sources and the three beams|900](@fig:diagram)

[Load](block:Load) makes the tip force (positive down). Three effort sources [FRound](block:FRound), [FSquare](block:FSquare) and [FIPE](block:FIPE) apply it to the tip ports of [Round](block:Round), [Square](block:Square) and [IPE](block:IPE). Each beam is a `ModalCantilever`: three clamped-free assumed modes (see [the physics](page:physics)), its section given by global parameters.

## What it shows

- **Same mass, 21 times stiffer.** Under 250 N the bars deflect 40.7 and 38.8 mm, the I-beam 1.94 mm ([Round/w_mm](signal:Round/w_mm), [IPE/w_mm](signal:IPE/w_mm)). The I-beam puts its material far from the neutral axis: I = 163.3 cm⁴ against 7.8 cm⁴.
- **Stress.** The root moment is F L = 500 N m for all three; the stress M / W is 114, 96 and 15 MPa, a utilisation of 0.48, 0.41 and 0.065 ([Round/util](signal:Round/util)).
- **A sudden load more than doubles the stress.** The step swings the tips to 1.9 times their static deflection and the root moment to 2.21 F L: the round bar passes its yield stress for a moment ([Round/util](signal:Round/util) 1.07; the model stays elastic). A ramp of 1 s avoids it.
- **Resonance.** The bars' first modes are at 6.42 and 6.57 Hz, the I-beam's at 29.4 Hz. A 10 N sine at 6.42 Hz shakes the round bar to 39.5 mm and 130 MPa, more than the 250 N static load does.

## Try it

Open the **Dashboard** tab. Pick the **load** (constant, sine, constant + sine, sweep), set its force, ramp time, amplitude and frequency, press **Run**, and watch the **3D View**:

- a ramp time of 1 s: the overshoot of the step is gone;
- **sine** at 6.42 Hz, then 6.57 Hz (the square bar's f1), then 29.4 Hz with 100 N (the I-beam's);
- **sweep** (2 to 40 Hz in 10 s): each beam rings as the sweep passes its first mode;
- the own weight (g0 = 9.81) adds 9.3 mm to the bars' sag and 0.44 mm to the I-beam's.

The 3D view draws the deflection **x10, marked exaggerated**; pick x1 in its Deformation control for true scale. The colours always come from the true strain.
@@ page cantilever-sections physics overview | Physics
# Physics

## Sections

The IPE 100 has h = 100, b = 55, tw = 4.1 and tf = 5.7 mm; the model leaves out the root fillets (7 mm radius), so it has 96 % of the catalogue area and 95.5 % of the catalogue I. Bent about the strong axis (web vertical):

$$A = 2 b t_f + (h - 2t_f)\,t_w = 9.903\ \mathrm{cm^2}, \qquad I = \frac{b h^3 - (b - t_w)(h - 2t_f)^3}{12} = 163.32\ \mathrm{cm^4}, \qquad W = \frac{I}{h/2} = 32.67\ \mathrm{cm^3}.$$

The bars have the same area: $d = \sqrt{4A/\pi} = 35.51$ mm with $I = \pi d^4/64 = 7.803$ cm⁴, and $a = \sqrt{A} = 31.47$ mm with $I = a^4/12 = 8.172$ cm⁴. Steel: $E = 210$ GPa, $\rho = 7850$ kg/m³, $f_y = 235$ MPa.

## Modes

The deflection is $w(s,t) = \sum_{n=1}^{3} \phi_n(s)\,\eta_n(t)$ with the clamped-free Euler–Bernoulli shapes

$$\phi_n = \cosh\beta_n s - \cos\beta_n s - \sigma_n(\sinh\beta_n s - \sin\beta_n s), \qquad \beta_n = \lambda_n / L, \qquad 1 + \cos\lambda_n\cosh\lambda_n = 0,$$

$\lambda_n = 1.8751,\ 4.6941,\ 7.8548$, normalised to $\frac{1}{L}\int_0^L \phi_n^2\,ds = 1$, so $\phi_n(L) = 2, -2, 2$. Every mode has the modal mass $m = \rho A L$ and

$$m\,\ddot\eta_n + 2\zeta\omega_n m\,\dot\eta_n + k_n\eta_n = \phi_n(L)\,F + m g_0 a_n, \qquad k_n = \frac{\lambda_n^4 E I}{L^3}, \qquad f_n = \frac{\lambda_n^2}{2\pi}\sqrt{\frac{E I}{\rho A L^4}},$$

with $a_n = \frac1L\int\phi_n\,ds$. As a bond graph, each mode is a 1-junction with I = m, C = 1/k_n and R = 2ζω_n m, joined to the tip 0-junction by a TF of modulus φ_n(L) (example **cantilever-modes**).

## Readouts

- Tip deflection $w = \sum \phi_n(L)\eta_n$; statically $12\sum\lambda_n^{-4} = 99.86\,\%$ of $F L^3/(3EI)$.
- Root moment from the equilibrium of the beam, $M(0) = F L + \rho A g_0 L^2/2 - \rho A\int_0^L s\,\ddot w\,ds = F L + m g_0 L/2 - m L\sum b_n\ddot\eta_n$ with $b_n = \frac{1}{L^2}\int s\,\phi_n\,ds$: exact statically.
- From the curvature instead, $E I w''(0) = \frac{2EI}{L^2}\sum\lambda_n^2\eta_n$ ([Round/M_modal](signal:Round/M_modal)) converges slowly: $4FL(\lambda_1^{-2} - \lambda_2^{-2} + \lambda_3^{-2}) = 1.0210\,FL$. The 3D strain colours use this curvature.
- Stress $\sigma = M c / I$, utilisation $|\sigma|/f_y$.

## Step and sine

A step of F swings a damped mode to $1 + e^{-\zeta\pi/\sqrt{1-\zeta^2}} = 1.939$ times its static deflection (all modes together: 1.904). The root moment overshoots more, to $2.21\,FL$: at the wall the inertia of the higher modes adds to the first mode's swing (three modes and the finite element model with all modes agree to 0.1 %). A sine $F_a\sin 2\pi f t$ settles at the amplitude

$$|w| = \Bigl|\sum_n \frac{\phi_n(L)^2 F_a / k_n}{1 - r_n^2 + 2 i\zeta r_n}\Bigr|, \qquad r_n = f/f_n,$$

$1/(2\zeta) = 25$ times the static deflection at resonance.

## Limits

Linear Euler–Bernoulli beams with small deflections: no shear deformation (about 1 % on the I-beam's deflection), no lateral-torsional buckling of the I-beam (about 5 kN here), no plasticity, bending in the vertical plane only.
@@ page cantilever-sections results overview | Results and checks
# Results and checks

## The step (default run)

![250 N step at 0.2 s: tip deflection and root stress|900](@fig:step)

![Settled at 9.9 s (x10): the bars bend 41 and 39 mm, the I-beam 1.9 mm|700](@fig:scene-static)

| at 10 s | round bar | square bar | IPE 100 | reference |
| --- | --- | --- | --- | --- |
| tip deflection | 40.68 mm | 38.85 mm | 1.944 mm | $FL^3/(3EI)$, 0.2 % |
| root moment | 500 N m | 500 N m | 500 N m | $FL$, 0.1 % |
| stress | 113.8 MPa | 96.3 MPa | 15.3 MPa | $FL/W$, 0.1 % |
| utilisation | 0.484 | 0.410 | 0.065 | $\sigma/f_y$ |
| largest deflection after the step | 77.47 mm | 73.97 mm | 3.701 mm | finite elements, 0.5 % |
| largest root moment after the step | 1105 N m | 1105 N m | (not resolved) | finite elements: 1104 N m = 2.21 F L, 2 % |
| largest utilisation after the step | 1.07 | 0.905 | (FE: 0.144) | finite elements, 2 % |
| f1 (FFT of the ring-down) | 6.42 Hz | 6.57 Hz | 29.4 Hz | $1 + \cos\lambda\cosh\lambda = 0$, 1 % |

The ratios $w_{round}/w_{IPE} = 20.93$ and $w_{square}/w_{IPE} = 19.99$ are the ratios of the second moments (0.2 %).

## Resonance

![10 N at 6.42 Hz, the round bar's first eigenfrequency|900](@fig:resonance)

| steady state, 10 N at 6.4233 Hz | round bar | square bar | IPE 100 |
| --- | --- | --- | --- |
| tip amplitude | 39.49 mm | 25.32 mm | 0.0815 mm |
| stress amplitude | 129.5 MPa | 73.1 MPa | 0.65 MPa |

The references are a finite element model of each beam (60 Hermite elements, every mode damped by ζ = 0.02), checked over 10 to 12 s to 1 %. The same checks at 50 N and 4 Hz, below every resonance, give 13.13, 12.20 and 0.396 mm.

## Sweep

![10 N swept from 2 to 40 Hz in 10 s|900](@fig:sweep)

The sweep passes the bars' first modes at about 1.4 s and the I-beam's at 7.4 s. It moves fast through each narrow resonance (0.26 Hz wide for the bars), so the peaks stay below the steady-state amplitudes.

## Acceptance checks

`expected.json` runs the model as `cantilever-sections` (the step), `-sine`, `-resonance`, `-weight` (own weight on: $w = FL^3/(3EI) + qL^4/(8EI)$, $M = FL + qL^2/2$, q = 76.26 N/m) and `-sweep`, with the dashboard's run overrides. The references come from `design/reference.py` (numpy/scipy only).
