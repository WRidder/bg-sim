# Choices WP-O3b1 made

- **Generators, not the tool.** Every example of this package has a generator; each was run unchanged first and
  reproduced the committed models byte for byte (none is stale), then fixed and rerun. `tools/migrate_bond_orientation.py`
  was not used.
- **Tool cross-check.** Every model of the 15 examples (70 models, all generator output, so written after the law
  changes) gives `uv run tools/migrate_bond_orientation.py --check --skip-law-change O7 --skip-law-change O15`:
  "nothing to do". Without the skips the tool reports "neutral" law-change cancellations for models whose diagram did
  not change (for example ball-and-plate-lqr/pid/track, bridge/strut-buckling): those are the WP-O3a laws cancelling
  each other on a conforming cluster, no bond to reverse. The bridge generators were rerun and reproduce their models.
- **Mounts.** Every mount keeps `b` on the body side; only the body-side bond turned (`Body.p -> Mount.b`). No mount
  was turned round.
- **Hand-built body junctions** (pendulum-double/triple-fixed `BodyJk`, excavator `BodyJk`, rotary `BJk`): the joint
  parent bond now starts at the junction. Since the face of the rebuilt `RigidBody2D/3D` gives the junction the true
  twist, the reversal is neutral; no value changed.
- **`any` ports on a body (WP-O3a's hazard).** Two project blocks read the body junction through an undeclared port
  and compiled silently: `excavator`'s `SoilCutting2D` (bond reversed, `@orientation p => :in`, law kept: it already
  expected the true twist) and `aerial-contact`'s `OmniContact` (bond kept, law changed like the stdlib `ContactPoint`,
  `@orientation p => :in`). Without these two changes both blocks would read minus the twist (the soil force and the
  wall reaction acting with the wrong sign) and no E114 would say so.
- **Project copy of a stdlib joint** (`robird`'s `WingJoint`): given the WP-O3a child-side law and the joint
  orientations, exactly as `Revolute3DCompliant`.
- **Wire-only project blocks** (`Propeller`, `Crank`) and the actilink one-ports (`ALClamp`, `ALFriction`,
  `ALGearSpring`) declare their power ports `in` (O20, O6). No bond or law changed.
- **tetra-3d's template.** Its generator copies `cube-pyramid-3d/models/sequence-contact` (O3c's). The generator now
  reverses a wheel-mount bond that still leaves `WMountk.b` (route reversed too), so it gives the same diagram before
  and after the cube's migration. After O3c migrated the cube the regenerated model also inherits the tool's
  `"$comment": "migrate_bond_orientation: O7"` markers from the template; the diagram is otherwise identical.
- **Review: ball-and-plate gimbal locks.** The drive is `in`, so `Gimbal.drive -> Lock` became `Lock -> Gimbal.drive`;
  the C and R on the lock junction cannot turn with it (`in`), so the junction now carries `+qdot` and the lock spring is
  an odd element on a flipped chain: its start value is negated (`lock_preload` returns `+tau/k`) and the energy book's
  `dq1` (the angle at which the spring is relaxed) is written as `-lock_preload`, the same number as before.
- **Review: excavator rack-and-pinion.** Both `RackAndPinion` terminals are `in`. The rod junction bonds into `b`
  (the rack now reads the rod speed itself, before it read `-v`). `a` and the lever's `MTF.p2` were one bond; two `in`
  ends need a junction (O4, O20), and the physical object between them is the pinion shaft, a common-speed node, so a
  1-junction `<Cyl>Pinion` with a bond into each. Its two out-bonds give `a.f = p2.f` where the direct bond gave
  `a.f = -p2.f`; together with the rack's turn this keeps the lever, the joint and every physical signal unchanged.
  (A 0-junction there would reproduce the direct bond and leave the rack's sign flip uncompensated.)
- **Review: hybrid-powersplit machines.** `EMConverter.shaft` is `in`; the old model reached the shaft from the
  tail, so with its own law (`shaft.e = +k p.f`) a positive stator current drove the shaft forward. Kept by wiring the
  stator into `n` and grounding `p` (as the stdlib `DCMotor` wires the same gyrator), not by negating `k`: the torque
  constant stays the datasheet value and the inverter, its modulus and the HCU are untouched.
- **Review: hybrid-powersplit battery.** `Battery.p` is `in`; the battery and the current detector `BatCurrent` sit on
  the same 1-junction and are both `in` now, so the detector reads the battery's own current, the charging current
  (before, the discharge current). No bond arrangement keeps the old reading. The 0-1 bond `Bus -> BatJ` is reversed so
  that the bus still receives the discharge current, and a `Gain` `BatDischarge` (`k = -1`) gives the discharge
  current to the BMS coulomb counter and to `PBat`, so `BMS/y` and `PBat/y` are unchanged.
- **Review: maglev-train levers.** The 0-junction bonds `ZF/ZR -> Lever.b` are neutral. The rear lever's `a` was
  reached from the pitch junction's tail to give `v_z + x_m w_y` (the module is behind the centre of mass); `a` is `in`
  and the radius `r` cannot be negative (`min = 1e-9`), so a bond-graph `TF` `FlipR` with `n = -1` turns the pitch rate
  round before the rear pinion. `RackAndPinion` stays (the README describes it), and `LeverR`'s signals are unchanged.
- **Workarounds and prose removed (O12).** The "Bond direction" bullet of the aerial-contact README and of the robird
  README, the bond-direction paragraph of robird's `build_docs.py` and of the pendulum `pendulum_docs.py` /
  `pendulum_readme.py` sources (rewritten to the new directions; the two fixed-pendulum READMEs regenerated). The
  generated docs pages (`models/*.docs/pages/structure.md` of pendulum-double/triple-fixed and robird) still carry the
  old text: they are rebuilt by WP-O5 (`tools/example_docs`), not here.
