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