# Flexible bodies, part 1: the closed-form mode shapes of `src/mech/modes.jl` (the contract
# shared with the 3D viewer), the committed fixture `contracts/fixtures/modes/mode_shapes.json`
# and the literal modal tables inside the stdlib beam blocks.
#
# No simulation here; the beam dynamics are in `test_flex_beam.jl`.
using BGSim
using BGSim.Mech
using Test
import JSON3

const FLEX_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
include(joinpath(FLEX_ROOT, "tools", "gen_mode_shapes.jl"))

# The literal table equations `name[i] ~ expr` / `name[i, j] ~ expr` of a block source, as
# a Dict (name, i, j) => (value at basis = 0, value at basis = 1). The right-hand sides use
# only `basis` and numbers, so they are evaluated directly.
function block_tables(path)
    out = Dict{Tuple{String,Int,Int},Tuple{Float64,Float64}}()
    names = ("lam", "kk", "ta", "tb", "p0", "pL", "s0", "sL", "q0", "qL", "tat", "G0", "G1", "G2")
    for line in eachline(path)
        mt = match(r"^\s*(\w+)\[(\d)(?:,\s*(\d))?\]\s*~\s*(.+)$", line)
        mt === nothing && continue
        name = String(mt[1])
        name in names || continue
        i = parse(Int, mt[2])
        j = mt[3] === nothing ? 0 : parse(Int, mt[3])
        ex = Meta.parse(mt[4])
        val(b) = Float64(eval(:(let basis = $b; $ex; end)))
        out[(name, i, j)] = (val(0), val(1))
    end
    return out
end

@testset "flexible bodies: mode shapes" begin
    @testset "eigenvalues solve the frequency equations" begin
        for n in 1:3
            l = beam_lambda("clamped-free", n)
            @test abs(cos(l) * cosh(l) + 1) < 1e-6 * cosh(l)
            l = beam_lambda("free-free", n)
            @test abs(cos(l) * cosh(l) - 1) < 1e-6 * cosh(l)
        end
        @test beam_lambda(0, 1) == 1.87510407
        @test beam_lambda(1, 3) == 10.99560784
        @test beam_sigma("clamped-free", 1) ≈ 0.734095514 atol = 1e-8
        @test beam_sigma("free-free", 1) ≈ 0.982502215 atol = 1e-8
    end

    @testset "normalisation (1/L) int phi^2 = 1 and orthogonality" begin
        for basis in BEAM_BASES, m in 1:3, n in 1:3
            ip = mode_integral(x -> beam_phi(basis, m, x) * beam_phi(basis, n, x))
            @test ip ≈ (m == n ? 1.0 : 0.0) atol = 1e-8
            it = mode_integral(x -> torsion_psi(basis, m, x) * torsion_psi(basis, n, x))
            @test it ≈ (m == n ? 1.0 : 0.0) atol = 1e-10
        end
        # the free-free bending modes are orthogonal to the rigid motions
        for n in 1:3
            @test abs(mode_integral(x -> beam_phi("free-free", n, x))) < 1e-8
            @test abs(mode_integral(x -> x * beam_phi("free-free", n, x))) < 1e-8
        end
    end

    @testset "boundary conditions and end values" begin
        for n in 1:3
            @test abs(beam_phi("clamped-free", n, 0.0)) < 1e-12
            @test abs(beam_dphi("clamped-free", n, 0.0)) < 1e-10
            @test beam_phi("clamped-free", n, 1.0) ≈ 2.0 * (-1)^(n + 1) atol = 1e-9
            @test abs(beam_phi("free-free", n, 0.0)) ≈ 2.0 atol = 1e-9
            @test abs(beam_phi("free-free", n, 1.0)) ≈ 2.0 atol = 1e-7  # lambda to 9 digits
            @test torsion_psi("clamped-free", n, 0.0) == 0.0
            @test abs(torsion_dpsi("clamped-free", n, 1.0)) < 1e-12
            @test abs(torsion_dpsi("free-free", n, 0.0)) < 1e-12
            @test abs(torsion_dpsi("free-free", n, 1.0)) < 1e-12
            # the slope is the derivative of the shape
            h = 1e-6
            for basis in BEAM_BASES, x in (0.2, 0.55, 0.9)
                fd = (beam_phi(basis, n, x + h) - beam_phi(basis, n, x - h)) / (2h)
                @test fd ≈ beam_dphi(basis, n, x) rtol = 1e-6 atol = 1e-6
                fd = (torsion_psi(basis, n, x + h) - torsion_psi(basis, n, x - h)) / (2h)
                @test fd ≈ torsion_dpsi(basis, n, x) rtol = 1e-6 atol = 1e-6
            end
        end
        # psi = sqrt(2) sin((2n-1) pi xi / 2) and sqrt(2) cos(n pi xi)
        @test torsion_psi("clamped-free", 2, 0.3) ≈ sqrt(2) * sin(3pi * 0.3 / 2)
        @test torsion_psi("free-free", 2, 0.3) ≈ sqrt(2) * cos(2pi * 0.3)
    end

    @testset "eigenfrequencies" begin
        E, rho, d, L = 2.1e11, 7850.0, 0.01, 1.0
        A, I = pi * d^2 / 4, pi * d^4 / 64
        w1 = bending_omega("clamped-free", 1; E = E, I = I, rho = rho, A = A, L = L)
        @test w1 ≈ 1.87510407^2 * sqrt(E * I / (rho * A * L^4))
        # the Rayleigh quotient of the mode equals omega^2 (stiffness from phi'', by FD)
        for basis in BEAM_BASES, n in 1:3
            h = 1e-4
            d2(x) = (beam_dphi(basis, n, min(x + h, 1.0)) - beam_dphi(basis, n, max(x - h, 0.0))) /
                    (min(x + h, 1.0) - max(x - h, 0.0))
            kint = mode_integral(x -> d2(x)^2; panels = 64)
            @test kint ≈ beam_lambda(basis, n)^4 rtol = 1e-4
        end
        G, Jt, Ip = E / 2.6, pi * d^4 / 32, pi * d^4 / 32
        @test torsion_omega("clamped-free", 1; G = G, Jt = Jt, rho = rho, Ip = Ip, L = L) ≈
              pi / 2 / L * sqrt(G / rho)
        @test torsion_omega("free-free", 2; G = G, Jt = Jt, rho = rho, Ip = Ip, L = L) ≈
              2pi / L * sqrt(G / rho)
    end

    @testset "modal integrals (Southwell, static tip compliance)" begin
        t = beam_mode_tables("clamped-free")
        @test t.G2[1, 1] ≈ 1.1933 atol = 1e-4           # Southwell coefficient, first flap mode
        # the static tip deflection of a cantilever by n modes: delta = F L^3/(E I) sum phi(L)^2/lambda^4
        frac = cumsum([t.phiL[n]^2 / t.lambda[n]^4 for n in 1:3]) ./ (1 / 3)
        @test frac[1] ≈ 0.9707 atol = 1e-4
        @test frac[2] ≈ 0.9954 atol = 1e-4
        @test frac[3] ≈ 0.9986 atol = 1e-4
        # the foreshortening integral G0 = int phi'^2 is the Rayleigh axial-load matrix
        @test t.G0 ≈ t.G0'
        @test t.G1 ≈ t.G1'
    end

    @testset "the committed fixture matches modes.jl" begin
        path = joinpath(FLEX_ROOT, "contracts", "fixtures", "modes", "mode_shapes.json")
        @test isfile(path)
        committed = JSON3.read(read(path, String))
        fresh = JSON3.read(JSON3.write(mode_shape_fixture()))
        @test collect(committed.xi) == collect(fresh.xi)
        for basis in BEAM_BASES
            a, b = committed.bases[Symbol(basis)], fresh.bases[Symbol(basis)]
            for key in (:lambda, :sigma, :torsion_k)
                @test collect(a[key]) ≈ collect(b[key]) atol = 1e-12
            end
            for key in (:phi, :dphi, :psi), n in 1:3
                @test collect(a[key][n]) ≈ collect(b[key][n]) atol = 1e-10
            end
        end
    end

    @testset "the literal tables in the beam blocks" begin
        stdlib = joinpath(FLEX_ROOT, "julia", "BGSim", "stdlib")
        for (file, families) in (("spatial/ModalBeam3D.jl", true), ("planar/ModalBeam2D.jl", false))
            tab = block_tables(joinpath(stdlib, file))
            @test length(tab) >= (families ? 60 : 48)
            for (bi, basis) in enumerate(BEAM_BASES)
                t = beam_mode_tables(basis)
                ref = Dict(
                    "lam" => t.lambda, "ta" => t.a, "tb" => t.b, "p0" => t.phi0, "pL" => t.phiL,
                    "s0" => t.dphi0, "sL" => t.dphiL, "kk" => t.k, "q0" => t.psi0, "qL" => t.psiL,
                    "tat" => t.at, "G0" => t.G0, "G1" => t.G1, "G2" => t.G2,
                )
                for ((name, i, j), vals) in tab
                    want = j == 0 ? ref[name][i] : ref[name][i, j]
                    @test isapprox(vals[bi], want; rtol = 1e-8, atol = 1e-6) ||
                          (@info "table mismatch" file name i j basis vals[bi] want; false)
                end
            end
        end
    end
end
