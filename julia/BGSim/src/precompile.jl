# Precompile workload (plan section 2.1: "the worker precompiles through a PrecompileTools
# workload in BGSim"). It warms the MTK compile, codegen and callback paths on a tiny RC
# model and a bouncing ball, so the worker's first real simulation does not pay for them.

"""
    _rc_smoke_system()

Build the tiny RC circuit used by the precompile workload and by the test suite. Returns a
named tuple with the `System` and the symbolic quantities it is built from.
"""
function _rc_smoke_system()
    u_C = mtk_variable("rc.u_C")
    i = mtk_variable("rc.i")
    u_R = mtk_variable("rc.u_R")
    y = mtk_variable("rc.y")
    V = mtk_parameter("rc.V")
    R = mtk_parameter("rc.R")
    C = mtk_parameter("rc.C")
    eqs = [0 ~ V - u_R - u_C, u_R ~ R * i, i ~ C * D(u_C), y ~ u_C]
    sys = System(eqs, t, [u_C, i, u_R, y], [V, R, C]; name = :rc_smoke)
    return (; sys, u_C, i, u_R, y, V, R, C)
end

"""
    _bounce_smoke_system()

Build the bouncing-ball model used by the precompile workload: `ifelse` in the equations, a
one-directional (falling edge) `continuous_events` affect and a discrete impulse counter.
The drag coefficient `b` only acts while the ball rises, so the descent stays exact free
fall and the first bounce is analytically known (see `test/runtests.jl`).
"""
function _bounce_smoke_system()
    h = mtk_variable("ball.h")
    v = mtk_variable("ball.v")
    n = mtk_discrete("ball.n")
    g = mtk_parameter("ball.g")
    e = mtk_parameter("ball.e")
    b = mtk_parameter("ball.b")
    eqs = [D(h) ~ v, D(v) ~ -g - ifelse(v > 0, b * v, 0.0)]
    cb = ModelingToolkit.SymbolicContinuousCallback(
        h ~ 0;
        affect_neg = [v ~ -e * Pre(v), n ~ Pre(n) + 1],
        discrete_parameters = [n]
    )
    sys = System(eqs, t, [h, v], [g, e, b, n]; name = :ball_smoke, continuous_events = [cb])
    return (; sys, h, v, n, g, e, b)
end

@setup_workload begin
    @compile_workload begin
        rc = _rc_smoke_system()
        ssys = mtkcompile(rc.sys)
        prob = ODEProblem(
            ssys, [rc.u_C => 0.0, rc.V => 1.0, rc.R => 1.0, rc.C => 1.0], (0.0, 1.0)
        )
        sol = solve(prob, Rodas5P())
        sol(0.5, idxs = rc.y)

        integ = init(prob, Rodas5P())
        step!(integ, 0.5)
        getu(integ, rc.y)(integ)
        setp(integ, rc.V)(integ, 2.0)

        ball = _bounce_smoke_system()
        bsys = mtkcompile(ball.sys)
        bprob = ODEProblem(
            bsys,
            [ball.h => 1.0, ball.v => 0.0, ball.g => 9.81, ball.e => 0.8, ball.b => 0.1,
                ball.n => 0.0],
            (0.0, 0.7)
        )
        bs = solve(bprob, Rodas5P())
        bs(0.6, idxs = ball.v)
    end
end
