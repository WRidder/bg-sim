# Suction cup — one bellows cup holds a box through holds, bounces, steps, swings and a chirp: lift stroke, bottoming, sway and tilt resonances, overload

One bellows suction cup holds a small box (0.6 kg, 120 x 120 x 40 mm). The cup is the 1.5-fold bellows
cup of `fanuc-pick` (lip 32 mm, rest length 30 mm), a `stdlib:contact/SuctionCup` with the nonlinear
bellows switched on. It sits on a tool with a prescribed motion, and one compact ejector evacuates it.
The box is a free rigid body. It starts on a table (four corner contacts), is lifted, put through one
motion, put back and released.

The example shows the dynamics of the cup model:

- **Vacuum lift stroke.** The vacuum on the folds pulls the bellows shut (10 N at 59 kPa). That is more
  than the weight of the box, so the cup lifts the box off the table before the tool moves.
- **Axial spring-mass mode and bottoming.** A step and a vertical chirp ring the box on the bellows.
  At resonance the folds stack up, and the hardening shifts the resonance upward.
- **Sway and tilt.** A lateral load moves the bellows sideways and tilts the box. That gives two
  lateral modes and a peeling moment on the lip.
- **Holding limit.** The utilisation `U` (axial pull, peeling moment and shear as a fraction of the
  holding capacity `A_eff·dp`) shows the margin. Past 1 the lip lifts, leaks and the seal is lost.

The model docs (Docs tab, `models/*.docs`) hold the derivation and the plots. Their source is
`tools/example_docs/src/suction-cup.md`.

## Models

All seven models are the same plant with other global parameters (`motion` selects the excitation).
`linear-vs-nonlinear` has a second, identical cup and box next to the first, with the nonlinear bellows
terms at 0 (`k_bot`, `A_fold`, `c_vac`, `c_ext`).

| model | motion | outcome |
| --- | --- | --- |
| `hold-release` | vacuum on, lift 60 mm, hold, lower, release | the lift stroke lifts the box 1.7 mm off the table; hang ext −1.668 mm; max U 0.28 |
| `bounce` | 4 mm step down, then a vertical chirp 3 to 20 Hz, 1.7 mm | ring-down at 10.27 Hz, ζ 0.103; the folds bottom (69 N) near 13.9 Hz; held, max U 0.87 |
| `steps` | horizontal acceleration pulses 1.5, 3 and 4.5 m/s² | sway 6.6 Hz and tilt 13.1 Hz modes; max U 0.90 (quasi-static 0.61); held |
| `swing` | tool tilt to 30° and back, then ±10° at 1.5 Hz | at 30°: lateral deflection 1.013 mm, U 0.60; held, max U 0.84 |
| `chirp` | lateral chirp 1.5 to 20 Hz, 0.4 mm | transmissibility peaks 2.75 (6.6 Hz) and 3.28 (13.4 Hz); held |
| `overload` | 0.8 kg box on pulses of 3, 6 and 9 m/s² | survives 3 m/s² (U 0.87), lost at 2.51 s in the 6 m/s² pulse |
| `linear-vs-nonlinear` | `bounce` with both cups | nonlinear box hangs 4.02 mm higher; it bottoms (U 0.87), the linear cup does not (U 0.64); both hold |

Every model has a dashboard:

- an XY force-stroke plot (the transmitted force `T` against `ext` while the cup is sealed, from
  `CupMonitor`, so the free tool after a release or a loss does not stretch the axes), which shows the
  lift-stroke offset, the bottoming knee, the damping loops and the capacity limit;
- the lateral force against the lateral deflection, U over time and the transmissibility against the
  chirp frequency;
- readouts of U, the held flag, the lip gap, the vacuum, the axial and lateral deflection, the box tilt
  and the holding capacity;
- sliders for the payload mass, the centre-of-mass offset, the vacuum level (ejector end vacuum) and
  scales for the motion amplitude and frequency.

The 3D scene shows the cup see-through: the bellows follows the stretch and the tilt between the
tool and the box, the two fold rings move with it, the bellows is coloured by the vacuum and the lip
by U (blue to red). A lost seal leaves the lip behind on the box.

## Files

- `library/`: the project blocks.
  - `CupTool` is the tool pose and twist: the lift, lower and retract S-curves plus the excitation of
    each motion (step and vertical chirp, acceleration pulses, tilt swing, lateral chirp).
  - `CupMonitor` provides the drawn bellows and lip segments, the box tilt, the lip distance and the
    held latch. It also passes the cup's `ext` and `T` on, multiplied by the seal latch, for the
    force-stroke plot.
  - `Transmissibility` demodulates the box and tool motion at the chirp phase into `TR`.
- `design/params.py`: all parameters. They become global parameters of the models.
- `design/build_model.py`: writes `models/*.bgmodel.json`, `bgsim.project.json` and the scenes
  (`scenes/suction-cup.sdf`, `scenes/suction-cup-compare.sdf`, through `scene.py`).
- `design/analysis.py`: the hand calculation. It covers the operating vacuum, the static hold with the
  lift stroke and bottoming, the axial mode, the two-degree-of-freedom lateral model (modes and
  transmissibility) and the quasi-static utilisation of the steps and the tilt. With `--sim` it runs
  the hold and the swing and prints the simulated numbers next to the hand values. It writes
  `design/results.json`.
- `design/run_model.jl`: the Julia batch runner used by `analysis.py --sim`.

Regenerate:

```
uv run examples/suction-cup/design/build_model.py
uv run examples/suction-cup/design/analysis.py --sim
uv run examples/run_checks.py --only suction-cup
uv run tools/example_docs/build.py --only suction-cup
node tools/video/capture-suction-cup.mjs suction-cup-video   # BGSIM_VIDEO_URL = a backend with the real worker
```

## Results (design/results.json)

| quantity | simulation | hand calculation |
| --- | --- | --- |
| operating vacuum | 59 152.1 Pa | 59 152.3 Pa |
| holding capacity `A_eff·dp` | 29.576 N | 29.576 N |
| lift force `A_fold·dp`, unloaded lift stroke | – | 10.056 N, 4.022 mm |
| hanging extension (0.6 kg), nonlinear / linear cup | −1.668 / +2.345 mm | −1.668 / +2.354 mm |
| axial mode | 64.55 rad/s (10.27 Hz), ζ 0.1033 | 64.55 rad/s, ζ 0.1033 |
| lateral modes (side stiffness × kf 1.871) | 6.59 / 13.13 Hz | 6.55 / 13.20 Hz |
| lateral modes of the linear cup | – | 4.89 / 9.69 Hz |
| lateral deflection / U at a 30° tilt | 1.013 mm / 0.603 | 1.016 mm / 0.620 |
| U in the 4.5 m/s² steps | 0.90 (dynamic) | 0.61 (quasi-static) |
| U of the 0.8 kg box at 6 m/s² | lost | 0.996 (quasi-static) |

- **Lift stroke.** The vacuum pulls the folds in by `A_fold·dp/k_ax = 4.02 mm`. A 0.6 kg box only
  stretches the bellows by 2.35 mm, so the loaded nonlinear cup stays 1.67 mm short. On the table this
  lifts the box off; in the comparison the nonlinear box hangs 4.02 mm higher.
- **Bottoming.** The lift stroke and the static load use up 1.7 mm of the 6 mm compression travel. In
  the vertical chirp the nonlinear cup hits the stacked folds (`F_bot` up to 69 N). The hardening
  bends the resonance up, so the response stays large past 10.3 Hz and bottoms hardest at about 13.9 Hz.
  This raises the peak U from 0.64 (linear cup) to 0.87. With a slightly larger chirp (amplitude scale
  1.03 or 1.05) the bottoming rebound tears the nonlinear cup off while the linear cup still holds.
- **Centre-of-mass offset.** The cup carries an off-centre box poorly. A 30 mm offset makes a peeling
  moment of 0.18 N·m, which counts as 22 N against the 29.6 N capacity: the lip peels as soon as the box
  leaves the table.
- **Side stiffness.** The vacuum and the shortened bellows make the cup 1.87 times stiffer sideways.
  The lateral modes move from 4.9 / 9.7 Hz (linear cup) to 6.6 / 13.2 Hz.

`expected.json` pins these claims: the vacuum, the capacity, the hanging extension and the lift-off,
the axial mode and damping, the bottoming, both lateral modes, the tilt deflection, the transmissibility
peaks, the loss of the overloaded box and the held outcome of every other model.

## Notes

- All models use `FBDF` (the cup chamber is stiff).
- The nonlinear bellows parameters (`s_bot`, `k_bot`, `A_fold`, `c_vac`, `c_ext`) are estimates for a
  1.5-fold cup. They are not datasheet values.
- `U` has a smooth floor at −1: a bellows pushed hard against the box (compression, no pull) reads
  −1. That is why the bounce plots dip to −1.
- The video script is `tools/video/capture-suction-cup.mjs`. It records every model at 1x real time.
