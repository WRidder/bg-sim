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
    "stress" => Dict("hotspots" => Any[Dict("name" => "top mid", "position" => [L / 2, 0.0, H / 2]),
                                       Dict("name" => "top root", "position" => [0.03, 0.0, H / 2])]),
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

    @testset "stress: recovery, superposition, hotspots, peak points, files" begin
        # a tip force at B on the full model: sigma_xx on the top face is -F (L - x) c / I
        _, aux = craig_bampton(fe, r.interfaces; nf = 4, stiffening = false)
        c = aux.c
        Kc = aux.Kt[c, c]
        f = zeros(length(c))
        f[aux.nfree + 3] = 100.0
        u = aux.T[:, c] * (Kc \ f)
        S = BGSimFEM.nodal_stress(fe, u)
        I = B * H^3 / 12
        for x in (0.05, 0.1, 0.15)
            top = [i for i in axes(fe.X, 2) if abs(fe.X[1, i] - x) < 1e-3 && abs(fe.X[3, i] - H / 2) < 1e-9 && abs(fe.X[2, i]) < B / 4]
            @test !isempty(top)
            @test sum(S[1, top]) / length(top) ≈ -100 * (L - x) * (H / 2) / I rtol = 0.01
        end
        # the stress of the reduced static response is the superposition of the mode stresses,
        # and it is the full model's (the constraint modes make interface loads exact)
        q = (aux.Y' * f) ./ r.kk
        Sr = BGSimFEM.superpose(r.stress_modes, q)
        @test Sr ≈ S rtol = 1e-6 atol = 1e-6 * maximum(abs, S)
        @test BGSimFEM.von_mises([1.0, 0, 0, 0, 0, 0]) ≈ 1.0
        @test BGSimFEM.von_mises([0.0, 0, 0, 1.0, 0, 0]) ≈ sqrt(3)
        v = r.validation["stress"]
        @test v["max_peak_rel_error_interface_loads"] < 1e-6
        @test v["max_peak_rel_error_self_weight"] < 0.6        # axial self weight: no axial mode
        sw = [c for c in v["cases"] if occursin("along z", c["name"])][1]
        @test abs(sw["peak_rel_error"]) < 0.03                 # bending self weight: 4 modes do
        @test v["peak_coverage"]["mean_ratio"] > 0.97
        @test v["peak_coverage"]["within_5_percent"] > 0.9
        hot = [p for p in r.stress_points if p.kind == "hotspot"]
        @test [p.name for p in hot] == ["top mid", "top root"]
        @test norm(hot[1].position .- [L / 2, 0, H / 2]) < 0.006
        @test count(p -> p.kind == "peak", r.stress_points) == 24
        tied = Set(i for f in r.interfaces for i in f.nodes)
        @test !any(p -> p.node in tied, r.stress_points)
        @test all(p -> size(p.sigma) == (6, r.nm), r.stress_points)
        # the file: points with 6 x nm stress per unit modal coordinate
        d = JSON3.read(read(joinpath(dir, "bar.modal.json"), String))
        @test d.stress.hotspots == 2 && length(d.stress.points) == 26
        @test d.stress.points[1].name == "top mid" && length(d.stress.points[1].sigma) == 6
        @test length(d.stress.points[1].sigma[1]) == r.nm
        @test collect(d.stress.components) == ["xx", "yy", "zz", "xy", "xz", "yz"]
        # the GLB: the per-vertex table, Float32, (vertex, mode, component)
        json, bin = read_glb(joinpath(dir, "bar.glb"))
        st = json["asset"]["extras"]["bgsim"]["stress"]
        nv = size(vm.positions, 2)
        @test st["vertices"] == nv && st["modes"] == r.nm && st["layout"] == "vertex, mode, component"
        bv = json["bufferViews"][st["bufferView"] + 1]
        @test bv["byteLength"] == nv * r.nm * 6 * 4
        table = reinterpret(Float32, bin[(bv["byteOffset"] + 1):(bv["byteOffset"] + bv["byteLength"])])
        @test length(vm.stress) == r.nm
        for (vtx, k, comp) in ((1, 1, 1), (nv, r.nm, 6), (nv ÷ 2, 3, 4))
            @test table[((vtx - 1) * r.nm + (k - 1)) * 6 + comp] ≈ Float32(vm.stress[k][comp, vtx])
        end
    end

    @testset "rail: tables, load modes, full against reduced" begin
        # the bar clamped at A only, a rail along its top face from x = 20 to 180 mm, one
        # load-mode station at mid-rail
        rspec = Dict{String,Any}(
            "name" => "railbar",
            "geometry" => SPEC["geometry"], "material" => SPEC["material"], "mesh" => SPEC["mesh"],
            "interfaces" => Any[SPEC["interfaces"][1]],
            "rail" => Dict{String,Any}("name" => "top", "start" => [0.02, 0.0, H / 2], "end" => [0.18, 0.0, H / 2],
                "normal" => [0.0, 0.0, 1.0], "stations" => 33, "chebyshev" => 16,
                "footprint" => Dict("half_length" => 0.01,
                    "select" => Dict("box" => Dict("min" => [-1, -1, H / 2 - 1e-6], "max" => [1, 1, H / 2 + 1e-6]))),
                "load_modes" => [0.5]),
            "modes" => Dict("fixed_interface" => 4), "stiffening" => false, "validate" => 4, "stress" => false,
            "output" => Dict("model" => joinpath(dir, "railbar.modal.json"), "glb" => joinpath(dir, "railbar.glb")),
        )
        rr, rfe, _, _ = reduce_part(rspec; base_dir = dir, verbose = false)
        d = rr.rail
        @test d !== nothing && d["length"] ≈ 0.16 && d["chebyshev"] == 16
        @test d["start"] ≈ [0.02, 0.0, H / 2]
        # rail frame: x the face normal (z), z along the bar (x), y = z x x
        Rr = reduce(vcat, [collect(row)' for row in d["rotation_matrix"]])
        @test Rr[:, 1] ≈ [0, 0, 1] && Rr[:, 3] ≈ [1, 0, 0] && Rr[:, 2] ≈ cross(Rr[:, 3], Rr[:, 1])
        @test rr.validation["cb"]["load_modes"] == 3                # force x, force y, moment
        @test rr.nm == 4 + 3
        @test count(==("load"), rr.mode_kind) >= 1
        @test d["fit_error"]["translation"] < 0.03
        # the series' derivative is the derivative of the series
        h = 1e-6
        PT, PR, dPT, dPR = BGSimFEM.rail_eval(d, 0.07)
        PTp, PRp, _, _ = BGSimFEM.rail_eval(d, 0.07 + h)
        PTm, PRm, _, _ = BGSimFEM.rail_eval(d, 0.07 - h)
        @test dPT ≈ (PTp - PTm) / 2h rtol = 1e-5 atol = 1e-6 * maximum(abs, dPT)
        @test dPR ≈ (PRp - PRm) / 2h rtol = 1e-5 atol = 1e-6 * maximum(abs, dPR)
        v = rr.validation["rail"]
        mid = [c for c in v["cases"] if c["fraction"] == 0.5]
        @test length(mid) == 3 && all(c -> abs(c["rel_error"]) < 1e-2, mid)      # the load-mode station: exact
        # between the stations the forces are interpolated well; the torsion (no torsion mode
        # among the four vibration modes) only at the station
        @test maximum(abs(c["error_of_largest"]) for c in v["cases"] if c["load"] != "moment z") < 0.05
        # the full model against beam theory: a unit force along the rail frame's x (the face
        # normal, z: the bar's thin direction) at mid-rail on the cantilever, a^3 / (3 E I) at
        # the load
        c = [c for c in mid if c["load"] == "force x"][1]
        a = 0.02 + c["station"]
        @test c["full_compliance"] ≈ a^3 / (3 * MAT.E * B * H^3 / 12) rtol = 0.05
        # the file carries the tables
        df = JSON3.read(read(joinpath(dir, "railbar.modal.json"), String))
        @test df.rail.name == "top" && length(df.rail.translation) == 3
        @test length(df.rail.translation[1]) == rr.nm && length(df.rail.translation[1][1]) == 16
    end
end
