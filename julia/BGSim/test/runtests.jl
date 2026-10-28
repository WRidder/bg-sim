# BGSim test suite (milestone M0.3).
#
# These tests prove the ModelingToolkit APIs that plan section 5.8 relies on:
#   * a System built programmatically from strings, compiled with `mtkcompile`, turned into
#     an `ODEProblem` with one merged operating-point map, and solved with `Rodas5P()`;
#   * observed quantities read back through `SymbolicIndexingInterface` (`sol[y]`, `getu`);
#   * parameters set on a live integrator with `setp`;
#   * `ifelse` in the equations plus a one-directional `continuous_events` affect;
#   * a condition-only event that makes the integrator land on a switching instant.
using BGSim
using BGSim: _rc_smoke_system, _bounce_smoke_system
using Test
using ModelingToolkit
using ModelingToolkit: t_nounits as t, D_nounits as D,
    SymbolicContinuousCallback, ImperativeAffect
using OrdinaryDiffEqRosenbrock
using SymbolicIndexingInterface: getu, setu, getp, setp

@testset "BGSim" begin
    @testset "toolchain and MTK v10+ API surface" begin
        @test pkgversion(ModelingToolkit) >= v"11"
        @test isdefined(ModelingToolkit, :System)
        @test isdefined(ModelingToolkit, :mtkcompile)
        @test Base.isexported(ModelingToolkit, :System)
        @test Base.isexported(ModelingToolkit, :mtkcompile)

        # Variables, parameters and discretes created from strings (plan section 5.8:
        # "create variables programmatically ... and keep a Dict{String, Num}").
        x = mtk_variable("motor.omega")
        @test ModelingToolkit.isvariable(x)
        @test signal_name(x) == "motor.omega"
        @test isequal(x, mtk_variable("motor.omega"))
        @test !isequal(x, mtk_variable("motor.omega2"))

        p = mtk_parameter("motor.R")
        @test ModelingToolkit.isparameter(p)
        @test signal_name(p) == "motor.R"

        d = mtk_discrete("motor.mode")
        @test ModelingToolkit.isparameter(d)
        @test signal_name(d) == "motor.mode"

        @test_throws ArgumentError mtk_variable("")
        @test_throws ArgumentError mtk_parameter("")
        @test_throws ArgumentError mtk_discrete("")

        # `ifelse` is symbolic and survives into the equations (section 5.8).
        @test occursin("ifelse", string(ifelse(x > 0, 1.0, 2.0)))
    end

    @testset "RC circuit against the analytic solution" begin
        rc = _rc_smoke_system()
        sys = mtkcompile(rc.sys)
        @test sys isa System
        @test length(unknowns(sys)) == 1
        @test signal_name(only(unknowns(sys))) == "rc.u_C"

        V, R, C = 1.0, 1.0, 1.0
        u0 = 0.0
        tau = R * C
        prob = ODEProblem(sys, [rc.u_C => u0, rc.V => V, rc.R => R, rc.C => C], (0.0, 5.0))
        sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sol.retcode == ReturnCode.Success
        @test length(sol.t) > 10

        # The capacitor voltage follows u_C(t) = V * (1 - exp(-t / (R*C))).
        for tt in (0.1, 0.5, 1.0, 2.5, 5.0)
            exact = V * (1 - exp(-tt / tau))
            @test isapprox(sol(tt, idxs = rc.y), exact; rtol = 1e-4)
            @test isapprox(sol(tt, idxs = rc.y), exact; rtol = 1e-6)
        end

        # The observed quantity `y` and the state `u_C` are both readable by symbol, and
        # they agree pointwise (section 5.8: never parse MTK's generated names).
        @test sol[rc.y] == sol[rc.u_C]
        @test length(sol[rc.y]) == length(sol.t)

        # `getu` on a live integrator, including an observed quantity.
        integ = init(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        step!(integ, 1.0)
        @test isapprox(getu(integ, rc.u_C)(integ), getu(integ, rc.y)(integ); rtol = 1e-12)
        @test isapprox(getu(integ, rc.y)(integ), V * (1 - exp(-integ.t / tau)); rtol = 1e-6)
        @test getu(integ, rc.u_C)(integ) == integ.u[1]
        @test integ[rc.y] == getu(integ, rc.y)(integ)

        # `setp` on the integrator, and `setu` on the state.
        setp(integ, rc.V)(integ, 2.0)
        @test getp(integ, rc.V)(integ) == 2.0
        setp(integ, [rc.V, rc.R])(integ, [3.0, 4.0])
        @test getp(integ, [rc.V, rc.R])(integ) == [3.0, 4.0]
        setu(integ, rc.u_C)(integ, 0.25)
        @test getu(integ, rc.u_C)(integ) == 0.25

        # A parameter-only re-run through `remake` (decision D4) leaves `prob` untouched.
        prob2 = remake(prob; p = [rc.R => 2.0], u0 = [rc.u_C => 0.5])
        @test prob2.u0 == [0.5]
        @test getp(prob2, rc.R)(prob2) == 2.0
        @test getp(prob, rc.R)(prob) == 1.0
        sol2 = solve(prob2, Rodas5P())
        @test isapprox(sol2(0.0, idxs = rc.y), 0.5; rtol = 1e-12)
        # R = 2 gives tau = 2, so y(2) = 1 - 0.5 * exp(-1).
        @test isapprox(sol2(2.0, idxs = rc.y), 1 - 0.5 * exp(-1.0); rtol = 1e-6)
    end

    @testset "ifelse and a one-directional continuous event" begin
        h0 = 1.0
        g = 9.81
        e = 0.8
        b = 0.1
        t_bounce = sqrt(2 * h0 / g)
        v_impact = -sqrt(2 * g * h0)
        v_rebound = e * sqrt(2 * g * h0)

        ball = _bounce_smoke_system()
        sys = mtkcompile(ball.sys)
        prob = ODEProblem(
            sys,
            [ball.h => h0, ball.v => 0.0, ball.g => g, ball.e => e, ball.b => b,
                ball.n => 0.0],
            (0.0, 0.7)
        )
        sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sol.retcode == ReturnCode.Success

        # The event point is saved twice (pre- and post-affect) at the same time.
        i = findfirst(>=(t_bounce - 1e-6), sol.t)
        @test i !== nothing
        @test abs(sol.t[i] - t_bounce) <= 1e-6
        @test sol.t[i + 1] == sol.t[i]
        @test abs(sol[ball.h][i]) <= 1e-9

        # Bounce time and post-bounce velocity.
        @test isapprox(sol[ball.v][i], v_impact; rtol = 1e-4)
        @test isapprox(sol[ball.v][i + 1], v_rebound; rtol = 1e-4)

        # The discrete impulse counter has its own timeseries: the start value plus one
        # entry per event, so exactly one bounce in this window means [0.0, 1.0].
        @test sol[ball.n] == [0.0, 1.0]

        # The `ifelse` branch is really taken: while rising, D(v) = -g - b*v, whose exact
        # solution is v(t) = (v0 + g/b) * exp(-b*t) - g/b.
        dt = 0.05
        exact = (v_rebound + g / b) * exp(-b * dt) - g / b
        @test isapprox(sol(t_bounce + dt, idxs = ball.v), exact; rtol = 1e-6)
        # While falling the branch is not taken, so the fall is exact free fall: the ball
        # never rises above its release height after the bounce.
        @test maximum(sol[ball.h][sol.t .> t_bounce]) < h0

        # Direction: with the affect on the rising edge only, the ball falls through.
        rising = SymbolicContinuousCallback(
            ball.h ~ 0; affect = [ball.v ~ -e * Pre(ball.v)]
        )
        sys_up = mtkcompile(System(
            [D(ball.h) ~ ball.v,
                D(ball.v) ~ -ball.g - ifelse(ball.v > 0, b * ball.v, 0.0)],
            t, [ball.h, ball.v], [ball.g, ball.e, ball.b];
            name = :ball_rising, continuous_events = [rising]
        ))
        sol_up = solve(
            ODEProblem(sys_up,
                [ball.h => h0, ball.v => 0.0, ball.g => g, ball.e => e, ball.b => b],
                (0.0, 0.7)),
            Rodas5P()
        )
        @test sol_up.retcode == ReturnCode.Success
        @test sol_up(0.7, idxs = ball.v) < v_impact  # still falling, no bounce happened
        @test sol_up(0.7, idxs = ball.h) < 0.0

        # The imperative affect API gives the same bounce, and its counter counts bounces.
        n_imp = mtk_discrete("ball.n_imp")
        imp = ImperativeAffect(
            (m, o, ctx, integ) -> (; v = -o.e * m.v, n = m.n + 1);
            modified = (; v = ball.v, n = n_imp), observed = (; e = ball.e)
        )
        cb_imp = SymbolicContinuousCallback(ball.h ~ 0; affect_neg = imp)
        sys_imp = mtkcompile(System(
            [D(ball.h) ~ ball.v,
                D(ball.v) ~ -ball.g - ifelse(ball.v > 0, b * ball.v, 0.0)],
            t, [ball.h, ball.v], [ball.g, ball.e, ball.b, n_imp];
            name = :ball_imp, continuous_events = [cb_imp]
        ))
        sol_imp = solve(
            ODEProblem(sys_imp,
                [ball.h => h0, ball.v => 0.0, ball.g => g, ball.e => e, ball.b => b,
                    n_imp => 0.0],
                (0.0, 3.0)),
            Rodas5P()
        )
        @test sol_imp.retcode == ReturnCode.Success
        j = findfirst(>=(t_bounce - 1e-6), sol_imp.t)
        @test isapprox(sol_imp[ball.v][j + 1], v_rebound; rtol = 1e-4)
        @test sol_imp[n_imp][2] == 1.0

        # More than one bounce in three seconds, and the counter saw every one of them.
        n_bounces = count(1:(length(sol_imp.t) - 1)) do k
            abs(sol_imp[ball.h][k]) <= 1e-9 && abs(sol_imp[ball.h][k + 1]) <= 1e-9 &&
                sol_imp[ball.v][k] < 0 && sol_imp[ball.v][k + 1] > 0
        end
        @test n_bounces >= 2
        @test sol_imp[n_imp][end] == n_bounces
    end

    @testset "condition-only event lands on the switching instant" begin
        x = mtk_variable("sw.x")
        k = mtk_parameter("sw.k")
        eqs = [D(x) ~ -ifelse(x > 0.5, 1.0, 2.0)]

        # Without a condition-only event MTK adds no callback at all: collecting the
        # switching conditions from `ifelse` is the lowering stage's job (section 5.8).
        plain = mtkcompile(System(eqs, t, [x], [k]; name = :sw_plain))
        prob_plain = ODEProblem(plain, [x => 1.0, k => 1.0], (0.0, 2.0))
        @test !haskey(prob_plain.kwargs, :callback)

        cb = SymbolicContinuousCallback(x ~ 0.5)
        sys = mtkcompile(System(eqs, t, [x], [k]; name = :sw, continuous_events = [cb]))
        prob = ODEProblem(sys, [x => 1.0, k => 1.0], (0.0, 2.0))
        @test haskey(prob.kwargs, :callback)
        @test prob.kwargs[:callback].save_positions == [true, true]

        sol = solve(prob, Rodas5P(); abstol = 1e-10, reltol = 1e-10)
        @test sol.retcode == ReturnCode.Success
        # The saved point at the kink is as close to 0.5 as the callback root finder gets;
        # its precision follows the solver tolerances (observed: 6e-7 with 1e-10).
        hit = findfirst(tt -> abs(tt - 0.5) < 1e-5, sol.t)
        @test hit !== nothing
        @test isapprox(sol[hit][1], 0.5; atol = 1e-5)  # x at the switching instant
        # 0.5 s at rate 1, then 1.5 s at rate 2, so the kink is not smeared.
        @test isapprox(sol(2.0, idxs = x), 0.5 - 2.0 * 1.5; rtol = 1e-6)
    end
end

# Work package J1.1: the language front end (parser, whitelist, block-level checks).
include("test_syntax.jl")

# The M1 test files (DEC-5: plain includes now, so a missing file fails the gate).
include("test_units.jl")
include("test_library.jl")
include("test_flatten.jl")
include("test_frames.jl")
include("test_simulate.jl")
include("test_worker.jl")
include("test_language.jl")

# Work package J-MB3: the Lie-group / screw core (numeric, whitelist and registration).
include("test_mech.jl")

# Work package J-MB2: per-component units for multibond ports (Planar/Spatial).
include("test_units_multibond.jl")

# Work package J-MB4: the minimal planar multibond vertical slice and the Gate A pendulum.
include("test_multibond_slice.jl")

# Work package J-MB5: the full planar vector primitive set.
include("test_planar_primitives.jl")

# Work package J-MB6: planar bodies, joints and pose handling.
include("test_planar_mechanics.jl")

# Milestone M2 scaffolding: each WP creates exactly one of these files, and the M2 gate
# replaces these guards with plain includes (the same pattern DEC-5 used for M1).
for entry in ("test_events.jl", "test_discrete.jl", "test_units_model.jl",
              "test_components.jl", "test_cache.jl")
    path = joinpath(@__DIR__, entry)
    isfile(path) && include(path)
end

# Golden tests of the stdlib work packages: test/golden/<group>/test_<Name>.jl. The directory
# is walked so J2.7a–g do not all edit this file while they run in parallel.
let golden = joinpath(@__DIR__, "golden")
    if isdir(golden)
        for (root, _, files) in walkdir(golden)
            for file in sort(files)
                startswith(file, "test_") && endswith(file, ".jl") &&
                    include(joinpath(root, file))
            end
        end
    end
end
include("test_causality.jl")
