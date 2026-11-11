# Choices WP-O3c1

Package O3c1 migrated `quad-pendulum`, `pendulum-double-cart`, `pendulum-double-cart-lab`, `pendulum-triple-cart`,
`cube-3d`, `fem-bracket`, `fem-gantry`, `fem-torsion`, `robot-arm-3d`, `panda-3d`, `humanoid-dual-arm` and
`fanuc-pick`.

## Generators

Every generator found reproduced its committed models byte for byte apart from the reversed bonds (each was run
after the fix and `git diff` showed nothing else: no library block, scene, `expected.json` or project file
changed except where listed below). So every generated model was regenerated, none was migrated with the tool.

| example | generator (fixed) | how it was run |
| --- | --- | --- |
| `quad-pendulum` | `design/models.py` (`build_cart`, `build_rotary`) | `design/build_models.py` |
| `pendulum-double-cart`, `pendulum-triple-cart` | `pendulum-double-cart/design/cartmodel.py` (shared; imported only by these two and by `pendulum-double-cart-lab`) | the model step of `cartpend.write_all` (a scratch script calling `cartmodel.build` with the example's `SCENARIO`, without the design run and without rewriting the controller tables); `rlmodels.py --rl balance`, `--rl swingup` |
| `pendulum-double-cart-lab` | the same `cartmodel.py` | `design.py --models`, `rlmodels.py --rl --rl-robust`, `robustmodels.py` (library blocks rewritten identical) |
| `fem-bracket`, `fem-torsion`, `fem-gantry` | `design/build.py` | `design/build.py` (it also rewrites `expected.json` and the scenes: unchanged) |
| `robot-arm-3d` (`rrr-multibond*`) | `design/build_models.py` | as is |
| `panda-3d` | `design/build_models.py` | as is |
| `humanoid-dual-arm` | `design/build_models.py` | as is |
| `fanuc-pick` | `design/build_models.py`, `design/build_library.py` (and the hand-written `library/PneumaticCylinder.jl`) | both scripts (`PickPlanner.jl`, `PickMonitor.jl` rewritten identical) |

Hand-written JSON, migrated with `tools/migrate_bond_orientation.py` (unchanged; `--check` first):
`cube-3d/cube-3d-mb`, `cube-3d-mb-soft` and `robot-arm-3d/arm` (`arm` is not touched by its generator). All
neutral, no source and no review case.

## Decisions

- **Joint parents and mounted parents.** `Joint.parent -> N` becomes `N -> Joint.parent`; a mounted parent
  `T.b -> BodyJ` becomes `BodyJ -> T.b` (`T.a -> Joint.parent` kept). On a 1-junction that is now the body
  twist this reversal is exactly neutral: the parent port reads `+V` before (tail of a `-V` junction) and after
  (head of a `+V` junction), and its effort is fixed by the joint law. No value was negated.
- **FEM faces** (`ModalBody3D` A, B, E, S). The face junctions changed sign in WP-O3a (`nodeX -> core.pX`), so a
  bond kept on a face reads the other sign. `Bracket.B`/`Hub.p` -> weld parents, `Beam.E -> YGuide.parent` and
  the iconic `translation` ports on the slide face `S` (`YMotor.b`, `SlideSpring.b`, `SlideDamper.b`) are
  reversed to `face -> port`. For the slide face this is the "`any` port on a body face" hazard of WP-O3a: before
  O20 it would have compiled and read minus the slide rate; reversed it reads the same rate as before. The
  `CSpatial`/`RSpatial` clamps of the ring-down and static models were already `face -> element` and stay; they
  now read the other sign of the face twist (linear, odd: their port variables flip, the motion does not).
- **humanoid-dual-arm, the weld drives** (the tool's `--check` on the old model agrees and calls them neutral).
  `LWeld.drive -> LWeldJ` (and `R`) is reversed
  to `LWeldJ -> LWeld.drive`. The junction holds only the linear `WeldSpring` (C) and `WeldDamper` (R), so the
  junction flow changes from `-qdot` to `+qdot`, the spring and damper port variables and the spring's state
  change sign, the torque on the joint does not. The spring has no start value, so nothing else changes.
  No check, plot or dashboard reads these signals.
- **fanuc-pick, project blocks (O15, O17).**
  - `ToolMotion` is a spatial flow source (F4 lists it): declared `p => :out`, law `p.f ~ -(V + Vd (t - tk))`
    so that at the tail it imposes `+V` on the gripper junction `TJ`, and `W ~ -p.e` so the reported flange
    wrench keeps its meaning and sign (`Tool/W` is plotted). The joint mounts are now bonded `TJ -> JM.b`.
  - `SphereInBox`, `CylinderInBox` are two-body contacts like `SuctionCup`: declared `a`, `b` `in`; the port
    flows are now the body twists and the efforts minus the wrenches on the bodies (all `a.f`, `b.f` reads and all
    `a.e`, `b.e` writes negated in `build_library.py`, exactly as WP-O3a changed `SuctionCup`). Their bonds
    (`Parcel -> WA.b`, `WA.a -> Walls.a`, the same for the content) were already in the contact pattern and
    stay, so without this change the content would have seen the negated twists (no E114 shows it).
  - `PneumaticCylinder` is an effort source at the tail of its bond (`Cyl.p -> ZJ`), already right for O15:
    declared `p => :out`, law unchanged.
- **Workarounds and notes removed (O12).** The "bond directions matter: `Joint.parent -> N`" notes in
  `pendulum-double-cart/README.md`, `pendulum-triple-cart/README.md` and the docs source
  `pendulum-double-cart/design/docsgen.py` (used by both cart examples) state the old rule and are gone; the
  generator comments that justified the old directions (`fem-bracket`, `fem-torsion`, `fanuc-pick`) now state the
  new rule. The built docs (`models/*.docs`) still carry the old paragraph until WP-O5 rebuilds them.

## Cross-check with the tool

`tools/migrate_bond_orientation.py --check` run on the pre-migration copies of every generated model proposes
exactly the reversals the generators now make, all neutral (quad-pendulum 15 per model, double cart 9, triple
cart 12, fem-torsion 9, fem-bracket 9 and 5, fem-gantry 16 and 9, humanoid-hold 47, robot-arm and panda as listed
in the report). For `fanuc-pick` it reports 15 neutral and 11 review per model and leaves the joint-mount bonds
unchanged: `Tool` (`project:ToolMotion`) "flips sign and its law is not known to be odd", `Walls`
(`SphereInBox`/`CylinderInBox`) "multi-port block with a flipped port", and the rods, cups, floor contacts and
body faces in the same sign group. Those are the project-block law changes above, made by hand in the generator.

## The two models without a numeric check

`pendulum-double-cart-plant` and `pendulum-double-cart-lab-plant` share the bond graph of the checked
`-free` models (`cartmodel.build`). Each plant was started in the `-free` pose (Joint1/Joint2/Rail `q0` and pivot
deflections copied, the `-free` settings, `V = 0`, no push; for the lab plant the `LabRealism` forces set to 0 and
the end-stop start at 0.05, which the `-free` model does not have) and run against the `-free` model, whose angles
and cart position are checked against the design ODE. Max differences over the 2 s free swing (the plant run on a
4x coarser output grid, interpolated):

| signal | double cart: max abs / max diff | lab: max abs / max diff |
| --- | --- | --- |
| `Rail/qout` (m) | 6.07e-2 / 4.6e-7 | 7.80e-2 / 5.4e-7 |
| `Joint1/qout` (rad) | 2.72 / 4.2e-5 | 2.65 / 1.3e-5 |
| `Joint2/qout` (rad) | 1.13 / 1.1e-4 | 1.02 / 3.7e-5 |
| `Joint2/qdout` (rad/s) | 19.1 / 7.6e-3 | 9.56 / 9.3e-4 |
| `Motor/isense/y` (A) | 0.215 / 4.6e-4 | 0.491 / 1.1e-3 |
| `Joint1/child.e[1]` | 1.57e-3 / 5.7e-7 | 9.9e-4 / 6.8e-8 |

The differences are those of the output interpolation; no signal changes sign between the plant and the checked
model.

## Final state

- `tools/migrate_bond_orientation.py --check` reports "nothing to do" for all 60 models of the 12 examples:
  the 52 models a generator rewrote with `--skip-law-change O15 --skip-law-change O7` (they carry no markers),
  the 3 tool-migrated models (`cube-3d-mb`, `cube-3d-mb-soft`, `robot-arm-3d/arm`, marked) and the 5 untouched
  ones (`cube-3d`, `rrr`, `rrr-free`, `rrr-torque`, `humanoid-ik`) without flags. The tool knows no project-block
  law, so it cannot see the fanuc `ToolMotion`/`SphereInBox`/`CylinderInBox` changes; the fanuc checks cover them.
- `uv run examples/run_checks.py --only <name>`, no tolerance or expected value changed: quad-pendulum 183/0,
  pendulum-double-cart 95/0, pendulum-double-cart-lab 170/0, pendulum-triple-cart 72/0, cube-3d 88/0,
  fem-bracket 18/0, fem-gantry 88/0, fem-torsion 6/0, robot-arm-3d 124/0, panda-3d 247/0, humanoid-dual-arm 428/0,
  fanuc-pick 249/0 (passed/failed).
- `julia/BGSim/test/test_flatten.jl` (loads `examples/pendulum-double-cart-lab`): 438/438 pass.
