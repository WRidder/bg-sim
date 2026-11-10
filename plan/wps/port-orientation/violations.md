# WP-O0: violations

How many bonds in today's models break the rules of `plan/PORT_ORIENTATION_PLAN.md` once the orientations of
`orientation-table.md` are declared, and what a migration (O9) would have to do with each of them.

**Measured or estimated.**
- **Measured**: the examples and the fixture JSONs. Every model was flattened by the compiler's own instantiation,
  with subsystem faces resolved, and checked bond by bond.
- **Estimated**: the Julia test files, by a static parse of their source (section 6).

## 1. Method

1. `dump_bonds.jl` (scratch) flattens each model with `BGSim`'s instantiation, the same path `compile` takes. It
   writes every connection with its two ends resolved to an element port or a junction, plus the junction kinds and
   the instance refs.
   - Covered: all 234 models of the 68 examples (`examples/*/models/*.json`) and the 58 model fixtures (contracts
     and `julia/BGSim/test/fixtures`).
   - Composite internals are marked and counted separately (`composites.md`). They change with WP-O5, not with the
     migration.
2. `violations.py` applies the table to every bond:
   - **O3**: an `in` port at the tail, or an `out` port at the head.
   - **O4**: two ports with the same fixed orientation (in-in, out-out). No reversal fixes those.
3. Each O3 bond is classified for O9 by what its reversal does to the equations. The rules come from
   `orientation-table.md` section 1.
   - Reversing a bond on a 1-junction negates `(e, f)` of that port.
   - A bond between two elements, or to a 0-junction, is direction-free.
   - A table `change` negates the port's convention.
   - These negations travel along a **chain**: element-to-element bonds, plus the two sides of a pass-through
     two-port. Two negations on one chain cancel.
   - Reversing every bond of a 1-junction (or of a cluster of 1-junctions joined by 1-1 bonds) changes nothing. So
     per cluster the migration may reverse the violating set or its complement, and the script picks the cheaper
     one.
   - A chain with an odd net negation is then classified:
     - **neutral\***: it contains an odd one-port (I, C, R). The model is the same, but that element's variables
       change sign: its start value and any signal read from it must be negated.
     - **source**: it contains a source. Negating its value (or its input signal) restores the model.
     - **review**: neither, so a person must decide.
   - A chain with an even net negation is **neutral**: reverse the bond, and nothing else changes.
   - **Silent** chains are odd chains with no violating bond. The migration must still touch them, because a block
     on them changes its law. The plain bond count misses these.
4. Three variants of the table:
   - **V0**: the plan as written. Every pass-through two-port is fixed `a in, b out`; iconic ports are `any`.
   - **V1**: V0 plus amendment **A1**. The pass-through two-ports (the mounts FixedTransform2D/3D/3DNeutral, TFAd,
     TFAdNeutral, JointTransform2D/3D, FixedJoint2D, TF/GY/MTF/MGY, PowerSensor) carry the relation "`a` and `b`
     opposite", and the compiler resolves it from the neighbours. **Recommended.**
   - **V2**: V1 plus amendment **A2**: every iconic port `in`. Not recommended.

## 2. Totals (examples: 234 models, 6510 bonds outside composite internals)

| | V0 (plan as written) | V1 (A1, recommended) | V2 (A1 + A2) |
| --- | ---: | ---: | ---: |
| O3 bonds | 793 | **528** | 624 |
| O4 bonds | 959 | **30** | 42 |
| neutral | 561 | 457 | |
| neutral\* | 4 | 4 | |
| source | 37 | 31 | |
| review | 191 | **36** | 96 |
| silent chains (source / review) | 67 / 167 | 17 / 3 | |
| models with at least one O3/O4 bond | 178 | 147 | 148 |
| models the migration touches (O3/O4 or a silent chain) | 180 | 151 | 152 |

Notes on these totals:

- **O4 under V0** is the mounts.
  - 959 bonds; the top pairs are:
    - `FixedTransform3DNeutral.a -> Revolute3D.parent` 196
    - `-> ContactPoint.p` 179
    - `-> SuctionCup.a` and `.b` 146 each
    - `-> Prismatic3DLimit.parent` 90
    - `GroundSpatial.p -> FixedTransform3DNeutral.b` 40
    - `-> Prismatic3D.parent` 38
    - `-> MovingPlaneContact.p` 15
    - `-> Revolute3DRigid.parent` 14
    - `MTF.p1 -> Revolute2DLimit.drive` 12
    - `-> Rotor3D.p` 8
    - `-> WingJoint.parent` 8
  - A mount's `a` side is bonded to the thing it mounts, which is `in`. So `a in` makes every one of these in-in.
  - Reversing does not help, and flipping a mount around needs the inverted offset (ContactPoint.jl:7-11 already
    says so).
  - The plan as written would fail all those models with no fix. This is the main finding of WP-O0.
- **O4 under V1** is 30 bonds, all `Free3D.drive1..6 -> MR.p`: a passive damper bonded straight onto an `in` joint
  drive.
  - Affected models: lunar-module lm-ascent/lm-descent/lm-hover and rocket rocket-saturn-v/rocket-v2, 6 each.
  - The fix is a 1-junction between the drive and the damper. These are the models whose O12 workaround the plan
    removes anyway.
- **V1 O3 is larger than V0 O3 in some examples** (bicycle 0 -> 6, panda-3d 0 -> 24, pendulum-double-rotary
  0 -> 26). Their V0 violations were in-in O4 bonds on a mount. With A1 the mount takes its orientation from the
  mounted part, and the other side then shows up as an ordinary, fixable O3 bond.
- **Naive classification.** Classifying each V1 bond by the kind of its offending block alone gives review 471,
  source 50, neutral 7, against the real 36 / 31 / 457. So O9 must be junction-aware (section 7).

## 3. What the classes are in V1

**neutral (457)**: reverse the bond, and nothing else changes.
- Most of these are element-to-body bonds where the O7 body rebuild and the reversal cancel.
- The rest are element-to-element bonds and bonds to a 0-junction, which are notation only.

**neutral\* (4)**, industrial-servo: a C and an R on a chain that flips. Negate the C's start value, and the signals
read from both.

**source (31)**: negate a source value.
- `MSe.p` 22 (hybrid-powersplit 9, industrial-servo 5, maglev-train 1, quarter-car 2, wind-turbine 5)
- `Se.p` 6 (maglev-train)
- `MSf.p` 3 (f16)

**review (36)**: in all 9 cars models, `Prismatic3D.drive -> ` the suspension 1-junction that carries the project
block Strut (4 per model).
- Strut documents `j.f = -dx/dt` (bump positive), bonded junction -> strut.
- With the joint drive `in`, the drive bond must reverse. The Strut's own sign then has to follow.
- This needs a decision on the Strut convention, then a regenerated cars example. The other parts are mechanical.

**Silent source (17)**: Sf-type sources whose law changes but whose bond already conforms.
- planar-links 9 (`A*_Speed* -> A*_Torque*.b`)
- industrial-servo 5 (`IqSrc -> GY`)
- van-der-pol 2 (`Belt.p`, `Stribeck/Belt.p`)
- ball-and-plate 1 (`Shaker.p`)

Negate the value or the input. Without this the models would change silently.

**Silent review (3)**:
- flex-rotary-pendulum, 2 models: the chain `PivotMount.b, PivotMount.a, Pivot.parent`.
- flex-torsion: `Weld1.parent`.

Both are a joint parent on a mount on a 0-junction FEM node. The classifier finds an odd chain with no violating
bond, so either their sign is already wrong today (a latent bug), or it becomes wrong with the joint change.
`examples/flex-torsion/design/build.py:165,168` is the place to look. Settle it with a before/after signal compare,
not by analysis.

### Scalar against mechanics (V1)

| | violating bonds | classes | examples |
| --- | ---: | --- | --- |
| scalar (bondgraph / iconic only) | 40 | neutral 5, neutral\* 4, source 31 | f16, hybrid-powersplit, industrial-servo, inverted-pendulum-cart, maglev-train, quarter-car, wind-turbine |
| mechanics (planar / spatial / contact) | 488 | neutral 452, review 36 | 34 examples |

## 4. Per example

The coverage column comes from `expected.json`.
- **numeric**: at least one check besides scene bindings or plots.
- **weak**: scene bindings or plots only.
- **none**: no check.

| example | models | build script | checks (numeric/weak/none) | bonds | V0 O3 | V0 O4 | V1 O3 | V1 O4 | V1 neutral | V1 neutral* | V1 source | V1 review | V1 silent (src/rev) | V2 O3/O4/review |
| --- | ---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| a109 | 2 | yes | 2/0/0 | 171 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| aerial-contact | 1 | yes | 1/0/0 | 27 | 3 | 5 | 2 | 0 | 2 | 0 | 0 | 0 | 0/0 | 2/0/0 |
| ball-and-plate | 5 | yes | 5/0/0 | 143 | 3 | 10 | 3 | 0 | 3 | 0 | 0 | 0 | 1/0 | 3/0/0 |
| beaver | 3 | yes | 3/0/0 | 168 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| bicycle | 4 | yes | 4/0/0 | 34 | 0 | 6 | 6 | 0 | 6 | 0 | 0 | 0 | 0/0 | 6/0/0 |
| bouncing-ball | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| bridge | 9 | yes | 9/0/0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| cantilever-modes | 1 | - | 1/0/0 | 11 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| cantilever-sections | 1 | - | 1/0/0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| cars | 9 | yes | 9/0/0 | 781 | 71 | 54 | 99 | 0 | 63 | 0 | 0 | 36 | 0/0 | 125/0/62 |
| cessna | 2 | yes | 2/0/0 | 117 | 15 | 9 | 6 | 0 | 6 | 0 | 0 | 0 | 0/0 | 6/0/0 |
| cube-3d | 3 | - | 3/0/0 | 36 | 0 | 6 | 6 | 0 | 6 | 0 | 0 | 0 | 0/0 | 6/0/0 |
| cube-pyramid-3d | 3 | - | 3/0/0 | 67 | 8 | 20 | 12 | 0 | 12 | 0 | 0 | 0 | 0/0 | 12/0/0 |
| dc-motor | 3 | - | 3/0/0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| dead-time-noise | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| debug-tour | 1 | - | 1/0/0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| drivetrain | 2 | - | 2/0/0 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| drivetrain-kalman | 2 | - | 2/0/0 | 64 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| drivetrain-position | 3 | yes | 3/0/0 | 63 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| excavator | 4 | yes | 4/0/0 | 111 | 26 | 12 | 10 | 0 | 10 | 0 | 0 | 0 | 0/0 | 38/12/12 |
| f16 | 5 | yes | 5/0/0 | 138 | 6 | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 0/0 | 3/0/0 |
| fanuc-pick | 18 | - | 18/0/0 | 1184 | 268 | 358 | 90 | 0 | 90 | 0 | 0 | 0 | 0/0 | 90/0/0 |
| fem-bracket | 2 | - | 2/0/0 | 13 | 3 | 0 | 3 | 0 | 3 | 0 | 0 | 0 | 0/0 | 3/0/0 |
| fem-gantry | 2 | - | 2/0/0 | 27 | 4 | 4 | 4 | 0 | 4 | 0 | 0 | 0 | 0/0 | 7/0/0 |
| fem-torsion | 1 | - | 1/0/0 | 7 | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0/0 | 2/0/0 |
| flex-rotary-pendulum | 2 | - | 2/0/0 | 15 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0/2 | 0/0/0 |
| flex-torsion | 1 | - | 1/0/0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/1 | 0/0/0 |
| gripper | 2 | yes | 2/0/0 | 30 | 15 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| gyrover | 11 | yes | 11/0/0 | 78 | 0 | 12 | 12 | 0 | 12 | 0 | 0 | 0 | 0/0 | 12/0/0 |
| humanoid-dual-arm | 2 | - | 2/0/0 | 225 | 2 | 18 | 16 | 0 | 16 | 0 | 0 | 0 | 0/0 | 16/0/0 |
| hybrid-powersplit | 4 | yes | 4/0/0 | 203 | 37 | 0 | 9 | 0 | 0 | 0 | 9 | 0 | 0/0 | 21/0/12 |
| hydraulic-circuit | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| hydraulic-servo | 1 | - | 1/0/0 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| industrial-servo | 5 | - | 5/0/0 | 105 | 14 | 0 | 9 | 0 | 0 | 4 | 5 | 0 | 5/0 | 9/0/0 |
| ingenuity | 3 | yes | 3/0/0 | 94 | 8 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| inverted-pendulum-cart | 1 | - | 1/0/0 | 13 | 2 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 0/0 | 1/0/0 |
| lunar-module | 3 | yes | 3/0/0 | 58 | 12 | 26 | 20 | 18 | 20 | 0 | 0 | 0 | 0/0 | 20/18/0 |
| maglev | 3 | yes | 3/0/0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| maglev-train | 3 | yes | 3/0/0 | 107 | 11 | 0 | 11 | 0 | 4 | 0 | 7 | 0 | 0/0 | 14/0/1 |
| motion-servo | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| motor-thermal | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| multibond-pendulum-2d | 1 | - | 1/0/0 | 10 | 5 | 0 | 5 | 0 | 5 | 0 | 0 | 0 | 0/0 | 5/0/0 |
| panda-3d | 4 | - | 4/0/0 | 308 | 0 | 32 | 24 | 0 | 24 | 0 | 0 | 0 | 0/0 | 24/0/0 |
| pendulum-double-cart | 5 | - | 4/0/1 | 70 | 10 | 0 | 10 | 0 | 10 | 0 | 0 | 0 | 0/0 | 10/0/0 |
| pendulum-double-cart-lab | 8 | - | 7/0/1 | 112 | 16 | 0 | 16 | 0 | 16 | 0 | 0 | 0 | 0/0 | 16/0/0 |
| pendulum-double-fixed | 2 | yes | 2/0/0 | 19 | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0/0 | 2/0/0 |
| pendulum-double-rotary | 13 | yes | 13/0/0 | 442 | 0 | 52 | 26 | 0 | 26 | 0 | 0 | 0 | 0/0 | 26/0/0 |
| pendulum-triple-cart | 2 | - | 2/0/0 | 38 | 6 | 0 | 6 | 0 | 6 | 0 | 0 | 0 | 0/0 | 6/0/0 |
| pendulum-triple-fixed | 2 | yes | 2/0/0 | 29 | 4 | 0 | 4 | 0 | 4 | 0 | 0 | 0 | 0/0 | 4/0/0 |
| pendulum-triple-rotary | 5 | yes | 5/0/0 | 104 | 0 | 25 | 15 | 0 | 15 | 0 | 0 | 0 | 0/0 | 15/0/0 |
| planar-links | 3 | - | 3/0/0 | 152 | 8 | 0 | 8 | 0 | 8 | 0 | 0 | 0 | 9/0 | 32/0/9 |
| quad-pendulum | 6 | - | 6/0/0 | 153 | 12 | 18 | 24 | 0 | 24 | 0 | 0 | 0 | 0/0 | 24/0/0 |
| quadcopter | 3 | yes | 3/0/0 | 51 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| quarter-car | 1 | - | 1/0/0 | 14 | 2 | 0 | 2 | 0 | 0 | 0 | 2 | 0 | 0/0 | 2/0/0 |
| reaction-wheel-1d | 1 | - | 1/0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| reaction-wheel-2d | 2 | - | 2/0/0 | 16 | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0/0 | 2/0/0 |
| reaction-wheel-3d | 2 | - | 2/0/0 | 44 | 0 | 8 | 8 | 0 | 8 | 0 | 0 | 0 | 0/0 | 8/0/0 |
| rlc-dual | 1 | - | 1/0/0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| robird | 2 | yes | 2/0/0 | 98 | 0 | 14 | 14 | 0 | 14 | 0 | 0 | 0 | 0/0 | 14/0/0 |
| robot-arm-2d | 2 | - | 2/0/0 | 18 | 2 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 0/0 | 2/0/0 |
| robot-arm-3d | 7 | - | 7/0/0 | 96 | 0 | 19 | 11 | 0 | 11 | 0 | 0 | 0 | 0/0 | 11/0/0 |
| rocket | 2 | yes | 2/0/0 | 28 | 8 | 12 | 8 | 12 | 8 | 0 | 0 | 0 | 0/0 | 8/12/0 |
| segway | 4 | yes | 4/0/0 | 41 | 0 | 8 | 8 | 0 | 8 | 0 | 0 | 0 | 0/0 | 8/0/0 |
| suction-cup | 7 | yes | 7/0/0 | 103 | 48 | 48 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| suction-gripper | 8 | yes | 8/0/0 | 264 | 128 | 128 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 | 0/0/0 |
| tetra-3d | 1 | yes | 1/0/0 | 24 | 4 | 8 | 4 | 0 | 4 | 0 | 0 | 0 | 0/0 | 4/0/0 |
| van-der-pol | 3 | yes | 3/0/0 | 24 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2/0 | 0/0/0 |
| wind-turbine | 5 | yes | 5/0/0 | 85 | 5 | 0 | 5 | 0 | 0 | 0 | 5 | 0 | 0/0 | 5/0/0 |
| **total** | 234 | | | 6510 | 793 | 959 | 528 | 30 | 457 | 4 | 31 | 36 | 17/3 | 624/42/96 |

The V1 class columns split the V1 O3 bonds: neutral + neutral\* + source + review = O3 in every row. The silent
column counts chains, not bonds.

### The models hit hardest

| model | bonds | V0 O3 + O4 | V1 O3 + O4 | V1 review | checks |
| --- | ---: | ---: | ---: | ---: | --- |
| `fanuc-pick/loose-cylinder` (and -best, -opt, -tilt-best) | 68 | 16 + 21 | 5 + 0 | 0 | numeric |
| `fanuc-pick/loose-sphere` (and -best, -opt, -tilt-best) | 68 | 16 + 21 | 5 + 0 | 0 | numeric |
| `fanuc-pick/offset-com-best`, `-opt` | 64 | 14 + 19 | 5 + 0 | 0 | numeric |

| model (V1, by review + O4 + silent review) | V1 O3 | V1 O4 | review | source | checks |
| --- | ---: | ---: | ---: | ---: | --- |
| `lunar-module/lm-ascent` | 4 | 6 | 0 | 0 | numeric |
| `lunar-module/lm-descent`, `lm-hover` | 8 | 6 | 0 | 0 | numeric |
| `rocket/rocket-saturn-v`, `rocket-v2` | 4 | 6 | 0 | 0 | numeric |
| `cars/buggy-*`, `cars/racecar-*` (9 models) | 11 | 0 | 4 | 0 | numeric |
| `flex-rotary-pendulum/*` (2), `flex-torsion` | 0 | 0 | 0 (silent review 1 each) | 0 | numeric |

## 5. Fixtures (measured)

| file | bonds | V0 O3 | V0 O4 | V1 O3 | V1 O4 | V1 classes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `julia/BGSim/test/fixtures/causality/r_r_loop.json` | 1 | 0 | 1 | 0 | 1 | R -> R, in-in: a deliberately odd causality fixture; give it a junction or let one end be `any` |
| `julia/BGSim/test/fixtures/causality/two_c_series.json` | 2 | 2 | 0 | 2 | 0 | neutral 2 |
| `julia/BGSim/test/fixtures/multibond/pendulum.json` | 7 | 2 | 0 | 2 | 0 | neutral 2 |
| 16 other fixture files with bonds (contracts valid/invalid/semantic, causality, negative, planar) | 47 | 0 | 0 | 0 | 0 | - |

- The **contract fixtures** have no violations. Their inline blocks (GroundPlanar, FixedTransform2D, BodyPlanar
  without a stdlib ref) have no orientation, so they default to `any`. Declared, they would conform.
- `negative/e102_bond_cross_domain.json` is a negative fixture. The table gives it no O-error. Its expected
  diagnostic stays E102, as long as O3/O4 run after the domain check (WP-O1 should pin that order).
- The 6 composite-internal violations in fixtures go with WP-O5.

## 6. Julia tests (estimated)

The test files build models in code, so there is no JSON to flatten. `tests_static.py` (scratch) parses them.

**Method**:
- A node constructor that names a `stdlib:` ref binds an id, and a later bond literal
  `("id", "bond", from, fport, to, tport)` is checked against the V0 table.
- Interpolated ids, loops and helper rigs are not resolved, so the result is a **lower bound** for files that build
  models in loops.

**Result**: 39 files have 355 bond literals. 250 of them resolve, and of those, 22 are O3 and 26 are O4 under V0.

| file | literal bonds | resolved | O3 | O4 |
| --- | ---: | ---: | ---: | ---: |
| test_spatial_slice.jl | 36 | 32 | 12 | 3 |
| test_planar_primitives.jl | 28 | 23 | 4 | 3 |
| test_export_suction.jl | 4 | 4 | 1 | 3 |
| test_frames.jl | 43 | 12 | 0 | 4 |
| test_mech_planar.jl | 40 | 31 | 2 | 1 |
| test_multibond_slice.jl | 8 | 8 | 0 | 3 |
| fem_body_rigs.jl | 6 | 3 | 0 | 2 |
| test_flex_beam.jl | 18 | 13 | 0 | 2 |
| test_mech_spatial.jl | 29 | 13 | 0 | 2 |
| golden/contact/test_SuctionCup.jl | 4 | 2 | 1 | 1 |
| golden/contact/test_RollingSphere.jl | 10 | 10 | 1 | 0 |
| golden/spatial/test_floating_base.jl | 9 | 9 | 0 | 1 |

The O4 bonds are mostly mounts, and they are gone under V1. The ones that stay are `GroundPlanar -> GroundPlanar` (3),
`MTFPlanar.b -> SfPlanar` (2) and `SfPlanar -> Prismatic2D.child` (1). These are rigs that need a junction or a
reversed source.

More test files will change than these counts show. **53 test files** name a block whose law changes (Sf, MSf, the
gravity and wrench sources, the contacts, the joints, the bodies). Their numbers will move even where every bond
conforms:
- `test_library.jl` alone has 47 references, and `test_mech_spatial.jl` 20;
- the golden tests for the contacts and for MSf pin today's signs. The MSf golden test uses `gain = -1` to undo the
  `p.f ~ f` convention.

Treat the golden tests as the first thing to update with each block change in WP-O3, not as a regression guard.

## 7. Coverage and how each example is produced

- **Checks**: all 68 examples have `expected.json`.
  - Two models have no numeric check: `pendulum-double-cart/pendulum-double-cart-plant` and
    `pendulum-double-cart-lab/pendulum-double-cart-lab-plant`.
  - Both have 10 or 16 neutral violations in their example. Compare them before and after the migration, signal by
    signal, rather than relying on the checks.
- **`design/build_model.py` (31 examples).** Migrate these by fixing the build script and regenerating: a109,
  aerial-contact, ball-and-plate, beaver, bicycle, bridge, cars, cessna, drivetrain-position, excavator, f16,
  gripper, gyrover, hybrid-powersplit, ingenuity, lunar-module, maglev, maglev-train, pendulum-double-fixed,
  pendulum-double-rotary, pendulum-triple-fixed, pendulum-triple-rotary, quadcopter, robird, rocket, segway,
  suction-cup, suction-gripper, tetra-3d (it uses the cube-pyramid-3d JSON as a template), van-der-pol, wind-turbine.
- **Other generators.**
  - `build_models.py`: fanuc-pick, humanoid-dual-arm, panda-3d, quad-pendulum, robot-arm-3d. The fanuc library comes
    from `build_library.py`.
  - `design/build.py`: fem-*, cantilever-*, flex-*.
  - `design.py`: cube-3d, drivetrain-kalman, industrial-servo, inverted-pendulum-cart, reaction-wheel-1d,
    pendulum-double-cart-lab.
  - `cartpend.py`: pendulum-double-cart.
- **Hand-written JSON, no generator.** O9's JSON rewrite is the only path for these: bouncing-ball, cube-pyramid-3d,
  dc-motor, dead-time-noise, debug-tour, drivetrain, hydraulic-circuit, hydraulic-servo, motion-servo, motor-thermal,
  multibond-pendulum-2d, pendulum-triple-cart, planar-links, quarter-car, reaction-wheel-2d, reaction-wheel-3d,
  rlc-dual, robot-arm-2d.
  - Of these, only cube-pyramid-3d (12), planar-links (8 + 9 silent), quarter-car (2 source),
    multibond-pendulum-2d (5), pendulum-triple-cart (6), robot-arm-2d (2), reaction-wheel-2d (2) and
    reaction-wheel-3d (8) have V1 violations.

## 8. What the migration (O9) must do

The counts above give these requirements for the migration tool:

1. **Be junction-aware.** Decide per 1-junction cluster which side to reverse. Reversing a bond on a 0-junction or
   between two elements is notation only, and it must not be paired with a sign change.
2. **Follow chains.** Change the law of a block and also touch its non-violating neighbours (the 17 + 3 silent
   chains). Negate the start values, and the signals read from them, of odd elements on a flipped chain (neutral\*).
3. **Negate the source values** on source chains: an `Se`/`MSe` value or input, an `Sf`/`MSf` value.
4. **Insert a 1-junction** for the 30 drive -> damper O4 bonds (lunar-module, rocket).
5. **Refuse and report** review chains (36, cars) and every 0-1 junction-to-junction bond whose cluster it flips.
   Never guess.
6. **Check every rewritten model against its `expected.json` and against its own pre-migration signals**
   (`compare_signals`). The two models without numeric checks need the signal compare.

## 9. Split recommendation

**WP-O2 (scalar) can stay one package.**
- 40 violating bonds in 7 examples: neutral 5, neutral\* 4, source 31.
- Block changes: Sf, MSf and the MSf golden test.
- The work in the examples is source negations (MSe, Se, MSf) in hybrid-powersplit, industrial-servo, maglev-train,
  quarter-car, wind-turbine and f16. 6 of these 7 examples have build scripts or `design.py`.

**WP-O3 (mechanics) is too large for one package. Split it.**

- **O3a, stdlib and compiler.** No example edits beyond what the tests need.
  - The A1 relation for pass-through two-ports in the compiler.
  - The RigidBody2D/3D, ImpactBody3D, PinNode2D, Bar2D, FlexibleBeam2D/3D, ModalBody3D and Revolute2DRigid
    rebuilds (= WP-O5).
  - Sf/MSf for planar and spatial; Gravity and ExternalWrench.
  - The contacts and the joints' child side.
  - The Julia tests and goldens.
- **O3b, the examples with build scripts.** Fix the generator and regenerate. 2D first (pendulum-*-fixed, excavator,
  bridge), then 3D.
- **O3c, the rest.** fanuc-pick, humanoid-dual-arm and panda-3d through their `build_models.py`; then the hand-written
  JSON through the O9 tool.

**Order inside O3b/O3c, from the least to the most risk:**
1. Examples whose violations are all neutral and that have strong checks (suction-gripper, suction-cup, gripper,
   quadcopter and ingenuity have 0 under V1; then fanuc-pick and the pendulums).
2. Examples with source chains: industrial-servo, maglev-train, hybrid-powersplit, quarter-car, wind-turbine, f16
   (if WP-O2 has not already done them).
3. The O4 junction insertions: lunar-module and rocket, together with removing the O12 workaround.
4. Last, the review cases:
   - cars, which needs the Strut convention decided first;
   - flex-torsion and flex-rotary-pendulum, with a `compare_signals` before and after;
   - the two models without numeric checks.
