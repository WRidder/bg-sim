# Deferred: instance-scoped frame identity (FIX-MB-6)

Status: planned, deferred past M3 Gate B. Owner: the first spatial work package that needs it
(J-MB9, the 6-axis arm), or a dedicated FIX-MB-6 if the planar arm is extended to a direct
body-to-body chain. Raised by the Claude review of `stdlib/multibond/` + `stdlib/planar/`
(item 1), 2026-10-28.

## Problem

v1 frames are metadata-only and identified by their **unqualified name** (DEC-MB-1): two ports
are in the same frame when `a.frame == b.frame`. Every `RigidBody2D` port and every
`FixedJoint2D.child` is literally `"body"`, so in a 2-link chain body 1 and body 2 share the
name and a **direct bond between them passes E007**. The false negative is real; the current
target models do not exercise it because every body-to-body connection goes through a joint or
transform, which is frame-neutral and is the only legal bridge anyway.

## Why it is not a five-line change

- The primitives **inside** a composite (`IPlanar`, `CoriolisPlanar`, `GravityPlanar`) all
  declare `frame = "body"` and are wired to the composite's own face. Scoping every port by
  `(instance path, name)` makes the body's own interior conflict (`Body1/inertia/body` vs
  `Body1/coriolis/body`), unless a frame object/owner is introduced.
- The legal chains rely on a shared name across instances: `Ground(world)` →
  `FixedTransform2D(world→body)` → `Body(body)`. With instance scoping, the transform's `body`
  side must be neutral (adopt the adjacent body frame) or use an absolute name, or every legal
  bond becomes E007.
- The change touches: `src/compile/domains.jl` (the union-find/claim), the C-MB1 contract
  fixtures (frame strings), J-MB1's tests, the X-MB2 arm models, the editor's frame badge text
  (`{path}/{frame}` already), the ADR/DEC-MB-1 and the catalog descriptions.
- A full solution is a contract/language change (frame objects with explicit sharing), not a
  metadata tweak; D-MB5 deliberately deferred dependent frame typing.

## Options, in increasing cost

1. **Face-scoped frames (recommended next).** Subsystem/composite **faces** are
   instance-qualified (`Body1/body`, `Body2/body`); primitive ports keep their declared names;
   `world` is global; joints/transforms are frame-neutral on their non-world sides. A direct
   body-body bond then gives E007, while every legal body↔transform↔ground chain still works.
   Cost: `_FrameClaim` gains an `is_face` flag; `_unify_frames!` compares `(path, name)` only
   when both claims are faces, else compares names. Tests: direct `Body1/body↔Body2/body` →
   **E007**; the transform bridge and `world` sharing stay legal; the arm still runs. Residual
   limitation: a direct bond between two primitive (non-face) ports with the same name is still
   accepted; document it.
2. **Absolute frame references.** A frame name starting with `/` is global (`/arm1`); a bare
   name is instance-local by default. Library transforms/joints declare neutral or `/world`/
   `/arm1` frames. Exact and explicit, but every fixture/model/library block must be rewritten,
   and users must learn the syntax. No contract change, but a language convention change.
3. **Frame declarations in the model document** (`frames: [{id, parent}]`, ports reference
   ids). The full solution; a C-lane contract change (model.schema, catalog portDecl, generated
   bindings, fixtures, editor), then J-MB1's union-find and every frame string. This is the
   right long-term model but is out of M3 scope.

## Decision

Defer. Record the false negative in DEC-MB-1 and the Gate B summary. Do not start option 1 until
the 6-axis arm (J-MB9) or a planar model with a direct body-body bond actually needs it; at that
point implement option 1 with the face-scoped comparison and the tests above, and only then
decide whether option 2/3 is justified by the spatial library.

## Acceptance for the eventual fix (option 1)

- A direct bond between `Body1/p` (`Body1/body`) and `Body2/p` (`Body2/body`) gives one **E007**
  naming both instance paths; the same bond through a frame-neutral `FixedJoint2D`/`TFAd` is
  accepted.
- `Ground(world)` shares the global `world` frame across instances; a transform's non-world
  side is neutral and adopts the adjacent body frame.
- The composite interiors (`RigidBody2D`'s I/Coriolis/Gravity, the joint's 0-junction) are
  unchanged and check clean.
- The X-MB2 arm and X-MB1 pendulum keep their numbers; the editor frame badge still shows
  `{path}/{frame}`.
- `model.check.frames` remains display-qualified; the comparison rule is documented in the ADR.
