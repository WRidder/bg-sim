# Golden test for `stdlib:hydraulic/Pipe`, through the real pipeline.
#
# Model: a `PressureSource` steps the inlet a to p_a = 10 bar at t = 0, a `Tank` holds the
# outlet b at 1 bar; the line starts at rest (all flows and chamber pressures zero). With
# A = pi*d^2/4, the whole-line inertance I = rho*L/A, laminar resistance
# R = 128*rho*nu*L/(pi*d^4) and volume V = A*L, the N-segment line is the linear system
#
#   (I/2N)*qa'   = p_a - p[1] - (R/2N)*qa
#   (I/N)*q[i]'  = p[i] - p[i+1] - (R/N)*q[i]        (i < N)
#   (I/2N)*q[N]' = p[N] - p_b - (R/2N)*q[N]
#   (V/(N*beta))*p[i]' = q[i-1] - q[i]               (q[0] = qa)
#
# 1. Laminar, N = 1 and N = 3: every state against the exact solution
#    x(t) = x_ss + exp(M*t)*(x0 - x_ss) (matrix exponential, rtol 1e-6 of the scale), and
#    the steady state q = (p_a - p_b)/R with a linear pressure profile.
# 2. Turbulent (f_t = 0.03, N = 2): the steady flow solves
#    R*q + K_t*q*sqrt(q^2 + q_eps^2) = p_a - p_b, K_t = f_t*(L/d)*rho/(2*A^2),
#    q_eps = nu*A/d (bisection, rtol 1e-8).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using LinearAlgebra
using .BondGraphGolden

const _PIPE = (L = 2.0, d = 4.0e-3, rho = 850.0, nu = 3.2e-5, beta = 1.4e9)

function _pipe_model(N, p_a, p_b; f_t = 0.0, t_end = 1.0, points = 1001)
    params = Dict{String,Any}("L" => string(_PIPE.L), "d" => string(_PIPE.d),
        "rho" => string(_PIPE.rho), "nu" => string(_PIPE.nu), "beta" => string(_PIPE.beta),
        "f_t" => string(f_t))
    pipe = bg_node("n3", "PL", bg_ref("stdlib:hydraulic/Pipe"); params = params)
    pipe["constants"] = Dict{String,Any}("N" => N)
    return bg_model(
        "PipeBetweenSourceAndTank",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => "1.0")),
            bg_node("n2", "PS", bg_ref("stdlib:hydraulic/PressureSource");
                params = Dict{String,Any}("p" => string(p_a))),
            pipe,
            bg_node("n4", "TK", bg_ref("stdlib:hydraulic/Tank");
                params = Dict{String,Any}("p" => string(p_b))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "a", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = t_end, points = points,
    )
end

# The linear N-segment line as x' = M*x + c, x = [qa; q[1:N]; p[1:N]].
function _pipe_linear(N, p_a, p_b)
    (; L, d, rho, nu, beta) = _PIPE
    A = pi * d^2 / 4
    I, R, V = rho * L / A, 128 * rho * nu * L / (pi * d^4), A * L
    n = 2N + 1
    M, c = zeros(n, n), zeros(n)
    iq(k) = k + 1               # k = 0 is qa, k = 1..N are q[k]
    ip(k) = N + 1 + k           # p[k]
    # qa
    M[iq(0), iq(0)] = -R / I; M[iq(0), ip(1)] = -2N / I; c[iq(0)] = 2N * p_a / I
    for k in 1:N
        if k < N
            M[iq(k), iq(k)] = -R / I; M[iq(k), ip(k)] = N / I; M[iq(k), ip(k + 1)] = -N / I
        else
            M[iq(k), iq(k)] = -R / I; M[iq(k), ip(k)] = 2N / I; c[iq(k)] = -2N * p_b / I
        end
        M[ip(k), iq(k - 1)] = N * beta / V; M[ip(k), iq(k)] = -N * beta / V
    end
    return M, c, R
end

@testset "golden: Pipe" begin
    p_a, p_b = 1.0e6, 1.0e5
    @testset "laminar, N = $N" for N in (1, 3)
        M, c, R = _pipe_linear(N, p_a, p_b)
        x_ss = -(M \ c)
        q_ss = (p_a - p_b) / R
        @test all(isapprox.(x_ss[1:N+1], q_ss; rtol = 1e-9))
        columns, result, _ = bg_run(_pipe_model(N, p_a, p_b))
        @test result.status == "done"
        @test isempty([e for e in result.diagnostics if e.severity == "error"])
        names = vcat(["PL/qa"], ["PL/q[$k]" for k in 1:N], ["PL/p[$k]" for k in 1:N])
        for t in (0.0, 1.0e-3, 5.0e-3, 0.02, 0.1, 1.0)
            x = x_ss .+ exp(M * t) * (zeros(2N + 1) .- x_ss)
            for (j, name) in enumerate(names)
                scale = j <= N + 1 ? q_ss : p_a
                @test isapprox(bg_value(columns, name, t), x[j]; atol = 1e-6 * scale)
            end
        end
        # Steady state at 1 s (the slowest mode has decayed by e^-30): uniform flow,
        # linear pressure profile from the segment centres.
        @test isapprox(bg_value(columns, "PL/a.f", 1.0), q_ss; rtol = 1e-6)
        @test isapprox(bg_value(columns, "PL/b.f", 1.0), -q_ss; rtol = 1e-6)
        for k in 1:N
            @test isapprox(bg_value(columns, "PL/p[$k]", 1.0),
                p_a - (p_a - p_b) * (k - 0.5) / N; rtol = 1e-6)
        end
    end

    @testset "turbulent, N = 2" begin
        f_t = 0.03
        (; L, d, rho, nu) = _PIPE
        A = pi * d^2 / 4
        R = 128 * rho * nu * L / (pi * d^4)
        K_t = f_t * (L / d) * rho / (2 * A^2)
        q_eps = nu * A / d
        lo, hi = 0.0, (p_a - p_b) / R
        for _ in 1:200
            mid = (lo + hi) / 2
            R * mid + K_t * mid * sqrt(mid^2 + q_eps^2) < p_a - p_b ? (lo = mid) : (hi = mid)
        end
        q_ss = (lo + hi) / 2
        @test q_ss < 0.9 * (p_a - p_b) / R        # the turbulent loss is significant
        columns, result, _ = bg_run(_pipe_model(2, p_a, p_b; f_t = f_t, points = 11))
        @test result.status == "done"
        @test isapprox(bg_value(columns, "PL/a.f", 1.0), q_ss; rtol = 1e-8)
        @test isapprox(bg_value(columns, "PL/b.f", 1.0), -q_ss; rtol = 1e-8)
        # Power in at a minus power out at b is the friction loss (p_a - p_b)*q.
        @test isapprox(bg_value(columns, "PL/a.P", 1.0) + bg_value(columns, "PL/b.P", 1.0),
            (p_a - p_b) * q_ss; rtol = 1e-7)
    end
end
