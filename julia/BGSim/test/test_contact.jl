# Work package J-MB13: compliant plane contact (plan 6, row J-MB13; F11, D-MB11).
#
# `stdlib/contact/` holds a `ContactSurface` (a signal source: plane origin and the frame
# `(n, t1, t2)`) and `ContactPoint` (a one-port element on a `Power{Spatial}` bond: smooth
# Hunt-Crossley normal force, two scalar regularised Coulomb dampers along the tangents).
# Everything is smooth, so the models need no events (no W206) and run on the existing
# Rodas5P pipeline (`IR.parse_model` -> `Compile.flatten` -> `simulate`).
#
# The rig is a floating body (`RigidBody3D` + `PoseIntegrator3D` on the body twist) with
# `n` contact points; each point is a `FixedTransform3DNeutral` mount (contact = side `a`,
# body = side `b`, mount pose = body in the point frame) and its world pose is composed from
# the body pose and a `LocalPose3D`.
#
# Tolerances (stated where used):
#   * rest force/penetration: the Hunt-Crossley damping removes the landing transient; what is
#     left at t = 8 s is far below 1e-6.
#   * stick: the regularised Coulomb force is `mu f_n tanh(s/vs)`, so a held body creeps at
#     `s = vs atanh(tan(a)/mu)` (about 0.5 mm/s for the numbers below) instead of zero.
#   * slide: the friction equals `mu f_n` up to `1 - tanh(s/vs)`, which is below 1e-8 once
#     `s > 10 vs`; the acceleration is `g (sin a - mu cos a)` up to the Rodas5P error.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import JSON3
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const _CT_G0 = 9.81
const _CT_K = 1.0e4          # N/m at x = xref (force = k x sqrt(x/xref))
const _CT_XREF = 1.0e-3
const _CT_EPS = 1.0e-6       # penetration smoothing length (the block default)
const _CT_VS = 1.0e-3        # friction regularisation velocity (the block default)

"""
    _ct_model(; points, m, J, plane_n, plane_o, heading, pose0, P0, cp, t_end, npts)

A floating body over a plane. `points` is a list of body-frame offsets `(x, y, z)`; `cp` is
a `Dict` of `ContactPoint` parameter strings (shared by all points); `pose0` the start pose
`(qw, qx, qy, qz, px, py, pz)` and `P0` the start body momentum `[Lx..Lz; px..pz]`.
"""
function _ct_model(; points = [(0.0, 0.0, 0.0)], m = 2.0, J = (0.1, 0.1, 0.1),
    plane_n = (0.0, 0.0, 1.0), plane_o = (0.0, 0.0, 0.0), heading = 0.0,
    pose0 = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5), P0 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    cp = Dict{String,Any}(), g0 = _CT_G0, t_end = 1.0, npts = 101, name = "Contact")
    nodes = Any[
        bg_node("b", "Body", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => string(m),
                "J" => "[$(J[1]), $(J[2]), $(J[3])]", "g0" => string(g0)),
            starts = Dict{String,Any}("inertia/P" =>
                "[" * join(string.(P0), ", ") * "]")),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = Dict{String,Any}("qw" => string(pose0[1]), "qx" => string(pose0[2]),
                "qy" => string(pose0[3]), "qz" => string(pose0[4]),
                "px" => string(pose0[5]), "py" => string(pose0[6]),
                "pz" => string(pose0[7]))),
        bg_node("s", "Surf", bg_ref("stdlib:contact/ContactSurface");
            params = Dict{String,Any}("ox" => string(plane_o[1]), "oy" => string(plane_o[2]),
                "oz" => string(plane_o[3]), "nx" => string(plane_n[1]),
                "ny" => string(plane_n[2]), "nz" => string(plane_n[3]),
                "heading" => string(heading))),
    ]
    conns = Any[
        bg_conn("c1", "signal", "b", "V", "pose", "tw"),
        bg_conn("c2", "signal", "pose", "g", "b", "g"),
    ]
    for (i, pt) in enumerate(points)
        pos = Dict{String,Any}("x" => string(pt[1]), "y" => string(pt[2]), "z" => string(pt[3]))
        # The mount is the body pose in the POINT frame (contact side = parent `a`, body side =
        # child `b`): for a translation-only point that is the negated offset.
        mnt = Dict{String,Any}("x" => string(-pt[1]), "y" => string(-pt[2]), "z" => string(-pt[3]))
        push!(nodes, bg_node("m$i", "Mount$i", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = mnt))
        push!(nodes, bg_node("l$i", "Local$i", bg_ref("stdlib:spatial/LocalPose3D"); params = pos))
        push!(nodes, bg_node("k$i", "Compose$i", bg_ref("stdlib:multibond/ComposePose3D")))
        push!(nodes, bg_node("p$i", "C$i", bg_ref("stdlib:contact/ContactPoint"); params = cp))
        push!(conns, bg_conn("cm$i", "bond", "b", "p", "m$i", "b"))
        push!(conns, bg_conn("cp$i", "bond", "m$i", "a", "p$i", "p"))
        push!(conns, bg_conn("cg$i", "signal", "pose", "g", "k$i", "gp"))
        push!(conns, bg_conn("cl$i", "signal", "l$i", "g", "k$i", "gl"))
        push!(conns, bg_conn("cq$i", "signal", "k$i", "g", "p$i", "g"))
        push!(conns, bg_conn("co$i", "signal", "s", "o", "p$i", "o"))
        push!(conns, bg_conn("cf$i", "signal", "s", "fr", "p$i", "fr"))
    end
    return bg_model(name, nodes, conns; t_end = t_end, points = npts,
        reltol = 1.0e-9, abstol = 1.0e-11)
end

"""The parameters shared by every contact point of the rig (strings, as the document wants)."""
_ct_cp(; mu = 0.5, c = 5.0, k = _CT_K) = Dict{String,Any}(
    "k" => string(k), "xref" => string(_CT_XREF), "c" => string(c), "mu" => string(mu),
    "vs" => string(_CT_VS), "eps" => string(_CT_EPS))

"""Static smooth penetration `x` for a spring force `F` (inverse of `F = k x sqrt(x/xref)`)."""
_ct_x_of_force(F; k = _CT_K) = (F / k * sqrt(_CT_XREF))^(2 / 3)

"""The signed penetration `delta` for a smooth penetration `x` (inverse of `x = (d + r)/2`)."""
_ct_delta_of_x(x) = x - _CT_EPS^2 / (4x)

"""Kinetic energy of the body from the recorded momentum and twist."""
_ct_ke(cols, i) = 0.5 * sum(cols["Body/coriolis/P[$k]"][i] * cols["Body/flow/y[$k]"][i]
                            for k in 1:6)

"""Cumulative integral of `y` over the uniform grid `t`, fourth order: Simpson over pairs of
cells and the three-point cell formula on the odd cells (error O(h^4), so the identity checks
are not limited by the 1 ms output grid)."""
function _ct_cumtrapz(t, y)
    n = length(t)
    h = t[2] - t[1]
    out = zeros(n)
    for i in 2:n
        if iseven(i) && i < n
            out[i] = out[i - 1] + h / 12 * (5 * y[i - 1] + 8 * y[i] - y[i + 1])
        elseif iseven(i)
            out[i] = out[i - 1] + h / 12 * (-y[i - 2] + 8 * y[i - 1] + 5 * y[i])
        else
            out[i] = out[i - 2] + h / 3 * (y[i - 2] + 4 * y[i - 1] + y[i])
        end
    end
    return out
end

"""Run a document through the real pipeline and return `(columns, result, flat, seconds)`."""
function _ct_run(doc)
    t0 = time()
    cols, res, flat = bg_run(doc)
    return cols, res, flat, time() - t0
end

_ct_stat(res) = res.stats

"""A block on a slope of angle `a` (plane normal `(sin a, 0, cos a)`, downhill `(cos a, 0, -sin a)`),
with the body frame rotated by `a` about y so that its z axis is the plane normal (the contact
rotation `R(g)` is not the identity). One contact point at the body origin, started at the
static penetration so there is no normal transient."""
function _ct_slope(a, mu; heading = 0.0, rotate = true, t_end = 4.0, npts = 401, m = 2.0)
    Fn = m * _CT_G0 * cos(a)
    delta0 = _ct_delta_of_x(_ct_x_of_force(Fn))
    h = -delta0                                  # height of the point above the plane
    n = (sin(a), 0.0, cos(a))
    pose0 = rotate ? (cos(a / 2), 0.0, sin(a / 2), 0.0, h * n[1], 0.0, h * n[3]) :
            (1.0, 0.0, 0.0, 0.0, h * n[1], 0.0, h * n[3])
    return _ct_model(points = [(0.0, 0.0, 0.0)], m = m, plane_n = n, heading = heading,
        pose0 = pose0, cp = _ct_cp(mu = mu), t_end = t_end, npts = npts, name = "ContactSlope")
end

# The drop rig: a 0.4 x 0.3 m footprint with four points 0.05 m below the body origin.
const _CT_CORNERS = [(0.2, 0.15, -0.05), (-0.2, 0.15, -0.05), (0.2, -0.15, -0.05),
                     (-0.2, -0.15, -0.05)]

@testset "J-MB13 compliant plane contact" begin
    blocks = Dict(b.ref => b for b in Library.load_stdlib())

    # -----------------------------------------------------------------------------------
    # Catalog contract
    # -----------------------------------------------------------------------------------
    @testset "catalog: Contact group, clean blocks, per-component units" begin
        cs = blocks["stdlib:contact/ContactSurface"]
        cpt = blocks["stdlib:contact/ContactPoint"]
        for b in (cs, cpt)
            @test b.group == "Contact"
            @test isempty(check_block(b.ast))
            bal = block_balance(b.ast)
            @test bal.unknowns == bal.equations
            @test !isempty(b.description)
            @test !isempty(b.icon)
            for d in b.interface.parameters
                @test !isempty(d.description)
            end
        end
        @test isempty(cs.interface.ports)            # a pure signal source
        @test [p.name for p in cpt.interface.ports] == ["p"]
        @test only(cpt.interface.ports).domain == "Spatial"
        @test cpt.interface.dimension == 3
        @test cpt.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]
        env = BGSim.Units.unit_env(cpt.ast)
        for k in 1:3
            @test env.labels[Symbol("p.e[", k, "]")] == "N*m"
            @test env.labels[Symbol("p.f[", k, "]")] == "rad/s"
            @test env.labels[Symbol("p.e[", k + 3, "]")] == "N"
            @test env.labels[Symbol("p.f[", k + 3, "]")] == "m/s"
        end
        @test sort([d.name for d in cpt.interface.parameters]) ==
              ["bt", "c", "eps", "feps", "k", "mu", "vs", "xref"]
    end

    # -----------------------------------------------------------------------------------
    # Dropped body: comes to rest with sum f_n = m g and the static penetration
    # -----------------------------------------------------------------------------------
    drop = nothing
    @testset "dropped body rests at sum f_n = m g (four points)" begin
        m = 2.0
        # Points start 0.01 m above the plane (body origin 0.06 m, points 0.05 m below it).
        doc = _ct_model(points = _CT_CORNERS, m = m, pose0 = (1.0, 0, 0, 0, 0, 0, 0.06),
            cp = _ct_cp(), t_end = 8.0, npts = 8001, name = "ContactDrop")
        cols, res, flat, secs = _ct_run(doc)
        drop = (cols = cols, res = res)
        @test res.status == "done"
        n = length(cols["time"])
        # Smooth forms need no events: no W206, no duplicated event-pair rows.
        @test !any(d -> d.code == "W206", res.diagnostics)
        @test !any(d -> d.code == "W206", flat.diagnostics)
        @test length(unique(cols["time"])) == n
        fn = [cols["C$i/f_n"][end] for i in 1:4]
        ratio = sum(fn) / (m * _CT_G0)
        x4 = _ct_x_of_force(m * _CT_G0 / 4)
        d4 = _ct_delta_of_x(x4)
        pen = [cols["C$i/delta"][end] for i in 1:4]
        println("J-MB13 drop: sum f_n/(m g) - 1 = ", ratio - 1, ", delta = ", pen[1],
            " (expected ", d4, "), stats = ", _ct_stat(res), ", wall = ", round(secs; digits = 1), " s")
        @test abs(ratio - 1) < 1.0e-6
        @test all(abs.(pen .- d4) .< 1.0e-3 * d4)    # symmetric rest: equal penetration
        # The body origin sits 0.05 m above the point height `-delta`.
        @test abs(cols["Pose/pz"][end] - (0.05 - d4)) < 1.0e-3 * d4
        # It came to rest, and it did land from above through a penetration transient.
        @test maximum(abs, [cols["Body/flow/y[$k]"][end] for k in 1:6]) < 1.0e-6
        @test cols["C1/delta"][1] < 0
        @test maximum(cols["C1/f_n"]) > 1.2 * fn[1]
        # The normal force is never an adhesion pull.
        @test all(minimum(cols["C$i/f_n"]) >= -1.0e-9 for i in 1:4)
    end

    # -----------------------------------------------------------------------------------
    # Power consistency and non-negative dissipation (the landing, resolved at 50 us)
    # -----------------------------------------------------------------------------------
    @testset "power consistency and dissipation (landing window)" begin
        # The landing pulse is a few ms wide, so the energy bookkeeping uses its own window
        # with a 50 us output grid (same structure as the drop run: a compile-cache hit).
        doc = _ct_model(points = _CT_CORNERS, m = 2.0, pose0 = (1.0, 0, 0, 0, 0, 0, 0.06),
            cp = _ct_cp(), t_end = 0.5, npts = 10001, name = "ContactLanding")
        cols, res, _, _ = _ct_run(doc)
        @test res.status == "done"
        t = cols["time"]
        m = 2.0
        port_power = [sum(cols["C$i/p.e[$k]"][j] * cols["C$i/p.f[$k]"][j] for k in 1:6)
                      for i in 1:4, j in eachindex(t)]
        # Pointwise: the port power is exactly minus (world force . point velocity), i.e. the
        # power absorbed by the contact; the bond carries no extra term.
        perr = 0.0
        for j in eachindex(t), i in 1:4
            Fv = sum(cols["C$i/Fw$k"][j] * cols["C$i/v$k"][j] for k in 1:3)
            perr = max(perr, abs(port_power[i, j] + Fv) / max(1.0, abs(Fv)))
        end
        @test perr < 1.0e-9
        # Integrated: int(port power) = Ec(end) - Ec(0) + int(Pd), summed over the points.
        Ptot = vec(sum(port_power; dims = 1))
        Ec = sum(cols["C$i/Ec"] for i in 1:4)
        Pd = sum(cols["C$i/Pd"] for i in 1:4)
        lhs = _ct_cumtrapz(t, Ptot)
        rhs = (Ec .- Ec[1]) .+ _ct_cumtrapz(t, Pd)
        scale = maximum(abs, rhs)
        resid = maximum(abs, lhs .- rhs) / scale
        println("J-MB13 power: pointwise residual = ", perr, ", integrated residual = ", resid,
            " (relative to ", scale, " J)")
        @test resid < 1.0e-5        # fourth-order quadrature on the 50 us grid; the identity itself is exact
        # Dissipation is non-negative sample by sample and strictly positive overall.
        # (the only negative part is the no-pull clamp smoothing: Fc - Fx <= feps/2 times xdot)
        @test minimum(Pd) >= -4 * 0.5e-6 * maximum(abs, [maximum(abs, cols["C$i/xd"]) for i in 1:4])
        @test maximum(_ct_cumtrapz(t, Pd)) > 1.0e-4
        # The closed system conserves energy once the dissipation is counted:
        # KE + m g z + stored + int(Pd) = const (the pose, momentum and contact agree).
        E = [_ct_ke(cols, j) + m * _CT_G0 * cols["Pose/pz"][j] + Ec[j] for j in eachindex(t)]
        Etot = E .+ _ct_cumtrapz(t, Pd)
        drift = maximum(abs, Etot .- Etot[1]) / (m * _CT_G0 * 0.06)
        println("J-MB13 total-energy drift (relative to m g h) = ", drift)
        @test drift < 1.0e-5
        # The dissipation is real: the mechanical energy dropped by most of the drop height.
        @test E[1] - E[end] > 0.5 * (m * _CT_G0 * 0.01)
    end

    # -----------------------------------------------------------------------------------
    # Slope: stick (mu > tan a) and slide (mu < tan a), including the two tangents
    # -----------------------------------------------------------------------------------
    a = deg2rad(15.0)
    @testset "slope: mu > tan(a) sticks with the regularisation creep" begin
        mu = 0.6
        cols, res, flat, secs = _ct_run(_ct_slope(a, mu))
        @test res.status == "done"
        t = cols["time"]
        late = t .>= 1.0
        creep_ref = _CT_VS * atanh(tan(a) / mu)          # the regularised stick velocity
        s2 = cols["C1/s2"]
        println("J-MB13 stick: creep = ", s2[end], " m/s (regularised prediction ", creep_ref,
            "), distance over 4 s = ", cols["Pose/px"][end] * cos(a) - cols["Pose/pz"][end] * sin(a),
            " m, stats = ", _ct_stat(res), ", wall = ", round(secs; digits = 1), " s")
        # Held: the slip stays at the regularisation creep (a free body would reach 6 m/s) ...
        @test maximum(abs, s2[late]) < 1.1 * creep_ref
        @test abs(s2[end] - creep_ref) < 1.0e-2 * creep_ref
        # ... which is the tanh balance mu f_n tanh(s/vs) = m g sin(a) with f_n = m g cos(a).
        @test abs(cols["C1/ft2"][end] - 2.0 * _CT_G0 * sin(a)) < 1.0e-6
        @test abs(cols["C1/f_n"][end] - 2.0 * _CT_G0 * cos(a)) < 1.0e-6
        # No motion across the slope.
        @test maximum(abs, cols["C1/s1"]) < 1.0e-9
    end

    @testset "slope: mu < tan(a) slides with g (sin a - mu cos a)" begin
        mu = 0.1
        cols, res, flat, secs = _ct_run(_ct_slope(a, mu))
        @test res.status == "done"
        t = cols["time"]
        win = findall(x -> 0.5 <= x <= 3.5, t)
        # Least-squares slope of the downhill speed over the window.
        A = [ones(length(win)) t[win]]
        coef = A \ cols["C1/s2"][win]
        acc = coef[2]
        ref = _CT_G0 * (sin(a) - mu * cos(a))
        relerr = abs(acc - ref) / ref
        # The speed profile is linear (no velocity-dependent force left): max deviation.
        lin = maximum(abs, cols["C1/s2"][win] .- A * coef) / maximum(cols["C1/s2"][win])
        println("J-MB13 slide: a = ", acc, " (g(sin a - mu cos a) = ", ref, "), rel. error = ",
            relerr, ", linearity = ", lin, ", stats = ", _ct_stat(res), ", wall = ",
            round(secs; digits = 1), " s")
        # The only error sources are the tanh regularisation, 1 - tanh(s/vs) < 1e-8 once
        # s > 10 vs (reached within 6 ms), and the solver tolerance.
        @test relerr < 1.0e-5
        @test lin < 1.0e-5
        @test maximum(abs, cols["C1/s1"]) < 1.0e-9
        @test abs(cols["C1/f_n"][end] / (2.0 * _CT_G0 * cos(a)) - 1) < 1.0e-5   # pose-integration error after 8 m of travel
    end

    @testset "two tangents: heading 45 deg turns the box friction into sqrt(2) mu" begin
        # With t1, t2 at 45 deg to the sliding direction each scalar damper carries
        # mu f_n tanh(s/(sqrt(2) vs)) and their sum along the slide is sqrt(2) mu f_n: the
        # documented anisotropy of the two-scalar-damper (box) friction. The unrotated body
        # on the same slope checks the frame mapping the other way round.
        mu = 0.1
        cols, res, flat, secs = _ct_run(_ct_slope(a, mu; heading = pi / 4, rotate = false))
        @test res.status == "done"
        t = cols["time"]
        win = findall(x -> 0.5 <= x <= 3.5, t)
        A = [ones(length(win)) t[win]]
        acc = (A \ ((cols["C1/s1"][win] .+ cols["C1/s2"][win]) ./ sqrt(2)))[2]
        ref = _CT_G0 * (sin(a) - sqrt(2) * mu * cos(a))
        println("J-MB13 slide at 45 deg heading: a = ", acc, " (reference ", ref,
            "), rel. error = ", abs(acc - ref) / ref)
        @test abs(acc - ref) / ref < 1.0e-5
        # Both tangents carry the same friction force (symmetric), and both are active.
        @test abs(cols["C1/ft1"][end] - cols["C1/ft2"][end]) < 1.0e-6
        @test cols["C1/ft1"][end] > 0.1
    end

    # -----------------------------------------------------------------------------------
    # Controls: a contact with mu = 0 does not hold the slope (the friction is what holds it)
    # -----------------------------------------------------------------------------------
    @testset "control: mu = 0 slides at g sin(a); stiffness sets penetration" begin
        cols, res, flat, secs = _ct_run(_ct_slope(a, 0.0; t_end = 2.0, npts = 201))
        @test res.status == "done"
        t = cols["time"]
        win = findall(x -> 0.5 <= x <= 1.8, t)
        A = [ones(length(win)) t[win]]
        acc = (A \ cols["C1/s2"][win])[2]
        @test abs(acc - _CT_G0 * sin(a)) / (_CT_G0 * sin(a)) < 1.0e-5
        @test abs(cols["C1/ft2"][end]) < 1.0e-9
        # The penetration follows the Hertz law: the static x for the same normal load.
        @test abs(cols["C1/delta"][end] - _ct_delta_of_x(_ct_x_of_force(2.0 * _CT_G0 * cos(a)))) <
              1.0e-6 * abs(cols["C1/delta"][end]) + 1.0e-12
    end
end
