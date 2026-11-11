# Example migration brief (WP-O3b and WP-O3c)

Common instructions for the agents that migrate the examples to the port-orientation rules. Read
`CLAUDE.md`, then `plan/PORT_ORIENTATION_PLAN.md` in full (decisions O1 to O21 and every "Choices WP-O… made"
list), then `sign-changes.md` in this folder.

## State of the branch `port-orientation`

The language, compiler, editor and the whole stdlib are done and committed (last commit `ee4708d`). A bond
drawn against a declared orientation is error E114. 134 of the 234 example models raise E114 and wait for
this migration; the scan with every diagnostic is
`C:\Users\WVDR\AppData\Local\Temp\claude\200ca067a23040a0\f799f0c5-827e-478b-a017-89dec347bf5a\scratchpad\o21\scan_after.txt`
(the scripts that made it are in `scratchpad\o21\`, `scratchpad\o3a\` and `scratchpad\wp-o0\`).

## The rules a model must follow now

A body is a 1-junction whose flow is the true twist `+V` (the library `RigidBody2D/3D` port is that
junction). Bonds between two junctions may run either way (a 0-1 bond sets a reference direction, O14).
In a `through` pair (mount, transform, `TF`, `GY`) one bond arrives and the other leaves.

- **Storage, dissipation, detectors on a junction** (`I`, `C`, `R`, `De`, `Df`, Coriolis, planar and spatial
  forms): `Junction -> element`.
- **Sources** (`Se`, `Sf`, `MSe`, `MSf`, gravity, external wrench, planar and spatial forms):
  `Source -> Junction`, or `Source.p -> Mount.a` then `Mount.b -> Body`. `Sf`/`MSf` now impose `+f` on the
  junction they point at (O15); gravity and external wrench give `p.e = +wrench`.
- **Contacts** (`ContactPoint`, `MovingPlaneContact.p`, `RollingDisk`, `RollingSphere` a/b, `SuctionCup` a/b,
  `Tyre.p`, `DeckContact2D`, `ImpactInertia3D`): `Body -> Contact.p`, or `Body -> Mount.b` then
  `Mount.a -> Contact.p`. The contact sees the true twist; its port effort is minus the wrench on the body.
- **Joints and `Free3D`**: `ParentBody -> Joint.parent`, `Joint.child -> ChildBody`. Mounted parent:
  `ParentBody -> Mount.b`, `Mount.a -> Joint.parent`. Mounted child: `Joint.child -> Mount.a`,
  `Mount.b -> ChildBody`. Drives are `in`: `SourceOrJunction -> Joint.drive`; a sensor or a dissipator on a
  drive goes through a junction (O16).
- **Mounts** (`FixedTransform*`, `JointTransform*`, `FixedJoint2D`): keep `b` on the body side. Do not turn a
  mount round (`a` toward the body): that is a different, badly conditioned causality.
- **Iconic components** (electrical, rotation, translation, hydraulic, thermal, drives, motion, converters):
  a bond to an iconic port always ends at the port (`Junction -> port`); the port then behaves exactly as if
  wired. Two iconic ports are joined by a wire, or by a junction with a bond into each (O20). A composite face
  that fans out to several leaf ports (`DCMotor` shaft, `Gearbox` a/b) must be wired, not bonded.
- **Project library blocks** (`examples/<name>/library/*.jl`) follow the same rules: declare `@orientation` on
  their power ports, fix their laws so they see the true twist or rate, and fix the internal `connect`
  directions of project composites (O17).
- `multibond/FixedTransform2D` is now an explicit law; a 2D model that ran with `solver: "auto"` may need
  `Rodas5P` (the stiff joint otherwise stops at MaxIters).

## How to migrate one example

1. Record the baseline first: on a scratch copy of the repository state before the stdlib change you cannot
   run, so use the example's own evidence instead: its `expected.json` checks are the acceptance, and they
   compare against independent references.
2. If the example has a generator (`design/build_model.py` or another script in `design/` that writes the
   model JSON): fix the generator and regenerate. Do not hand-edit generated JSON. If the generator is stale
   (it no longer reproduces the committed model apart from bond directions), say so and migrate the JSON
   with the tool instead, as WP-O2 did for industrial-servo.
3. If it has no generator: `uv run tools/migrate_bond_orientation.py` (`--check` first). It reverses bonds per
   1-junction cluster, negates source values, start values and listed signal references, and leaves `review`
   cases to you: decide each one from the physics and record the decision.
4. Run `uv run examples/run_checks.py --only <name>`. It must pass with **no tolerance widened and no
   expected value changed**, except the sign of a signal that is on the sign-change list (O18): a port
   variable (`p.e`, `p.f`, or a signal defined as one) of a block whose convention changed. Add each such
   signal to your sign-change file before you negate anything. If a position, a twist, a state or any other
   physical output differs, the migration is wrong: find the bond or the value, do not adjust the check.
5. A model that compiles clean is not proof: an old hand-built body or a formerly unchecked attachment can
   have changed meaning. Run the checks of every example in your list, including its models that had no
   E114.
6. Remove workarounds and README or docs-source notes that exist only because of the old inconsistency (O12).
   Do not rebuild the example docs (`tools/example_docs`) or thumbnails: a later package does that.

## Shared-tree rules (several agents work at the same time)

- Edit only the examples in your own list, plus the files your brief names. Do not edit `julia/BGSim/stdlib/`,
  `julia/BGSim/src/`, `contracts/`, `web/` or another agent's examples. If you believe a stdlib block or the
  compiler is wrong, write the evidence in your report and work on the next example; do not patch it.
- Only the agent whose brief says so may edit `tools/migrate_bond_orientation.py`. Everyone else reports a tool
  problem and handles the case by hand.
- Write sign changes to your own file `plan/wps/port-orientation/sign-changes-<package>.md` (not to
  `sign-changes.md`), and choices to `plan/wps/port-orientation/choices-<package>.md` (not to the plan file).
- Do not commit. No git checkout/stash/restore/reset. Python only through `uv run`; Julia with
  `julia --project=julia/BGSim`; never install global Julia packages; LF line endings; never use port 8765;
  do not run `npm run build`; do not leave background processes running when you finish.
- Several agents run Julia at once, so runs are slower than usual. Be patient rather than killing them.

## Report back (concise)

Per example: generator fixed or tool used; the number of bonds reversed, values negated and review cases, with
the decision for each review case; the final summary line of its check run (paste it); anything left failing
with the numbers. Then: the signals in your sign-change file; workarounds removed; every stdlib or tool
problem you found with the evidence; anything deviating from the plan.
