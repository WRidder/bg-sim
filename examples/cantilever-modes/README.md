# cantilever-modes — a cantilever in two modes, as a scalar bond graph

A teaching example for the assumed-modes method. A clamped steel rod (E = 210 GPa, ρ = 7850 kg/m³, d = 10 mm, L = 1 m) gets a 1 N tip force step at t = 0.05 s. The rod is two cantilever eigenmodes, each a plain 1-junction with I, C and R, joined to the tip by a TF whose modulus is the mode's tip value |φ_n(L)| = 2. The tip is a 0-junction: one force, and the modal shares of the tip velocity add.

```
          Step ─► MSe ── 0 (tip) ──┬── TF(2) ── 1 (mode 1) ── I m, C 1/k1, R c1
                                   └── TF(2) ── 1 (mode 2) ── I m, C 1/k2, R c2
```

Every element parameter is a global parameter derived from `E`, `rho`, `d`, `L`, `F0` and `zeta` (Model > Global parameters). The library's `FlexibleBeam2D`/`FlexibleBeam3D` blocks are the multibond form of the same graph (see the manual page *Flexible bodies*).

## Numbers

| quantity | value |
| --- | --- |
| modal mass `m = rho A L` | 0.6165 kg |
| `k1 = lambda1^4 E I / L^3`, `k2` | 1274.3 N/m, 50050 N/m |
| f1, f2 (analytic) | 7.2358 Hz, 45.346 Hz |
| f1, f2 (FFT of `C1/q`, `C2/q`, damped) | 7.2267 Hz, 45.289 Hz |
| static tip deflection 2 (eta1 + eta2) | 3.2188 mm = 0.9954 F L^3/(3 E I) |
| tip deflection with 1 / 2 / 3 modes | 97.07 % / 99.54 % / 99.86 % of F L^3/(3 E I) |

`expected.json` checks both frequencies (FFT, 1 %), both settled modal coordinates (`eta_n = phi_n(L) F / k_n`) and the force step.

## Files

| file | content |
| --- | --- |
| `design/build.py` | uv script: writes the model and `expected.json` from the parameters at its top |
| `models/cantilever-modes.bgmodel.json` | the bond graph with its global parameters |
| `models/cantilever-modes.docs` | the model documentation (equations, sign of mode 2) |

Rebuild with `uv run examples/cantilever-modes/design/build.py`; check with `uv run examples/run_checks.py --only cantilever-modes`.

## Notes

- The second cantilever mode has φ2(L) = −2. The library TF modulus is positive, so the graph uses +2 for both modes and its `C2/q` is −η2 of the mode-shape convention.
- A global expression cannot use the built-in `pi`; the model declares a global `Pi`.
