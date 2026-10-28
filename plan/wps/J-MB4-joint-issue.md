# J-MB4: why the planar revolute joint is the hard part

Status: open issue note for review, 2026-10-28. Author: orchestrator (M3).
Related work: `plan/MULTIBOND_PLAN.md` section 6 (J-MB4, J-MB6), section 5.5, section 9.3 Gate A;
`plan/adr/ADR-MB1-multibond.md`; `design/multi-bond-graph.md` sections 3–5 and 8.
Current code: `julia/BGSim/stdlib/multibond/` (13 blocks), `julia/BGSim/test/test_multibond_slice.jl`,
`julia/BGSim/test/fixtures/multibond/pendulum.json`.

**Review verdict (2026-10-28, accepted).** The index-3 diagnosis is structural. "No W201" was
the wrong acceptance item for the rigid revolute and is the right one for the compliant pivot:
J-MB4 is amended to require the compliant-pivot variant and zero W201; J-MB6 owns the rigid
variant with **exactly two W201 by design**. Translational pivot compliance (not rotational) is
the correct reading of "compliant"; `kt -> Inf` recovers the rigid joint. The gravity wrench
(zero torque about the CoM, `R^T` on the force) and the Coriolis sign `Coriolis.e = -ad(V)^T P`
on a 1-junction were both confirmed independently.


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
- `qdot = V_rel[1]`, `ddt(q) = qdot`, and the **rotating-frame** deflection update
  `ddt(d[1]) = V_rel[2] + qdot*d[2]`, `ddt(d[2]) = V_rel[3] - qdot*d[1]` (the `z x d` transport
  term; `d . (z x d) = 0`, so the power identity is unchanged);
- `fs = [0, kt*d[1] + bt*V_rel[2], kt*d[2] + bt*V_rel[3]]` (the port effort is `+kt d` under
  the `e·f`-into-the-element convention used by `IPlanar`; it gives the body a restoring force);
- `tau = S^T child.e`, `child.e = fs + S*tau`, `parent.e = -Ad(g(q))^-T child.e`,
  `drive.e = -tau`.

The power identity that must hold on random states is

```
parent.e . parent.f + child.e . child.f + drive.e * qdot
    = fs . V_rel
    = + d/dt( 1/2 kt |d|^2 ) + bt ( V_rel[2]^2 + V_rel[3]^2 )
```

so the joint stores spring energy and dissipates only through `bt`. With `bt = 0` the pendulum
is conservative. The fast translational mode is `sqrt(kt/m)`; the slow pendulum mode is
`sqrt((J + mL^2)/(m g L))`.

Expected state count for the pendulum: `P` (3) + `d` (2) + `q` (1) = 6, all differential. The
only algebraics are `qdot`, `tau = S^T child.e` and `fs`, and each is explicitly solvable from
the equations above (`qdot` from `V_rel[1]`, `tau` from `child.e[1]`, `fs` from `d`/`V_rel`), so
`mtkcompile` should reach index 0 with no dummy derivatives. The body pose for gravity is still
composed from `q` through `ComposePose2D`; no pose is integrated.

The `z x d` transport term in `ddt(d)` is **included**: `d` is expressed in the rotating child
frame, and omitting the term lets the spring's rest position wander tangentially by
`(mg/kt) * delta_q` (about 2e-7 m over the swing, a 1e-5 period effect). Including it costs
nothing and keeps the energy expression `h = gy + sin(q) d1 + cos(q) d2` consistent.

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
5. **The period assertion.** Two effects are not in the model and both are at the 1e-5 level,
   so a 1e-5 tolerance must either include them or be relaxed to 1e-4:
   - **finite amplitude:** `T = T0 (1 + theta0^2/16 + ...)`; at `q0 = 0.01` this is 6.25e-6. The
     6.3e-6 "error" measured with the old joint is almost exactly this correction, not a joint
     error.
   - **static pivot stretch:** `mg/kt = 9.8e-8 m` at `kt = 1e8` (it was `9.8e-6 m` at
     `kt = 1e6`), so at the chosen `kt` the period shift is ~1e-7 and the 1e-5 assertion is
     safe. For robustness document the effective length `L_eff = L + m g0 cos(q0)/kt` in the
     test and, if `kt` is ever lowered, use it or loosen to the plan's 1e-4.
   The test compares the **amplitude-corrected** physical period at 1e-5 (and reports the plan's
   1e-3 check against `2*pi*sqrt(L/g)`), and the energy drift is normalised by the KE/PE swing,
   not by `|E|`.
6. **Energy and the fast mode.** Unless `d` is initialised at its static deflection, the fast
   `sqrt(kt/m)` mode is excited at `t = 0` with energy `1/2 kt |d0|^2`. Rodas5P damps it
   numerically, and that loss appears as "drift" — on the order of 1e-3 of the swing energy is
   enough to fail a swing-normalised 1e-6 check. The acceptance run must initialise `d`
   consistently (the static deflection in the child frame at `q0`) and include `1/2 kt |d|^2` in
   the energy budget.
7. **A convention-independent free-body check.** The current free-body test compares the
   implementation to `P' = ad(V)^T P`, so it shares the convention it checks. Add the invariant
   that does not: for a free planar body with no external wrench, the world linear momentum
   `m R(theta) [vx, vy]` and the angular momentum about the CoM are constant (to integrator
   order). It is cheap and catches a wrong `Ad`/`ad` convention that the equation-level test
   would reproduce.


## 6. Acceptance and next steps

- `julia --project=julia/BGSim julia/BGSim/test/test_multibond_slice.jl`: pendulum period,
  energy (normalised by the swing), stable equilibrium from `q0 = 0.01`, no W201 in
  `model.check` or the run, joint power sum <= 1e-9, Coriolis free-body error <= 1e-6.
- Full `Pkg.test()`, pytest + real-worker tests, web typecheck.
- If the compliant pivot runs: J-MB4 is done with the deviation recorded ("the minimal revolute
  is a compliant-pivot variant; J-MB6 adds the rigid and per-axis compliant variants and the
  composite"). If it does not initialise, the triage order is: first the **initial `d`/`P`
  consistency** (a non-zero static deflection or a body momentum inconsistent with the
  constraints), then the algebraic equation count/solvability (`qdot`, `tau`, `fs`), and only
  then the joint equations themselves. Report the exact algebraic variable and equation set
  before another design change; the fallback is the rigid variant with its two by-design W201
  (J-MB6 owns that variant).

- J-MB6 then owns: the rigid variant for the DAE/index-reduction tests, the per-axis
  compliance, friction/limits, and the composite form. The six-axis arm (J-MB9/J-MB10) will
  face the same 6-DOF/1-DOF structure, so the decision here sets the pattern for Phase C.

## 7. Files and measurements to look at

- `julia/BGSim/stdlib/multibond/Revolute2D.jl` — the joint under revision.
- `julia/BGSim/stdlib/multibond/{IPlanar,CoriolisPlanar,GravityPlanar,ComposePose2D,TFAd,FixedTransform2D,ScrewTF}.jl`
  — the slice elements.
- `julia/BGSim/test/test_multibond_slice.jl` and
  `julia/BGSim/test/fixtures/multibond/pendulum.json` — the acceptance model.
- Measured with the earlier (kinematically wrong) rigid joint, as historical reference only:
  period 1.418795892 s vs physical 1.418787026 s (6.3e-6). That residual is the finite-amplitude
  correction `theta0^2/16 = 6.25e-6`, not a joint error; the model cannot be used as a
  correctness reference. It also reported 2 post-compile W201 (`Body/P[1]`, `Body/P[2]`) with a
  W201-free `model.check`.
- The Coriolis free-body reference after the sign fix: max relative error 4.1e-14 over 2 s.

