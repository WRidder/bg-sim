# Golden test for `stdlib:electrical/MutualInductance`, through the real pipeline.
#
# Model: a 10 V source drives winding 1 through R1; winding 2 is loaded by R2. Both n
# terminals are grounded. With the inductance matrix L = [L1 M; M L2], M = k*sqrt(L1*L2),
# the currents i = (i1, i2) obey
#
#   L * di/dt = b - R*i,   b = (V, 0),   R = diag(R1, R2),   i(0) = 0,
#
# so i(t) = A^-1 * (exp(A*t) - I) * L^-1 * b with A = -L^-1 * R (evaluated with the matrix
# exponential). The secondary current starts negative (Lenz) and decays back to zero, while
# the primary settles at V/R1. The two-port I-field stores E = i'*L*i/2 and conserves power:
# v1*i1 + v2*i2 = i' * L * di/dt, checked at every sample time.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using LinearAlgebra
using .BondGraphGolden

@testset "golden: MutualInductance" begin
    V = 10.0
    R1 = 5.0
    R2 = 20.0
    L1 = 0.01
    L2 = 0.04
    k = 0.8
    M = k * sqrt(L1 * L2)
    Lm = [L1 M; M L2]
    Rm = Diagonal([R1, R2])
    b = [V, 0.0]
    A = -(Lm \ Matrix(Rm))
    currents(t) = A \ ((exp(A * t) - I) * (Lm \ b))

    model = bg_model(
        "MutualInductanceRL",
        [
            bg_node("n1", "C1", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(V))),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource")),
            bg_node("n3", "R1", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => string(R1))),
            bg_node("n4", "MI1", bg_ref("stdlib:electrical/MutualInductance");
                params = Dict{String,Any}("L1" => string(L1), "L2" => string(L2),
                    "k" => string(k))),
            bg_node("n5", "R2", bg_ref("stdlib:electrical/Resistor");
                params = Dict{String,Any}("R" => string(R2))),
            bg_node("n6", "G1", bg_ref("stdlib:electrical/Ground")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p1"),
            bg_conn("c4", "wire", "n4", "n1", "n6", "p"),
            bg_conn("c5", "wire", "n4", "p2", "n5", "p"),
            bg_conn("c6", "wire", "n5", "n", "n6", "p"),
            bg_conn("c7", "wire", "n4", "n2", "n6", "p"),
            bg_conn("c8", "wire", "n2", "n", "n6", "p"),
        ];
        t_end = 0.04, points = 201,
    )
    columns, result, flat = bg_run(model)
    @test result.status == "done"
    @test isempty([e for e in result.diagnostics if e.severity == "error"])
    @test flat.stats.states == 2

    for t in (0.0, 0.0004, 0.001, 0.002, 0.005, 0.01, 0.02, 0.04)
        i = currents(t)
        @test isapprox(bg_value(columns, "MI1/i1", t), i[1]; rtol = 1e-6, atol = 1e-10)
        @test isapprox(bg_value(columns, "MI1/i2", t), i[2]; rtol = 1e-6, atol = 1e-10)
        @test isapprox(bg_value(columns, "R2/p.f", t), -i[2]; rtol = 1e-6, atol = 1e-10)
        # The winding voltages are L * di/dt.
        di = Lm \ (b - Rm * i)
        v = Lm * di
        @test isapprox(bg_value(columns, "MI1/p1.e", t), v[1]; rtol = 1e-6, atol = 1e-9)
        @test isapprox(bg_value(columns, "MI1/p2.e", t), v[2]; rtol = 1e-6, atol = 1e-9)
        # Power: what enters the windings is the rate of change of the stored energy.
        p = sum(bg_value(columns, "MI1/$(port).P", t) for port in ("p1", "n1", "p2", "n2"))
        @test isapprox(p, dot(i, Lm * di); rtol = 1e-6, atol = 1e-9)
    end
    # Lenz: the induced secondary current opposes the primary one, then decays away.
    @test bg_value(columns, "MI1/i2", 0.001) < 0.0
    @test abs(bg_value(columns, "MI1/i2", 0.04)) < 1e-3 * abs(minimum(bg_all(columns, "MI1/i2")))
    @test isapprox(bg_value(columns, "MI1/i1", 0.04), V / R1; rtol = 1e-3)
end
