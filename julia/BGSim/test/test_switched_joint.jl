# Work package J-MB14: SwitchedPivot3D and the impact map (plan 6, row J-MB14; F11, F12, D-MB11).
#
# Three layers, tested in this order (the plan asks for the projection to be derived and
# tested independently before it is wired to an event):
#   1. `Mech.impact_projection` on random SPD inertias (the corrected F12 map);
#   2. the closed form inside `stdlib:contact/ImpactInertia3D`'s event against that numeric
#      projection on the simulated states (pre/post limits recorded at the event instant);
#   3. the compliant switched pivot against two `ContactPoint`s on an edge.
# Every helper is `_sj_`-prefixed because the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Mech
using LinearAlgebra
using Random

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

# The edge-balance comparison reuses the `_ct_model`/`_ct_cp`/`_ct_run` rig of test_contact.jl.
isdefined(@__MODULE__, :_ct_model) || include(joinpath(@__DIR__, "test_contact.jl"))

_sj_vec(v) = "[" * join(string.(v), ", ") * "]"

"""
    _sj_rig(; r, m, J, q0, p0, P0, mode0, tsw, mode_new, g0, ...)

`GroundSpatial -> SwitchedPivot3D -> ImpactBody3D`. `r` is the pivot origin in the body (centre
of mass) frame (so the centre of mass sits at `-r` in the pivot frame). `q0`, `p0` the start
pose of the pivot frame in the world; the pivot starts in `mode0` (zero deflections), the
guard ramp crosses 0.5 at `tsw` and applies `mode_new`.
"""
function _sj_rig(; r = (0.1, 0.1, 0.0), m = 2.0, J = (0.1, 0.1, 0.1), q0 = (1.0, 0.0, 0.0, 0.0),
    p0 = (0.0, 0.0, 0.0), P0 = zeros(6), mode0 = 0, tsw = 0.2, mode_new = 2, g0 = 9.81,
    t_end = 0.5, npts = 501, kt = 1.0e6, bt = 1.0e3, kr = 1.0e5, br = 1.0e2, name = "Switched")
    nodes = Any[
        bg_node("w", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("j", "Joint", bg_ref("stdlib:contact/SwitchedPivot3D");
            params = Dict{String,Any}("kt" => string(kt), "bt" => string(bt), "kr" => string(kr),
                "br" => string(br)),
            starts = Dict{String,Any}("qw" => string(q0[1]), "qx" => string(q0[2]),
                "qy" => string(q0[3]), "qz" => string(q0[4]), "px" => string(p0[1]),
                "py" => string(p0[2]), "pz" => string(p0[3]), "mode" => string(mode0),
                "mt" => string(mode0 >= 1 ? 1.0 : 0.0), "mr" => string(mode0 >= 2 ? 1.0 : 0.0),
                "mz" => string(mode0 >= 3 ? 1.0 : 0.0))),
        bg_node("b", "Body", bg_ref("stdlib:contact/ImpactBody3D");
            params = Dict{String,Any}("m" => string(m), "J" => _sj_vec(J), "cx" => string(-r[1]),
                "cy" => string(-r[2]), "cz" => string(-r[3]), "g0" => string(g0)),
            starts = Dict{String,Any}("inertia/P" => _sj_vec(P0))),
        bg_node("lp", "CoM", bg_ref("stdlib:spatial/LocalPose3D");
            params = Dict{String,Any}("x" => string(-r[1]), "y" => string(-r[2]), "z" => string(-r[3]))),
        bg_node("c", "Compose", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("ts", "Guard", bg_ref("stdlib:sources/Ramp");
            params = Dict{String,Any}("t_start" => "0.0", "slope" => "1.0", "initial" => string(0.5 - tsw))),
        bg_node("mn", "NewMode", bg_ref("stdlib:sources/Constant");
            params = Dict{String,Any}("value" => string(mode_new))),
    ]
    conns = Any[
        bg_conn("c1", "bond", "w", "p", "j", "parent"),
        bg_conn("c2", "bond", "j", "child", "b", "p"),
        bg_conn("c3", "signal", "j", "pose", "c", "gp"),
        bg_conn("c4", "signal", "lp", "g", "c", "gl"),
        bg_conn("c5", "signal", "c", "g", "b", "g"),
        bg_conn("c6", "signal", "ts", "y", "j", "sw"),
        bg_conn("c7", "signal", "ts", "y", "b", "sw"),
        bg_conn("c8", "signal", "mn", "y", "j", "mode_new"),
        bg_conn("c9", "signal", "mn", "y", "b", "mode_new"),
    ]
    return bg_model(name, nodes, conns; t_end = t_end, points = npts, reltol = 1.0e-9,
        abstol = 1.0e-11)
end

"""First and last recorded row at the guard instant `tsw`: the left limit before and the right
limit after all events of that instant (the joint and the body each record their own pair)."""
function _sj_event_rows(cols, tsw)
    t = cols["time"]
    rows = [k for k in eachindex(t) if abs(t[k] - tsw) < 1e-6]
    return first(rows), last(rows)
end

_sj_P(cols, i) = [cols["Body/inertia/P[$k]"][i] for k in 1:6]

@testset "J-MB14 SwitchedPivot3D and the impact map" begin
    # -----------------------------------------------------------------------------------
    # 1. The numeric projection (independent of the event)
    # -----------------------------------------------------------------------------------
    @testset "impulse.jl: V+ = S (S'MS)^-1 S'M V-" begin
        rng = MersenneTwister(14)
        worst = Dict(:mom => 0.0, :con => 0.0, :forms => 0.0, :ke => -Inf)
        for n in (0, 1, 3), trial in 1:20
            A = randn(rng, 6, 6)
            M = A * A' + 0.1I
            V = randn(rng, 6)
            S = randn(rng, 6, n)
            C = n == 0 ? Matrix{Float64}(I, 6, 6) : nullspace(S')
            Vp = Mech.impact_projection(M, S, V)
            Vc = Mech.impact_projection_complement(M, C, V)
            mom = n == 0 ? 0.0 : norm(S' * M * Vp - S' * M * V) / norm(S' * M * V)
            con = norm(C' * Vp) / norm(V)
            forms = norm(Vp - Vc) / norm(V)
            dke = (Mech.kinetic_energy(M, Vp) - Mech.kinetic_energy(M, V)) / Mech.kinetic_energy(M, V)
            worst[:mom] = max(worst[:mom], mom)
            worst[:con] = max(worst[:con], con)
            worst[:forms] = max(worst[:forms], forms)
            worst[:ke] = max(worst[:ke], dke)
            # The first-order guess of the earlier ADR does NOT satisfy the momentum identity.
            if n > 0
                Vwrong = V - S * ((S' * M * S) \ (S' * V))
                @test norm(S' * M * Vwrong - S' * M * V) > 1e-3 * norm(S' * M * V)
            end
        end
        @info "impulse.jl worst residuals" worst
        @test worst[:mom] < 1e-9
        @test worst[:con] < 1e-9
        @test worst[:forms] < 1e-9
        @test worst[:ke] <= 1e-9          # kinetic energy never increases
        # the face (n = 0) is the zero twist; the free mode (no constraint) is the identity
        @test Mech.impact_projection(Matrix{Float64}(I, 6, 6), zeros(6, 0), ones(6)) == zeros(6)
        @test Mech.impact_projection_complement(Matrix{Float64}(I, 6, 6), zeros(6, 0), ones(6)) == ones(6)
        @test_throws ArgumentError Mech.impact_projection(-Matrix{Float64}(I, 6, 6), zeros(6, 1), ones(6))
        @test_throws ArgumentError Mech.switched_basis(7)
        @test Mech.switched_basis(:edge) == Mech.switched_basis(2)
    end

    @testset "impulse.jl: effective inertia at a pivot" begin
        J = Mech.SVector(0.1, 0.2, 0.3)
        m = 2.0
        r = [0.15, -0.1, 0.07]                       # pivot origin in the body frame
        Mc = Mech.spatial_inertia(m, J)
        Mp = Mech.pivot_inertia(Mc, Mech.SE3(Matrix{Float64}(I, 3, 3), r))
        # independent: the parallel-axis theorem for the angular block
        A = Diagonal(collect(J)) + m * (dot(r, r) * I - r * r')
        @test norm(Mp[1:3, 1:3] - A) < 1e-12
        @test norm(Mp[4:6, 4:6] - m * I) < 1e-12
        @test norm(Mp - Mech.spatial_inertia(m, J, -r)) < 1e-12
        @test isposdef(Symmetric(Matrix(Mp)))
        # kinetic energy is frame independent: 1/2 V' M V at the pivot equals the CoM energy
        Vc = randn(MersenneTwister(2), 6)
        Vp = Matrix(Mech.Ad(Mech.SE3(Matrix{Float64}(I, 3, 3), r))) \ Vc
        @test abs(Mech.kinetic_energy(Mp, Vp) - Mech.kinetic_energy(Mc, Vc)) < 1e-12
    end

    # -----------------------------------------------------------------------------------
    # catalog contract
    # -----------------------------------------------------------------------------------
    blocks = Dict(b.ref => b for b in Library.load_stdlib())
    @testset "catalog: Contact group, clean blocks" begin
        for ref in ("stdlib:contact/SwitchedPivot3D", "stdlib:contact/ImpactInertia3D",
            "stdlib:contact/ImpactBody3D")
            b = blocks[ref]
            @test b.group == "Contact"
            @test isempty(check_block(b.ast))
            @test !isempty(b.description)
        end
        for ref in ("stdlib:contact/SwitchedPivot3D", "stdlib:contact/ImpactInertia3D")
            bal = BGSim.block_balance(blocks[ref].ast)
            @test bal.unknowns == bal.equations
        end
    end

    # -----------------------------------------------------------------------------------
    # 2. The event against the numeric projection, on the simulated states
    # -----------------------------------------------------------------------------------
    J = (0.1, 0.2, 0.3)
    m = 2.0
    r = (0.15, -0.1, 0.07)
    P0 = [0.3, -0.2, 0.5, 1.2, -0.7, 0.9]
    Mc = Mech.spatial_inertia(m, Mech.SVector(J...))
    gpiv = Mech.SE3(Matrix{Float64}(I, 3, 3), collect(r))
    Mp = Mech.pivot_inertia(Mc, gpiv)
    Ad = Matrix(Mech.Ad(gpiv))

    for (mode, label) in ((1, "corner"), (2, "edge"), (3, "face"), (0, "free"))
        @testset "impact at the switch to $label (g0 = 0, free flight before)" begin
            doc = _sj_rig(; r = r, m = m, J = J, P0 = P0, g0 = 0.0, mode_new = mode, tsw = 0.2,
                t_end = 0.4, npts = 401)
            t0 = time()
            cols, res, flat = bg_run(doc)
            secs = time() - t0
            @test res.status == "done"
            i, j = _sj_event_rows(cols, 0.2)
            @test j > i                     # the left and the right limit were recorded
            Pm = _sj_P(cols, i)
            Pp = _sj_P(cols, j)
            Vc_m = Pm ./ [J..., m, m, m]
            Vc_p = Pp ./ [J..., m, m, m]
            Vm = Ad \ Vc_m                     # pivot-frame twists
            Vp = Ad \ Vc_p
            S, C = Mech.switched_basis(mode)
            # the closed form in the event equals the numeric projection of impulse.jl
            Vref = Mech.impact_projection(Mp, S, Vm)
            err_ref = norm(Vp - Vref) / norm(Vm)
            err_mom = size(S, 2) == 0 ? 0.0 : norm(S' * Mp * Vp - S' * Mp * Vm) / norm(S' * Mp * Vm)
            err_con = size(C, 2) == 0 ? 0.0 : norm(C' * Vp) / norm(Vm)
            Vcomp = Mech.impact_projection_complement(Mp, C, Vm)
            err_forms = norm(Vp - Vcomp) / norm(Vm)
            ke_m = Mech.kinetic_energy(Mp, Vm)
            ke_p = Mech.kinetic_energy(Mp, Vp)
            @info "event $label" err_ref err_mom err_con err_forms ke_m ke_p secs
            @test err_ref < 1e-9
            @test err_mom < 1e-9
            @test err_con < 1e-9
            @test err_forms < 1e-9
            @test ke_p <= ke_m * (1 + 1e-9)
            if mode == 0
                @test norm(Pp - Pm) < 1e-12
            else
                @test ke_p < ke_m              # an impact dissipates
            end
            # the joint adopted the mode and re-anchored at its current pose
            @test cols["Joint/modeout"][i] == 0.0
            @test cols["Joint/modeout"][j] == Float64(mode)
        end
    end

    # -----------------------------------------------------------------------------------
    # 2b. A body falling onto a corner pivot under gravity: the held pivot stays put
    # -----------------------------------------------------------------------------------
    @testset "falling body caught at a corner pivot" begin
        a = 0.2
        doc = _sj_rig(; r = (a / 2, a / 2, 0.0), m = m, J = (0.03, 0.03, 0.03),
            P0 = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], g0 = 9.81, mode_new = 1, tsw = 0.2,
            q0 = (cos(-pi / 4), sin(-pi / 4), 0.0, 0.0), t_end = 0.6, npts = 601)
        cols, res, flat = bg_run(doc)
        @test res.status == "done"
        i, j = _sj_event_rows(cols, 0.2)
        # after the catch the pivot origin stays at the anchor (compliance only)
        px = cols["Joint/pose[5]"]
        py = cols["Joint/pose[6]"]
        pz = cols["Joint/pose[7]"]
        drift = maximum(norm([px[k] - px[j], py[k] - py[j], pz[k] - pz[j]]) for k in j:length(px))
        fall = norm([px[i], py[i], pz[i]])
        @info "corner catch" drift fall
        @test fall > 1e-2                    # it did fall freely before the switch
        # stiffness-consistent: weight / kt = 2 * 9.81 / 1e6 and the swing loads add less than 10x that
        @test drift < 2.0e-4
    end

    # -----------------------------------------------------------------------------------
    # 3. Edge balance against two ContactPoints
    # -----------------------------------------------------------------------------------
    @testset "edge balance agrees with two ContactPoints" begin
        a = 0.2
        mm = 2.0
        Jc = mm * a^2 / 6
        phi0 = 0.70                          # tilt about the edge (balance point is pi/4)
        # pivot frame: x -> world x, y -> world -z, z -> world y (edge along world y)
        qref = (cos(-pi / 4), sin(-pi / 4), 0.0, 0.0)
        qz = (cos(phi0 / 2), 0.0, 0.0, sin(phi0 / 2))
        hq(p, q) = (p[1] * q[1] - p[2] * q[2] - p[3] * q[3] - p[4] * q[4],
            p[1] * q[2] + p[2] * q[1] + p[3] * q[4] - p[4] * q[3],
            p[1] * q[3] - p[2] * q[4] + p[3] * q[1] + p[4] * q[2],
            p[1] * q[4] + p[2] * q[3] - p[3] * q[2] + p[4] * q[1])
        q0 = hq(qref, qz)
        Rq(q) = [q[1]^2 + q[2]^2 - q[3]^2 - q[4]^2 2 * (q[2] * q[3] - q[1] * q[4]) 2 * (q[2] * q[4] + q[1] * q[3]);
                 2 * (q[2] * q[3] + q[1] * q[4]) q[1]^2 - q[2]^2 + q[3]^2 - q[4]^2 2 * (q[3] * q[4] - q[1] * q[2]);
                 2 * (q[2] * q[4] - q[1] * q[3]) 2 * (q[3] * q[4] + q[1] * q[2]) q[1]^2 - q[2]^2 - q[3]^2 + q[4]^2]
        t_end = 0.3
        npts = 301
        kc = 1.0e6
        # --- switched model: edge from the start (mode0 = 2), pivot at the world origin ----
        r = (a / 2, a / 2, 0.0)
        sdoc = _sj_rig(; r = r, m = mm, J = (Jc, Jc, Jc), q0 = q0, mode0 = 2, mode_new = 2,
            tsw = 100.0, t_end = t_end, npts = npts, kt = kc, bt = 2.0e3, kr = 1.0e5, br = 1.0e2,
            name = "SwitchedEdge")
        t0 = time()
        scols, sres, _ = bg_run(sdoc)
        t_sw = time() - t0
        @test sres.status == "done"
        # --- contact model: two ContactPoints at the edge vertices (body offsets r + (0,0,+-a/2)) --
        Rm = Rq(q0)
        com0 = Rm * [-r[1], -r[2], -r[3]]          # centre of mass in the world (pivot at the origin)
        # start at the static penetration of the two points (each carries half the weight)
        xeq = (mm * 9.81 / 2 / kc * sqrt(1.0e-3))^(2 / 3)
        delta0 = xeq - 1.0e-6^2 / (4xeq)
        com0z = com0[3] - delta0
        pts = [(r[1], r[2], a / 2), (r[1], r[2], -a / 2)]
        cdoc = _ct_model(points = pts, m = mm, J = (Jc, Jc, Jc),
            pose0 = (q0..., com0[1], com0[2], com0z), cp = _ct_cp(mu = 2.0, c = 5.0, k = kc),
            t_end = t_end, npts = npts, name = "ContactEdge")
        t0 = time()
        ccols, cres, _, _ = _ct_run(cdoc)
        t_ct = time() - t0
        @test cres.status == "done"
        # compare the centre-of-mass world position and orientation over the run
        sx = scols["Compose/g[5]"]; sy = scols["Compose/g[6]"]; sz = scols["Compose/g[7]"]
        cx = ccols["Pose/g[5]"]; cy = ccols["Pose/g[6]"]; cz = ccols["Pose/g[7]"]
        dpos = maximum(norm([sx[k] - cx[k], sy[k] - cy[k], sz[k] - cz[k]]) for k in 1:npts)
        dq = maximum(min(norm([scols["Compose/g[$l]"][k] - ccols["Pose/g[$l]"][k] for l in 1:4]),
            norm([scols["Compose/g[$l]"][k] + ccols["Pose/g[$l]"][k] for l in 1:4])) for k in 1:npts)
        moved = norm([sx[end] - sx[1], sy[end] - sy[1], sz[end] - sz[1]])
        # stiffness-consistent bound: 4x the sum of the contact static penetration, the pivot
        # weight deflection mg/kt and the friction creep vs*atanh(Ft/(mu Fn)) over the run (about 1 mm/s)
        tol_pos = 4 * (xeq + mm * 9.81 / kc + 1.0e-3 * 0.3)
        tol_ang = tol_pos / a
        @info "edge balance" dpos dq moved tol_pos tol_ang t_sw t_ct
        @test moved > 0.02                    # the cube really rocks (not a trivial agreement)
        @test dpos < tol_pos
        @test dq < tol_ang
    end
end
