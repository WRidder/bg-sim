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
`test/test_simulate.jl` (166 assertions), run by `Pkg.test()`; the full suite is green.

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


