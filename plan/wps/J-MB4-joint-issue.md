# J-MB4: why the planar revolute joint is the hard part

Status: open issue note for review, 2026-10-28. Author: orchestrator (M3).
Related work: `plan/MULTIBOND_PLAN.md` section 6 (J-MB4, J-MB6), section 5.5, section 9.3 Gate A;
`plan/adr/ADR-MB1-multibond.md`; `design/multi-bond-graph.md` sections 3–5 and 8.
Current code: `julia/BGSim/stdlib/multibond/` (13 blocks), `julia/BGSim/test/test_multibond_slice.jl`,
`julia/BGSim/test/fixtures/multibond/pendulum.json`.

## 1. What Gate A needs

Gate A is the planar vertical slice. The plan's acceptance model is

```
GroundPlanar -> Revolute2D -> Body (IPlanar + GravityPlanar [+ CoriolisPlanar])
```

on the existing MTK/OrdinaryDiffEq backend, with

- the small-angle period within 1e-3 of `2*pi*sqrt(L/g)`,
- constant energy,
- a fixed-base link pose composed from `q` (not an integrated pose),
- the editor showing a two-stroke planar bond.

J-MB4's own row additionally says "no W201". That last item is the source of the conflict
described below: for a genuine 3-DOF planar body on a 1-DOF revolute joint, MTK's index
reduction *must* put two of the body's momentum components in derivative causality, and that
is exactly what W201 reports (plan 5.5 explicitly allows a rigid joint through MTK's DAE/index
reduction and says W201 reports the result).

## 2. The physics in one page

A planar multibond carries

- flow (twist) `V = [omega, vx, vy]`,
- effort (wrench) `W = [tau, fx, fy]`,
- power `W . V`.

A planar pose is `g = (theta, p)` with `p = (px, py)`. The adjoint that maps a child twist to the
parent frame is

```
Ad(g) = [ 1      0     0
          py     cos t -sin t
         -px     sin t  cos t ]
```

and a revolute joint about the z axis through the point `r = (rx, ry)` has the screw

```
S = [1, ry, -rx]^T          (twist of a body whose frame origin is at the parent origin)
S = [1, 0, 0]^T             (twist when the child frame origin is AT the axis point)
```

The joint kinematics are `V_child = Ad(g(q))^-1 V_parent + S qdot`, and power continuity fixes
the effort relation with one negative sign. In a flat bond graph the joint is a 0-junction
(common wrench), an `MTF: Ad(g(q))` between the parent and child multibond sides, and a
`MTF: S` from the multibond side to the scalar `1` junction that carries `tau` and `qdot`.
The scalar drive (`Se`, motor, rotor inertia) attaches to that `1` junction.

## 3. Why the obvious implementation is a high-index DAE

Take a rigid revolute joint and a rigid planar body with momentum state `P in R^3`:

```
V      = M^-1 P                 (M = diag(J, m, m))
ddt(P) = W_port + ad(V)^T P     (Euler/Coriolis term)
V_child = Ad(g(q))^-1 V_parent + S qdot
```

With `Ground` as the parent, `V_parent = 0`, so `V_child = S qdot` has only **one** independent
component. Two of the three momentum equations are therefore constraints, not dynamics. MTK's
Pantelides/dummy-derivative pass can reduce the index, but it must

- differentiate the two constraints twice,
- eliminate two momentum states,
- solve for two algebraic constraint forces,

and the initialisation problem is over-determined unless the initial momentum is exactly
consistent with the constraints. In practice `mtkcompile` leaves algebraic variables such as
`Body/p.f[1]_t` and `init` returns `Unstable` at `t = 0`. That is a structural property of a
3-DOF body on a 1-DOF joint, not a sign bug and not a solver-tolerance problem.

The first implementation avoided the failure with a non-physical trick: it set the joint
kinematics to `S = [1, ry, -rx]` while also placing the child frame at the axis point, and used
`rx = 1e-7`. That runs and gives plausible numbers (measured period 1.418795892 s, energy drift
4e-9 over 10 s), but the reviewer showed it is not the revolute screw for that frame: at
`rx = 0.2` the energy drifts by 27 %. The `1e-7` regularisation was masking a wrong equation. It
cannot ship.

Two further variants were tried and rejected:

1. **1-axis compliance** (a spring/damper on the joint angle only). This adds a deflection
   state but leaves the two *translational* constraint directions rigid, so the DAE stays
   index-3 and still fails to initialise. A revolute joint's hard constraints are the two
   translations of the pivot, not its rotation.
2. **Removing the 3-DOF body** (a 1-DOF link). Then the `Power{Planar}` child port has two
   effort components that nothing terminates: `mtkcompile` reports a structurally singular
   system, and forcing them to zero unbalances the block (E103). This would also defeat the
   purpose of the slice, which is to exercise a planar multibond body.

## 4. The design now being implemented: a compliant pivot

Keep the exact rotation (so `q` is the physical link angle and the period is the physical
pendulum), and make the **two translational directions** of the pivot compliant. This is a
compliant revolute joint in the plan's Mode A sense (D-MB7): every state is integral, and the
joint converges to the rigid revolute as the translational stiffness grows. It is also the
standard way to build a compliant joint in a bond graph: a stiff translational bushing at the
pivot plus a free rotational DOF.

Block `Revolute2D`, native for now (J-MB6 replaces it with a composite and adds the per-axis
variants):

- ports `parent`, `child` (`Power{Planar}`; child frame origin at the pivot), `drive`
  (`Power{Rotation}`);
- parameters `rx`, `ry` [m], `kt` [N/m], `bt` [N*s/m], `q0` [rad];
- states `q`, `d = (dx, dy)`; `qdot` algebraic;
- `g(q) = (q, rx, ry)`, `S = [1, 0, 0]`;
- `V_rel = child.f - Ad(g(q))^-1 parent.f`;
- `qdot = V_rel[1]`, `ddt(q) = qdot`, `ddt(d[i]) = V_rel[i+1]`;
- `fs = [0, -kt*d[1] - bt*V_rel[2], -kt*d[2] - bt*V_rel[3]]`;
- `tau = S^T child.e`, `child.e = fs + S*tau`, `parent.e = -Ad(g(q))^-T child.e`,
  `drive.e = -tau`.

The power identity that must hold on random states is

```
parent.e . parent.f + child.e . child.f + drive.e * qdot
    = fs . V_rel
    = - d/dt( 1/2 kt |d|^2 ) - bt ( V_rel[2]^2 + V_rel[3]^2 )
```

so the joint stores spring energy and dissipates only through `bt`. With `bt = 0` the pendulum
is conservative. The fast translational mode is `sqrt(kt/m)` (about 1000 rad/s at
`kt = 1e6`, `m = 1`), well inside Rodas5P's range for a 10 s run; the slow pendulum mode is
`sqrt((J + mL^2)/(m g L))`.

Expected state count for the pendulum: `P` (3) + `d` (2) + `q` (1) = 6, all differential, no
W201. The body pose for gravity is still composed from `q` through `ComposePose2D`; no pose is
integrated.

Current implementation state: the `CoriolisPlanar` **sign bug is fixed** (the port effort is
now `-ad(V)^T P`; a free-body integration test against an independent RK4 of
`P' = ad(V)^T P`, `V = M^-1 P` gives relative errors 4e-15 to 4e-14, and the old sign fails it).
The `Revolute2D` rewrite and the pendulum acceptance run are in progress; the slice test is red
until they land.

## 5. Open questions for review

1. **Is "no W201" the right WP acceptance item?** A strict 3-DOF body + rigid 1-DOF joint is
   index-3; W201 is the designed report for that (plan 5.5), and Gate A (plan 9.3) does not
   list W201. If the answer is "W201 is acceptable for the rigid variant", then the rigid
   formulation still has to initialise, which it currently does not without a consistent
   initialisation strategy. The compliant pivot sidesteps both problems.
2. **Is a 2-DOF translational compliance at the pivot still a "Revolute2D"?** It is a compliant
   revolute joint (exact rotation, soft pivot). The alternative is a full 3-DOF bushing with a
   3-component deflection and a stiffness matrix; that is more general but is also a new
   element (`CPlanar`/spring) and a J-MB6 concern. The plan's per-axis compliance wording
   refers to the joint's own axes; a revolute joint's hard directions are translational, so
   this reading of "compliant" is the one that actually removes the index problem.
3. **The gravity wrench.** The literal `-Ad(g)^-T [0, 0, m g0]` is wrong when the body frame
   origin is the CoM: it adds a spurious `p x (m g)` torque. The implemented
   `p.e = -R(theta)^T [0, -m g0] = [0, sin(theta) m g0, cos(theta) m g0]` is the correct CoM
   wrench and gives the stable equilibrium at `q = 0` and the torque `-m g L sin(theta)`. The
   review should confirm this reading (the plan's formula assumes a frame at the reference
   point, not at the CoM).
4. **Coriolis sign.** The 1-junction sums efforts to zero, so the `I` element sees
   `ddt(P) = I.e = -Gravity.e - Coriolis.e`; with `Gravity.e = -W_g`, the correct body
   equation `ddt(P) = W_g + ad(V)^T P` requires `Coriolis.e = -ad(V)^T P`. This is what is now
   implemented and tested against the free-body reference. The plan's `e = ad(V)^T P` is the
   effort of the element in the opposite port convention; the sign must be chosen from the
   power direction of the enclosing junction.
5. **The period assertion.** `2*pi*sqrt(L/g)` (1.418503353 s) and the physical rigid-body
   period `2*pi*sqrt((J + mL^2)/(m g L))` (1.418787026 s) differ by 2.1e-4, so a 1e-3 test
   against both is not a strong assertion. The current test is being tightened to the physical
   period at 1e-5 (plus the plan's 1e-3 check against `2*pi*sqrt(L/g)` as reported), and the
   energy drift is normalised by the KE/PE swing, not by `|E|`.

## 6. Acceptance and next steps

- `julia --project=julia/BGSim julia/BGSim/test/test_multibond_slice.jl`: pendulum period,
  energy (normalised by the swing), stable equilibrium from `q0 = 0.01`, no W201 in
  `model.check` or the run, joint power sum <= 1e-9, Coriolis free-body error <= 1e-6.
- Full `Pkg.test()`, pytest + real-worker tests, web typecheck.
- If the compliant pivot runs: J-MB4 is done with the deviation recorded ("the minimal revolute
  is a compliant-pivot variant; J-MB6 adds the rigid and per-axis compliant variants and the
  composite"). If it does not initialise, the exact algebraic variable and equation set must be
  reported before another design change; the fallback is to accept the rigid variant's two
  W201 and amend the J-MB4 acceptance with the plan's 5.5 wording.
- J-MB6 then owns: the rigid variant for the DAE/index-reduction tests, the per-axis
  compliance, friction/limits, and the composite form. The six-axis arm (J-MB9/J-MB10) will
  face the same 6-DOF/1-DOF structure, so the decision here sets the pattern for Phase C.

## 7. Files and measurements to look at

- `julia/BGSim/stdlib/multibond/Revolute2D.jl` — the joint under revision.
- `julia/BGSim/stdlib/multibond/{IPlanar,CoriolisPlanar,GravityPlanar,ComposePose2D,TFAd,FixedTransform2D,ScrewTF}.jl`
  — the slice elements.
- `julia/BGSim/test/test_multibond_slice.jl` and
  `julia/BGSim/test/fixtures/multibond/pendulum.json` — the acceptance model.
- Measured with the earlier (kinematically wrong) rigid joint, for reference only:
  period 1.418795892 s vs physical 1.418787026 s (6.3e-6), energy drift 4.0e-9 relative over
  10 s, stable equilibrium 4.0e-7 rad, 2 post-compile W201 (`Body/P[1]`, `Body/P[2]`),
  `model.check` W201-free.
- The Coriolis free-body reference after the sign fix: max relative error 4.1e-14 over 2 s.
