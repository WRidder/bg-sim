# BGSim NOTES snippet script — run with
#   julia --project=julia/BGSim notes_snippet.jl
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
