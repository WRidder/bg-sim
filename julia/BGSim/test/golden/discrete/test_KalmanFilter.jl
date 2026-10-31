# Golden test for `stdlib:discrete/KalmanFilter`, through the real pipeline.
#
# Reference: the time-varying Kalman recurrence of the block's documentation, evaluated in
# Julia tick by tick (the first tick at t = Ts):
#   pc = P*C,  K = pc / (C'*pc + R),  x_hat = x + K*(y - C'*x - D*u),  Pf = P - K*pc',
#   x = A*x_hat + B*u,  P = sym(A*Pf*A' + Q).
# The plant is a discretized double integrator (Ts = 0.01) driven by u = 1 and measured as
# y = 0.7 (constant inputs, so every sample is exact). The filtered estimate, the gain and
# the covariance match the recurrence to rounding, P stays symmetric, and the gain settles at
# the steady-state Kalman gain of the discrete Riccati equation.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
if !isdefined(@__MODULE__, :dg_model)
    include(joinpath(@__DIR__, "golden_discrete.jl"))
end
using Test
using LinearAlgebra
using .BondGraphGolden

function _kf_reference(A, B, C, D, Q, R, u, y, ticks)
    x = zeros(2)
    P = Matrix{Float64}(I, 2, 2)
    xh, K = zeros(2), zeros(2)
    for _ in 1:ticks
        pc = P * C
        K = pc / (dot(C, pc) + R)
        xh = x + K * (y - dot(C, x) - D * u)
        Pf = P - K * pc'
        x = A * xh + B * u
        pn = A * Pf * A' + Q
        P = 0.5 * (pn + pn')
    end
    return xh, K, P
end

@testset "golden: KalmanFilter" begin
    A = [1.0 0.01; 0.0 1.0]
    B = [0.0, 0.01]
    C = [1.0, 0.0]
    Q = [1.0e-6 0.0; 0.0 1.0e-4]
    R = 1.0e-2
    model = dg_model("KalmanFilterRecurrence",
        [dg_node("n1", "U", bg_ref("stdlib:sources/Constant"); params = Dict{String,Any}("value" => "1.0")),
            dg_node("n2", "Y", bg_ref("stdlib:sources/Constant"); params = Dict{String,Any}("value" => "0.7")),
            dg_node("n3", "KF", bg_ref("stdlib:discrete/KalmanFilter");
                constants = Dict{String,Any}("sample_period" => 0.01),
                params = Dict{String,Any}("A" => "[1.0 0.01; 0.0 1.0]", "B" => "[0.0, 0.01]"))],
        [bg_conn("c1", "signal", "n1", "y", "n3", "u"), bg_conn("c2", "signal", "n2", "y", "n3", "y")];
        t_end = 2.0, points = 401)
    columns, result, _ = bg_run(model)
    @test result.status == "done"
    @test isempty([d for d in result.diagnostics if d.severity == "error"])
    for ticks in (1, 2, 10, 50, 199)
        t = ticks * 0.01 + 0.005                  # between two ticks
        xh, K, P = _kf_reference(A, B, C, 0.0, Q, R, 1.0, 0.7, ticks)
        @test isapprox(bg_value(columns, "KF/x_hat[1]", t), xh[1]; rtol = 1e-10, atol = 1e-12)
        @test isapprox(bg_value(columns, "KF/x_hat[2]", t), xh[2]; rtol = 1e-10, atol = 1e-12)
        @test isapprox(bg_value(columns, "KF/y_hat", t), xh[1]; rtol = 1e-10, atol = 1e-12)
        @test isapprox(bg_value(columns, "KF/K[1]", t), K[1]; rtol = 1e-10)
        @test isapprox(bg_value(columns, "KF/P[1,2]", t), P[1, 2]; rtol = 1e-10)
        @test bg_value(columns, "KF/P[1,2]", t) == bg_value(columns, "KF/P[2,1]", t)
    end
    # The first tick: K = P*C/(C'*P*C + R) with P = I.
    @test isapprox(bg_value(columns, "KF/K[1]", 0.015), 1 / (1 + R); rtol = 1e-14)
    # Before the first tick the outputs hold their start values.
    @test bg_value(columns, "KF/y_hat", 0.005) == 0.0
    # The gain converges to the steady-state gain: iterate the Riccati map to a fixed point.
    _, Kss, _ = _kf_reference(A, B, C, 0.0, Q, R, 1.0, 0.7, 20000)
    _, K199, _ = _kf_reference(A, B, C, 0.0, Q, R, 1.0, 0.7, 199)
    @test norm(K199 - Kss) < 0.1 * norm(Kss)
end
