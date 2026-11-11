# Sign changes of WP-O3b2 (O18)

Package O3b2 migrated lunar-module, rocket, ingenuity, cars, and checked suction-cup, suction-gripper, gripper,
quadcopter, a109, f16, beaver, cessna, wind-turbine, flex-rotary-pendulum and flex-torsion. The rules and the meaning
of the columns are those of `sign-changes.md`. A bond of a stdlib block whose law changed in WP-O3a and that kept its
direction changes sign as that file's WP-O3a block table says (for example `<Wrench>/p.e` of every
`ExternalWrenchSpatial` that already pointed at its body); those rows are not repeated here.

No `expected.json` entry, golden file, plot, binding or dashboard card of these examples names a signal on this
list, so none was edited and nothing was negated.

## Project library blocks

| block | change | what changes sign in a model |
| --- | --- | --- |
| `cars/library/Strut` | O17: the port flow is the true travel rate, `v ~ j.f`, `j.e ~ F` (was `v ~ -j.f`, `j.e ~ -F`); `j => :in` | `<Corner>/Strut/j.e`, `<Corner>/Strut/j.f`. `x`, `v`, `travel`, `F`, `E`, `Pd` keep their sign. |
| `cars/library/AntiRollBar` | O17, as `Strut`: `ddt(d) ~ jl.f - jr.f`, `jl.e ~ F`, `jr.e ~ -F` (was the negatives); `jl`, `jr` `in` | `ArbF/jl.*`, `ArbF/jr.*`, `ArbR/jl.*`, `ArbR/jr.*`. `d`, `F`, `E` keep their sign. |
| `cars/library/TractionMachine` | declared `(dc, shaft) => :through`, law unchanged | nothing (every bond already conformed) |
| `cars/library/TractionBattery` | declared `p => :in`, law unchanged | nothing |
| `cessna/library/GearContact` (copied to `f16/library` by f16's build) | O7: the port flow is the point twist and the port effort minus the wrench on the body: `v = R p.f[4:6]`, `p.e = -[0; R^T F]` (was `v = -R p.f[4:6]`, `p.e = +[0; R^T F]`, written for the old `RigidBody3D` junction); `p`, `n`, `x`, `y` `in` | `Contact_<leg>/p.e`, `Contact_<leg>/p.f`, and the mount between it and the body, `Mount_<leg>/a.*`, `Mount_<leg>/b.*` (the body face flow changed sign in WP-O3a). `n.*`, `x.*`, `y.*`, `fn`, `vx`, `vy`, `delta` keep their sign. |
| `cessna/library/StrutSpring`, `StrutDamper`, `WheelFriction`, `WheelSide` (and their f16 copies), `Propeller`, `PistonEngine` | declared `in`, law unchanged | nothing |
| `a109/library/ShaftAxis` | declared `p => :in`, `s => :out`, law unchanged; bonded like a contact now (body -> mount.b, mount.a -> `p`) | nothing: the reversed chain on the rebuilt body gives `p` the same twist and effort as before WP-O3a, and `s` sits on a 0-junction. |
| `lunar-module/library/VariableInertia3D`, `rocket/library/VariableInertia3D` | declared `p => :in`, law unchanged | nothing (their bonds kept their direction on a junction that kept its sign) |
| `ingenuity/library/RotorBEMT` | declared `shaft => :in`, law unchanged | nothing |
| `gripper/library/JawGuides`, `LeadScrew`, `WedgeHook`, `suction-gripper/library/CupValve`, `quadcopter/library/Propeller` | iconic (wired only): every power port declared `in` (O20), law unchanged | nothing (no bond reaches them) |

## Models

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `lunar-module` (3 models), `rocket` (2 models) | build script: `Free.child -> Body`; the wrench sources `ThrustW`, `RcsW`/`DragW`, `GravityW` now point at `Body` (values kept: the ExternalWrenchSpatial law change of WP-O3a cancels the reversal); a 1-junction `Axis1..6` between each `Free.drive_k` and its `MR` `Out_k` (O16); lunar-module descent and hover: `Body -> Pad<k>Mount.b` (was `Pad<k>Mount.b -> Body`) | `Free/child.e`, `Free/child.f`; `ThrustW/p.e`, `ThrustW/p.f`, `RcsW/p.*`, `GravityW/p.*` (rocket: `DragW/p.*`); `Out1..6/p.e`, `Out1..6/p.f` (an element-to-element bond became a junction with a bond into each port); lunar-module: `Pad1..4/p.*`, `Pad1..4Mount/a.*`, `Pad1..4Mount/b.*`. `Inertia/*`, `Coriolis/*`, `Twist/*`, `Free/drive_k.*`, `Free/parent.*` and every joint and body variable keep their sign. |
| `ingenuity` (3 models) | nothing changed in the model (declaration only) | none beyond WP-O3a's block table |
| `cars` (9 models) | build script: chassis -> corner `mount` (was `mount -> Chassis`); `Upright.p -> KingFT.b` (was `KingFT.b -> Upright.p`); `Travel -> Susp.drive` (was `Susp.drive -> Travel`); `Spin -> LsdTF.p2` and corner `spin2` (= `LsdTF.p1`) -> `Lsd<A>.a`/`.b` (both were the other way) | `<Corner>/Strut/j.*`, `<Corner>/TravelTF/p1.*`, `p2.*` (where the corner has an anti-roll bar), `ArbF/*`, `ArbR/*` port variables (above); `<Corner>/LsdTF/p1.*`, `p2.*`, `LsdF/a.*`, `b.*`, `LsdR/a.*`, `b.*` (driven axles). Unchanged: `<Corner>/Susp/drive.*`, `<Corner>/Mount/*`, `<Corner>/KingFT/*` (the reversed bond meets a body junction whose flow changed sign in WP-O3a, so the two cancel). |
| `a109` (2 models) | build script: `Body -> MShaft.b`, `MShaft.a -> Shaft.p`, `Shaft.s -> Mast` (all three were the other way) | none |
| `f16` (5 models), `cessna` (2 models) | `GearContact` law (above); the models are unchanged (regenerated, identical) | as the `GearContact` row |
| `suction-cup`, `suction-gripper`, `gripper`, `quadcopter`, `beaver`, `wind-turbine`, `flex-torsion`, `flex-rotary-pendulum` | nothing changed in the models | none beyond WP-O3a's block table |
