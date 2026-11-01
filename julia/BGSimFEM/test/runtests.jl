# BGSimFEM: meshing, assembly, Craig–Bampton reduction, invariants, validation and output.
#
#   julia --project=julia/BGSimFEM julia/BGSimFEM/test/runtests.jl
#
# The part is a steel bar 200 x 20 x 10 mm (x along the bar), interfaces A (x = 0) and B
# (x = L): coarse enough to run in about a minute, fine enough (quadratic tetrahedra) that the
# clamped-free bending frequencies are within 1 % of Euler–Bernoulli.
using Test
using LinearAlgebra
using SparseArrays
using BGSimFEM
import JSON3

const L, B, H = 0.2, 0.02, 0.01
const MAT = (E = 2.1e11, nu = 0.3, rho = 7850.0)

const SPEC = Dict{String,Any}(
    "name" => "bar",
    "geometry" => Dict("box" => Dict("corner" => [0.0, -B / 2, -H / 2], "size" => [L, B, H])),
    "material" => Dict("E" => MAT.E, "nu" => MAT.nu, "rho" => MAT.rho),
    "mesh" => Dict("size" => 0.006, "order" => 2),
    "interfaces" => Any[
        Dict("name" => "A", "position" => [0.0, 0, 0], "select" => Dict("box" => Dict("min" => [-1e-6, -1, -1], "max" => [1e-6, 1, 1]))),
        Dict("name" => "B", "position" => [L, 0, 0], "select" => Dict("box" => Dict("min" => [L - 1e-6, -1, -1], "max" => [L + 1e-6, 1, 1]))),
    ],
    "modes" => Dict("fixed_interface" => 4),
    "stiffening" => true,
    "validate" => 6,
    "validate_attached" => Any[Dict("interface" => "B", "mass" => 0.5, "inertia" => [1e-4, 1e-4, 1e-4], "com" => [0.01, 0, 0])],
)

# Euler–Bernoulli cantilever: lambda_1 L = 1.8751
_cantilever_hz(I) = 1.8751^2 / (2pi * L^2) * sqrt(MAT.E * I / (MAT.rho * B * H))

@testset "BGSimFEM" begin
    dir = mktempdir()
    spec = merge(SPEC, Dict("output" => Dict("model" => joinpath(dir, "bar.modal.json"), "glb" => joinpath(dir, "bar.glb"))))
    r, fe, vm, files = reduce_part(spec; base_dir = dir, verbose = false)

    @testset "mass properties are exact" begin
        m = MAT.rho * L * B * H
        @test r.mass ≈ m rtol = 1e-10
        @test r.S0 ≈ [m * L / 2, 0, 0] atol = 1e-12
        Jx = m * (B^2 + H^2) / 12
        Jy = m * (L^2 / 3 + H^2 / 12)
        Jz = m * (L^2 / 3 + B^2 / 12)
        @test r.J0 ≈ Diagonal([Jx, Jy, Jz]) rtol = 1e-9 atol = 1e-12
    end

    @testset "reduced basis: sizes, diagonal modal mass, invariants" begin
        @test r.nm == 4 + 6
        @test length(r.mk) == r.nm && all(>(0), r.mk) && all(>(0), r.kk)
        # E_xx + E_yy + E_zz = Phi' M Phi = diag(mk)
        @test r.E[1] + r.E[2] + r.E[3] ≈ Diagonal(r.mk) atol = 1e-10 * maximum(r.mk)
        # every mode has a largest nodal translation of 1
        for k in 1:r.nm
            U = BGSimFEM.dofs_to_nodal(fe, view(r.modes, :, k))
            @test maximum(norm.(eachcol(U))) ≈ 1.0 rtol = 1e-12
        end
        # interface A is the reference frame: its mode values are zero
        @test all(iszero, r.PT[1]) && all(iszero, r.PR[1])
    end

    @testset "frequencies: Euler–Bernoulli and the full model" begin
        f = sort(frequencies_hz(r))
        fz = _cantilever_hz(B * H^3 / 12)    # bending about y (thin direction)
        fy = _cantilever_hz(H * B^3 / 12)
        @test f[1] ≈ fz rtol = 0.01
        @test any(x -> isapprox(x, fy; rtol = 0.01), f)
        v = r.validation["frequencies"]
        @test v["band_hz"] > 0
        @test v["clamped"]["max_rel_error_in_band"] < 1e-2
        @test abs(v["clamped"]["rel_error"][1]) < 1e-3     # the first modes are much closer
        @test v["free"]["max_rel_error_in_band"] < 1e-2
        @test v["free"]["full_rigid_hz_max"] < 1.0      # six rigid modes of the free part
        a = r.validation["attached"]
        @test a["max_rel_error_in_band"] < 1e-3
        @test a["full_hz"][1] < f[1]                    # the payload lowers the first mode
    end

    @testset "constraint modes: static response to interface loads is exact" begin
        _, aux = craig_bampton(fe, r.interfaces; nf = 4, stiffening = false)
        c = aux.c
        Kc = aux.Kt[c, c]
        nfree = aux.nfree
        for a in 1:6
            F = zeros(length(c))
            F[nfree + a] = 1.0                           # unit load on interface B dof a
            u = Kc \ Vector(F)
            full = u[nfree .+ (1:6)]
            P = vcat(r.PT[2], r.interfaces[2].rotation * r.PR[2])
            red = P * ((P[a, :]) ./ r.kk)
            @test red ≈ full rtol = 1e-6 atol = 1e-9 * maximum(abs, full)
        end
    end

    @testset "geometric stiffening: tension at B stiffens bending" begin
        st = r.stiffening
        @test st !== nothing
        @test length(st["translation"]) == 3 && length(st["inertia"]) == 6 && length(st["rotation"]) == 3
        @test length(st["interface_force"]) == 3
        Gx = st["interface_force"][1]                    # unit axial force at B (tension)
        @test Gx ≈ Gx'
        k1 = argmin(frequencies_hz(r))                   # first bending mode
        @test Gx[k1, k1] > 0
        # beam theory: a tip tension N raises the cantilever's k by about 1.24 N / L per unit
        # tip deflection squared (Rayleigh with the static shape)
        tip = r.PT[2][:, k1]
        @test Gx[k1, k1] / norm(tip)^2 ≈ 1.2 / L rtol = 0.1
    end

    @testset "files: the reduced-model JSON and the GLB with one morph target per mode" begin
        @test length(files) == 2 && all(isfile, files)
        d = JSON3.read(read(joinpath(dir, "bar.modal.json"), String))
        @test d.format == "bgsim.modal-body" && d.version == 1
        @test d.nm == r.nm && length(d.modal_mass) == r.nm && length(d.interfaces) == 2
        @test d.interfaces[2].name == "B" && length(d.interfaces[2].translation) == 3
        @test length(d.stiffening.interface_force) == 3
        @test d.visual.glb == "bar.glb"
        json, bin = read_glb(joinpath(dir, "bar.glb"))
        prim = json["meshes"][1]["primitives"][1]
        @test length(prim["targets"]) == r.nm
        @test json["meshes"][1]["extras"]["targetNames"][1] == "mode 1"
        @test json["asset"]["extras"]["bgsim"]["modes"] == r.nm
        @test size(vm.positions, 2) == json["accessors"][prim["attributes"]["POSITION"] + 1]["count"]
    end
end
