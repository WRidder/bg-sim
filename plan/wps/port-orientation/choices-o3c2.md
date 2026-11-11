# Choices WP-O3c2 made

Examples: cube-pyramid-3d, multibond-pendulum-2d, planar-links, reaction-wheel-2d, reaction-wheel-3d, robot-arm-2d,
all migrated with `tools/migrate_bond_orientation.py`. Every check passes with no tolerance or expected value changed
(312 checks).

## Review cases and their decisions

- **planar-links (inverse and payload): the series `TorqueSensor`.** The arm's speed source drives the joint-side
  1-junction through a torque sensor: `Speed.p -> Torque.b`, `Torque.a -> Drive`. Both sensor terminals are `in`
  (O20), so `Torque.a -> Drive` must be reversed, which flips that terminal. The other terminal sits on an
  element-to-element chain with the `MSf`; flipping it too (gain negated) makes the reversal consistent, but flipping
  both terminals negates the sensed torque `y` (`a.e = y`, `b.e = -y`), and `y` feeds `TauErr` (`tau - ref`), whose
  `max_abs_le` checks would then fail. Renaming `Drive` instead flips the joint's drive port (not odd). Decision from
  the law: the sensor is antisymmetric in its terminals (exchanging `a` and `b` negates `y`), so flipping both
  terminals **and exchanging them** keeps `y`: `Speed.p -> Torque.a`, `Drive -> Torque.b`, `MSf` gain `-1.0 -> 1.0`.
  Derivation: the source imposes `Speed.p.f = -u`, so `Torque.a.f = u = Torque.b.f = f_Drive` (the CSV speed, as
  before), and with all three bonds leaving `Drive`, `Torque.b.e = -(drive.e + gear.b.e)`, so `y = -b.e` is the
  torque delivered into the drive, as before. The tool now does this itself (below), so the model needed no hand
  edit. The joint review cases of the first `--check` were the same sign group (the tool had no review-free choice
  before), not a separate decision.
- **planar-links: the `IdealGear` on the motor junction.** `Gear.a -> Motor` violates `a in`. Reversing it alone
  flips one gear terminal (review); the tool renames the motor junction instead, so `Jm` and `Bm` (linear `I` and `R`)
  flip with their bonds kept. The motor junction flow is now `+n qdot` (it was `-n qdot`): the motor speed in the
  joint's sense. Accepted: `Jm/p.*`, `Jm/P`, `Bm/p.*` are port variables and the integral of one (O18).

## Model edits beyond the tool

- **multibond-pendulum-2d:** `settings.solver` `auto -> Rodas5P` (O21 made `FixedTransform2D` explicit; the pure ODE
  made `auto` pick a non-stiff method). The README and the docs source (`tools/example_docs/src/multibond-pendulum-2d.md`)
  said `GravityPlanar` applies "the negative of the physical wrench, because a 1-junction sums efforts": now it is the
  physical wrench, bonded into the body junction like every source (O12). The README's measured step counts
  (`4 072` / `10 072` adaptive steps) were measured with the old solver choice; the docs rebuild (WP-O5) refreshes the
  generated pages.
- **planar-links: the generator.** `reference/build_model.py` writes the three models and was not stale: apart from the
  WP-O2 `MSf` gain and its marker it reproduced the committed JSON exactly. Following the orchestrator, the JSON was
  migrated with the tool (as WP-O2 did for this example), and then the generator was brought in line: the elbow bond
  `body junction -> Joint.parent`, `Motor -> Gear.a`, `Speed.p -> Torque.a`, `Drive -> Torque.b`, and the tool's
  markers (`MARKERS`: O7 on the joints and bodies, O15 on the `MSf`), so `uv run reference/build_model.py` now writes
  the committed models byte for byte and a later tool run on them reports nothing to do.

## Tool changes (`tools/migrate_bond_orientation.py`, tests in `backend/tests/test_migrate_bond_orientation.py`)

- **Series sensors whose output is used (`SWAP_SENSORS`).** `TorqueSensor`, `ForceSensor` (`a`, `b`; flows change
  sign), `CurrentSensor` (`p`, `n`), `FlowSensor`, `HeatFlowSensor` (`a`, `b`; efforts change sign). When both
  terminals flip and `y` drives a block (formerly review), the tool exchanges the two port names at the bond ends
  (reversal and rename in one format-preserving edit). Only when each terminal has exactly one bond that names the
  sensor's port directly (same diagram, no subsystem port); otherwise it stays review. `VoltageSensor` is not in the
  table: exchanging its terminals is not a pure sign change of its port variables. Cost `COST_SWAP = 2` (as a
  `through` flip). Tests: `test_series_sensor_terminals_swapped`, `test_series_sensor_bonded_twice_is_review`.
- **Route reversal keeps the layout.** A reversed bond's `route` was rewritten as one-line `json.dumps`; it is now
  reversed by moving the items' source text (`JsonDoc.reverse_array`). Test: `test_route_reversed_in_place`.
- **`--skip-law-change DECISION` (`skip=` in `run`/`analyse`).** `--no-law-changes` is all or nothing, but a model a
  build script regenerated in WP-O2 (after O15, no marker) and not yet migrated for O7 needs only the O7 step. Test:
  `test_skip_one_law_change`.
- The tool stays idempotent on all six examples (second run: nothing to do) and never edits a review group.

## The `--check` scan over every model (step 2)

`tools/migrate_bond_orientation.py` cannot see whether a model without a marker was written before or after a law
change. The scan (a throwaway script in the session's scratch folder, `o3c2/scan.py`) therefore picks the mode per model: a model with a marker, or unchanged
since `master`, runs with every law change; a model a build script rewrote in WP-O2 (committed on the branch, no
marker) with `--skip-law-change O15`; a model rewritten in the working tree by another package and without a marker
with both skipped. A generator-built model that conforms reports law-change "edits" otherwise (vdp-belt: `Belt.f`
negated, a false positive that `--skip-law-change O15` removes).
