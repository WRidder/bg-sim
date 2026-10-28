# multibond-pendulum-2d — the Gate A planar multibond pendulum

The M3 vertical slice and the gate for the multibond plan (plan 9.3, section 6 row
X-MB1): a rigid link hanging from a **compliant-pivot planar revolute joint**, built
from the `Power{Planar}` primitives of `stdlib/multibond/`. A planar multibond is
drawn as **two parallel strokes**; this model is the sample that shows the 2-stroke
convention end to end (editor → worker → run → plot).

```
Ground ──0── Pivot ── Revolute2D ── FixedTransform2D ── 1 ──┬── IPlanar      Body
             │       (kt, bt, d)      (pivot → CoM, 90°)      ├── GravityPlanar
             └── De (pivot wrench)                            ├── CoriolisPlanar
                                                              └── Df (body twist)
                                                                    ▲
    Se (0 N·m) ── drive (Rotation)                                  │ P from Body.Pm
                                                              ComposePose2D ── CoM pose
```

## The physics

A planar multibond carries the twist `V = [ω, vx, vy]` and the wrench
`W = [τ, fx, fy]`, with power `W·V`. A planar revolute joint couples a 3-DOF body
(one rotation + two translations) to a 1-DOF rotation, and its **hard constraints are
the two pivot translations, not the rotation**. A rigid revolute on a rigid 3-DOF body
is therefore index-3 by construction: MTK's index reduction puts two momentum
components into derivative causality and reports two `W201` by design (plan 5.5,
DEC-MB-2). That variant belongs to J-MB6.

This example uses the **compliant-pivot** `Revolute2D`:

- the rotation is exact — `q` is the link-side angle, `g(q) = (q, rx, ry)` with
  `rx = ry = 0`, and `S = [1, 0, 0]`, so the measured period is the physical pendulum
  period;
- the two pivot translations are spring states `d`, with stiffness `kt = 1e8 N/m` and
  damping `bt = 0`. The joint effort is `fs = kt·d + bt·V_rel` (positive into the
  joint), so the body sees the restoring force and the joint stores `½·kt·|d|²`;
- the state vector is only `P` (3 momenta), `d` (2 deflections) and the integrated
  `q` — six differential states, no algebraic constraint forces, **no `W201`**;
- `kt → ∞` recovers the rigid revolute (J-MB6 owns the convergence test).

At `q0 = 0.01 rad` the pivot carries the weight, and the released-from-rest state
also has the constant angular acceleration `alpha = -m*g*L*sin(q0)/(J + m*L^2)`.
The pivot spring must supply the tangential reaction, so the initial deflection is

```
d0 = (-m*g*J/(J + m*L^2)*sin(q0)/kt, -m*g*cos(q0)/kt)
   = (-3.9223657e-13, -9.8095095e-8) m
```

in the rotating child frame. This released-from-rest `d0` is what keeps the fast
translational mode (`sqrt(kt/m) = 1e4 rad/s`) from being excited; the *held* static
value `(-m*g*sin(q0)/kt, -m*g*cos(q0)/kt)` applies a spurious tangential force
`m*g*sin(q0)` and lets the integrator damp the spring transient as energy "drift".

The CoM pose is **composed from `q`, never integrated** (D-MB6): `ComposePose2D`
multiplies the joint pose `(q, 0, 0)` by the constant CoM offset `(π/2, 0, −0.5)`,
so the composed body angle is `θ = q + π/2` (the 90° body frame). `GravityPlanar`
reads that pose and applies the CoM wrench — zero torque about the CoM, `R(θ)ᵀ` on
the force, i.e. the body-frame effort `[0, sin(θ)·m·g, cos(θ)·m·g]` (the negative
of the physical wrench, because a 1-junction sums the efforts). Through the link
transform and the joint this is the physical pendulum torque `−m·g·L·sin(q)`.
`CoriolisPlanar` is Breedveld's Eulerian junction structure with `e = −ad(V)ᵀ·P`; it
takes `P` as a signal from `IPlanar.Pm`, so the inertia `M` is never copied out of
`I` (D-MB3). The element identity `e·f = 0` holds on every sample, and the energy
below is the acceptance test for the pair.

The drive is a zero-torque `Se` (`e = 0 N·m`) on the `Rotation` port of the joint:
the pendulum is torque-free and the run is conservative.

## The flat graph

Every box is a documented primitive or a junction; there is no opaque body or joint
block.

| instance | block | role |
| --- | --- | --- |
| `Ground` | `stdlib:multibond/GroundPlanar` | world flow source, `f = 0` |
| `Pivot` | 0-junction | common pivot wrench; joins `Ground`, `De` and `Joint.parent` |
| `De` | `stdlib:multibond/DePlanar` | zero-flow effort tap: the pivot reaction wrench |
| `Joint` | `stdlib:multibond/Revolute2D` | compliant-pivot revolute, `rx = ry = 0`, `kt = 1e8`, `bt = 0`, `q0 = 0.01` |
| `Drive` | `stdlib:bondgraph/Se` | `e = 0 N·m`, the torque-free drive on the `Rotation` port |
| `Link` | `stdlib:multibond/FixedTransform2D` | pivot → CoM: `x = 0`, `y = −0.5 m`, `θ = π/2` (the 90° body frame) |
| `J1` | 1-junction | common CoM twist: `Body`, `Gravity`, `Coriolis`, `Df` |
| `Body` | `stdlib:multibond/IPlanar` | `J = 1e-4 kg·m²`, `m = 1 kg`; `P` is the state, `Pm` the tap |
| `Gravity` | `stdlib:multibond/GravityPlanar` | `m = 1`, `g0 = 9.81 m/s²`, CoM wrench from the composed pose |
| `Coriolis` | `stdlib:multibond/CoriolisPlanar` | `e = −ad(V)ᵀ·P`, `P` from `Body.Pm` |
| `Df` | `stdlib:multibond/DfPlanar` | zero-effort flow tap: the body twist `[ω, vx, vy]` |
| `CoMOffset` | project inline `CoMOffsetPose2D` | constant local pose `(π/2, 0, −0.5)` as a `Vec{3}` signal |
| `Compose` | `stdlib:multibond/ComposePose2D` | `g = g_joint ∘ g_offset`, the composed CoM pose |

`CoMOffset` is the one non-bond-graph box: it is a constant pose signal, the same
role the M2 examples' signal sources play (D28). It lives in the model document as
an inline block because the language has no vector-constant source yet.

Signal wires: `Joint.pose → Compose.gp` (the joint pose is `(q, rx, ry)`; the link
angle enters here), `CoMOffset.g → Compose.gl`, `Compose.g → Gravity.g`, and
`Body.Pm → Coriolis.P`. The `De` and `Df` taps are the effort/flow pair for the
plot (`De/y`, `Df/y`); `Joint.qout`, `Joint.dout`, `Joint.Vrelout` expose the joint
states directly.

## The two-stroke visual

Section 7 of the plan: the stroke count encodes the **model dimension**, not the
port size. A `Planar` port has three components but is drawn as **two parallel
strokes** with one half arrow per stroke and **one** causal bar across the bundle;
a `Spatial` port is three strokes; a scalar domain stays one stroke. Here every
`Power{Planar}` bond (the pivot, the link, the body 1-junction and the two taps)
carries `data-multibond-strokes="2"`, while the drive bond (`Power{Rotation}`) stays
a single stroke. The editor derives the count from the connection domain; the model
document has no visual field.

## Measured (this example, the real worker)

| quantity | value |
| --- | --- |
| measured period from `Joint/q` up-crossings | **1.41879603183 s** |
| amplitude-corrected physical period (`L_eff = 0.5000000981 m`, `q0²/16`) | 1.41879603223 s (rel −2.8e-10) |
| simple reference `2π√(L/g)` | 1.41850335344 s (rel +2.1e-4; plan target 1e-3) |
| energy drift over 10 s | **1.77636e-15 J** |
| KE/PE swing `m·g·L·(1 − cos q0)` | 2.4524796e-4 J |
| drift / swing | **7.2431e-12** (target 1e-6) |
| static deflection `d0` (released from rest) | (-3.9223657e-13, -9.8095095e-8) m |
| states | 6 (P 3, d 2, q 1), all differential |
| diagnostics | none (`W201`, `E101`, `E102`, `E103`, `E106`, `W206` absent) |
| run cost | **4 072 adaptive steps for the 4 s run, 10 072 for the 10 s run** (no fast transient) |

The model document runs `t_end = 4 s` (what the editor's **Run** does); the checks
re-run the same model with a 10 s settings override for the energy budget, so one
model file backs both windows. `expected.json`:

1. `Joint/q = 0.01 rad` and the static `d0` at `t = 0` (three `cursor_value`
   checks);
2. the **period** from the first two upward zero crossings within `1e-5` of the
   amplitude-corrected physical period, and a second `period` check against the
   simple `2π√(L/g)` at `1e-3`;
3. the amplitude `max|q| = 0.01` over 4 s (`max_abs`);
4. the **energy** check: `E = ½·PᵀM⁻¹P + m·g·h + ½·kt·|d|²` with
   `h = g_y + sin(q)·d1 + cos(q)·d2`, normalised by the swing (the runner's
   `energy` kind, X-MB1; X-MB6 generalises it);
5. `no_diagnostics` on both runs.

## Run it

```
uv run bgsim
```

then **Open** (Ctrl+O) → **Samples** → **multibond-pendulum-2d** (imports a copy),
press **Run**, and open the **Plots** tab: “Joint angle and pivot deflection”,
“Body momentum” and “CoM height and body twist”. The acceptance checks run every
example through the real worker:

```
uv run examples/run_checks.py
```

and the browser acceptance (real worker, two strokes, run, plot, screenshot):

```
cd web
$env:BGSIM_E2E_REAL="1"; npx playwright test tests/e2e/multibond-pendulum.spec.ts --workers=1
```

## What to try

- Set `Joint.q0` to `0.2 rad` and rerun: the period rises by `q0²/16 ≈ 0.25 %`; the
  `period` check against the amplitude-corrected value still passes at the new
  amplitude only if you update `expected.json`, which is the intended signal that
  the physical input changed.
- Lower `Joint.kt` and recompute the `Joint.d` start from
  `d0 = (-m*g*J/(J + m*L^2)*sin(q0)/kt, -m*g*cos(q0)/kt)`: the released-from-rest
  value is what keeps the fast `sqrt(kt/m)` mode out of the budget. Change one
  without the other and the energy check reports the leftover transient (at
  `kt = 1e6` the deflection is 9.8 um, a hundred times the value here).
- Put a torque on `Drive` (set `e = 0.01 N·m`): the pendulum gains energy linearly
  and the `energy` check fails — that is the budget telling you the drive is doing
  work.
- Open the **Signals** tab and plot `De/y[2]`/`De/y[3]` (the pivot reaction force)
  next to `Df/y[1]` (the link rate): the visible vertical reaction peaks at the
  bottom of the swing, once per half period, while the horizontal component tracks
  the tangential load — the signature of a rotating constraint force.
