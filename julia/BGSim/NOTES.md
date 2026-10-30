# BGSim — Julia lane notes (milestone M0.3)

Verified against the installed packages on this machine (Windows 11, Julia 1.13.2, fresh
depot). Everything below was **run**, not read: the snippets are one script
(`notes_snippet.jl`) that ends with `ALL SNIPPETS RAN`, and the same behaviour is asserted
by `test/runtests.jl`. When this file and a plan section disagree, this file wins for the J
lane (plan section 11, "MTK API differs from section 5.8").

## Resolved versions (first resolve, `Pkg.add`, 2026-10-21)

| package | version | | package | version |
| --- | --- | --- | --- | --- |
| julia | 1.13.2 | | JuliaSyntax | 1.0.2 |
| ModelingToolkit | 11.45.5 | | JSON3 | 1.14.3 |
| ModelingToolkitBase | 1.77.5 | | StaticArrays | 1.9.24 |
| Symbolics | 7.47.0 | | PrecompileTools | 1.3.4 |
| SymbolicIndexingInterface | 0.3.55 | | RuntimeGeneratedFunctions | 0.5.27 |
| OrdinaryDiffEqRosenbrock | 2.7.5 | | Sockets | 1.11.0 (stdlib) |
| OrdinaryDiffEqTsit5 | 2.1.5 | | Test | 1.11.0 (stdlib) |
| OrdinaryDiffEqBDF | 2.4.13 | | SciMLBase (transitive) | pulled in by MTK |
| OrdinaryDiffEqVerner | 2.4.2 | | | |

No fallback to Julia 1.12 was needed: MTK 11.45.5 and all four OrdinaryDiffEq sub-packages
resolve and precompile on 1.13.2.

Timings on this machine (cold depot, one process at a time):
`Pkg.add` + dependency precompile **893 s** (241 deps, 776 s of it precompiling);
BGSim's own first precompile **29.9 s** (the `PrecompileTools` workload dominates);
first green `Pkg.test()` **32.5 s**. Total cold chain: **~960 s**.

## Verified API (what section 5.8 must use)

```julia
using ModelingToolkit, Symbolics
using SymbolicIndexingInterface: getu, setu, getp, setp      # NOT exported by MTK
import SymbolicIndexingInterface
using OrdinaryDiffEqRosenbrock                                # Rodas5P, solve, init, step!
using ModelingToolkit: t_nounits as t, D_nounits as D,
    SymbolicContinuousCallback, ImperativeAffect              # public, NOT exported
```

* **Variables from strings** — `only(@variables $(Symbol(name))(t))` works inside a
  function, with no warning, and accepts a dotted bg-sim signal ID verbatim:
  `mtk_variable("motor.omega")` prints as `var"motor.omega"(t)`,
  `SymbolicIndexingInterface.getname` returns `"motor.omega"`, and two calls with the same
  string give the same variable (`isequal` is `true`). `BGSim.mtk_variable`,
  `BGSim.mtk_parameter` and `BGSim.mtk_discrete` wrap this.
  Parameters are `only(@parameters $(Symbol(name)))`, discretes are
  `only(@discretes $(Symbol(name))(t))` (a discrete is a *time-dependent parameter*:
  `isparameter` is `true`, and it belongs in the `System` parameter list).
* **System → mtkcompile → ODEProblem → solve** — `System(eqs, t, vars, pars; name = :x)`,
  `mtkcompile(sys)`, `ODEProblem(sys, op, tspan)` with **one merged operating-point map**
  (start values *and* parameter values in the same vector or `Dict`), then
  `solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)`.
* **Observed values with `getu`** — `getu(indp, sym)` returns a *callable getter*, so the
  observed value is `getu(integ, y)(integ)`. `integ[sym]` and `sol[sym]` work too.
  `sol(t, idxs = sym)` interpolates. `getu(integ)` with no symbol does **not** exist; the
  state vector is `integ.u`.
* **Parameters on the integrator with `setp`** — curried: `setp(integ, V)(integ, 2.0)`,
  several at once with `setp(integ, [V, R])(integ, [3.0, 4.0])`. Read with
  `getp(integ, V)(integ)`. `integ.p[V]` does **not** work (`p` is an
  `MTKParameters`/`DespecializedParameters` struct). `setu(integ, x)(integ, 0.5)` sets a
  state.
* **One-directional continuous events** — `SymbolicContinuousCallback(cond; affect, affect_neg)`.
  `affect` fires on the rising edge, `affect_neg` on the falling edge; **both default to
  `nothing`**, so a condition-only event (no affect at all) is
  `SymbolicContinuousCallback(c ~ 0)`, and a falling-edge-only event is
  `SymbolicContinuousCallback(c ~ 0; affect_neg = [...])`. The event point is saved twice
  (`save_positions == [true, true]`), i.e. pre- and post-affect values at the same `t`.
  `rootfind = SciMLBase.RightRootFind` also works (default `LeftRootFind`).
* **Imperative affects** — `ImperativeAffect(f; modified = (; x), observed = (; y))` where
  `f(modified, observed, ctx, integrator)` returns a `NamedTuple` of the new values of the
  modified variables (no Setfield/Accessors needed). `modified` must be bare variables;
  every discrete written this way is picked up automatically, so no `discrete_parameters`
  is needed on the callback.
* **Condition-only events from `ifelse`** — MTK does **not** add callbacks for `ifelse`.
  `ODEProblem(...).kwargs` has no `:callback` unless we pass `continuous_events`, so the
  collection of switching conditions that section 5.8 describes is ours to do, and it
  works: with `SymbolicContinuousCallback(x ~ 0.5)` the solver saves a point at the kink
  (t = 0.4999993411925162, x = 0.500000658807484 with `1e-10` tolerances) and the solution
  after the kink is exact.
* **`remake`** — `remake(prob; p = [R => 2.0], u0 = [x => 0.5])` works with symbolic maps and
  leaves `prob` untouched (decision D4).

## API surprises and gotchas

1. **`Pre(...)` is required in affect *equations*.** `[v ~ -e * v]` silently solves the
   simultaneous system `v = -e*v`, i.e. it sets `v = 0` — no error, wrong physics. Write
   `[v ~ -e * Pre(v)]`. The `Pair` form `[v => -e * v]` is safe because `AssignmentAffect`
   wraps the right-hand side in `Pre` for you.
2. **`getu`, `setp`, `getp`, `setu`, `SymbolicContinuousCallback` and `ImperativeAffect` are
   not exported** by ModelingToolkit (they are `@public`). Import them explicitly from
   `SymbolicIndexingInterface` / `ModelingToolkit`. `using SymbolicIndexingInterface`
   wholesale clashes with MTK on `observed`.
3. **`getu(integ)` (no symbol) does not exist** in SymbolicIndexingInterface 0.3.55; use
   `integ.u` for the whole state vector.
4. **A discrete counter has its own timeseries.** `sol[n]` for a discrete returns one entry
   per event plus the start value (e.g. `[0.0, 1.0, …, 6.0]`), so it must not be indexed
   with an index into `sol.t`.
5. **`==` on symbolic variables builds an `Equation`**, not a `Bool`. Use `isequal`.
6. **`ODESystem` and `structural_simplify` still exist but are deprecated aliases** that emit
   a `depwarn` and forward to `System`/`mtkcompile`. Never use them.
7. **An `ifelse` guard on the contact variable causes Zeno chatter.** A model with
   `D(v) ~ ifelse(h < 0, 0.0, -g)` plus a condition-only/edge event on `h ~ 0` re-triggered
   66 662 times inside 0.45 s and ended in `retcode = MaxIters`. Keep switching guards off
   the variable that a callback watches (the WP W206 event limit is exactly for this).
8. **The first re-run after a parameter change pays JIT.** `remake` + `solve` on a freshly
   compiled model took 1.1–2.7 s the first time and 3–5 ms afterwards; reusing one
   integrator with `setp` + `reinit!` + `solve!` took 525 ms the first time and <1 ms
   afterwards. The 300 ms target of section 5.8 must therefore be measured **after** one
   warm-up re-run, and the worker's start-up warm-up should include a parameter change.
9. `ifelse` has two lazy/eager variants in SymbolicUtils (`ifelse_eager`, `ifelse_branching`,
   the latter never evaluates the untaken branch). Plain `ifelse` is the default and is
   intended to pick a strategy by heuristic later; if a branch is only valid when its
   condition holds (division by zero, `NaN`), prefer `ifelse_branching`.
10. `System` accepts a `Dict` for the operating-point map as well as a vector of pairs.

## Snippet script

The block below is also saved as `julia/BGSim/test/notes_snippet.jl` and can be run directly
with `julia --project=julia/BGSim julia/BGSim/test/notes_snippet.jl` from `D:/bg-sim`
(it is not part of `Pkg.test()`, which runs `test/runtests.jl`). Captured output follows it.

```julia
using ModelingToolkit, Symbolics
using SymbolicIndexingInterface: getu, setu, getp, setp
import SymbolicIndexingInterface
using OrdinaryDiffEqRosenbrock
import OrdinaryDiffEqTsit5, OrdinaryDiffEqBDF, OrdinaryDiffEqVerner, JSON3, JuliaSyntax,
    StaticArrays, PrecompileTools, RuntimeGeneratedFunctions
using ModelingToolkit: t_nounits as t, D_nounits as D,
    SymbolicContinuousCallback, ImperativeAffect

println("## 0. versions")
for p in (ModelingToolkit, Symbolics, SymbolicIndexingInterface, OrdinaryDiffEqRosenbrock,
    OrdinaryDiffEqTsit5, OrdinaryDiffEqBDF, OrdinaryDiffEqVerner, JSON3, JuliaSyntax,
    StaticArrays, PrecompileTools, RuntimeGeneratedFunctions)
    println("   ", rpad(string(nameof(p)), 30), pkgversion(p))
end
println("   ", rpad("julia", 30), VERSION)

println("\n## 1. variables from strings")
function mtk_variable(name)
    return only(@variables $(Symbol(name))(t))
end
function mtk_parameter(name)
    return only(@parameters $(Symbol(name)))
end
function mtk_discrete(name)
    return only(@discretes $(Symbol(name))(t))
end
u_C = mtk_variable("motor.omega")           # -> var"motor.omega"(t)
R = mtk_parameter("motor.R")                # -> var"motor.R"
n = mtk_discrete("motor.mode")              # -> var"motor.mode"(t)
println("   u_C = ", u_C, "   isvariable = ", ModelingToolkit.isvariable(u_C))
println("   R   = ", R, "   isparameter = ", ModelingToolkit.isparameter(R))
println("   n   = ", n, "   isparameter = ", ModelingToolkit.isparameter(n))
println("   getname(u_C) = ", SymbolicIndexingInterface.getname(u_C))
println("   same name gives the same variable: ", isequal(u_C, mtk_variable("motor.omega")))
println("   never use == on variables (it builds an Equation): ", u_C == u_C)

println("\n## 2. RC circuit: System -> mtkcompile -> ODEProblem -> solve(Rodas5P())")
uu = mtk_variable("rc.u_C")
ii = mtk_variable("rc.i")
ur = mtk_variable("rc.u_R")
yy = mtk_variable("rc.y")
V = mtk_parameter("rc.V")
Rr = mtk_parameter("rc.R")
Cc = mtk_parameter("rc.C")
eqs = [0 ~ V - ur - uu, ur ~ Rr * ii, ii ~ Cc * D(uu), yy ~ uu]
sys = System(eqs, t, [uu, ii, ur, yy], [V, Rr, Cc]; name = :rc)
println("   unknowns before = ", unknowns(sys), "  observed before = ", observed(sys))
csys = mtkcompile(sys)                      # NOT structural_simplify (deprecated alias)
println("   unknowns after  = ", unknowns(csys))
println("   observed after  = ", observed(csys))
# ONE merged operating-point map: start values and parameter values together.
prob = ODEProblem(csys, [uu => 0.0, V => 1.0, Rr => 1.0, Cc => 1.0], (0.0, 5.0))
sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
println("   sol.retcode = ", sol.retcode)
println("   sol(1.0, idxs=yy) = ", sol(1.0, idxs = yy), "   analytic = ", 1 - exp(-1.0))
println("   sol[yy] (whole observed timeseries) = ", length(sol[yy]), " points")

println("\n## 3. getu / setp / setu on a live integrator")
integ = init(prob, Rodas5P())
step!(integ, 1.0)
println("   integ.u = ", integ.u, "   integ.t = ", integ.t)
println("   getu(integ, yy)(integ) = ", getu(integ, yy)(integ), "   (observed)")
println("   getu(integ, uu)(integ) = ", getu(integ, uu)(integ), "   (state)")
println("   integ[yy] = ", integ[yy], "   (getindex shortcut)")
println("   getu(integ) does not exist -> state vector is integ.u: ",
    hasmethod(getu, Tuple{typeof(integ)}))
setp(integ, V)(integ, 2.0)                  # curried: setp(integ, sym)(integ, value)
println("   after setp(integ, V)(integ, 2.0): getp(integ, V)(integ) = ",
    getp(integ, V)(integ))
setp(integ, [V, Rr])(integ, [3.0, 4.0])
println("   setp with several parameters: ", getp(integ, [V, Rr])(integ))
setu(integ, uu)(integ, 0.25)
println("   after setu(integ, uu)(integ, 0.25): getu(integ, uu)(integ) = ",
    getu(integ, uu)(integ))
println("   integ.p[V] does not work (MTKParameters is a struct): ",
    try
        integ.p[V]
        "works"
    catch err
        string(typeof(err))
    end)

println("\n## 4. one-directional continuous events")
h = mtk_variable("ball.h")
v = mtk_variable("ball.v")
g = mtk_parameter("ball.g")
e = mtk_parameter("ball.e")
b = mtk_parameter("ball.b")
ball_eqs = [D(h) ~ v, D(v) ~ -g - ifelse(v > 0, b * v, 0.0)]
# affect_neg = falling edge only; affect = rising edge only; both default to nothing.
cb = SymbolicContinuousCallback(h ~ 0;
    affect_neg = [v ~ -e * Pre(v)],        # Pre() is REQUIRED here, see gotchas
    discrete_parameters = Symbol[])        # or nothing when no discrete is written
bsys = mtkcompile(System(ball_eqs, t, [h, v], [g, e, b]; name = :ball,
    continuous_events = [cb]))
bprob = ODEProblem(bsys, [h => 1.0, v => 0.0, g => 9.81, e => 0.8, b => 0.1], (0.0, 0.7))
bsol = solve(bprob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
i = findfirst(>=(sqrt(2 / 9.81) - 1e-9), bsol.t)
println("   bounce time = ", bsol.t[i], "   analytic = ", sqrt(2 / 9.81))
println("   v before = ", bsol[v][i], "  v after = ", bsol[v][i + 1],
    "  analytic = ", 0.8 * sqrt(2 * 9.81))
println("   the event point is saved twice (save_positions = ",
    bprob.kwargs[:callback].save_positions, ")")
rising = SymbolicContinuousCallback(h ~ 0; affect = [v ~ -e * Pre(v)])
rsys = mtkcompile(System(ball_eqs, t, [h, v], [g, e, b]; name = :ball_up,
    continuous_events = [rising]))
rsol = solve(ODEProblem(rsys, [h => 1.0, v => 0.0, g => 9.81, e => 0.8, b => 0.1], (0.0, 0.7)),
    Rodas5P())
println("   rising-edge-only affect: v(0.7) = ", rsol(0.7, idxs = v),
    " (ball falls through, no bounce)")

println("\n## 5. imperative affect (function of the integrator state)")
n_imp = mtk_discrete("ball.n_imp")
imp = ImperativeAffect(
    (m, o, ctx, integ) -> (; v = -o.e * m.v, n = m.n + 1);   # returns the new values
    modified = (; v, n = n_imp), observed = (; e))
isys = mtkcompile(System(ball_eqs, t, [h, v], [g, e, b, n_imp]; name = :ball_imp,
    continuous_events = [SymbolicContinuousCallback(h ~ 0; affect_neg = imp)]))
isol = solve(ODEProblem(isys,
        [h => 1.0, v => 0.0, g => 9.81, e => 0.8, b => 0.1, n_imp => 0.0], (0.0, 3.0)),
    Rodas5P())
println("   retcode = ", isol.retcode, "  impulses counted = ", isol[n_imp][end])
println("   discrete counter timeseries = ", isol[n_imp])
j = findfirst(>=(sqrt(2 / 9.81) - 1e-9), isol.t)
println("   v after first bounce = ", isol[v][j + 1])

println("\n## 6. condition-only event (no affect) lands on a switching instant")
x = mtk_variable("sw.x")
k = mtk_parameter("sw.k")
sw_eqs = [D(x) ~ -ifelse(x > 0.5, 1.0, 2.0)]
plain = ODEProblem(mtkcompile(System(sw_eqs, t, [x], [k]; name = :sw_plain)),
    [x => 1.0, k => 1.0], (0.0, 2.0))
println("   without an explicit event MTK adds no callback: ",
    !haskey(plain.kwargs, :callback))
ssys = mtkcompile(System(sw_eqs, t, [x], [k]; name = :sw,
    continuous_events = [SymbolicContinuousCallback(x ~ 0.5)]))
ssol = solve(ODEProblem(ssys, [x => 1.0, k => 1.0], (0.0, 2.0)), Rodas5P();
    abstol = 1e-10, reltol = 1e-10)
hit = findfirst(tt -> abs(tt - 0.5) < 1e-6, ssol.t)
println("   saved point at the kink: t = ", ssol.t[hit], "  x = ", ssol[hit][1])

println("\n## 7. remake: a parameter-only re-run reuses the compiled system")
prob2 = remake(prob; p = [Rr => 2.0], u0 = [uu => 0.5])
println("   prob2.u0 = ", prob2.u0, "  getp(prob2, Rr) = ", getp(prob2, Rr)(prob2))
println("   prob untouched: ", getp(prob, Rr)(prob))
solve(prob2, Rodas5P())
t0 = time()
solve(remake(prob; p = [Rr => 3.0]), Rodas5P())
println("   warm remake + solve: ", round(1000 * (time() - t0); digits = 1), " ms")
println("\nALL SNIPPETS RAN")
```

Captured output (`julia --project=julia/BGSim`, Julia 1.13.2):

```
## 0. versions
   ModelingToolkit               11.45.5
   Symbolics                     7.47.0
   SymbolicIndexingInterface     0.3.55
   OrdinaryDiffEqRosenbrock      2.7.5
   OrdinaryDiffEqTsit5           2.1.5
   OrdinaryDiffEqBDF             2.4.13
   OrdinaryDiffEqVerner          2.4.2
   JSON3                         1.14.3
   JuliaSyntax                   1.0.2
   StaticArrays                  1.9.24
   PrecompileTools               1.3.4
   RuntimeGeneratedFunctions     0.5.27
   julia                         1.13.2

## 1. variables from strings
   u_C = var"motor.omega"(t)   isvariable = true
   R   = var"motor.R"   isparameter = true
   n   = var"motor.mode"(t)   isparameter = true
   getname(u_C) = motor.omega
   same name gives the same variable: true
   never use == on variables (it builds an Equation): var"motor.omega"(t) == var"motor.omega"(t)

## 2. RC circuit: System -> mtkcompile -> ODEProblem -> solve(Rodas5P())
   unknowns before = ...[var"rc.u_C"(t), var"rc.i"(t), var"rc.u_R"(t), var"rc.y"(t)]  observed before = Equation[]
   unknowns after  = ...[var"rc.u_C"(t)]
   observed after  = Equation[var"rc.u_R"(t) ~ var"rc.V" - var"rc.u_C"(t), var"rc.y"(t) ~ var"rc.u_C"(t), var"rc.i"(t) ~ var"rc.u_R"(t) / var"rc.R"]
   sol.retcode = Success
   sol(1.0, idxs=yy) = 0.6321205588232383   analytic = 0.6321205588285577
   sol[yy] (whole observed timeseries) = 80 points

## 3. getu / setp / setu on a live integrator
   integ.u = [0.6644230230232697]   integ.t = 1.091903923893989
   getu(integ, yy)(integ) = 0.6644230230232697   (observed)
   getu(integ, uu)(integ) = 0.6644230230232697   (state)
   integ[yy] = 0.6644230230232697   (getindex shortcut)
   getu(integ) does not exist -> state vector is integ.u: false
   after setp(integ, V)(integ, 2.0): getp(integ, V)(integ) = 2.0
   setp with several parameters: [3.0, 4.0]
   after setu(integ, uu)(integ, 0.25): getu(integ, uu)(integ) = 0.25
   integ.p[V] does not work (MTKParameters is a struct): MethodError

## 4. one-directional continuous events
   bounce time = 0.45152364098572684   analytic = 0.4515236409857309
   v before = -4.429446918070044  v after = 3.5435575344560357  analytic = 3.5435575344560166
   the event point is saved twice (save_positions = Bool[1, 1])
   rising-edge-only affect: v(0.7) = -6.86700000000013 (ball falls through, no bounce)

## 5. imperative affect (function of the integrator state)
   retcode = Success  impulses counted = 6.0
   discrete counter timeseries = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
   v after first bounce = 3.543557534456057

## 6. condition-only event (no affect) lands on a switching instant
   without an explicit event MTK adds no callback: true
   saved point at the kink: t = 0.4999993411925162  x = 0.500000658807484

## 7. remake: a parameter-only re-run reuses the compiled system
   prob2.u0 = [0.5]  getp(prob2, Rr) = 2.0
   prob untouched: 1.0
   warm remake + solve: 304.0 ms

ALL SNIPPETS RAN
```

The 304 ms in section 7 is the *first* re-run after a parameter change (JIT of the
re-specialized parameter path); it was 249 ms on a later run of the same script. Timed in a
loop afterwards, `remake` + `solve` is 3–5 ms and `setp` + `reinit!` + `solve!` on a reused
integrator is under 1 ms, so the section 5.8 "under 300 ms when warm" target is reachable
with a warm-up re-run first.

---

# J1.1 — the language front end (verified 2026-10-22)

Everything below was run on the installed JuliaSyntax 1.0.2 (Julia 1.13.2) and is asserted by
`test/test_syntax.jl`. The front end never calls `eval`, `Meta.parse`-and-`eval` or `include`
on user text: `src/syntax/parse.jl` walks a `JuliaSyntax.SyntaxNode` tree and builds the
immutable AST in `src/syntax/ast.jl`; `src/syntax/constfold.jl` folds constant expressions
with a small interpreter.

## JuliaSyntax 1.0.2 API (what the walker relies on)

```julia
using JuliaSyntax
tree = JuliaSyntax.parseall(SyntaxNode, text; filename, ignore_errors=false)
kind(node)                      # JuliaSyntax.Kind, compare with K"call" etc.
children(node)                  # Vector{SyntaxNode} for branch nodes, nothing for leaves
is_leaf(node)
byte_range(node)                # 1-based byte indices into the source String
sourcefile(node)                # JuliaSyntax.SourceFile
source_location(sf, byte)       # (line, col), col in characters
JuliaSyntax.filename(node)      # the `filename` kwarg, or ""
isa(node, JuliaSyntax.SyntaxNode)
```

Verified node shapes (all asserted in the tests via the golden blocks):

| source | JuliaSyntax shape |
| --- | --- |
| `@block C begin ... end` | `K"macrocall"` → `K"MacroName"(Symbol("@block"))`, `Identifier`, `K"block"` |
| `@ports p::Power{Generic}` | `K"macrocall"` → `K"::"`(`Identifier`, `K"curly"`) |
| `@parameters c::Real = 1.0, [min = 0]` | `K"macrocall"` → `K"="`(`K"::"`, default) where default is `K"tuple"`(`Float`, `K"vect"` of `K"="`) |
| `w::Real, [unit = "rad/s"]` (no default) | `K"tuple"`(`K"::"`, `K"vect"`) — *not* a comma-separated list |
| `lhs ~ rhs` | `K"call"` with three children: lhs, `Identifier(:~)`, rhs |
| `a + b + c` | one `K"call"`: `[a, Identifier(:+), b, c]` — one operator leaf, the rest operands (fold left!) |
| `a - b + c`, `a * b / c` | nested `K"call"`s (different operators) |
| `-x`, `!x` | two-child `K"call"`: `[Identifier(:-), x]` |
| `p.e` | `K"."`(`Identifier`, `Identifier`) |
| `v[i, j]` | `K"ref"`(base, indices...) |
| `[1.0, 2.0]` / `[1 2; 3 4]` | `K"vect"` / `K"vcat"` of `K"row"`s (`K"hcat"` for a single row) |
| `if c ... else ... end` | `K"if"`(`cond`, `K"block"`, `K"block"` or `K"elseif"`) |
| `for i in 1:N` | `K"for"`(`K"iteration"`(`K"in"`(`Identifier`, range)), `K"block"`) |
| `x = 1` / `x += 1` | `K"="` / `K"op="` |
| `:prefer`, `:effort_out` | `K"quote"`(`Identifier`) |
| string literal | `K"string"` with one `K"String"` leaf; interpolation adds more children |

Two API facts that are easy to get wrong:

1. **`Base.isoperator(:+)` is `true`, `Base.isoperator(:sin)` is `false`.** That is how an
   infix operator leaf is told apart from an ordinary identifier: `f(a, b)` and `a + b` both
   have the shape `[Identifier, Identifier, ...]`. `Base.isoperator` is not exported and is
   not in the public docs; it was probed on 1.13.2, and `src/syntax/parse.jl` is the only
   user. `in`/`isa`/`where` are `K"in"`/`K"isa"`/`K"where"` leaves, not `Identifier`s.
2. **`parseall` throws `JuliaSyntax.ParseError`**, whose `diagnostics::Vector{Diagnostic}`
   field carries `first_byte`/`last_byte`/`level`/`message` and `source::SourceFile`. Error
   ranges can be empty at EOF (`last_byte < first_byte`), so the range builder clamps the
   end to the start. The parser's message ("Expected `end`", "invalid identifier") is passed
   through as `E000` with the prefix `syntax error: `.

## The front-end contract (do not rename)

`src/diagnostics.jl`: `SourceRange(file, line, col, endLine, endCol)`, `SourceRef(kind, ref,
range)`, `Related(path, message)`, `Diagnostic(...)` exactly as plan 3.4. `severity_of(code)`
is the one table (`E*` error, `W*` warning, else info). `diag`, `to_namedtuple`, `to_dict`,
`from_dict`, `sort_diagnostics`, `source_kind` are the API. The single severity override is
the block-level balance precheck: `E103` is reported as a `"warning"` when a block is checked
alone (plan 4.4).

`src/syntax/ast.jl`: `abstract type Expr` with `Lit`, `Name`, `Field`, `Call`, `BinOp`,
`UnOp`, `Index`, `VectorLit`, `MatrixLit`, `IfElse`, `Comparison`, `BoolOp`;
`expr_range(e)` (also `source_range(e)`). `Field` is an addition to the work-package list:
`p.e` must stay structured for flattening. `Call.fn` is a `Name`, so `expr_range(call.fn)` is
the callee range that E002 points at.

Declarations: `Decl` with `decl_name`, `decl_type`, `decl_default`, `decl_attrs`,
`decl_scope`, `decl_range`, `decl_default_text`. `decl_type` is a `TypeSpec(kind, args)`:
`:Real`, `:Int`, `:Bool`, `:Vec`, `:Mat`, `:Power`; size args stay `Symbol`s (`Vec{N}`)
because D13 lets an instance override `N`. Resolve them with
`type_size(t, constant_env(pb))` → `[]`, `[N]` or `[N,M]`, or `nothing` when not static.
`type_element(t)` is `:Real` for `Vec`/`Mat` (the catalog's `type` field).
`decl_attrs` keys: `:unit` (String), `:min`/`:max`/`:nominal` (Int/Float64),
`:tunable`/`:structural` (Bool), `:description` (String), `:state` (`:prefer`/`:avoid`),
`:options` (`Vector{String}`).

Equations: `equations(pb)` returns `Equation(lhs, rhs, range, scope)`,
`IfEquation(branches)`, `ForEquation(var, lo, hi, step, body, range)`. `if` in `@equations`
requires an `else` and equal branch counts; `ForEquation` bounds must fold.

`block_interface(pb)` returns the plan 3.2 `blockInterface` NamedTuple — exactly the seven
arrays, each a `Vector` of NamedTuples with the catalog schema fields. Constants carry the
folded value (`2`), parameters/variables carry the *source text* of their default (`"1e-3"`,
`"[1.0, 1.0]"`), so `catalog.get` matches the fixture. `block_equations(pb)` returns the
equation items or `Any[]` when `check_block` reports an error (warnings do not suppress it).

`parse_blocks(text)` parses several top-level `@block`s; `parse_block` requires exactly one.
`@initial @discrete @events @components @connections` are rejected with E001 naming the scope
(J2.1/J2.6 enable them).

## E005, as implemented in J1.1

* a `Vec`/`Mat` size that is neither an integer literal nor a `@constants` value → E005
  (a `@parameters` value is *not* structural);
* a literal index out of range when the size is known (`v[4]` with `Vec{3}`);
* the wrong number of indices for a `Vec`/`Mat`;
* indexing a scalar;
* a size below 1;
* a non-constant `for` bound.
Loop-variable indices are accepted unchecked; J2.1 owns the full unrolled index check.

## Catalog fixture notes (contracts/ not edited)

Three fixture blocks carry metadata that their `source` text does not produce; the parser
follows the source, which is normative:

* `stdlib:continuous/Sum`: the parameter description in the fixture is
  `"Sign of every input, +1 or -1 (D11)"`, the source text says
  `"Sign of every input, +1 or -1"`.
* `stdlib:electrical/VoltageSource`, `stdlib:translation/ForceSource`,
  `stdlib:rotation/TorqueSource`: the fixture lists a `fixed` causality entry that the
  source text does not declare (no `@causality` line).

---

# J1.5 — lowering and simulation (verified 2026-10-22)

Everything below was run on the installed packages. The acceptance is
`test/test_simulate.jl` (169 assertions), run by `Pkg.test()`; the full suite is green.

## The lowering contract

* `BGSim.compile_key(flat)` hashes the structure as 64 lowercase hex: variables,
  parameters, equations, `initial`, `events`, `discrete`, derived power signals and the
  recording order. Parameter values and start values are **not** in the key (D4), so a
  parameter-only or start-only change hits the cache.
* `BGSim.lower_model(flat; t_start, t_end)` returns `(model, problem, cache_hit)`. A miss
  builds `System(eqs, t, vars, pars; name)` → `mtkcompile` → `ODEProblem`. A hit rebuilds
  only the problem through `remake(prob; u0, p, tspan)`.
* The **operating point must contain only `ModelingToolkit.unknowns(csys)`**. Passing every
  flat variable (including observed and algebraic ones) made MTK treat 24 start guesses as
  initialization equations, warn "overdetermined initialization" and spend 7 s in `init`;
  with the unknowns only, the DC motor's `init` is milliseconds. `_u0_pairs` filters by the
  compiled unknowns and looks the start up by signal id.
* **States vs algebraic (FIX-M2-1).** `u0` may contain only the compiled unknowns that
  appear under `Differential`; `collect_differential_variables(csys)` gives exactly that set.
  A value in `u0` is an initial **condition**, so a start for an algebraic unknown becomes an
  extra initialization equation (one equation, no unknowns) and fails whenever the true value
  differs. The `tf_chain` fixture is the regression: its TF second-port effort is 0.5 at
  t = 0. Algebraic starts are passed to `ODEProblem(...; guesses = ...)` instead; the
  compile-cache `remake` keeps the guesses of the cached problem (it takes `u0`, `p` and
  `tspan`; start guesses do not change the structure, D4).
* Derived port power (`e*f`, D15) is added as an extra variable and equation. `mtkcompile`
  turns it into an observed value, so the recorder reads it with the same `getu` getter as
  every other signal. The flat `stats.states`/`stats.equations` do not count it; the run
  manifest reports the model counts.
* `int(x, x0)` becomes a hidden state `__bgint/<path>/<n>` with `D(state) ~ x`. `x0` is kept
  as an AST and evaluated with the current parameter values on every run, so a parameter
  change that feeds an integral's start value is honoured by `remake`. The manifest's
  `stats.states` and `stats.equations` add one per `int`.
* `nonsmooth_conditions(flat)` is the J2.3 seam. It returns real expressions whose upward
  zero crossing is the switch; `lower_flat` turns each into
  `SymbolicContinuousCallback(c ~ 0)` and passes `continuous_events` only when the collector
  is non-empty. The continuous M1 collector is empty.
* Nonsmooth functions are lowered to explicit `ifelse`: `abs`, `sign`, `min`, `max`, `clamp`,
  `saturate`, `deadzone`, and `round` (as `ifelse(x >= 0, floor(x + 0.5), ceil(x - 0.5))`).
  `floor`, `ceil`, `mod`, `rem`, `hypot` and two-argument `atan` are native Symbolics heads.
  `&&`/`||` lower to `&`/`|`; `==`/`!=` build comparison expressions that `ifelse` accepts.
* `"auto"` chooses `Rodas5P()` when `prob.f.mass_matrix` is not the identity (a real DAE),
  `Tsit5()` otherwise. The explicit choices are `Rodas5P`, `Tsit5`, `FBDF` and `Vern7`, all
  from the split sub-packages. An unknown name is E901.

## The run loop and recorder

* The output grid is `points` equally spaced values including both ends, or `interval` steps
  including `t_end`. The loop calls `step!(integ, dt, true)` so the integrator lands **exactly
  on each grid time**, then reads every signal with the current state. This matters:
  `integ(t, idxs = y)` for a time in the past was 4e-6 off (it uses the current step's
  interpolant), while `integ.sol(t, idxs = y)` was accurate but needs saved points. Stepping
  to the grid point avoids interpolation completely.
* Getters are built once: `getu(integ, sym)(integ)` for variables/observed values,
  `getp(integ, sym)(integ)` for parameters (the future discrete signals).
* `stream.f64` is row-major `[t, v1 … vn]` little-endian Float64 (`htol` on the bit pattern,
  so it is independent of the host). `columns.f64` is the time column followed by one
  contiguous column per signal. Duplicate `t` rows are supported and tested (J2.3 records
  the two sides of an event at the same instant).
* The manifest is written **before the first row** with `status: "running"` and the full
  signal list (REQ-1), then rewritten atomically (temp file + rename) with the final status,
  stats, `n`/`t0`/`t1` and diagnostics. A run that cannot start (flatten error) writes only
  the failed manifest. The document validates against `run-manifest.schema.json` (checked
  with the backend's `jsonschema` registry) and numpy `memmap` reads `columns.f64` correctly.
* Cancellation is an atomic flag checked before and after every `step!`; the status becomes
  `cancelled` and the files hold the rows written so far. Progress is a `(t, rows)` callback
  throttled to 100 ms (the first row is reported immediately); phases are `("mtkcompile" |
  "init" | "simulate" | "write", t_s)`.
* Solver failures are E901 with `t`, the retcode and the five largest states; MTK's
  `ExtraEquationsSystemException`/`ExtraVariablesSystemException` are E103; a failed
  initialization is E103 "initial conditions are inconsistent"; anything else is E900 with
  the exception text in the hint and the last-touched instance path.

## Physics fixes made by J1.5 (CONTRACT-5)

The 9.1 comparison found two sign errors that CONTRACT-4's power-conservation fix did not
cover. Both are fixed in the stdlib and in the catalog fixture's normative `source` text:

1. `stdlib/converters/DCMotor.jl`: the shaft port is power-positive into the motor, so the
   electromagnetic torque leaves through it:
   `shaft.e ~ -k_t*i + J*ddt(w_rel) + d*w_rel` (was `+k_t*i`). The old sign made the iconic
   model unstable (`omega` reached 1e107 at t = 2 s); the correct model settles at
   `k*V/(R*d + k^2)`.
2. `stdlib/bondgraph/GY.jl`: with `p1` on the electrical side and `p2` on the mechanical side
   (the 9.1 bond graph), the motor orientation is `p1.e ~ -r*p2.f`, `p2.e ~ r*p1.f` (was the
   opposite). Power is conserved either way; the old choice made a generator, so the bond
   graph settled at −239.81 rad/s.

The RLC models did not need a fix: they agree to 7.6e-13 V and their peak matches the analytic
16.3 % overshoot.

## Measured numbers (this machine, 2026-10-22)

| item | measured |
| --- | --- |
| DC motor steady state (plan 9.1, rtol 1e-4) | **239.80815347721813 rad/s** (target 239.80815347721824) |
| iconic vs bond graph, settled (`t ≥ 0.5 s`) | **max abs difference 5.68e-14 rad/s**, max current difference 2.02e-15 A |
| RLC iconic vs bond graph | **max abs difference 7.64e-13 V**; peak 1.161862 V vs analytic 1.163034 V (grid sampling) |
| first run, fresh process, 5000 points | compile 1.2–1.7 s + init/getters ≈ 3.5 s + sim 1.2–1.3 s; **first data 5.1–6.4 s**; total 9.9–11.3 s (the spread is one-time JSON3/column-writer JIT; a warm worker does the whole run in milliseconds) |
| first run, warm process after `clear_compile_cache!` | **50–360 ms** (whole `simulate`, cache miss) |
| parameter-only re-run, after one warm-up re-run | **16–101 ms to first data** (target < 300 ms) |

The fresh-process total includes the first JSON3 manifest write and the first
`columns.f64` write; the worker's start-up warm-up should include one tiny `simulate`, which
removes that tail. The 300 ms target is measured after one warm-up re-run, exactly as the
NOTES section 8 requires.

---

# J1.6 — the worker protocol (verified 2026-10-22)

Everything below was probed on this machine (Julia 1.13.2) and is asserted by
`test/test_worker.jl` (138 tests) or measured through the real backend supervisor.

## APIs the worker relies on

* **JSON3 and the wire.** `JSON3.Object <: AbstractDict` is `true`, so `IR.parse_model` and
  the param helpers accept a decoded frame directly. `JSON3.write` accepts nested
  `NamedTuple`s, `Dict`s, `Symbol` values (as strings) and `nothing` (as `null`).
  **`JSON3.write` specialises on the concrete response-envelope type**: serialising a result
  alone is not enough. Before the workload serialised `(; id, result)`, the *first* wire
  answer of `model.check` paid **1.2–2.1 s** of codegen and a `block.check` **0.2–0.4 s**.
  Warm the envelope (`result_message`, `error_message`, `notification_message`) too.
* **The JSON3.Object input type.** `IR.parse_model(::JSON3.Object)` is a different method
  specialisation from `IR.parse_model(::Dict)`; the worker always gets the former, so the
  warm-up must parse `JSON3.read(JSON3.write(dict))`, not only the `Dict`.
* **Listening on a random port.** `server = Sockets.listen(ip"127.0.0.1", 0)` and
  `Sockets.getsockname(server)` returns `(ip"127.0.0.1", port::UInt16)`; the port is
  `Int(getsockname(server)[2])`. `Sockets.accept(server)` blocks until the worker connects.
* **`EOFError` has no message.** `EOFError("text")` is a `MethodError` on 1.13; use
  `throw(EOFError())`. This was a latent bug in the M0.4 `protocol.jl`, found by the
  truncation tests.
* **Concurrency.** With the backend's `--threads=2`, `Threads.@spawn` request handlers run
  alongside a run. Independently of the thread count, the run task yields by making its
  cancellation callback `() -> (yield(); flag[])`; `simulate` calls it before and after every
  `step!`, so a `block.check` is served while the loop is stepping even on one thread.
  Socket writes are serialised by one `ReentrantLock`, so frames never interleave.
* **`run.start` and REQ-1.** `simulate` writes its running manifest only when the run task
  starts, which is one task hop after the response. The worker therefore flattens the model
  in `run.start`, writes the same manifest itself (`BGSim._manifest` +
  `BGSim.write_manifest_atomic`, the same document shape as `open_recorder`), and only then
  answers `accepted`; the run task starts *after* the answer is on the wire (`Deferred`).
* **`Threads.Atomic{Bool}`** is the cancellation flag (`flag[] = true`); `simulate` already
  accepts `Threads.Atomic{Bool}`, `Base.RefValue{Bool}` or a predicate.
* **PrecompileTools.** Two `@setup_workload` blocks in one package are fine (the M0.3 one in
  `precompile.jl` and the worker one). The workload runs at precompile time with the
  interpreter disabled, so file reads (`Library.catalog`, `mktempdir`) execute normally and
  no result is retained except compiled code; `Library._CACHE` is serialised into the image,
  which is why the first `catalog.get` after start is ~8–12 ms.

## Measured (this machine, 2026-10-22)

| item | measured |
| --- | --- |
| worker cold start to `ready`, precompiled package | **19.5 / 23.0 s** in two fresh processes (median **21.2 s**); `using BGSim` dominates, the warm-up itself is ~3 s. A *first-ever* start also precompiles BGSim: **129.6 s** once. |
| `block.check` on a 40-line block, over the wire | **1.6 ms median** (1.5–2.0 ms warm), first call **60 ms**; target < 150 ms |
| `model.check` DC motor (37 signals) | first **305–371 ms**, warm **7–12 ms**; target < 1.5 s |
| `catalog.get` (36 blocks, 35 KiB JSON) | first **31–46 ms**, warm **6–12 ms** |
| `run.start` to `accepted` (RLC, 2000 points) | **53–59 ms**, manifest already `running` with 31 signals |
| first run of the RLC fixture in a fresh worker (cache miss) | **compile 2.3 s + sim 1.2 s**, well under the 10 s target |
| warm-up workload | **~3 s** in-process (catalog + block/model check + two RC runs, the second with a changed parameter) |



---

# J2.3 — events and nonsmooth (verified 2026-10-26)

* **`SymbolicContinuousCallback` takes the positive-edge affect positionally in MTK 11.45.5**:
  `SymbolicContinuousCallback(cond, affect; affect_neg = nothing)`. The signature is
  `(conditions, affect = nothing; affect_neg = affect, ...)`, so passing `affect = ...` as a
  keyword is silently ignored and `affect_neg` defaults to the positive affect. The earlier
  M0.3 note ("`affect` is the rising edge and `affect_neg` the falling edge, both default
  `nothing`") does not hold for this version: a rising-edge-only `@events` entry must pass
  the equations positionally **and** set `affect_neg = nothing`.
* The event affect equations use explicit `Pre(...)`; the `Pair` form is not used because its
  auto-wrap would also wrap the right-hand side of a sequentially substituted body. A
  `Vector{Equation}` (not `Vector{Any}`) is what the constructor recognises.
* `@events` is compiled to `Compile.FlatEvent` (condition normalised to the upward zero
  crossing, final `target => value` map); `Compile.event_callbacks(flat, ctx)` lowers it.
  Nonsmooth `ifelse`/`abs`/`sign`/`min`/`max`/`clamp`/`saturate`/`deadzone`/`floor`/`ceil`/
  `round` kinks become condition-only callbacks.
* Event instants are detected from the pairs of equal times in `Integrator.sol.t` (the MTK
  callbacks save left/right even with `save_everystep = false`). `simulate` records both
  through the `record_event(t, side, values)` seam; `side` is `:left` or `:right`.
* **W206** counts callback firings by wrapping the compiled affect with
  `remake(prob; callback = wrapped)` (an `init` callback kwarg is merged, not substituted)
  and calls `SciMLBase.terminate!` after `event_limit + 1` firings. The run ends with status
  `done`, stats.events = the count, and a W206 warning in the manifest. A condition-only
  callback counts every crossing; a one-directional `@events` callback counts only its
  non-empty edge (a falling zero crossing is still saved by the solver but is not a firing).
* The plan 9.2 ball reproduces 0.45152364098572856 s / 1.173961466562895 s and a 0.6399973 m
  peak; the relay switches at 1/12, 7/12, 13/12 s with a maximum error of 3.35e-13 s.

---

# FIX-M2-2 — discrete hardening (verified 2026-10-27)

* **The `@discrete` clock is folded per instance.** `parse.jl` folds `Ts`/`offset` once against
  the block's own `@constants` defaults, which is not enough for D13: an instance may override
  a structural constant. `Compile._collect_partition!` re-folds `ds.period`/`ds.offset`
  against `st.consts` (which `_bind_constants!` has already patched with the instance's
  `constants`), and `Ts` inside the generated body is that per-instance literal. So two
  instances of `UnitDelay` can run at 1 ms and 5 ms; the gcd base tick, the tick grid, E104
  (including an override that is not a whole nanosecond) and `previous` all use the instance
  value. Two *different* periods change `DiscretePartition.show`, hence `compile_key`.
* **`vec[k] = ...` on a declared Vec/Mat works inside `@discrete`.** The old code qualified the
  target with an empty locals dict, so a `for` loop variable was E003/E005. `_disc_assign!`
  now qualifies an indexed target through `_qualify_discrete_target`, which passes the walk's
  locals (loop variables, `Ts`, D18 temps); a local is never a declared name, so the base
  still resolves through `st.ids`. `hu[k] = ...` on a temporary keeps its own path.
* **Zero-state models.** A model with no continuous state (no `ddt`, no `int`) has nothing to
  integrate: every signal is an exact algebraic function of `t` and the parameters. MTK's
  compiled scalar condition writes its result into `tmp[1]` of the (empty) state cache and
  reads it back, so any continuous callback on such a model threw a `BoundsError` inside the
  first `step!`, which surfaced as `E901` with the useless hint "no states were available"
  (NOTE-4 gap 3). Decision: `lower_flat` **skips condition-only callbacks** for a stateless
  model (their only purpose is landing the integrator for state interpolation), so a
  `Step`-like `t`-dependent source runs exactly, with no extra event rows. An `@events`
  affect *changes a value* and cannot be dropped, so `simulate` refuses a stateless model that
  has one **up front** with `E901`: "«model» has no continuous state, so its `@events` affect
  cannot be solved" and the hint "the solver's event root finder needs at least one state; add
  a state (for example an Integrator) or use a `@discrete` clocked update". A model with one
  state keeps its callbacks unchanged (the J2.3 left/right event rows still appear).
* Regressions live in `test/test_discrete.jl` (the `FIX-M2-2` group): per-instance 1 ms/5 ms
  sequences identical to J2.2's, `previous` across two instance clocks (14/19/24/29), the E104
  override, `vec[k]`/`vec[1]` exact tick values (12/3/4, y = 19), the zero-state `Step`
  (21 exact rows, `stats.events == 0`) and the clear `@events` refusal.



---

# J-MB3 — Lie core (verified 2026-10-28)

`src/mech/` is the submodule `BGSim.Mech` (`mech.jl` includes `lie.jl`, `quat.jl`, `se2.jl`,
`se3.jl`; `BGSim.jl` includes it after the diagnostics and re-exports the numeric API).
Everything below was **run** on this machine; `test/test_mech.jl` asserts it (2078 assertions,
green).

## Conventions (frozen — do not re-litigate in later WPs)

* **Angular first** (D-MB2): a twist is `[ω; v]`, a wrench is `[m; f]`; planar `D = 3`
  `(ω, vx, vy)` / `(τ, fx, fy)`, spatial `D = 6`.
* The **linear part of a twist is the velocity of the frame origin**, not of the CoM and not
  of a joint point. The planar revolute screw is therefore `[1, r_y, -r_x]` (plan 3.1), the
  **unit-ω** convention; every screw constructor normalises its axis (`screw`,
  `revolute_screw`, `prismatic_screw`) and refuses a zero one, so a joint coordinate is always
  radians or metres and never silently scaled.
* `Ad(g)` maps a body twist to the base frame. A wrench is its **dual** and maps with
  `Ad(inv(g))'`, so `dot(W, V)` is frame invariant. In this library that is written
  `AdDual(g) * W`; `Ad(g) * W` (and any other matrix × `Wrench`) throws an `ArgumentError`
  instead of returning a plausible-but-wrong value. `ad(V)` is the Lie bracket and satisfies
  `ad(V) V = 0`; `dot(V, Wrench(transpose(ad(V)) * P.v)) == 0` is the Coriolis/gyrator power
  test (the wrench-space bracket applied through the explicit dual).
* A spatial **pose chart** (the shape used in the language and in the `bg_*` functions) is
  `Vec{7} = (q_w, q_x, q_y, q_z, p_x, p_y, p_z)`, i.e. quaternion + position (D-MB6). The
  **conversion** paths (`quat_from_rotation`, `chart`, `quat_log`) canonicalise the sign to
  `q_w >= 0`; the **algebra** (`compose`, `inv`, `normalise`, `quat_exp`, `quat_to_matrix`)
  does not — a product of two canonical quaternions may have `q_w < 0`, which is the same
  rotation. A planar pose chart is `Vec{3} = (θ, p_x, p_y)`; a planar twist is the same
  `Vec{3}`.
* An inertia is expressed about the **body origin**; `spatial_inertia(m, Ic, c)` takes `Ic`
  about the CoM and the CoM offset `c`, both in body coordinates, and builds
  `[[Ic + m ĉ ĉᵀ, m ĉ], [m ĉᵀ, m I]]`. `planar_inertia(m, J, c)` is its plane restriction
  (`diag(J, m, m)` at `c = 0`, the D-MB3 v1 case). Both **validate** symmetry and positive
  definiteness and throw an `ArgumentError` naming the failed property (E108); nothing is
  accepted silently. The symmetry tolerance is one constant, `Mech.INERTIA_RTOL = 1e-12`,
  used by the validator *and* the builder, so a matrix that is symmetric to rounding (1e-13)
  is accepted by both and a real asymmetry (1e-6) is rejected by both.
* `Twist{D}` / `Wrench{D}` are `AbstractVector` wrappers (not bare `SVector` aliases), so
  `exp`/`log`/`inv` extend Base only on our own types, `hat`/`Ad` dispatch on the screw type,
  and `V + W` is refused with an `ArgumentError` instead of Base's elementwise `+`.

## Frozen API (for J-MB4 .. J-MB15 and J-MB8)

`BGSim` re-exports: `Screw, Twist, Wrench, SE2, SE3, Quat, CoAdjoint, hat, vee, skew, Ad,
AdDual, ad, rotation, translation, spatial_inertia, planar_inertia, validate_inertia, screw,
revolute_screw, prismatic_screw, joint_basis, quat_exp, quat_log, quat_from_rotation,
quat_to_matrix, quat_rotate, normalise`.

| signature | meaning |
| --- | --- |
| `Twist{D}(xs::Vararg{Real,D})`, `Wrench{D}(xs…)` | construct from components (promoted); `Twist(v::AbstractVector)` takes `D` from the length |
| `SVector(t)`, `collect(t)`, `t.v` | the underlying `SVector` / a `Vector` |
| `hat(::Twist{3})::SMatrix{3,3}`, `hat(::Twist{6})::SMatrix{4,4}` | `se(2)` / `se(3)` matrix; `exp(hat(V))` is the homogeneous transform |
| `vee(::AbstractMatrix)::Twist{3/6}` | inverse of `hat` (3x3 → planar, 4x4 → spatial) |
| `skew(::SVector{3})::SMatrix{3,3}` | cross-product matrix |
| `Ad(::SE2)::SMatrix{3,3}`, `Ad(::SE3)::SMatrix{6,6}` | twist adjoint; `Ad(g1*g2) == Ad(g1)*Ad(g2)`; the planar one is the 6x6 restricted to indices `[3,4,5]` |
| `AdDual(g) -> CoAdjoint` | the wrench dual `Ad(inv(g))'`: `AdDual(g) * W` maps a wrench to the base frame; `Matrix(AdDual(g))` is the matrix; only a `Wrench` may be multiplied |
| `ad(::Twist{3})::SMatrix{3,3}`, `ad(::Twist{6})::SMatrix{6,6}` | Lie bracket matrix |
| `SE2()`, `SE2(θ[, x, y])`, `SE2(θ, p)` | planar pose |
| `SE3()`, `SE3(R, p)` (validated: orthonormal within `1e-8`, `det = +1`), `SE3(q::Quat, p)` | spatial pose |
| `compose(a, b)` / `a * b`, `inv(g)`, `rotation(g)`, `translation(g)` | group operations (`compose` is **not** exported by `BGSim`: ModelingToolkit re-exports `CompositionsBase.compose`; write `a * b` or `BGSim.Mech.compose`) |
| `exp(::Twist{3})::SE2`, `log(::SE2)::Twist{3}` | SE(2), small-angle series below `|θ| = 1e-2`, principal angle `(-π, π]` in `log` (so `θ ≈ 2π` round-trips) |
| `exp(::Twist{6})::SE3`, `log(::SE3)::Twist{6}` | SE(3), Rodrigues + left Jacobian, quaternion branch for `log` (accurate at and near `π`) |
| `Quat()`, `Quat(w, x, y, z)`, `Quat(w, v)`, `Quat(v)`, `compose`/`*`, `inv`, `normalise`, `exp`, `log` | quaternion algebra (scalar part first) |
| `quat_exp(::SVector{3})`, `quat_log(::Quat)::SVector{3}` | rotation-vector exp/log (principal branch) |
| `quat_to_matrix(q)` / `rotation(q)`, `quat_from_rotation(R)`, `quat_rotate(q, v)` | the D-MB6 pose state |
| `spatial_inertia(m, Ic[, c])`, `spatial_inertia(m, J::SVector{3}[, c])` | 6x6 inertia, validated |
| `planar_inertia(m, J[, c::SVector{2}])`, `planar_inertia(m, J, cx, cy)` | 3x3 inertia, validated |
| `validate_inertia(M; atol = 0, rtol = Mech.INERTIA_RTOL)` | symmetry + SPD check, returns `M`, throws a named `ArgumentError` |
| `inertia_entry(m, J, c, i, j)` | one entry of the diagonal-`J` 6x6 inertia, no validation (used by `bg_inertia3`) |
| `screw(axis, point, pitch = 0)`, `revolute_screw(axis, point)`, `revolute_screw(r::SVector{2})`, `prismatic_screw(axis)` | joint screws, origin-velocity convention, **axis normalised** and non-zero (else `ArgumentError`) |
| `joint_basis(Vs)::SMatrix{D,N}`, `joint_basis(S1, S2, …)` | the `Mat{D,N}` joint basis `S` (D-MB8) |
| `chart(::SE2/SE3)`, `pose(SE2/SE3, v)` | the `Vec{3}`/`Vec{7}` language chart and back (`BGSim.Mech` only) |

## Symbolics registration: the probe and what is differentiable

The equation layer splits the screw algebra in two, and the difference decides whether
`ODEProblem(...; jac = true)` works:

* **Expanded symbolically by `lower_mech`** (no opaque call, so `Symbolics.jacobian` sees
  plain arithmetic): `hat`, `vee`, `Ad`, `ad`, `compose`, `inv`, `rotation`, `translation`,
  `spatial_inertia`, `SE3`, and the **whole quaternion algebra** — product (16 products),
  conjugation, normalisation (`q/sqrt(|q|²)`), rotation matrix (9 quadratic quotients) and
  rotation of a vector. This is the D-MB6 pose path
  (`dq = 0.5 q ⊗ [0, ω]`, `dp = R(q) v`), which a symbolic Jacobian must differentiate.
* **Nine opaque registered functions** (`Symbolics.@register_symbolic`), only where the
  closed form has a branch that cannot be taken symbolically: `bg_exp2`, `bg_log2`,
  `bg_exp3`, `bg_log3` (SE(2)/SE(3) `exp`/`log`), `bg_quat_exp`, `bg_quat_log` (the
  rotation-vector pair), `bg_quat_from_rotation` (Shepperd's four branches) and
  `bg_inertia2`, `bg_inertia3` (the component inertia entries a native block calls).

Each takes the pose/twist/quaternion as **separate scalar components plus a 1-based
selector** (`k`, or a row/column pair) because the flat IR is scalar (`p.e[k]`, plan 5.3,
D-MB10).

Probe results (run, not guessed):

1. **An opaque call is usable in a `System` equation and stays unexpanded.** `mtkcompile`
   keeps one call per component (`observed: e1 ~ bg_exp2(w, 1.0, 0.5, 2)`), and the quoted
   literals (including the `Int` selector) survive: `arguments(...) == [w(t), 1.0, 0.5, 2]`.
2. **`Symbolics.derivative` of an opaque call does not error and does not expand**: it returns
   an unevaluated `Differential(w(t), 1)(bg_exp2(w(t), 0.0, 0.0, 1))` (a `Num`).
   `@register_derivative` **exists** in Symbolics 7.47 but is not needed: the M3 blocks never
   differentiate an `exp`/`log`/`from_rotation` symbolically (D-MB6 integrates the quaternion,
   not a pose through `exp`), and the quaternion algebra is expanded instead (below).
3. **The default solver path does not need a derivative rule.** A `System` with an opaque call
   in `D(w) ~ -k*bg_exp2(w, 1, 0, 2)` compiles with `mtkcompile`, and `Rodas5P()` and `FBDF()`
   both reach `retcode = Success`. `Rodas5P`'s Jacobian differentiates the *generated*
   right-hand side numerically: a recording wrapper saw **182 calls with `Float64` and 20 with
   `ForwardDiff.Dual{DiffEqBase.OrdinaryDiffEqTag, Float64}`**. Every `bg_*`/`Mech` method is
   therefore generic over `Real`, with branches on primal values and no `Float64` conversion
   (`spatial_inertia` validates with `isposdef`, which is why the equation path calls the
   unvalidated `inertia_entry`/`bg_inertia3` instead).
4. **`jac = true` needs the symbolic Jacobian, and that is why the quaternion algebra is
   expanded.** The review proved that an opaque `bg_quat_mul` in `dq = 0.5 q ⊗ [0, ω]` leaves
   a `Differential` term in the symbolic Jacobian and `ODEProblem(...; jac = true)` fails with
   `Float64(::Num)`. After the fix, a 7-chart pose system (`D(q[k]) ~ 0.5 (q ⊗ [0, ω])[k]`,
   `D(p[k]) ~ (R(q) v)[k]`) builds a problem with `prob.f.jac` set and solves with `Rodas5P`
   (`Success`); against the analytic solution for a constant z-rate **max |q − q_exact| =
   6.4e-16** and **max |p − p_exact| = 2.2e-13**. The symbolic Jacobian of the product and of
   the rotation matches a central finite difference of the numeric core to **2.2e-11** and
   **2.0e-10** (scale 0.3 and 1.7). An algebraic `Ad(g(q))` with the seven chart components as
   *states* compiles and solves with `jac = true` too, and its matrix contains no `bg_*` call.
5. **Index reduction is unaffected**: a DAE with `0 ~ y - bg_exp2(w, …)` plus `D(w) ~ -y`
   compiles and solves (`Success`).
6. **Still not supported (by design):** `jac = true` on a system whose equations contain one
   of the nine opaque functions (`exp`/`log`, the quaternion exp/log, `from_rotation`, the
   inertia entries): the symbolic Jacobian would keep a `Differential` and fail to compile.
   The production lowering (`src/lower/mtk.jl`) does not pass `jac = true`, and the default
   ForwardDiff Jacobian of the generated code is tested for `bg_exp2` and `bg_inertia3`
   (item 3). A block that needs the inertia on a `jac = true` path can use the
   `spatial_inertia` language function, which is expanded.

Regression ("registration" and "differentiability: jac = true on the D-MB6 pose path" in
`test/test_mech.jl`): `bg_exp2` in a state derivative and `bg_inertia3` in an observed
equation solved with `Rodas5P` (values equal the numeric core, rtol 1e-9); one entry of the
**lowered** `Ad(g)` matrix as a solved state function; the 7-chart quaternion/position
integration with `jac = true` against the analytic solution; the AD Jacobian of the product
and the rotation against a finite difference (rel 1e-6); and an algebraic `Ad(g(q))` with
`q` as states under `jac = true`.

## Language surface (whitelist) and one open interface point

`src/syntax/whitelist.jl` gains `MECH_FUNCTION_RULES` (18 rows, spec table "Function
additions", same `FunctionRule` style; `function_rule` consults it after the base table, and
`mech_function_rule(name)` is the mech-only lookup). The base `FUNCTION_RULES`/`FUNCTION_LOOKUP`
are **unchanged** (23 rows), so the M1 per-row tests and the web parity test keep their
meaning. `pose_of`/`jacobian` stay out (MULTIBOND_PLAN section 12). Lowering of every row is
implemented in `fnmap.jl` (`lower_mech`) and tested against the numeric core.

Two table facts for consumers:

* **`exp` and `log` are not rows of `MECH_FUNCTION_RULES`.** They keep their M1 rows
  (`lowering = :math`) and `lower_call` *shape-dispatches* them: a scalar argument is the
  ordinary exponential/logarithm, a `Vec` argument is the screw exponential/logarithm. A
  consumer that selects mech functions by `rule.lowering === :mech` (rather than calling
  `lower_call`) therefore misses them; J-MB4 goes through `lower_call`, which is correct.
* **The spec's `H1 * H2` composition syntax is not wired, deliberately.** `*` on two `Vec{3}`
  or `Vec{7}` charts is ordinary vector/scalar arithmetic (there is no pose value type in v1),
  so a `*` that silently meant composition would be ambiguous with scaling and matrix
  products. v1 spells pose composition out: `compose(g1, g2)` (the whitelisted function), or
  `BGSim.Mech.compose(g1, g2)` / `g1 * g2` on the *numeric* `SE2`/`SE3`/`Quat` types. Typed
  pose multiplication belongs to the deferred dependent-frame type system (D-MB5, spec v0.3);
  when that lands, `H1 * H2` can be that type's `*` without touching this lowering.

**Open for J-MB4/J-MB5 (not owned by J-MB3):** `_check_call!`'s tail in
`src/syntax/scopes.jl` rejects a `Vec`/`Mat` argument (`_numeric` is `Real`/`Int` only), so a
*block* that calls `Ad(g)` on a `Vec{3}` currently gets `E004`. The mech rows, their arities,
their lowering and their return shapes are in place; the expression-type rules (which shape a
row accepts and returns, and the indexing of a call result) belong to the WP that introduces
the pose-valued expressions. `lower_mech` already handles `Vec{3}`, `Vec{6}`, `Vec{7}` and
`Mat` arguments, including nested calls (`Ad(exp(T))`).

## Deviations / notes for the reviewer

* `LinearAlgebra` was added to `julia/BGSim/Project.toml` `[deps]`/`[compat]` (a **stdlib**, no
  new package): `isposdef`, `Symmetric`, `det` and `norm` are needed by the validation and the
  inertia builder. `Project.toml` is outside this WP's `Owns`; nothing else changed in it.
* `web/src/code/completion.ts` gained the 18 names so the W2.1 whitelist-parity test still
  holds (`FunctionRule([…])` rows are scraped from `whitelist.jl`).
* `compose` is intentionally **not** exported from `BGSim` (ModelingToolkit exports a different
  `compose`); use `g1 * g2` or `BGSim.Mech.compose`.
* Two M1 assertions that hard-coded `function_rule(:inv) === nothing` were changed to
  `:jacobian` (which is out of scope): `inv` is now a whitelisted pose function.
* **The spec's own names collide.** The LQGController block of plan 9.5 declares its discrete
  transition matrix as `Ad`, which is now a built-in (`Ad(H)`), and the checker refuses a
  declaration that shadows a built-in (E003). The golden fixture in
  `test/test_language.jl` therefore calls it `Phi` (the conventional name); the plan's 9.5
  text and the `examples/drivetrain-kalman` README description still say `Ad` and should be
  updated by the docs/contracts lane. `ad` (the Lie bracket) and `Ad` are both built-ins, so a
  model may not declare either name.

### Review round 1 (fixed in the same tree)

* **Differentiation.** The four quaternion component functions (`bg_quat_mul`,
  `bg_quat_normalise`, `bg_quat_to_matrix`, `bg_quat_rotate`) were removed; the lowering emits
  the algebra directly, so `jac = true` works on the D-MB6 pose path (numbers in "Measured").
  The nine opaque functions that remain, and the fact that `jac = true` is unsupported on a
  system that differentiates one of them, are stated above.
* **Wrench safety.** `Ad(g) * W` (and every other `StaticMatrix`/`Matrix`/`Diagonal` ×
  `Wrench`) throws an `ArgumentError` with a hint; the dual is `AdDual(g) * W`
  (`CoAdjoint`, exports `AdDual`, `CoAdjoint`). A wrench-space bracket is applied explicitly:
  `Wrench(transpose(ad(V)) * P.v)`.
* **`prismatic_screw` normalises its axis** and rejects a zero one (this is a value change:
  `prismatic_screw([2, 0, 0])` used to be `[0; 2, 0, 0]` and is now `[0; 1, 0, 0]`, which is
  the unit-ω/unit-displacement convention). `screw` also rejects a zero axis.
* **One inertia symmetry tolerance**: `Mech.INERTIA_RTOL = 1e-12`, used by both
  `validate_inertia` and `spatial_inertia` (a 1e-13 one-sided asymmetry is accepted by both,
  a 1e-6 one is rejected by both).
* **The finite-difference `ad` test** is now step-relative
  (`max |fd - ad| <= 1e-9 * max(1, |ad(V)|)`), ~1e3 above the measured 1.3e-12/3.6e-12 and
  tight enough that a 1e-6 error fails.
* **Docs**: the planar `Ad` comment names the correct restriction (`(ω_z, v_x, v_y)`, indices
  3/4/5, not "drop z"), and the quaternion canonicalisation (`q_w >= 0`) is scoped to
  `quat_from_rotation`/`chart`/`quat_log` — the algebra does not canonicalise.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| `Ad(g1 ∘ g2)` vs `Ad(g1) Ad(g2)`, 1000 random SE(3) pairs | **max rel 7.1e-16** (target 1e-9) |
| central difference of `Ad(exp(V t))` at `t = 0` (`h = 1e-6`) vs `ad(V)`, 200 twists | **planar max abs 1.3e-12, spatial 3.6e-12** (target 1e-6) |
| `exp(log(g))` random poses, 1000 each | **SE(2) 2.4e-15, SE(3) 2.6e-15** |
| `exp(log(g))` at a rotation angle of 0 … π (5 axes, 8 angles) | **max rel 1.5e-15** |
| `exp(log(g))` at an SE(2) angle of ±2π (6 angles × 3 positions) | **max rel 1.1e-16** |
| `log(exp(T)) - T` small twists, 1000 each | **planar 9.8e-15, spatial 3.2e-15** |
| quaternion norm drift over **1e5** random compositions | **2.35e-14** (target < 1e-12) |
| symbolic Jacobian of the quaternion product vs central difference (scale 0.3) | **2.2e-11** (target 1e-6) |
| symbolic Jacobian of `quat_to_matrix` vs central difference (scale 1.7) | **2.0e-10** (target 1e-6) |
| 7-chart pose system with `jac = true`, `Rodas5P` | `Success`; **max \|q − q_exact\| 6.4e-16**, **max \|p − p_exact\| 2.2e-13** |
| `test_mech.jl` | **2078 assertions, all pass, 36 s** |

**Full suite state at the time of writing:** another agent is landing C-MB1/J-MB1 in this
same working tree, so `test_library.jl` (and only that file) is red while the catalog
code catches up with the new contract. The last full `Pkg.test()` run reported **5140
passed / 246 failed / 10 errored**, and *every* failure and error is in
`test/test_library.jl` (`:211`, `:212`, `:1326`, `:1363`: the catalog schema now has
`dimension` and `portDecl.frame`, and the catalog fixture files changed, while
`src/library/` has not landed the matching fields). A failing top-level `@testset` throws, so
that run aborts before the later files. Nothing under `contracts/`, `src/library/` or
`src/compile/` is touched by this WP. A driver that uses `runtests.jl`'s header and skips only
`test_library.jl` runs the whole remaining chain — `test_syntax`, `test_units`,
`test_flatten`, `test_simulate`, `test_worker`, `test_language` (incl. the LQGController
golden block), **`test_mech` (2078)**, the M2 files, every `golden/*` group and
`test_causality` — **green (exit 0)**.

---

# J-MB4 - planar multibond slice (verified 2026-10-28)

New group `stdlib/multibond/` (13 blocks, catalog group **Multibond**, `dimension = 2`,
per-component units from the J-MB2 table): `IPlanar` (+ `Pm`, `wout` taps), `CoriolisPlanar`,
`SePlanar`, `SfPlanar`, `GroundPlanar`, `DePlanar`, `DfPlanar`, `TFAd`,
`FixedTransform2D`, `ScrewTF`, `ComposePose2D`, `GravityPlanar`, `Revolute2D`.
`test/test_multibond_slice.jl` (6365 assertions) and
`test/fixtures/multibond/pendulum.json` are the acceptance.

## Frozen conventions

* **Transforms.** With `Ad(g)` mapping a b-frame twist to the a frame, power continuity
  forces `a.f = -Ad(g) b.f` **and** `a.e = Ad(g)^-T b.e`. The C-MB1 hand-written fixture's
  `+Ad` pair is not power-continuous; the multibond blocks use the continuous pair.
* **ScrewTF.** `a.f = S b.f` with `S = [1, ry, -rx]` needs `b.e = -S^T a.e`.
* **Gravity.** The physical gravity wrench at the CoM is
  `W = [0, -sin(theta) m g0, -cos(theta) m g0]` in the body frame. A 1-junction sums
  efforts, so the port effort is `-W` (`[0, sin(theta) m g0, cos(theta) m g0]`).
* **Coriolis.** The block's port effort is `e = [f2 P3 - f3 P2, -f1 P3, f1 P2]` for its
  own port flow `f`. On a 1-junction the Coriolis bond flow is `-V_body`, so the inertia
  receives `+ad(V_body)^T P`: `dP/dt = ad(V)^T P + W`. The free-body test compares against
  an independent RK4 of that equation (errors **3.8e-14, 1.7e-14, 4.1e-15** relative for
  the reviewer's three P0 cases), and also checks the convention-independent invariants
  `m R(theta) [vx, vy]` and the CoM angular momentum (drift **8.0e-15 to 1.8e-13**).

## Compliant-pivot Revolute2D (Mode A, the shipped joint)

The joint has an exact rotation `q` and two compliant pivot translations `d`:

```
V_rel = child.f - Ad(g(q))^-1 parent.f,   g(q) = (q, rx, ry),  S = [1,0,0]
qdot = V_rel[1],  ddt(q) = qdot,  ddt(d) = V_rel[2:3] + qdot * [-d[2], d[1]]
fs = [0, kt d[1] + bt V_rel[2], kt d[2] + bt V_rel[3]]
tau = S^T child.e,  child.e = fs + S tau,  parent.e = -Ad(g)^-T child.e,  drive.e = -tau
```

`d` is a displacement in the rotating child frame, so the `qdot * [-d2, d1]` transport
term is included (the earlier omission made the spring rest position wander by
`(mg/kt) Δq`; at kt = 1e8 that was a ~1e-7 m effect). It is power-neutral because
`d . (z_hat x d) = 0`, so `fs . V_rel` and `1/2 kt |d|^2` stay exact. The **sign**
`fs = +kt d + bt V_rel` is correct under the `e.f`-into-the-element convention: it gives
the body the restoring force. `child.e = fs + S tau` and the energy budget are tested on
the produced run (port power = spring rate + damping, <= 1e-9).

The body is `IPlanar` (+ `CoriolisPlanar` + `GravityPlanar`) on a 1-junction. All storage
is integral; there is **no W201** in `model.check` or the run. `rx = ry = 0` (no pivot
offset). The body-frame orientation is chosen as `theta = pi/2` in `FixedTransform2D`
and in the `LocalPose2D` used for gravity: this is a **coordinate orientation** of the
link frame (the CoM position, period and energy are invariant), not a pivot offset. At
`theta = 0` the transform's two effort components decouple and the tearing leaves the
pivot x-force `Link/b.e[2]` as an unsolvable algebraic (the exact structural triage
variable); the 90-degree frame couples them and makes the equation set solvable without
changing the physics. The only algebraics are `qdot`, `fs`, `Vrel` and the algebraic
`q = q0 + int(qdot)`; the int state, `d` and `P` are the states. The block is index-0 for
this 90-degree mounting, but the tearing workaround is **not solved**: **FIX-MB-2** keeps
the dummy-derivative issue, and arbitrary mounting angles still fail `E901` with
`Link/b.e[2]` as the dummy derivative.

**Released-from-rest initial deflection.** `d` is initialised at the constant-acceleration
value `d = [-m g0 J/(J + m L^2) sin(q0)/kt, -m g0 cos(q0)/kt]` in the child frame: the
first term is the tangential reaction that goes with
`alpha = -m g0 L sin(q0)/(J + m L^2)`. The *held* static value
`[-m g0 sin(q0)/kt, -m g0 cos(q0)/kt]` applies a spurious tangential force `m g sin(q0)`
and excites the fast `sqrt(kt/m)` mode. At `q0 = 0.01`, `kt = 1e8`:
`d0 = [-3.9223657e-13, -9.8095095e-8]` m for the released-from-rest state. The energy
includes `1/2 kt |d|^2` and the actual CoM height `h = Compose/g[3] + sin(q) d1 +
cos(q) d2`. At `q0 = 0` the start is `[0, -m g0/kt] = [0, -9.81e-8]` m.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| Gate A pendulum period, 4 s / 4001 pts | **1.4187960318344 s** (also through the worker `run.start`) |
| raw physical `2pi sqrt((J+mL^2)/(m g L))` | 1.4187870257492 s (measured rel **6.4e-6**) |
| effective length `L_eff = L + m g0 cos(q0)/kt` | 0.5000000981 m; physical 1.4187871648139 s |
| amplitude-corrected `T0 (1 + q0^2/16)` | 1.4187960322337 s (measured rel **2.8e-10**, target 1e-5) |
| plan check `2pi sqrt(L/g)` | 1.4185033534429 s (measured rel **2.1e-4**, target 1e-3) |
| energy drift over 10 s (KE + PE_actual + 1/2 kt|d|^2) | **1.776e-15 J**, ratio **7.24e-12** of the swing 2.4525e-4 J (target 1e-6) |
| `max|q|` at `q0 = 0.01` / equilibrium `q0 = 0` | **0.01** / **0.0** |
| W201 `model.check` / run | **0 / 0** |
| run steps / sim time | **4072 steps, 0.44 s** (4 s); **10072 steps, 0.74 s** (10 s, 10001 pts, reltol 1e-9, abstol 1e-11, Rodas5P) |
| fast translational mode `sqrt(kt/m)` | **1e4 rad/s** (kt = 1e8 N/m) |
| Coriolis free-body error / world-momentum drift | **3.8e-14** / **8.0e-15** (worst 4.1e-15 / 1.8e-13) |
| joint + transform + Coriolis power identities on the run | <= 1e-9 relative at every sample |
| `test_multibond_slice.jl` | **6367 assertions, ~39 s, green** |
| full `Pkg.test()` | **green** |
| `uv run pytest backend/tests -q` / `-m julia` | **264 passed, 4 deselected** / **4 passed** |
| `web npm run typecheck` | clean |

**Out-of-owns edit:** `test/test_frames.jl` lines 415-421 asserted *every* catalog block
omits `dimension` and has null port frames - true before the first multibond group, false
now. The assertion was split: scalar blocks keep the old check; a block with a Planar/
Spatial port must carry `dimension` 2/3 and a nullable frame. Nothing was weakened
(scalar blocks still assert null frames and no dimension).

**Left for J-MB5/J-MB6:** `FixedTransform2D` hard-codes the frames `world`/`body` (a
2-link chain needs parameterised frame names in `JointTransform`), and `ScrewTF` is not
used in this slice. The rigid 1-DOF variant and its exactly-two-W201 behaviour belong to
J-MB6.

# J-MB2 review round 1 — component units, whole-field rule, labels (verified 2026-10-28)

The verification of J-MB2 found two unit holes and three quality issues; all are fixed in
`src/units/{dims,unitcheck}.jl`, `src/compile/{instantiate,domains}.jl`, `src/ir/flat.jl`
and the J-MB2 tests. `test_multibond_slice.jl` stays at **4327 assertions, green**, with the
same pendulum numbers (period 1.418795892 s, drift 4.00e-9, equilibrium 4.00e-7).

## The component-wise rule is enforced

* **A bare multibond field is E006.** `p.e`/`p.f` without an index (`p.e ~ [F,F,F]`,
  `p.e ~ p.f`, `p.f ~ scalar`) has no single unit, so `_build_env` records the whole-field
  key in `UnitEnv.multibond` and `_dims!(::Field)` reports E006 with the hint
  "write `p.e[k]` component-wise (D-MB10)". It is not a wildcard and never compares or
  silently skips. Scalar domains keep the whole-field meaning.
* **Component indices are folded.** `_index_value` folds the index with
  `eval_const_number` over the block's `@constants` plus `ctx.loops` (the `for` bindings),
  so `p.e[1+1]`, `p.e[N]` and `p.e[k+1]` inside a loop resolve to the right component.
  `p.e[1+1]` is a force and a torque variable equated to it is E006.
* **Out of range is E005, once.** The size check (`scopes.jl`) owns E005 and already covers
  a literal, a folded constant, a loop range wider than the port and a non-static index.
  The unit pass therefore returns a wildcard for an out-of-range component instead of
  duplicating E005 or mislabelling it as a whole-field E006.

## Port component labels

* A multibond port component carries the catalog spelling (`N*m`, `rad/s`) in
  `FlatVar.attrs[:unit_label]`; `Flat.signal_namedtuple` prefers it, so the manifest,
  `model.check.signals` and the editor show `N*m`/`rad/s` and `P = "W"`. Scalar ports,
  declarations and computed signals keep the canonical `unit_string` (`J`, `1/s`).
* `units.jl` asserts at load time that every label in `DOMAIN_UNIT_LABELS` and
  `DOMAIN_COMPONENT_LABELS` parses back to the `Dims` in the component tables, so the
  hand-maintained label and dimension tables cannot drift.
* Subsystem `effortUnits`/`flowUnits` are compared **by parsed `Dims`** per component, so
  `["J","N","N"]` is accepted for `N*m,N,N`; an unparseable entry, a wrong length or a
  component array on a scalar domain is E102.

## Contract fixtures pending C-MB1 (orchestrator-owned, not edited)

Whole-field multibond equations that must become component-wise:

* `contracts/fixtures/model/valid/model.planar.multibond.json:13` (`p.f ~ [0.0, 0.0, 0.0]`).
* `contracts/fixtures/model/valid/model.frame-bridge.json:13` (same line).
* `contracts/fixtures/model/valid/model.spatial.multibond.json:13` (six zeros) and
  `:41` (`a.f ~ Ad(...) * b.f`, `b.e ~ transpose(Ad(...)) * a.e`; `Ad` also awaits the
  pose-valued primitive).
* `contracts/fixtures/model/semantic/model.e006-unit-mismatch.json:13` (same Ground) and
  `model.e007-frame-mismatch.json` (same Ground; the E007 test patches it in memory until
  the fixture is updated).

`test_units_multibond.jl` pins the raw fixtures' pending E006; `test_frames.jl` uses the
`_unit_valid_fixture` in-memory rewrite (component-wise Ground) for its frame/domain
assertions, so the subject under test is reached. Both go away with the contract update.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| `test_units_multibond.jl` | **259 assertions, green** |
| `test_multibond_slice.jl` | **4327 assertions, green**; period 1.418795892 s, drift 4.00e-9, equilibrium 4.00e-7 (unchanged) |
| planar manifest units | `p.e[1]="N*m"`, `p.e[2]="N"`, `p.e[3]="N"`, `p.f[1]="rad/s"`, `p.f[2]="m/s"`, `p.f[3]="m/s"`, `p.P="W"` |
| spatial manifest units | `p.e[1..3]="N*m"`, `p.e[4..6]="N"`, `p.f[1..3]="rad/s"`, `p.f[4..6]="m/s"`, `p.P="W"`; `P = Σ e[k]f[k] = 91t` to 1e-9 |
---

# J-MB5 — full planar vector primitives (verified 2026-10-28)

The planar element set of the plan is complete. Ten blocks were added to
`stdlib/multibond/` beside the thirteen from J-MB4, so the group holds **23** blocks and the
catalog **149** (`test_library` derives the count from `M3_REFS`; nothing hard-codes it).
`test/test_planar_primitives.jl` (**124 481 assertions**) is the acceptance; it is included by
`runtests.jl`. The J-MB4 slice is unchanged: **6367** green, period 1.418796031834393 s,
energy drift 1.776e-15 J.

## The elements and the naming rule

`stdlib:multibond/XPlanar` **is** the planar `X` of the plan's element list (`C`, `R`, `MSe`,
`MSf`, `TF`, `GY`, `MTF`, `MGY`, `Se`, `Sf`, `De`, `Df`, `I`). The suffix is not decoration: a
block *name* may not repeat in the catalog, and `C`/`R`/`TF`/`GY`/`MSe`/`MSf`/`MTF`/`MGY`/`Se`/`Sf`/
`De`/`Df`/`I` already exist in `stdlib:bondgraph/`. `Gravity`, `Ground`, `De` and `Df` are
therefore **not** aliased either (`Ground` exists in `stdlib:electrical`, `De`/`Df` in
`stdlib:bondgraph`); the suffixed names `GravityPlanar`, `GroundPlanar`, `DePlanar`,
`DfPlanar` are the plan's elements. `ComposePose2D` is the plan's `ComposePose`;
`JointTransform2D` is its `JointTransform`.

## Frozen interface decisions

* **`CPlanar` stores three scalar states** (`qr`, `qx`, `qy`), not a `Vec{3}`. A vector
  declaration carries one `unit` for the whole array, but a planar capacitance holds an
  angular displacement (rad) beside two linear ones (m) (D-MB2/D-MB10). Parameters
  `kr`/`kx`/`ky` (N*m/rad, N/m, N/m) plus a zero-default rest deflection `qr0`/`qx0`/`qy0`.
  Preferred effort-out causality, exactly like the scalar `C`; `ddt(q[k]) = p.f[k]`,
  `p.e[k] = k[k]*(q[k] - q0[k])`.
* **`RPlanar`** is free causality (no declaration, like the scalar `R`), `p.e[k] = b[k]*p.f[k]`
  with `br` in N*m*s/rad and `bx`/`by` in N*s/m; its port power is `sum b f^2 >= 0`.
* **`MSePlanar`/`MSfPlanar`/`ExternalWrenchPlanar` take three scalar inputs** (`ur/ux/uy`,
  `vr/vx/vy`, `wr/wx/wy`) with their own units, because a `Vec` signal is unit-homogeneous in
  v1. `ExternalWrenchPlanar` is an effort source whose inputs are the **physical external
  wrench** `W_ext`: `p.e = -W_ext` (FIX-MB-4), so on a 1-junction the body feels `+W_ext`
  (`dP/dt = +W_ext`), the same sign algebra as `GravityPlanar` (whose port effort is
  `-W_gravity`). Before the fix the block used `p.e = w`, so a body on a 1-junction felt
  `-W_ext` and the input name was misleading.
* **`TFPlanar`/`MTFPlanar` are the diagonal variant** (`n::Vec{3}`, `u::Vec{3}`, both
  dimensionless): `a.f[k] = n[k]*b.f[k]`, `b.e[k] = -n[k]*a.e[k]`. The general matrix transformer
  is `TFPlanarMat`/`MTFPlanarMat` (FIX-MB-4), a `Mat{3,3}` `M` with `a.f = M*b.f` and
  `b.e = -M^T*a.e`: power-continuous for every `M` and needing **no inverse** (the earlier
  claim that the reverse direction needs an inverse transpose was wrong; the continuous pair
  is the forward flow / dual effort relation). The diagonal variant stays because its modulus
  is unit-homogeneous (dimensionless), so the per-component unit proof survives.
* **`GYPlanar`/`MGYPlanar` take a full `Mat{3,3}`** `G` (parameter / signal input):
  `a.e = G*b.f`, `b.e = -G^T*a.f` written component-wise, power-continuous for every `G`; the
  `G` is invertible-free (the block never inverts it). **Unit caveat:** a general planar
  gyrator matrix is *not* unit-homogeneous (its rotational/translational entries differ by a
  length), and a `Mat` declaration has one `unit` slot, so `G` is declared without a unit —
  the products are unit wildcards instead of a wrong unit (D-MB10 defers vector unit
  inference). The ports keep their own per-component units, and `TFPlanar`'s dimensionless
  `n` keeps the component-by-component unit proof alive through a transformer.
* **`JointTransform2D`** carries `TFAd`'s adjoint equations with the two frame roles
  `parent`/`child`, so a joint's parent-side and child-side ports bridge legally. v1
  limitation (D-MB5): a `frame` is a string literal, not a parameter, so a multi-joint chain
  cannot rename the two roles per instance; typed frame objects are deferred. `ScrewTF`
  remains the joint-coordinate TF for J-MB6.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| catalog | **149** blocks, `multibond` group **23**, every new block `block.check` 0/0, `dimension = 2`, balanced |
| `CPlanar` stored energy `|dE - int p.P|` | **1.99e-13 J** of 50.83 J |
| `RPlanar` `|p.P - sum b f^2|` | **0** of 0.6225 W |
| `TFPlanar` / `MTFPlanar` / `JointTransform2D` worst power residual | **1.1e-16 / 2.2e-16 / 2.0e-16** |
| `GYPlanar` power residual, 4 random full matrices | **8.5e-15** worst |
| `MGYPlanar` power residual | **2.1e-16** |
| `CoriolisPlanar` + `CPlanar` + `RPlanar` on one 1-junction vs an independent RK4 | P **4.5e-15**, q **1.2e-15** relative; energy loss = damper integral to 1e-9 |
| closed bond graph (source, I, C, R, TF, GY, sink; 8 001 points) | chain residuals <= **8.9e-16**, max `|junction power|` **8.9e-16 W**, ledger residual **7.7e-9 J** of 0.0375 J supplied |
| `test_planar_primitives.jl` | **124 481 assertions, green, ~1 m 39 s** |
| `test_multibond_slice.jl` | **6367 assertions, green**, same period/energy |
| full `Pkg.test()` | **green** (`library` 7335, J-MB4 6367, J-MB5 124 481) |
| `uv run pytest backend/tests -q` / `-m julia` | **269 passed, 4 deselected** + the pre-existing `test_decimate` perf gate (median 52.8 ms vs 50 ms on this loaded machine; **10/10 alone**) / **4 passed** |
| `web` `npm run typecheck` / `npm test -- --run` | clean / **433 passed (44 files)** |

**Out-of-owns edit (needed, flagged):** `src/library/catalog.jl` gained the ten
`BLOCK_METADATA` entries (description + icon). `test_library` asserts that the metadata table
covers *exactly* the stdlib refs and that every block has a non-empty description and icon, so
a new block cannot ship without an entry; the edit is data only (no code path changed).
Everything else is under `stdlib/multibond/`, the new test file, `runtests.jl` (one include),
`test_library.jl` (the `M3_REFS` list and the new blocks' interface fields) and this file.

# J-MB6 — planar bodies, joints and pose handling (verified 2026-10-28)

New group `stdlib/planar/` (**11 blocks**, catalog group **Planar mechanics**, catalog
**160**): `RigidBody2D`, `Free2D`, `FixedJoint2D`, `JointPose2D`, `LocalPose2D`,
`PoseIntegrator2D`, `Prismatic2D`, `Revolute2DCompliant`, `Revolute2DFriction`,
`Revolute2DLimit`, `Revolute2DRigid`. `test/test_planar_mechanics.jl` (**407 assertions**) and
`test/fixtures/planar/pendulum.json` are the acceptance. Every block `block.check` 0/0,
`dimension 2` on a Planar port, per-component units from the J-MB2 table.

## Textual composites can now declare a junction (language extension, flagged)

`@components` gains one entry shape: **`name = Junction(1)`** (or `Junction(0)`), lowering to
the same `IR.ModelNode(:junction)` a model-JSON diagram uses. `ComponentDecl` keeps its shape
(`block = :Junction`, one `:kind` literal; `component_is_junction`/
`component_junction_kind`). Touched: `src/syntax/{parse,ast,scopes}.jl`,
`src/compile/instantiate.jl`. Without it a composite cannot contain the 1-junction of the
plan 5.2 body or the 0-junction of the plan 5.2 joint, so this is the "composite 0-junction +
TF" FIX-MB-2 option and the 5.2 acceptance made expressible. A **junction face** is
supported too: the composite's power port may *be* the junction (`connect(p, node)`), which is
how one body port carries the 1-junction; the exterior bond then joins the junction's bond
list exactly like `port: "junction"` in the model JSON (`_bind_boundary!` accepts
`kind :junction`, `domains.jl` seeds the island with the face's declared domain).

## Composite instances can set an internal start (flagged)

`node.starts` of a composite instance address the owning component as
`"<component>/<variable>"` (`"inertia/P"`, nested `"body/inertia/P"`): `_composite_starts`
splits them and `_composite_diagram!` forwards them to the synthetic component nodes. A rigid
body's initial momentum has no other spelling. Unknown component names are E003.

## Lowering: a start value is found through the alias chain (flagged)

`src/lower/mtk.jl` `_u0_pairs` now follows the compiled pure aliases (`u ~ v` in `observed`,
BFS) to the flat variable that carries the start. MTK aliases `IPlanar/Pm -> CoriolisPlanar/P`
(and, for a rigid joint, the momentum to the twist), so the state it keeps is *not* the
variable the start was written on; before this the free body started at rest no matter what
was set. Regressions: `Free2D` screw motion, the `DCMotor` composite's rotor start.

## FIX-MB-2 — the composite joint runs at any mounting angle

Root cause (measured, not guessed): `FixedTransform2D` writes `a.e = Ad^-T b.e` *implicitly*;
MTK's alias elimination solved one row for `b.e[3]` by dividing by `sin(theta)` and left
`b.e[2]` as a tearing variable, so the J-MB4 slice only ran near +-pi/2. The new
`FixedJoint2D`/`TFAd` effort relation is written in the chain's causal direction
(`b.e = Ad(g)^T a.e`, no division for any angle).

Measured on `test_planar_mechanics.jl` (composite body + `FixedJoint2D`):

| theta | period (s) | compiled unknowns | dummy derivatives | steps (4 s) |
| --- | --- | --- | --- | --- |
| 0.0 | 1.4187960322911772 | 6 | 0 | 4049 |
| 0.3 | 1.4187960322911777 | 6 | 0 | 4035 |
| pi/2 | 1.4187960322911790 | 6 | 0 | 4037 |

The three periods agree to **1.3e-15** relative; the state count is **6** (`P[1:3]`, `d[1:2]`,
`q`), there is **no** `Link/b.e[2]`-style tearing variable and **no W201** in `model.check`,
the compiled warnings or the run. `TFAd` keeps the same relation in the same explicit form;
`FixedTransform2D` is **unchanged** (it is the J-MB4 slice's block, and the slice stays
bit-identical), so the slice fixture still uses its 90-degree coordinate choice — that
workaround is now unnecessary for any model built from the planar group.

**Deviation:** the rigid variant is a composite of the plan 5.2 graph (0-junction + `TFAd` +
`ScrewTF` + 1-junction + `Df` + `Integrator`), and MTK's index reduction parametrises the body
by its twist, so it reports **3 momentum W201** (`Body/inertia/P[1..3]`, all aliases of the
twist state) instead of 2, plus three dummy derivatives, of which **two** are the joint-frame
velocity components `xform/b.f[2]`, `xform/b.f[3]` (the third is the body's zero-power Df bond) — the two constrained pivot translations, which is
the physical two-constraint signature the test asserts. The run fails with **E103
"initial conditions are inconsistent"** (the documented DEC-MB-2 limit: a 3-DOF body on a rigid
1-DOF revolute is index-3). A native rigid formulation was measured too and also gives 3
momentum W201, so this is MTK's choice, not the composite's.

## Why the compliant pivot is still native, and where the taps live

A compliant-pivot revolute is **not** a junction tree: its child effort is a *sum*
(child.e = fs + S*tau) while its child flow is also a sum (child.f = Ad^-1 parent.f + Vrel),
so no 0- or 1-junction expresses it. The rigid joint (a 0-junction with the common wrench) is a
composite; the compliant base joint stays the J-MB4 native stdlib:multibond/Revolute2D, and
the three variants (Revolute2DCompliant, Revolute2DFriction, Revolute2DLimit) are native
too because each adds a torque to the drive/link effort chain. Recorded as the WP allows
("if the signal wiring cannot express it, keep a native block and record why").

Signal paths a controller reads (all recorded): Joint/qout, Joint/qdout, Joint/pose[k],
Joint/dout[k], Joint/Vrelout[k], Joint/tauout (compliant/friction/limit);
Body/inertia/P[k] (momentum), Body/inertia/p.f[k] and Body/flow/y[k] (twist),
Body/gravity/g[k] (the composed pose), Body/inertia/p.P (port power), plus the composite
output faces Body/P, Body/V, Body/g. A composite power port that *is* a junction (the
body's own port) has no <path>/<port>.e[k] signal of its own: the flat ids are the junction's
bond ids, and the internal per-component signals above are the stable names.
## Solver note for phase B models

The compliant pivot with the explicit transforms is an **index-0 ODE**, so `solver: "auto"`
now picks `Tsit5` and grinds on the 1e4 rad/s pivot mode (986 k steps, `E901` MaxIters). The
planar fixtures and tests set **`solver: "Rodas5P"`** (plan 5.5: "use Rodas5P/FBDF and a
stiffness chosen by the model"). An `auto` that inspects the fastest eigenvalue would be a
solver-heuristic change outside this WP.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| pendulum period (composite body/joint) | **1.4187960322912 s** vs amplitude-corrected physical **1.4187960322337 s** (rel **4.1e-11**) and `2π√(L/g)` 1.4185033534 (rel 2.1e-4) |
| energy drift over 10 s | **1.776e-15 J** = **7.24e-12** of the 2.4525e-4 J swing; the `1/2 kt |d|^2` term is now load-bearing (q0 = 1, kt = 1e6: 1.79e-13 with it, **7.24e-5** without) |
| `kt` sweep 1e6 / 1e7 / 1e8 | periods 1.41880980 / 1.41879728 / 1.41879603 s; rel error vs the rigid period **9.71e-6 / 8.82e-7 / 4.05e-11** (decreasing) |
| compliant `k` sweep 25/100/400 (locked actuator) | settles at `qrest + tau/k` = 0.180/0.120/0.105 rad (tau = 2, qrest = 0.1), `qdot -> 0`; torsional period matches `2π√(Jp/k)` to 2e-3 |
| friction | monotone spin-up to the analytic terminal rate 15.0 rad/s (t = 20 s, 8 time constants), `tau_f*qdot <= 0`; stick creep `v_eps*atanh(tau/Fc)` = 4.4e-4 rad/s |
| limit | one-sided stop settles at `upper + tau/kL` = 0.0400 rad, stop torque 2.0 N*m, no W206 |
| prismatic | mass 2 kg, k = 200 N/m: period **0.62832 s** = `2π√(m/k)`, pose = (0, q, 0), perpendicular/rotational deflections < 1e-8 |
| free body (pure rotation / pure translation) | exact screw motion, max pose error **4.3e-14 / 3.7e-14**; general case: CoM straight-line error **3.4e-15**, world momentum drift 2.8e-14 |
| fixed-base composed vs integrated pose | max diff <= **1.0e-6** over 4 s (CoM pose, `ComposePose2D`) |
| joint/transform/junction power identities on the run | <= 1e-9 relative at every sample |
| `test_planar_mechanics.jl` | **407 assertions, ~60 s, green** |
| `test_multibond_slice.jl` | **6367**, unchanged numbers |
| `test_library.jl` | **8178** (catalog 160 blocks) |

# FIX-MB-4 - Phase B review fixes (verified 2026-10-28)

The review of J-MB5/J-MB6 left eight findings. The physics that J-MB5/J-MB6 measured is
unchanged: the J-MB4 slice is **6367** assertions with period 1.418796031834393 s and the same
1.776e-15 J drift, and the J-MB6 pendulum is 1.4187960322911772 s with ratio 7.24e-12.

## 1. Matrix transformer (`TFPlanarMat` / `MTFPlanarMat`)

The plan requires a matrix TF. The earlier note ("a general matrix transformer needs the
inverse transpose, so it is not offered") was wrong: with `a.f = M b.f` and `b.e = -M^T a.e`
the power `a.e . a.f + b.e . b.f = (M^T a.e)^T b.f - (M^T a.e)^T b.f = 0` identically, for
every `M`, and no inverse is ever written. The two new blocks are the constant `Mat{3,3}`
parameter and the `Mat{3,3}` signal input; the equations are component-wise
(`a.f[k] = sum_j M[k,j] b.f[j]`, `b.e[k] = -sum_j M[j,k] a.e[j]`). The diagonal `TFPlanar` /
`MTFPlanar` stay: their dimensionless `Vec{3}` modulus keeps the per-component unit proof
alive, while a general `M` is not unit-homogeneous and is declared without a unit (exactly
like `GYPlanar`; one `Mat` has one unit slot, D-MB10).

Measured: random `M`, `V`, `W` give worst power residual **2.2e-16** (4 random matrices per
block), and the constitutive relations match to 1e-12. A **frame-neutral adjoint**
(`TFAdNeutral`, the `TFAd` equations with both ports null) was added for the rigid joint: see
2. Catalog **163** blocks (160 + the two matrix TFs + the neutral adjoint); `test_library`
**8311** (M3_REFS carries all three).

## 2. `Revolute2DRigid` parent frame

The composite's `parent` port is frame-neutral now, but that alone is not enough: the internal
adjoint was `TFAd`, whose `a` side declares `world`, and the frame union-find adopts it through
the joint's own 0-junction. `TFAdNeutral` leaves both sides null, so the parent group stays
neutral and one instance attaches to `GroundPlanar` (world) **and** to a link-1 body
1-junction as an elbow. Measured on the 2-link chain: no `E007`; the rigid rig is a DAE
(15 compiled unknowns, 4 differential; model.check W201 2, post-compile W201 6, run fails
`E901` at t = 0 as DEC-MB-2 documents).

## 3. `FixedJoint2D` lever arm: the finding is the port orientation, not `x != 0`

Probe result (run, not guessed): the block is written in the **joint -> fixed -> body** causal
direction (`parent.f` from `child.f`, `child.e` from `parent.e`). In that direction, which is
what the X-MB2 arm uses (`Link1`/`Link2` have `x = 0.2` with their **child** on the body
1-junction), the model is an index-0 ODE: the 2-link arm chain compiles to **12 unknowns /
12 differential**, no W201, and the tip pose equals the analytic FK to **2.2e-16 m**.

If the fixed joint is instead used as a **frame extension** off a body 1-junction
(`Lever.parent` on the body junction, `Lever.child -> Elbow.parent`), the compiled model has
**14 unknowns / 12 differential and exactly two algebraic tearing unknowns**,
`Elbow/parent.f[2]` and `Lever/parent.e[2]`. This is *not* an `x != 0` effect: the same 14/12
signature appears with `x = y = 0` and with a `y`-only lever. It is the reverse causal pairing,
which needs the inverse pairing (`child.f` from `parent.f`) and cannot be written in the same
block without a second orientation. Under the current compiler (post-FIX-MB-2 sources plus
FIX-M2-1 algebraic guesses) those two algebraics **do initialise and the run completes**, but
the model is a DAE rather than the 12-state ODE. The supported spellings are therefore: the
fixed joint with its child on the body junction (the X-MB2 arm), or the joint's own `rx/ry`
pivot offset (the `rx` route, 12/12). The test
`FIX-MB-4: FixedJoint2D lever arm and the reverse-causality limit` asserts both the supported
12/12 chain and the 14/12 + two-algebraic reverse signature, so J-MB7/J-MB10 know exactly
what to expect and do not "fix" it by accident.

## 4. The rigid acceptance set (DEC-MB-2's "exactly two")

"Exactly two W201" is not reachable without changing the verified body. Measured on the single
rigid pendulum: **3 momentum W201** (`Body/inertia/P[1..3]`, all MTK aliases of the twist
state it parametrises), **3 dummy derivatives** - the two physical pivot translations
(`Joint/xform/b.f[2]`, `Joint/xform/b.f[3]`) and the first component of the body twist tap
(`Body/flow/p.f[1]`) - and **2 differential** unknowns; the run fails `E103`. The `DfPlanar`
tap lives inside `RigidBody2D`, which this WP does not own, so the acceptance is:

> the two joint-frame translations are derivative-causal; MTK reports them plus the body
> momentum aliases (and the body twist tap), not literally two.

**The `Df` tap is not the cause (probed, FIX-MB-4 follow-up).** A `RigidBody2DRigid` variant
(`1-junction + I + Coriolis + Gravity`, no `DfPlanar`, no `V` output) was built and measured
on the same models: the three momentum W201 remain, the third dummy simply moves from
`Body/flow/p.f[1]` to `Body/coriolis/p.f[1]`, and the single-body model loses its algebraic
guess (NaN u0 before the `E103`). Reason: `IPlanar` defines `p.f = P/M`, so MTK eliminates the
momentum in favour of the twist whichever zero-power bond reads it; the aliases are the
parametrisation of the 3-DOF body by its twist, not an artefact of the tap. The variant was
reverted (it is a worse model), so the acceptance stays the measured set.

The 2-link rigid chain: 15 unknowns / 4 differential, model.check W201 2, post-compile W201 6
(3 per inertia), run `E901`. Both sets are asserted in `test_planar_mechanics.jl`.

## 5. `ExternalWrenchPlanar` input is the physical wrench

`p.e = -w` now (was `p.e = w`), so the three inputs `wr/wx/wy` are the physical external
wrench `W_ext` and a body on a 1-junction feels `+W_ext` (`dP/dt = +W_ext`); the element
supplies `-W_ext` to the junction, like `GravityPlanar`. Test: `E/p.e = -w`, `D/y = -w`,
and a free inertia's momentum is `P0 + w t` (was `P0 - w t`).

## 6. Composite starts

A composite start key that does not address a component is **E003** with the hint
`use `<component>/<variable>``: a bare key (`"P"` on `RigidBody2D`), a junction component
(`"node/x"`) and an unknown component all report it on the instance path and name the
composite and the key. The correct `"inertia/P"` still works (the free-body test relies on
it). `src/compile/instantiate.jl` `_composite_diagram!`, tests in
`test_planar_mechanics.jl` (`FIX-MB-4: composite starts ... (E003)`).

## 7. Recorded, not changed

* **`Mat` parameter serialization (for C-MB2/W-MB3).** `GYPlanar`'s `G::Mat{3,3}` and the new
  `TFPlanarMat`/`MTFPlanarMat` matrices serialize through `block_interface` as `type: "Real"`
  with the matrix text in `default` and **no size**: the contract's `parameterDecl` has no
  `size` field (only `blockInterface` declarations have one). The editor therefore sees
  `Real`. A contract change (add `parameterDecl.size`, regenerate pydantic/TS, teach the
  inspector) is a separate WP; nothing in the equation path is affected.
* **Native vs composite joint deviation.** The rigid revolute is a composite of the plan 5.2
  graph; the compliant-pivot joint (and its friction/limit/torsional variants) stays **native**
  because its child effort and flow are both *sums* (`child.e = fs + S*tau`,
  `child.f = Ad^-1 parent.f + Vrel`), which no 0/1-junction tree expresses. The native path is
  the documented deviation, not a missing composite.
* **Compliance coordinate convention.** `Revolute2DCompliant` implements the **link-side**
  coordinate: `q` is the link angle (the pose composed from `q` is the geometric link pose),
  and the torsional spring acts on `q - qrest`; the plan's actuator-side `q - delta` (a `C`
  state between actuator and link) is **not** implemented because the drive port is a
  torque/rate port, not a second coordinate. Locked-actuator tests settle at `qrest + tau/k`
  as the link-side reading predicts.

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| matrix TF power residual (random `M`, 4 cases per block) | **2.22e-16** worst |
| time-varying MGYPlanar power residual | **4.20e-16** |
| time-varying TFAd: power residual / momentum vs independent RK4 | **1.54e-16 / 3.55e-16** |
| 2-link compliant chain | **12 unknowns / 12 differential**, no W201, tip vs analytic FK **2.22e-16 m** |
| rigid 2-link chain | 15 unknowns / 4 differential; W201 2 (model.check) + 6 (post-compile); run `E901` |
| FixedJoint2D reverse orientation | 14 unknowns / 12 differential; algebraic `Elbow/parent.f[2]`, `Lever/parent.e[2]`; run done |
| single rigid pendulum dummy set | `Joint/xform/b.f[2]`, `[3]`, `Body/flow/p.f[1]` (3), differential 2 |
| prismatic phi = 0.7 / pi/2 | period **0.6283185298 s** vs analytic 0.6283185307 (1.4e-9 rel) |
| joint rx/ry offset | period 1.4187960322911772 s (4.05e-11 rel), pose offset exact |
| `test_planar_primitives.jl` | **124 728** assertions |
| `test_planar_mechanics.jl` | **546** assertions |
| `test_library.jl` | **8311** (catalog 163) |
| `test_multibond_slice.jl` | **6367**, unchanged period/energy |

# J-MB7 — the planar mechanics suite (Gate B, verified 2026-10-28)

`test/test_mech_planar.jl` (**259 assertions**) closes Phase B. It drives every model through
the real pipeline (`parse_model -> flatten -> simulate`, Rodas5P, reltol 1e-9, abstol 1e-11)
and shares the golden helpers module. No golden fixture was needed: every reference here is
analytic or an independent integrator, so there is nothing to re-baseline when a number
improves.

## The double pendulum's independent reference

The two-link reference is the standard Lagrangian written by hand in the test (mass matrix
`M(q2)`, `C(q,qdot)qdot` with `h = m2 l1 r2 sin q2`, `grad V` for gravity along -y), integrated
with a classical RK4 at `dt = 1e-5` and checked against `dt = 5e-6` (**5.16e-13** maximum state
difference, so the reference is converged far below the model errors it measures). The model's
chain is the J-MB6 `Ground -> J1 -> L1 -> (B1 + J2) -> L2 -> B2` topology: uniform rods
`l = 0.4 m`, `r = 0.2 m`, `J = m l^2/12`, masses 2.0/1.5 kg, gravity 9.81, release from rest at
`q1 = -pi/2 + 0.4`, `q2 = 0.6`, with the elbow at `rx = 0.2` in link 1's CoM frame (the supported
route). The pivot deflections are initialised at the released-from-rest force of the reference
(`d = -F/kt`, with `F` the force the rigid reference needs at t = 0; the FIX-MB-3 lesson
generalised to a chain), so the stiff pivot mode is not excited by the release.

| kt (N/m) | trajectory error vs the RK4 reference (rad) | error at t = 1 s | energy drift / swing |
| --- | --- | --- | --- |
| 1e6 | **6.124e-4** | 2.895e-4 | 1.9e-12 |
| 1e7 | **6.119e-5** | 2.896e-5 | 2.2e-12 |
| 1e8 | **6.119e-6** | 2.896e-6 | 2.0e-12 |
| 1e9 | **6.119e-7** | 2.897e-7 | 9.3e-12 |

The error is **O(1/kt)**: the measured per-decade ratios are **10.008** (trajectory) and
**10.001** (at t = 1 s). The test asserts strict decrease, both ratios inside [8, 12], and
`<= 1e-5` at 1e8; the extra 1e9 run reaches the plan's 1e-6 integrated tolerance (6.119e-7) at a
13 015-step run. `t = 1 s` is an output grid point; the reference and the run share it exactly.

## The joint's `d` transport uses the child's absolute rate (kinematics fix)

The energy check exposed a real kinematics bug in the compliant joints, not a bookkeeping
term: `d` lives in the rotating child frame, so its coordinate rate must carry the child's
**absolute** angular rate `child.f[1]`, not the relative joint rate `qdot`. With a rotating
parent (the second link) `child.f[1] = parent.f[1] + qdot`, and `V_rel[2:3]` already contains
the lever term, so the relative rate integrated the wrong displacement. Fixed in
`Revolute2D`/`Revolute2DCompliant`/`Revolute2DFriction`/`Revolute2DLimit` as

    ddt(d[1]) ~ Vrel[2] + child.f[1] * d[2]
    ddt(d[2]) ~ Vrel[3] - child.f[1] * d[1]

The power identity is unchanged (`d·(ẑ×d) = 0`). A single-pendulum test cannot see the bug
(`parent.f[1] = 0` there); the double-pendulum energy check is its regression: the
deflection-corrected budget (`KE + m g y(nominal + R d) + 1/2 kt |d|^2`, deflections propagated
through the chain) went from **2.1e-5** of the swing at kt = 1e6 to **1.9e-12**, and it is now
independent of kt (4.0e-12, 4.8e-12, 4.2e-12, 2.0e-11 at kt = 1e6..1e9), i.e. solver level.
`test_multibond_slice` (6367) and `test_planar_mechanics` (546) are unchanged and green.

Notes for the reviewer: (a) the *damped* pivot (`bt > 0`) force is not parallel to `δ`, so the
nominal-adjoint lever adds a second O(δ) term; every model here has `bt = 0`, so it is
negligible and not "fixed" in this suite.

## `Prismatic2D`'s axial rate carries the parent-rotation transport term

The review of the planar set found the same class of bug as the revolute transport fix, in the
prismatic joint. The nominal child frame is at `q*n`; the actual child origin is at
`q*n + d*m`, so `n · V_rel` contains the lever velocity `-omega_parent*d` from the
perpendicular deflection. The axial rate is therefore

    qdot ~ cos(phi)*V_rel[2] + sin(phi)*V_rel[3] + parent.f[1]*d

Without the last term `q` drifts at `-omega_parent*d` whenever the parent rotates and `d` is
non-zero even though no axial force acts. The new kinematic regression prescribes the parent
and child twists with `SfPlanar` (`parent = (omega,0,0)`, child co-rotating at the offset:
`(omega, -omega*d, 0)`), sets `d = 1e-3` and `kd = 0`, and asserts `max|q| = max|qdot| = 0`
exactly; the pre-fix equation gives `qdot = -2e-3 m/s`. `Prismatic2D`'s `dr` is still a scalar
body-fixed component and the nominal adjoint still ignores it, which is a documented
first-order approximation (exact for `kr -> Inf` and for the static cases the suite runs).

## Measured (this machine, 2026-10-28)

| item | measured |
| --- | --- |
| single pendulum period (composite body + compliant joint) | **1.4187960322912 s** vs amplitude-corrected physical 1.4187960322337 (rel **4.05e-11**) and `2π√(L/g)` 1.4185033534 (rel 2.1e-4) |
| single pendulum energy over 10 s | **1.78e-15 J = 7.24e-12** of the 2.4525e-4 J swing; peak rate 0.04428542 rad/s vs analytic 0.04428543 |
| double pendulum kt sweep | **6.124e-4 / 6.119e-5 / 6.119e-6 / 6.119e-7 rad**, per-decade ratios **10.008 / 10.001 / 10.000**; 12 states, 12 differential, no dummy derivative |
| double pendulum energy | **1.9e-12 / 2.2e-12 / 2.0e-12 / 9.3e-12** of the swing at kt = 1e6..1e9, all inside the 1e-6 plan tolerance |
| prismatic | period **0.6283185298 s** vs analytic 0.6283185307 (1.4e-9); damped + loaded period 0.6314801 vs 0.6314839 (6.0e-6); `q_ss = -0.1000000002` vs `-F/k = -0.1`; drive `Translation`, `e` N, `f` m/s, no E006 |
| prismatic on a rotating parent | prescribed twists `(2,0,0)` / `(2,-2e-3,0)`, `d = 1e-3`: **max \|q\| = 0, max \|qdot\| = 0** with the transport term (pre-fix `qdot = -2e-3 m/s`) |
| free body over 10 s | exact SE(2) screw error **1.42e-12** (rotation) / **2.03e-13** (translation); general case theta 1.4e-12, CoM 1.3e-12; world momentum drift px 1.2e-13, py 8.2e-13, H 1.86e-12 |
| applied wrench | force case `P(t) = W t` to 1e-9, pose to 4e-14; torque case `alpha = 4` exactly, theta(2) = 8.3 |
| friction | viscous decay `5 -> 0.09172475` vs analytic 0.09172478 (2.5e-7 rel), monotone, `-tau_f w <= 0`; stick creep 1.0986e-3 rad/s = `v_eps atanh(0.4/0.5)`; slide 1.2007 rad/s at 3 s |
| limits | inside `|tau| = 0` exactly; `tau = kL(q-lower)` outside to 2 %; stop range -9.74..0.011 N*m; elastic rebound to 0.59999995 rad; no W206 |
| W201 | **0** in `model.check` and **0** in the run for 9 compliant models; rigid variant: 1 model-check W201, 3 post-compile (all `Body/inertia/P[1..3]`), dummies `Joint/xform/b.f[2]`, `[3]`, `Body/flow/p.f[1]`, run E103/E901 |
| fixed-base pose vs integrated truth over 10 s | **9.22e-8** max (theta 1.7e-15, x 9.2e-8, y 6.6e-8); gravity reads the composed pose exactly (and the integrated pose in `Free2D`) |
| `test_mech_planar.jl` | **259 assertions, ~56 s, green** |

# J-MB8 — spatial vector primitives and pose integration (verified 2026-10-29)

The spatial element set is in `stdlib/multibond/` beside the planar one, group **Multibond**,
catalog **184** blocks (**20** new): `ISpatial`, `CoriolisSpatial`, `CSpatial`, `RSpatial`,
`SeSpatial`, `SfSpatial`, `TFSpatial` (diagonal `Vec{6}`), `TFSpatialMat` (6x6), `GYSpatial`
(6x6), `MTFSpatial` (diagonal signal), `MGYSpatial` (6x6 signal), `GravitySpatial`,
`GroundSpatial`, `ExternalWrenchSpatial`, `FixedTransform3D`, `FixedTransform3DNeutral`,
`JointTransform3D`, `ComposePose3D`, `DeSpatial`, `DfSpatial`, `PoseIntegrator3D`.
`test/test_spatial_slice.jl` (**901 assertions**) is the acceptance; every model runs through
`IR.parse_model -> Compile.flatten -> simulate` (Rodas5P, reltol 1e-9, abstol 1e-11).

## Conventions and the frozen interface

* Angular first (D-MB2): twist `[w; v]`, wrench `[m; f]`, D = 6. The pose chart is
  `Vec{7} = (q_w, q_x, q_y, q_z, p_x, p_y, p_z)` (quaternion first, then the body origin in the
  world, D-MB6). `ISpatial` carries a diagonal principal `J::Vec{3}` (kg*m^2) and `m`; the
  momentum `P::Vec{6}` has **no** single unit and every component is written on its own
  (D-MB10). `m` has `min = 1e-12`; `J[k] > 0` is documented (positivity is not a runtime E108
  check yet).
* `TFSpatial` is the diagonal, dimensionless `Vec{6}` form (it keeps the per-component unit
  proof alive); `TFSpatialMat` is the general 6x6 `Mat` (`a.f = M b.f`, `b.e = -M^T a.e`, no
  inverse). `GYSpatial` is a full 6x6 `Mat` (`a.e = G b.f`, `b.e = -G^T a.f`); `MTF`/`MGY` are
  their signal-modulated forms. `MSeSpatial`/`MSfSpatial` were **not** added (not in the
  J-MB8 element list); a per-component wrench source is `ExternalWrenchSpatial` (six scalar
  inputs with their own units) and `SeSpatial`/`SfSpatial` take one `Vec{6}` signal.
* Transforms: `a.f = -Ad(g) b.f` and `b.e = Ad(g)^T a.e`, written component-wise with the
  explicit causal direction (`b.e` from `a.e`, FIX-MB-2 style). `FixedTransform3D` is the
  checked **world -> body** mount. `FixedTransform3DNeutral` (both ports neutral) is the
  **body -> body** mount, and `JointTransform3D` is **frame-neutral on both ports** because a
  joint composite must bond it to `ISpatial` (`body`) or `GroundSpatial` (`world`); the two
  ports stay separate frame unions bridged by the block, so two bodies' frames are never
  falsely unified (the `TFAdNeutral` pattern). The old `parent`/`child` names made every
  joint-to-body bond E007 (review major 1).
* Frames pack: `GroundSpatial -> FixedTransform3D -> ISpatial` is E007-clean
  (`frames["c1"] = "Mount/world"`, `"c2" = "I/body"`); the same chain with a direct
  `GroundSpatial -> ISpatial` bond gives exactly one E007; `SeSpatial -> FixedTransform3D ->
  SfSpatial` runs and reports `T/world` / `T/body`. A **rigidly clamped inertia** is the
  documented DEC-MB-2 derivative-causality DAE (1 W201, run E901), exactly like the planar rigid
  joint; the runnable mount model is the transformer's forward direction. A body -> body mount
  through `FixedTransform3DNeutral` (and through `JointTransform3D`) is frame-accepted, with
  the two body unions separate (`IA/body` vs `IB/body`) and a W201 for the rigid constraint.

## PoseIntegrator3D and the ManifoldProjection deviation

The floating-base pose is seven states (`qw, qx, qy, qz, px, py, pz`; the initial pose is a
start value, D4). The RHS is

    ddt(q) = 0.5 q (x) [0, w],      ddt(p) = R(q) v,

with `R` the unnormalised quadratic form divided by `|q|^2` (the same expansion as
`_quat_matrix`). **`q . qdot = 0` identically**, so `d/dt |q|^2 = 2 q . qdot = 0`: the unit
norm is a first integral of the RHS and the norm drift is only the solver's accumulation. No
`ManifoldProjection` callback is attached: there is **no seam** for it — `lower/mtk.jl`
passes only `continuous_events`/`initialization_eqs` to `System`, and `simulate` only remakes
the problem to wrap the event callbacks. Adding one needs a new `src/sim` callback kwarg
(outside J-MB8's paths), recorded as the D-MB6 deviation. Measured norm drift over 10 s:
**9.33e-15** (constant-screw run) and **6.13e-14** (general free body).

D-MB6 also wants the floating-base-only rule: a fixed-base chain composes its pose and holds
no pose state. `ComposePose3D` is `q = qp (x) ql` (raw Hamilton product, not renormalised or
sign-canonicalised, like `Mech.compose`), `p = p_p + R(qp) p_l`; a fixed-base chain has one
state (the joint angle), the composition model with a truth integrator has eight, and a
composed pose drives `GravitySpatial` (`e = [0; m g0 R(g)[3,:]]`, error 6.4e-14 / 1.4e-13
against the analytic direction).

## Element notes

* `CoriolisSpatial`: `p.e = -ad(f)^T P` component-wise (the spatial EJS); the element power is
  0 (`V^T ad(V)^T P = 0`), and the free-body run reproduces the body-frame Euler equation.
* `ExternalWrenchSpatial` takes the **physical** wrench as six scalar inputs (N*m x3, N x3)
  and sets `p.e = -W`; a body on a 1-junction feels `+W_ext` (component units proven end to
  end: a torque moves only the angular momentum, a force only the linear one).
* `GravitySpatial`: `p.e = [0; m g0 R(g)[3,:]]` (the negative of the physical gravity wrench
  at the CoM), reading the composed or integrated pose chart.
* `CSpatial`/`RSpatial` keep six scalar states/parameters because a torsional and a
  translational entry do not share a unit; `DeSpatial`/`DfSpatial` are the detectors.
* **C-MB2 contract gap (recorded, not changed):** a `Vec{6}` *signal* has one unit slot, so
  the `u`/`y` inputs/outputs of `SeSpatial`/`SfSpatial`/`DeSpatial`/`DfSpatial` show no
  per-component unit in the manifest (the planar `Se`/`De` precede them). The power ports are
  per-component in the manifest: `p.e = N*m,N*m,N*m,N,N,N`, `p.f = rad/s x3, m/s x3`,
  `P = "W"`; a per-component signal declaration is a contract change owned by C-MB2.

## Measured (this machine, 2026-10-29)

| item | measured |
| --- | --- |
| free body over 10 s (J = 1,2,3; m = 2) | KE drift **5.52e-14**, world H **5.43e-14**, world P **3.00e-14**, quat norm **6.13e-14** |
| Dzhanibekov (spin about the intermediate axis) | `w_y` in **[-3.0, 3.0]**, 2 sign changes; world H **4.87e-14**, KE **9.59e-14** |
| floating-base constant screw vs `exp(V t)` | max pose error **1.24e-12** (quaternion 1.25e-14), quat norm drift **9.33e-15** |
| fixed-base composition vs integrated truth | **1.34e-12** over 10 s; fixed chain 1 state vs 8 with the truth integrator; composed pose exact to 5.95e-14 |
| two-port power residual (TF/TFMat/GY/MTF/MGY, 10 random models) | **1.61e-15**; Coriolis `abs(e.f)` **6.41e-17** |
| gravity / wrench | `P_y(1 s) = -12.6395510236034` vs analytic -12.6395510236035; torque `P_ang_x(2 s) = 2.80000000000007` for tau*t = 2.8, force `P_lin = F t` to 1e-9 |
| port power on a run | `abs(P_I + P_W) = 1.11e-16 W`; `p.P = sum e[k] f[k]` to 1e-16 |
| `test_spatial_slice.jl` | **901 assertions, green** |
| full `Pkg.test()` | **green** (`library` 9330, J-MB8 901) |

# J-MB9 — spatial body and joint composites (verified 2026-10-29)

`stdlib/spatial/` (group **Spatial mechanics**, 16 blocks): `RigidBody3D`, `LocalPose3D`,
`Revolute3D`, `Prismatic3D` (each with `Compliant`/`Friction`/`Limit` variants), `Helical3D`,
`Cylindrical3D`, `Universal3D`, `Spherical3D`, `Planar3D`, `Free3D`. The generic 6x6
`JointBasis` and `JointPose3D` were dropped (user correction 2026-10-29, see
`plan/wps/M3-remaining-orchestration.md`). Acceptance: `test/test_mech_spatial.jl`.

## Conventions

* **Axis = local z of the joint frame.** Place and orient a joint with `FixedTransform3D` /
  `FixedTransform3DNeutral` on either side; `[S | N]` is then the identity (up to the pitch).
* **Port orientation in rigs.** Transformers are `a.f = -Ad(g) b.f`, `b.e = Ad(g)^T a.e`; side
  `a` attaches to the joint port, side `b` to the ground/body, and `g` is the body-side pose in
  the joint-side frame. The opposite orientation gives NaN at initialisation. Bonds run
  `transform.b -> body.p`; the reverse flips the relative-rate sign.
* Joints are **frame-neutral** (FIX-MB-6: two `RigidBody3D` faces are always bridged by a joint
  or neutral transform). One scalar port per axis, domain from the screw.
* `Spherical3D`/`Free3D` ports carry the **relative body-frame twist components** (quasi-
  velocities) and integrate a relative quaternion (+ position); no Euler angles, no
  `ManifoldProjection` (the J-MB8 deviation: `q.qdot = 0` keeps the norm, measured 5e-14).

## The exact deflected chart (Fable review, replaces the first-order chart)

The first-order chart (nominal `Ad(g(q))` + small-angle `dθ`) closed the joint port power but
not total energy: the pose fed to gravity was not the integral of the twists the joint
produced (missing `O(dθ x w_p)` term), giving an `O(1/k)` drift (2.6e-6 of the swing at
k = 1e5). Now every compliant joint uses the **actual deflected pose** `H(q, dθ, dl)` in both
adjoints: `V_rel = child.f - Ad(H)^-1 parent.f` (the exact body twist of `H`, reported as
`Vrelout`), `parent.e = -Ad(H)^-T child.e`. The chart rates are `xdot = B V_rel` with `B` the
closed-form inverse of the chart Jacobian, and the wrench is its transpose,
`child.e = B^T [tau; kr dθ + br dθ'; kt dl + bt dl']`, so
`child.e . V_rel = tau qdot + dE/dt + dissipation` identically.

* Vector rotational deflections use the Gibbs vector `g = dθ/2` (`dθ = 2 tan(θ/2) u`, the
  rotation vector to third order); `R_g` is the rotation of the unnormalised quaternion
  `(1, g)`, polynomial over `D = 1 + |g|^2`; strain `½ kr |dθ|²`.
* Damping acts on the chart rates (`br|dθ'|²`, `bt|dl'|²`), identical to first order.
* `dl` is in the child frame (FIX-MB-5 transport `dl' = v - w x dl`), except `Prismatic3D`
  (parent frame) and `Cylindrical3D` (nominal child frame), as their poses already implied.
* `Universal3D` uses the exact deflection angle with one division by `cos(dt)` (1 at zero
  deflection); no other division besides `D` appears in the set.

## Measured (this machine, 2026-10-29)

| Item | Value |
| --- | --- |
| two-link non-planar chain, energy drift of the swing, k = 1e5/1e6/1e7/1e8/1e9 | **3.6e-12 / 6.0e-13 / 1.6e-12 / 2.7e-11 / 1.1e-10** (first-order chart: 2.6e-6 ... 3e-10) |
| same chain vs independent rigid RNE/RK4 | 2.72e-3 ... 2.71e-7, ratio **10.00 per decade** |
| joint port-power identity (8 variants, driven parent) | 3.4e-16 ... 7.9e-16 |
| pose = integral of the relative twist (8 joints, large deflections) | 1.5e-7 (finite-difference floor; first-order chart ~1e-2) |
| spatial pendulum | period rel 6.3e-8, energy 7.2e-12; composed vs integrated pose 6.7e-8 |
| spherical pendulum / Free3D | Lz drift 1.8e-13, |q| drift 5e-14 / identical to `PoseIntegrator3D` |
| `test_mech_spatial.jl` | **1067 assertions, ~5 min, green** |

# J4.1 - debug run engine (verified 2026-10-30)

Code: `src/sim/debug.jl`; `# M4 debug:` insertion points in `src/sim/simulate.jl`; tests `test/test_debug.jl`.

* **`step!(integ, dt, stop_at_tdt)`** (SciMLBase 7.21.4, `src/integrator_interface.jl`): checks `dt*tdir >= 0`, `next_t = t + dt`, `add_tstop!(integ, next_t)` when `stop_at_tdt`, then `while integ.t*tdir < next_t*tdir; step!(integ); retcode in (Default, Success) || break; end`. `_dbg_step!` replicates exactly this with the checkpoint after each single `step!(integ)`; `columns.f64` is byte-identical to a normal run (dc-motor, drivetrain-kalman, bouncing-ball).
* **MTK callbacks of the problem.** `prob.kwargs[:callback]` is ONE `VectorContinuousCallback` (`len` = number of callbacks) when there is more than one; its `affect!` is a `VectorAffect(eq2affect, affects, affect_negs)`. Slot order = the `continuous_events` order of the lowering: the `@events` entries in `flat.events` order, then the condition-only nonsmooth kinks (`EMPTY_AFFECT`). `@events` affects are positive-edge only. So slot `i <= length(flat.events)` with non-empty `flat.events[i].actions` is the firing of that event; the debug run wraps `affects[i]` (like `_with_event_limit`) to push `i` to `ctx.fired`. Verified with a two-`@events` relay: the pause location is the entry that fired.
* **Events at a pause.** `dbg_pause!` first calls `_record_new_events!` (cursor in `session.event_cursor`, synced with the loop's local cursor), so paused data includes the left/right event rows and no row is written twice.
* `add_tstop!` on a live integrator works for `runTo` and time breakpoints (results after such a stop match a normal run only within tolerances).
* `--compiled-modules=existing` loads the stale BGSim from source without re-precompiling (start about 20 s instead of 4.5 min).
* Closures posted to the run task (`with_paused`) are called with `invokelatest` (the run task's world age is older than a closure defined later at top level).
* t1 of the bouncing ball is `sqrt(2/9.81) = 0.4515236...` (the plan's 0.45152 is rounded).

# J4.3 - watch pool, evaluate and explain (verified 2026-10-30)

Code: `src/syntax/watch.jl` (the `watch` scope), `src/sim/watch.jl` (pool, `debug_evaluate`, `debug_values`), `src/compile/explain.jl` (`model_explain`); tests `test/test_watch.jl`, `test/test_explain.jl`.

Probes (dc-motor iconic, SymbolicIndexingInterface 0.3.55, SciMLBase 7.21.4, DiffEqBase of the project manifest):

* **`observed(sys, expr)`** (`SymbolicIndexingInterface.observed`; `ModelingToolkit.observed` is the equation list) returns a `GeneratedFunctionWrapper` called as `f(u, p, t)` with `u = integ.u`, `p = integ.p`. It works for a variable that `mtkcompile` eliminated (`Motor1/i` is not in `unknowns(sys)`; the observed equation is `Motor1/i ~ Motor1/gyrator/n.f`) and inside a callback condition (`condition(out, u, t, integ)` calls `f(u, integ.p, t)`; `u` is the interpolated state during root finding). Building one costs about 50 ms. A constant expression needs no `observed` function (test `Symbolics.unwrap(num) isa Number`; `Num <: Real`).
* **`init` merges a `callback` keyword with the problem's callbacks.** The dc-motor problem carries one scalar `ContinuousCallback` (the `ifelse` kink of the step source); `init(prob, alg; callback = pool)` gave a `CallbackSet` with 2 continuous callbacks and both fired. So the pool is passed as `init_kwargs.callback` (the marked `_dbg_init_kwargs` in `simulate.jl`), not by remaking the problem. The callbacks J4.1 wrapped (`_dbg_wrap_callback`) stay in the problem.
* **`add_tstop!(integ, t)` on a running integrator** works (stepping stopped at exactly `t`); J4.1's `runTo` and time breakpoints use it.
* **`VectorContinuousCallback` semantics** (DiffEqBase `src/callbacks.jl`): `affect!(integ, events)` gets an `Int8` view; `events[i] = +1` is an upward crossing (the condition was negative before), `-1` a downward one (a vector callback has no `affect_neg!`, the pool ignores `-1`). The previous sign is **recomputed at `tprev`** in every step (`get_condition(integrator, callback, tprev)`); nothing is cached across steps, so a slot that is added, changed or removed while paused starts from the state at the pause and cannot report a crossing from before. Only after an event of the same callback does `event_last_time` nudge `tprev` for the slots that fired. `rootfind = RightRootFind`: the paused state satisfies `c >= 0` (`i >= 5 A`). The affect calls `derivative_discontinuity!(integ, false)` (it changes nothing). `interp_points = 10` (default) also catches a crossing inside one step.
* **Accuracy.** dc-motor, `Motor1/i > 5`, the model's tolerances (reltol 1e-6, abstol 1e-8): pause at t = 0.01047110360826133, reference (reltol = abstol = 1e-12, bisection on the dense output) 0.010471103651189466, error 4.3e-11 s.
* **Bit identity.** The 16-slot pool is installed in every debug run (also without watches); `test_debug.jl` still gets byte-identical `columns.f64`/`stream.f64` for dc-motor, drivetrain-kalman and bouncing-ball. So there is no re-init when the first watch is added while paused. The debug overhead of J4.1's target (1.3 x) measured 1.12 (dc-motor) and 1.24 (drivetrain-kalman) with the pool.
* **Limitation.** DiffEqBase applies only the earliest callback of a step. If another callback has the same or an earlier event time in that step, the pool's event is lost: a watch on `Motor1/p.e > 6` (the step source jumps at t = 0.01, the time of the kink callback) is not reported, because after the kink the condition is already positive. Watches on continuous quantities are not affected.
* A watch condition that throws (for example `sqrt` of a negative number) evaluates to `NaN`, which never crosses; the first message is kept (`watch_errors(ctx)`).

Design: the `watch` scope parses with JuliaSyntax into the language AST (`s"..."` becomes a `SignalRef`, never evaluated), resolves bare names (frame locals, `t`, `context/name`, `name`) and checks the whitelist (E002), names (E003), types (E004) and units (E006, only where both sides have a unit), all with `scope = "watch"`. `a > b` is `a - b`, `a < b` is `b - a`, `&&`/`||` are `min`/`max`, `!` negates, a bare real expression fires on its upward zero crossing. The condition is lowered with `lower_expression` (the model's walker) and compiled with `observed`. `hitCount = n` pauses on the n-th hit only (like J4.2's line breakpoints). A 17th enabled watch is refused (`verified = false`, E001 "at most 16 watch breakpoints"); disabled watches use no slot. `debug_evaluate` runs `eval_const` over the resolved AST: `WatchEnv <: AbstractDict` supplies `t`, the frame's names (`ctx.ext[:frame].env`) and signal values (recorded getters, `getu`/`getp` for the rest).
`model_explain` classifies a signal from the compiled system: parameter or discrete (in `compiled.params`), state or algebraic (in `unknowns(sys)`; state when a `Differential` of it occurs), alias (an observed equation whose right-hand side is one variable), observed (the right-hand side rendered with `s"id"` through `isvariable` + `signal_name`). A warm (cache hit) call takes about 20 ms.

# J4.2 - statement hooks and line breakpoints (verified 2026-10-30)

Code: `src/sim/hooks.jl`; the debug variant and the block-source registry in `src/compile/discrete.jl`; `# M4 debug:` points in `scheduler.jl` (`discrete_schedule(...; debug)`) and `simulate.jl`; tests `test/test_hooks.jl`.

* **Debug variant.** `step_expression(p, ...; debug = DebugEmit)` returns the unchanged 4-argument expression when `debug === nothing` (checked: the debug expression minus its hook `if`s equals the normal one). The debug function is `(dstate, inputs, params, t, dbg) -> ...`, built with `RuntimeGeneratedFunction` like the normal one, and wrapped in `DebugStep(fn, hooks)` whose 4-argument call passes the `HookState`, so `run_tick!` and `ScheduledPartition.step` are untouched. The cache key needs no debug flag: partitions are not cached anywhere (the generated functions are built per run in `discrete_schedule`).
* **Hook granularity.** One hook per *source* statement: `DiscreteAssign.group` marks the scalar elements one broadcast assignment produced (`xhat = ...` over five elements is one hook, one `if` is one hook, an unrolled `for` iteration is one hook each). The hook statement is `if dbg.armed[k] | stepping(dbg); hook(dbg, k, (assigned temp slots...)) end`; the tuple is built only when the hook fires. `stepping` reads `ctx.step_mode === :statement`, so `debug_step!(ctx, "statement")` from any pause needs no extra state.
* **Statement hooks of drivetrain-kalman LQG.** 9 hooks at lines 39, 41, 42, 43, 45, 47 (the `if`), 48, 50, 51; the quantizer next to it has 1.
* **Block sources.** `FlatModel` has no parsed blocks, so `collect_discrete!` registers a `BlockInfo` (per block ref: the source items with scope and range; per `path/name`: the declared shape) in `Compile.BLOCK_INFO`, a `WeakKeyDict` keyed by the `flat.discrete` vector (the same object survives `set_parameter_values`/`set_start_values`). E401 picks the smallest item that contains the line (`@equations`, `@events`, `@parameters`, ...).
* **Frame at a pause.** A pause at a hook is *before* the statement runs, so `held` shows each value as the previous statement or tick left it. For a line breakpoint on the first statement that reads `xhat` (LQGController line 41), `xhat` at tick i equals what a normal run recorded in the last row before `t_i` (the left row at `t_i` when the tick changed it): both are the value after tick i-1. `tick` is the number of ticks executed so far (i-1); `t` is the tick time. `locals` are the D18 temporaries assigned so far (a vector temporary is a vector; a matrix temporary degrades to a vector), `held` every held value of the block instance (scalars, `Vec`, `Mat` as nested arrays), `previous` the values `previous(x)` reads this tick (`dstate.prev`/`inputs.prev`).
* **Frame for evaluate.** `ctx.ext[:frame]` (`paused_frame(ctx)`) is a `PausedFrame(hook, site, view, env)` while paused at a statement: `env::Dict{Symbol,Any}` holds the raw values of every name in scope (temporaries, held values, the parameters and inputs the partition reads, `t`, `Ts`), directly usable as `eval_const(expr, env)`. It is removed when the run resumes.
* **Conditions** are parsed as the default of a one-parameter throwaway block (`parse_block`), checked (names in the frame scope of every matching hook: E003; functions limited to the pure `eval_const` set: E004; parse errors: E001; all with `scope = "breakpoint condition"`) and evaluated with `eval_const` over a name environment built when the hook fires, only for the names the condition uses. A condition that fails at run time pauses with an E004 diagnostic. Hit counts count hits whose condition holds and fire on the n-th only; they survive a re-`setBreakpoints` with an unchanged breakpoint.
* **Pre-run statuses.** Before the run exists a `line` breakpoint is `verified = false` without diagnostics; `_dbg_begin!` resolves it when the run starts (the registry calls the resolver at run start).
* **Latent J4.1 issue fixed.** `session.event_cursor` was only synced at the start of `_dbg_step!`, so a pause at a tick or statement right after a step that crossed an `@events` firing recorded its left/right rows twice. `_dbg_sync_cursor!` (marked in `simulate.jl`) mirrors the loop's local cursor; test "an @events firing between ticks" runs a ramp that restarts at 0.0105 s next to 1 ms ticks and compares `columns.f64` byte for byte.
* **Existing behaviour noticed (not changed).** A vector assignment lowers to one scalar assignment per element in order, so a later element reads the *already updated* earlier elements (`xhat[2] = xhat[2] + L[2]*(y - dot(Cd, xhat))` sees the new `xhat[1]`). The debug variant keeps that order, so frames and results match the normal run; the statement-level semantics belong to J2.2.
* Probes: a Julia script run with `timeout` and stderr redirected to a file loses its output when it hangs (buffered); print with `flush(stderr)`. `parse` is ambiguous inside `BGSim` (use `Base.parse`).

# J4.4 - edits, replay and branch (verified 2026-10-30)

Code: `src/sim/edits.jl`; marked `M4 debug (J4.4)` lines in `src/sim/debug.jl` (two `DebugCtx` fields `replay`, `at`, and a `_replay_checkpoint!` call in `dbg_after_step!`, `_dbg_target!`, `_dbg_entry!`); tests `test/test_edits.jl`.

* **Parameter edit = parameter discontinuity.** `setp(integ, sym)(integ, v)`, then on a DAE `initialize_dae!(integ, BrownFullBasicInit())`, then `reeval_internals_due_to_modification!(integ, false; callback_initializealg = NoInit())`: the exact sequence of `run_tick!` for a published held output. `u_modified!` is deprecated in SciMLBase 7.21.4 (forwards to `derivative_discontinuity!` with a depwarn); `setp` already flags the discontinuity, and a bare flag on a DAE makes `loopheader!` call `initialize_dae!` with the problem's default (the t = 0 operating point), hence the explicit Brown init. State edits use `setu` + the same re-evaluation (+ Brown init on a DAE).
* **E402 rule (deviation from D24's wording).** drivetrain-kalman keeps one algebraic equation (`0 ~ -TFa/p2.fˍt + GY/p2.fˍt*TFa/n`, mass matrix last row 0) that depends on differential states through the observed equations, so "no algebraic equations" would refuse the acceptance case. Rule used: refuse (E402) when an algebraic equation (observed substituted) is nonlinear in the algebraic unknowns; when all are linear, Brown init is exact and the state edit is allowed. The test model (`ddt(x) ~ -k*x + y`, `y + sin(y) ~ x`) keeps the algebraic equation (`lowered.algebraic`, one equation without derivative) and gets E402. Non-states (alias, observed, algebraic unknown, held output) get E402 with the differential states listed; unknown ids E003; non-finite values E004; held outputs in `setParameter` E402.
* **Replay positions.** Edits are replayed at the checkpoint they were made at. The contract's `Edit` has no field for it, so it is stored in the schema's free `$comment` as `at=entry|step|target|statement`. A statement pause replays as `step` at its tick time (identical unless a later partition of the same tick reads the edited parameter); tested bit-identical on drivetrain-kalman. At `step` the replay first records the pending event rows (as `dbg_pause!` does), then applies the edit. Time stops: every parent pause with reason `time` or `breakpoint` is re-added with `add_tstop!` before the first step (tick-time duplicates are harmless).
* **Replay is a debug run** (`DebugCtx` + `ReplayPlan`, never pauses); a debug run without pauses writes the same bytes as a normal run (J4.1). Its manifest has `parentRun` plus the parent's `debug.edits`/`debug.pauses`, so a replay of a replay is the same again. `branch_run` replays edits and stops before `t`, adds a time breakpoint `branch` at `t`, records `parentRun` and `branchAt`; rows before `t` equal the parent's bit for bit. A replay edit refused by the model raises an error; unapplied edits at the end of a `done` run raise too.
* **Model for replay/branch:** `write_run_model(run_dir, model, project_dir)` writes `<run_dir>/model.json`; `replay_run`/`branch_run` use it unless `flat` is passed.
* **Watch pause replay:** max relative column error 3.9e-8 (dc-motor, `Motor1/i > 5`, edit of R) at reltol 1e-6; the test asserts < 1e-5.
* Test gotcha: a single top-level `@testset` prints nothing until the end; a helper that waits for a notification while the run is paused hangs (resume first).
