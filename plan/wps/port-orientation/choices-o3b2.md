# Choices WP-O3b2 made

Examples: lunar-module, rocket, ingenuity, cars (with build scripts); checked: suction-cup, suction-gripper, gripper,
quadcopter, a109, f16, beaver, cessna, wind-turbine, flex-rotary-pendulum, flex-torsion. Every generator that was run
reproduced its committed models apart from the intended changes (none was stale), so no model JSON was migrated with
the tool and no JSON was edited by hand.

- **O16, the drive junctions of lunar-module and rocket.** Each `Free.drive_k` gets its own 1-junction `Axis<k>`
  with a bond into the drive and a bond into the `MR` `Out<k>` (a sensor or dissipator on a drive goes through a
  junction). The `MR` law is odd and linear in the flow, so the drive sees the same `e = -r f` as before; only the
  `MR`'s own port variables change sign. The node ids after `Axis1` shift by the inserted nodes; nothing refers to
  node ids (plots, bindings and dashboards name signals).
- **O12, the workarounds.** lunar-module and rocket bonded their inertia the textbook way and every attachment the
  other way (`Body -> ThrustW.p`, `Body -> Free.child`, `Pad<k>Mount.b -> Body`, with a comment "b at the from end:
  b.f = -twist (ContactPoint convention)"). They now follow the uniform rules and the comment is gone. Neither README
  nor `tools/example_docs/src/<name>.md` had a bond-direction note (the docs describe the topology only), so they
  were not changed; the generators' docstrings and the diagram notes now mention the drive junctions. ingenuity's
  only note was a comment in its generator ("a wrench source bonds out of its port (as in the stdlib examples)"),
  now the rule ("sources point at the body: wrench -> mount.a, mount.b -> body"); a109's "towards the contact (as
  stdlib ContactPoint expects)" comment went the same way.
- **O17, `cars/Strut` and the anti-roll bar.** `Strut.j.f` is the true travel rate (`v = j.f`, bump positive) and
  `j.e = F` (the force pushing the wheel away from the chassis); the corner's `Travel` junction is reversed with it
  (`Travel -> Susp.drive`, so the junction flow is `+qdot` of the `Prismatic3D`). `AntiRollBar` sits on the same
  junction through `TravelTF`, so it follows the same convention (`ddt(d) = jl.f - jr.f`, `jl.e = F`, `jr.e = -F`).
  The joint's drive variables, the strut's state `x` (start `-dz`, unchanged), `travel`, `F`, `E`, `Pd` keep
  their sign.
- **The limited-slip damper of cars.** `RotationalDamper.a`/`b` are iconic and `in` (O20), and `LsdTF` is a
  `through` TF, so the TF is turned round as a whole: `Spin -> LsdTF.p2`, and the corner port `spin2` (`LsdTF.p1`)
  bonds into the damper. Both corners of an axle flip together, so the odd linear damper is neutral (as the O20
  rule for a multi-terminal iconic block whose bonded terminals all flip).
- **cars: mounted parents.** The corner's chassis mount and the kingpin mount carried a joint parent with both bonds
  leaving the mount; the body side now bonds into the mount's `b` (`Chassis -> <corner>.mount`, `Upright -> KingFT.b`).
  Each reversed bond meets a body junction whose flow changed sign in WP-O3a, so the joint parents see what they saw
  before.
- **`TractionMachine` is `(dc, shaft) => :through`** (a modulated TF, like the stdlib `MTF`); `TractionBattery.p` is
  `in` (a storage element with a series R, written into the port, on a 0-junction).
- **f16 and cessna: `GearContact` was silently wrong after WP-O3a.** The project contact was written for the old
  `RigidBody3D` (its header: "the port flow is then the NEGATIVE point twist and the port effort the wrench on the
  body"). Both examples compiled clean, but the rebuilt body gives the true twist at the mount, so every leg read a
  mirrored velocity and pushed with the wrong sign. Fixed as O7 fixed `ContactPoint`: `v = R p.f[4:6]` and
  `p.e = -[0; R^T F]`; `p`, `n`, `x`, `y` declared `in` (a multiport field, as `MovingPlaneContact`). The law is still
  power-continuous (`p.e . p.f = -F . v = -(n.e n.f + x.e x.f + y.e y.f)`). The edit is in `cessna/library`; f16's build
  copies the Cessna gear blocks, so f16 was regenerated (its models are unchanged, the library copies follow).
- **a109: `ShaftAxis` was silently wrong after WP-O3a.** The block (a transformer from the airframe's spatial port to
  the mast's rotation bond) was bonded like a source (`Shaft.p -> MShaft.a`, `MShaft.b -> Body`) and documented
  "the spatial port then carries the frame's twist". With the rebuilt body that chain gives minus the twist, so the
  rotor speed coupling and the torque reaction flipped: before the fix the a109 run diverged (`a109-open-loop`
  stopped at 5.7 s of 10 with W206, yaw rate -134 deg/s against +2.2 at 1.5 s, and the harness ran out of memory on
  the result; 1 of 99 checks passed). Fixed without a law change: `p => :in`, `s => :out`, and the chain is bonded
  like a contact (`Body -> MShaft.b`, `MShaft.a -> Shaft.p`), which gives `p` exactly the twist and effort it had
  before WP-O3a; `Shaft.s -> Mast` reverses a bond on a 0-junction (neutral). A `through` declaration was not used:
  it would also accept the old topology, which compiles and is wrong.
- **`PistonEngine` (cessna) is `in`, not `out`.** It is a modulated torque source written in the into-port form
  (`p.e = -tau_e`) on the crankshaft's 1-junction, with a state. Declaring it `out` would need a law change and a
  reversed bond for no protection gained; `in` fixes the one direction its law is written for (like the iconic
  sources, O20). `Propeller` (an R) and the strut and wheel elements are `in`.
- **Iconic project blocks** (`gripper` `JawGuides`, `LeadScrew`, `WedgeHook`; `suction-gripper` `CupValve`;
  `quadcopter` `Propeller`) are wired only; their power ports are declared `in` (O20). No model changes.
- **flex-torsion and flex-rotary-pendulum (F6): no sign error.** The chains are Weld1.child -> Mount.a,
  Mount.b -> Shaft.A, Shaft.B -> Weld2.parent (flex-torsion) and Arm -> PivotMount.b, PivotMount.a -> Pivot.parent,
  Pivot.child -> Rod.A (flex-rotary-pendulum); all follow the rules. Independent references:
  (1) the pose chain (signals only, no bonds: `PDisk1/g`, `PDisk2/g`, `PArm/g`, `PRod/g`, `Rod/pose`) differentiated
  numerically against each body's bond-graph twist (`<Body>/inertia/twout`, `Rod/V`): they agree to the
  differentiation error (flex-torsion disks 1e-2 rad/s at the pulse edges against 8.6 rad/s peaks; flex-rotary-pendulum
  arm and rod 0.06 and 0.14 rad/s against 13 rad/s; the negated twist would differ by 17 to 27 rad/s); (2) flex-torsion
  conserves the angular momentum of the pulse: the mean spin after it is 4.9489 rad/s for both disks against
  `T dt / (J1 + J2 + J_shaft)` = 0.1 / 0.0202024 = 4.9499 rad/s. A sign error anywhere in either chain would make a
  disk or the rod turn against its pose. Both examples pass their checks unchanged.
- **Silent-change candidates that were neutral.** suction-cup and suction-gripper drive the tool by an `SfSpatial`
  that already pointed at its junction: the O15 law change (`p.f = -u`) and the O7 contact change of `SuctionCup` cancel,
  and the checks pass unchanged.
- **The migration tool on these examples.** `tools/migrate_bond_orientation.py --check` without flags cannot tell a
  model written for the new laws from one that predates them. On the untouched examples (beaver, gripper,
  quadcopter, suction-cup, suction-gripper, ingenuity, f16 and cessna except their `-sim` models) its "neutral"
  findings are law changes that cancel on the rebuilt body ("law change O7 cancelled by the reversal"): applied, the
  tool only adds its `$comment` idempotency markers and changes no bond and no value (checked by writing to a
  scratch copy of beaver-steps, suction-cup linear-vs-nonlinear, gripper block-gripper, f16-open-loop,
  cessna-open-loop, quadcopter, suction-gripper transfer and ingenuity). Its "review" findings are the models this
  package rewrote by their generators (lunar-module, rocket, cars, a109), the ones with a fixed project block
  (`GearContact` in f16-sim and cessna-sim), ingenuity-rotor-stand (a `Rotor3D` on a ground through a mount: zero
  carrier twist, so the sign is moot) and the flex chains settled above. The markers were not added (generated JSON
  is not edited by hand, and the generators do not write them). With `--skip-law-change O7 --skip-law-change O15`
  the tool reports "nothing to do" for all 57 models of the 15 examples.
- **FMU exports.** `test_export_cars.jl` 26/26, `test_export_f16.jl` 16/16, `export_cars_check.py`,
  `export_f16_check.py` and `export_cessna_check.py` PASS (MSYS2 gcc on this machine). `apps/web/` was not touched;
  its games were built from FMUs exported before the port-orientation branch, which hold the same physics. To bring
  them in line with the sources, rebuild the FMUs of `cars` (racecar-sim, buggy-sim: Strut/ARB/LSD bonds), `a109`
  (a109-sim: ShaftAxis chain), `f16` (f16-sim) and `cessna` (cessna-sim: `GearContact` law) and then
  `build_wasm.py` for `cars` (racecar and buggy), `a109`, `f16` and `cessna` (`apps/web/README.md`).
