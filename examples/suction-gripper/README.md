# Suction gripper — a six-cup vacuum gripper moves a carton: profiles, yaw, tilt, porosity and supply layouts decide when cups peel off

A six-cup bellows vacuum gripper on a gantry picks a closed 10 kg carton (0.5 x 0.3 x 0.3 m) from a
conveyor, lifts it 0.15 m, moves it 1 m, lowers it onto the place table and releases it. The carton is
a free rigid body, held by six `stdlib:contact/SuctionCup` elements. They are fed through per-cup lines
(`CupValve`) from a manifold `Volume` and a `stdlib:contact/VacuumGenerator`.

The example answers three questions:

- What is the fastest move with safety factor 2, for sealed, cardboard and porous parcels?
- Does the motion profile matter, at equal time and at equal peak acceleration?
- What is the effect of the cup-pattern yaw and of tilting the gripper ("waiter's tray")?

It also covers the air side: the generator curve, leaks through the lip and the material, the supply
topology and the pick-up time.

The model docs (Docs tab, `models/*.docs`) hold the full derivation and the tables. Their source is
`tools/example_docs/src/suction-gripper.md`.

## Models

All eight models are the same plant with other global parameters. `separate-generators` replaces the
manifold with a generator per cup.

| model | what | outcome |
| --- | --- | --- |
| `transfer` | S-curve, 1.75 s, cardboard, 60 l/min | max U 0.450 ≤ 0.5, placed at x = 1.000 m |
| `aggressive-trapezoid` | trapezoid, 0.74 s (8.2 m/s²) | the bellows ring at the deceleration step, and all six cups peel |
| `aggressive-scurve` | S-curve, 0.74 s (11.7 m/s²) | max U 1.53, but held |
| `tilt-tray` | cycloidal, 1.25 s, tilt gain 1 | max U 0.45 (0.62 level) |
| `porous-undersized` | porous parcel, 36 l/min, S-curve 1.1 s | 21.6 kPa, lost in the deceleration |
| `edge-leak` | cup 1 over the edge (20 mm² leak), common manifold | all cups at 16.7 kPa, nothing lifted |
| `edge-leak-valves` | the same, with per-cup flow valves | cup 1 isolated, the others at 48.7 kPa, held |
| `separate-generators` | the same, with a 10 l/min generator per cup | good cups at 48.3 kPa, held |

The `transfer` model has a dashboard with these controls:

- plots of U and vacuum;
- the held indicator and the lost-cup counter;
- sliders for the profile, transfer time, yaw, tilt gain, permeance and generator flow.

The 3D scene colours each cup by its utilisation, from blue to red, and turns a lost cup grey.

## Files

- `library/`: the project blocks.
  - `GripperPath` is the gripper pose and twist from the profiles, with the previewed tilt servo.
  - `ProfileSelect` picks one of the four transfer profiles.
  - `CupValve` is a line with an optional check valve or flow-closing valve.
  - `GripMonitor` provides the held flag and the lost-cup count.
  - `ContactFoot.bgsub.json` is a library subsystem: one table contact (mount, corner pose and
    `ContactPoint` on the table plane). The four corners under the carton (`Floor1` to `Floor4`) are
    instances of it, pinned to their corner offsets.
- `design/params.py`: all parameters. They become global parameters of the models.
- `design/sizing.py`: the analytic sizing. It covers quasi-static cup loads (bellows statics linearised at
  the hang point, with the lift stroke, the bottoming and the vacuum- and stroke-dependent side stiffness
  of the nonlinear `SuctionCup`, and the bolt-group formula), the operating vacuum, the generator size, the
  pick-up ODE and the topology.
- `design/build_model.py`: writes `models/*.bgmodel.json`, `library/ContactFoot.bgsub.json` and
  `scenes/suction-gripper.sdf` (through `scene.py`).
- `design/design.py`: the analysis.
  - It runs the hand calculation and validates it against simulations.
  - It covers DAF against jerk, the equal-time comparison and the scenarios.
  - It bisects the shortest safe move time per parcel, profile, yaw and tilt.
  - It writes `design/results.json` and `design/min_move_time.svg`.
- `design/run_model.jl`: the Julia batch runner used by `design.py`. It compiles once and applies the
  overrides to the global parameters.

Regenerate:

```
uv run examples/suction-gripper/design/build_model.py
uv run examples/suction-gripper/design/design.py --procs 7      # about 25 min
uv run examples/run_checks.py --only suction-gripper
uv run tools/example_docs/build.py --only suction-gripper
node tools/video/capture-suction.mjs suction.mp4                 # BGSIM_VIDEO_URL = a backend with the real worker
```

## Results (design/results.json)

Operating vacuum per cup in kPa (simulation against analytic: 48 329.8 / 48 329.9 Pa for cardboard at
60 l/min):

| parcel | 20 l/min | 30 | 45 | 60 | 90 |
| --- | --- | --- | --- | --- | --- |
| sealed | 54.1 | 56.0 | 57.3 | 58.0 | 58.6 |
| cardboard | 34.4 | 40.3 | 45.4 | 48.3 | 51.7 |
| porous | 14.1 | 19.1 | 24.7 | 29.0 | 35.0 |

Shortest safe transfer time in seconds (U ≤ 0.5, 60 l/min, yaw 0, level / tilted):

| parcel | trapezoid | S-curve | polynomial | cycloidal |
| --- | --- | --- | --- | --- |
| sealed | 1.43 / 1.61 | 1.43 / 1.39 | 1.26 / 1.08 | 1.32 / 1.08 |
| cardboard | 1.74 / 1.91 | 1.61 / 1.46 | 1.50 / 1.16 | 1.54 / 1.19 |
| porous | > 3.9 / 3.60 | 3.40 / 2.50 | 3.03 / 2.38 | 3.10 / 2.13 |

- **Profile.** At equal time (0.74 s) the trapezoid is the only profile that loses the parcel, although its
  peak acceleration is the lowest (8.2 against 10.5 to 11.7 m/s²). At 0.7 s the S-curve (13.1 m/s²) is
  lost too, while the polynomial and the cycloid still hold; at 0.8 s all four hold. The dynamic
  amplification at 4 m/s² is 1.80 for the trapezoid and falls from 1.63 to 0.96 for S-curves with λ = 0.1
  to 0.5.
- **Yaw.** A pattern at 45° or 90° to the path is 10 to 31 % slower (cardboard S-curve: 1.61 to 1.96 /
  2.00 s).
- **Tilt.** Tilting saves 14 to 31 % with the polynomial and the cycloid, 3 to 26 % with the S-curve. The
  trapezoid gets 10 to 13 % slower with the tilt for sealed and cardboard parcels: its acceleration
  jumps, so the smooth tilt servo is wrong right after each step, where the ringing peak decides.
- **Generator.** For S = 2 at 2 m/s² the generator needs 5 l/min for sealed parcels, 31 l/min for
  cardboard and 138 l/min for porous parcels.
- **Supply topology.** One cup off the edge on a common manifold drops every cup. Flow valves (48.7 kPa),
  restrictor nozzles (40.9 kPa) or separate generators (48.3 kPa) keep the other five cups holding.

`expected.json` pins these claims: the vacuum levels, the generator flow, U ≤ 0.5 over the safe moves,
held/lost by phase and the placed position.

## Notes

- All models use `FBDF`. The `auto` choice (Tsit5) is about 5 times slower on these stiff cup chambers
  and stops with `MaxIters` in the porous and edge-leak runs.
- The video script is `tools/video/capture-suction.mjs`. It records the safe move, the trapezoid loss,
  the S-curve at the same time and the porous parcel, using the dashboard sliders.
