# Van der Pol oscillator

The Van der Pol oscillator in practice: a tunnel-diode LC oscillator, a block on a spring riding a belt, and the textbook equation at four values of mu.

    x'' - mu (1 - x^2) x' + x = 0

The damping `-mu (1 - x^2) x'` is negative at small amplitude and positive at large amplitude. Every motion except rest ends on one limit cycle. Its amplitude is close to 2 for every mu. For small mu it is a near-sine of period `2 pi (1 + mu^2/16)`. For large mu it becomes a relaxation oscillation of period about `(3 - 2 ln 2) mu + 7.014 mu^(-1/3)`.

## Models

| model | what it shows |
| --- | --- |
| `vdp-tunnel-diode` | **Electronics.** A parallel LC tank on a tunnel diode biased in its negative-resistance region, as a bond graph. C, I and a nonlinear R (`TunnelDiode`, `i = -a v + b v^3`) hang on one 0-junction. The textbook equation runs alongside in the circuit's seconds. A cycle meter and an energy split read the limit cycle. Dashboard: mu, start amplitude, frequency/amplitude/period readouts, the component values for the chosen mu, plots. |
| `vdp-belt` | **Mechanics.** A block on a spring rides a belt. The friction contact is a nonlinear R in resistance causality: `BeltFriction` (the Taylor fit of the friction curve about the belt speed, exactly Rayleigh/Van der Pol) and, in a second rig, `StribeckFriction` (the full Stribeck curve). The textbook equation runs in the rig's seconds. 3D scene of the rig. |
| `vdp-textbook` | **Reference.** The equation at mu = 0.1, 1, 5 and 20, each as a block diagram (integrators, `Polynomial`, `Product`, `Gain`) and as an equation block (`VanDerPol`), with a cycle meter. |

The plots of BG-Sim are against time: there is no XY plot. Plot `x` and `x'` against time. The phase portraits in the model docs (`models/<model>.docs/`) come from the same runs, drawn by the docs build.

## 1. Tunnel-diode oscillator

Diode (a germanium tunnel diode of the 4.7 mA class, rounded values): peak 4.7 mA at 65 mV, valley 0.6 mA at 355 mV. It is biased at `V0 = 210 mV`, `I0 = 2.65 mA`. The bond graph models the deviations about this point. The cubic `i = -a v + b v^3` has its extrema at the peak and the valley when

    A = (V_v - V_p)/2 = 145 mV,   a = 3 (I_p - I_v)/(4 A) = 21.207 mS (-47.15 Ohm),   b = a/(3 A^2) = 0.33622 A/V^3

Bond graph: `C v' = -i_L + a v - b v^3` and `L i_L' = v`. Differentiating and scaling with `tau = w0 t`, `w0 = 1/sqrt(L C)` and `v = A x` gives

    x'' - mu (1 - x^2) x' + x = 0,     mu = a sqrt(L/C),   A = sqrt(a/(3 b)),   x' = i_C/(w0 C A)

`mu` is the diode's negative conductance times the tank impedance `Z0 = sqrt(L/C)`. The model keeps the tank resonance at `f0 = 10 MHz` and derives `Z0 = mu/a`, `L = Z0/w0` and `C = 1/(Z0 w0)` from the global `mu`:

| mu | Z0 | L | C | frequency | peak voltage |
| --- | --- | --- | --- | --- | --- |
| 0.2 | 9.43 Ohm | 150.10 nH | 1687.6 pF | 9.975089 MHz | 290.06 mV |
| 1 (default) | 47.15 Ohm | 750.49 nH | 337.52 pF | 9.429558 MHz | 291.25 mV |
| 5 | 235.77 Ohm | 3752.4 nH | 67.50 pF | 5.410834 MHz | 293.12 mV |

The run starts at `v = A x0` with `i_L = i_D(v)`, so `i_C = 0` and the circuit starts at `(x, x') = (x0, 0)`.

**Energy.** The diode power is `P_D = v i_D = -a A^2 (x^2 - x^4/3)`. The diode supplies energy while `|v| < sqrt(a/b) = 251 mV` and dissipates it beyond. The tank loses exactly what the diode absorbs: `C v^2/2 + L i_L^2/2 + int P_D dt` is constant. On the limit cycle at mu = 1 the diode supplies 13.418 pJ per cycle and dissipates the same 13.418 pJ.

## 2. Belt-driven oscillator

Block `m = 1 kg`, spring `k = 100 N/m` (`w0 = 10 rad/s`), normal force `F_n = 40 N` (the block's weight and a pressure pad). The friction curve over the slip `w = v_b - x'` is

    F(w) = F_n (mu_c + (mu_s - mu_c) exp(-(w/v_s)^2)) + sigma w,     mu_s = 0.45, mu_c = 0.30, v_s = 0.1 m/s

The belt runs at the inflection point of the Gaussian drop, `v_b = v_s/sqrt(2) = 70.71 mm/s`. There the Taylor series has no quadratic term:

    F = F0 + alpha x' - beta x'^3,   alpha = alpha_f - sigma,   alpha_f = 51.466 N s/m,   beta = F'''(v_b)/6 = 3431.06 N s^3/m^3

so the block obeys **Rayleigh's equation** `m y'' - alpha y' + beta y'^3 + k y = 0` (`y = x - x_s`, `x_s = F0/k = 189.25 mm`). Its derivative is Van der Pol in the **velocity**:

    mu = alpha/sqrt(k m),   tau = sqrt(k/m) t,   x_vdp = x'/V,   V = sqrt(alpha/(3 beta))

The model sets `mu = 0.5`, so `alpha = 5 N s/m`, `sigma = 46.466 N s/m` and `V = 22.04 mm/s`. The viscous term is needed because `V/v_b = sqrt(alpha/alpha_f)`. Without it the velocity swing (about `2V`) would reach the belt speed and the block would stick: that is stick-slip, not Van der Pol. With it the swing is 62 % of `v_b`. A belt-driven oscillator is Van der Pol only near the onset of instability.

## 3. Textbook

From `x = 0.5`, `x' = 0`, 200 time units:

| mu | limit-cycle period | `2 pi (1 + mu^2/16)` | relaxation estimate | amplitude |
| --- | --- | --- | --- | --- |
| 0.1 | 6.28711127 | 6.287112 (+1.6e-7) | | 2.0001040 |
| 1 | 6.66328686 | 6.675884 (+0.19 %) | 8.628 | 2.0086199 |
| 5 | 11.61223067 | 16.10 | 12.1705 (+4.81 %) | 2.0215081 |
| 20 | 34.68232331 | 163.4 | 34.8582 (+0.51 %) | 2.0077900 |

## Validation (`expected.json`, `uv run examples/run_checks.py --only van-der-pol`)

All reference numbers come from `design/design.py`, an independent scipy calculation:

- the textbook limit cycle by shooting on the section `x = 0`, `x' > 0` (DOP853, or Radau for mu >= 5, tolerance 1e-13);
- the circuit and the belt integrated in SI units, not in the scaled form, then scaled and compared with the textbook run. The difference is 2e-11 to 5e-10 in scipy, so the mappings are exact.

89 checks, all passing. bgsim results against the references:

| quantity | bgsim | reference (scipy) |
| --- | --- | --- |
| textbook periods, mu = 0.1 / 1 / 5 / 20 (cycle meter, last cycle) | 6.28711127159 / 6.66328685932 / 11.6122306677 / 34.6823233116 | 6.28711127229 / 6.66328685932 / 11.6122306677 / 34.6823233117 |
| textbook amplitudes | 2.00010393 / 2.00861986 / 2.02150806 / 2.00778997 | 2.00010398 / 2.00861986 / 2.02150806 / 2.00778997 |
| block diagram vs equation block, max difference | 1.4e-14 / 0 / 0 / 1.8e-10 | |
| circuit, mu = 1: period, frequency | 106.0495041 ns, 9.42955847 MHz | 106.0495041 ns, 9.42955847 MHz |
| circuit, mu = 0.2 / 5: frequency | 9.97508856 / 5.41083405 MHz | 9.97508856 / 5.41083405 MHz |
| circuit scaled states vs textbook (Xc, Yc against Ref), mu = 0.2 / 1 / 5 | 1.2e-13 / 2.4e-12 / 9.6e-10 | |
| circuit energy invariant `E_tank + int P_D dt` | drift 4.4e-13 of the energy scale | exact |
| diode energy per cycle, supplied = dissipated (mu = 1) | 13.4184018 pJ = 13.4184018 pJ | 13.4184019 pJ each |
| belt (cubic) period, velocity amplitude | 0.638067580 s, 2.00248793 V = 44.135 mm/s | 0.638067580 s, 2.00248793 V |
| belt (cubic) scaled states vs textbook | 1.5e-11 | |
| belt (Stribeck) period, velocity amplitude | 0.638438423 s, 2.03988526 V | 0.638438423 s, 2.03988526 V |
| smallest slip (cubic / Stribeck) | 26.58 / 25.75 mm/s (never sticks) | 26.58 / 25.75 mm/s |
| belt energy invariant | drift 4.0e-11 of the energy scale | exact |
| contact energy per cycle, fed = taken back | 0.430904 mJ each | 0.430904 mJ each |
| small-mu period `2 pi (1 + mu^2/16)` | +1.6e-7 (mu = 0.1), +0.19 % (mu = 1) | |
| relaxation period | +4.8 % (mu = 5), +0.51 % (mu = 20) | |

## Files

- `design/design.py` writes `design/design.json` (the reference numbers);
- `design/build_model.py` writes the three models, the belt scene and `expected.json` from it;
- `library/`: `TunnelDiode` (cubic conductance), `BeltFriction` (cubic friction fit), `StribeckFriction`, `VanDerPol` (the equation block), `CycleMeter` (period, frequency, amplitude and energy per cycle from events), `EnergySplit` (supplied/absorbed energy), `StoredEnergy`, `Lin2`;
- the model docs come from `tools/example_docs/src/van-der-pol.md` (`uv run tools/example_docs/build.py --only van-der-pol`).
