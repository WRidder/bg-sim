# Rigs of the FEM flexible body tests (`stdlib:spatial/ModalBody3D`), shared by
# test_fem_body.jl and test_export_flex.jl.
#
# The fixture `fixtures/fem/lbar.modal.json` is a small L of a soft test material (E = 70 MPa,
# 26 g; modes 14 Hz to 1.4 kHz clamped, up to 2.5 kHz free) with three interfaces (A root,
# B leg end, C on the arm), reduced by Craig-Bampton to 1 fixed-interface + 12 constraint
# modes; regenerate it with
# `julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl julia/BGSim/test/fixtures/fem/lbar.fem.json`.
#
# The part is small: with the modes free its frame has a rotational inertia of about 2e-8
# kg m^2, so the starts are chosen as frame velocities (P = M_r V, see `_fem_momentum`) and
# the clamp of `_fem_clamped` is scaled to the part. The free body is an explicit ODE whose
# fastest mode is 2.5 kHz: it runs with an explicit Verner method. A clamp or joint on
# interface A acts on the tiny rotational Schur inertia and rings at 100 kHz and more, so
# those rigs run with Rodas5P (its ForwardDiff Jacobian compiles in about 10 s).
using BGSim
using LinearAlgebra
import JSON3

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const FEM_FX = joinpath(@__DIR__, "fixtures", "fem")
const FEM_DATA = JSON3.read(read(joinpath(FEM_FX, "lbar.modal.json"), String))
const FEM_NM = Int(FEM_DATA.nm)
const FEM_CONSTS = Dict(BGSim.load_modal_body(FEM_FX, Dict{String,Any}("file" => "lbar.modal.json")))

_femv(v) = "[" * join(string.(Float64.(v)), ", ") * "]"
_fem_errors(flat) = [d for d in flat.diagnostics if d.severity == "error"]
_fem_drift(E) = (maximum(E) - minimum(E)) / maximum(abs.(E))
_fem_mat(rows) = permutedims(reduce(hcat, [Float64.(collect(r)) for r in rows]))
_fem_skew(v) = [0.0 -v[3] v[2]; v[3] 0.0 -v[1]; -v[2] v[1] 0.0]

"""
The frame momentum P for frame velocity V = [w; v] (in R) with the modal momenta p = 0 at
q = 0: P = (M_VV - C' diag(1/mk) C) V, the Schur complement the block inverts.
"""
function _fem_momentum(V)
    d = FEM_CONSTS
    S = _fem_skew(d["S0"])
    MVV = [d["J0"] S; S' d["mass"]*I(3)]
    C = [d["Sr"]; d["St"]]
    return (MVV - C * Diagonal(1 ./ d["mk"]) * C') * V
end

function _fem_body(id, name; file = "lbar.modal.json", stiffening = 1, zeta = 0.0, g0 = 0.0,
        starts = Dict{String,Any}())
    node = bg_node(id, name, bg_ref("stdlib:spatial/ModalBody3D");
        params = Dict{String,Any}("zeta" => string(zeta), "g0" => string(g0)), starts = starts)
    node["constants"] = Dict{String,Any}("file" => file, "stiffening" => stiffening)
    return node
end

"""Mean frequency (Hz) of a signal from its upward mean crossings."""
function _fem_freq(t, x)
    xm = x .- (maximum(x) + minimum(x)) / 2
    cr = Float64[]
    for i in 1:(length(x) - 1)
        if xm[i] < 0 && xm[i + 1] >= 0
            push!(cr, t[i] - xm[i] * (t[i + 1] - t[i]) / (xm[i + 1] - xm[i]))
        end
    end
    return (length(cr) - 1) / (cr[end] - cr[1])
end

"""
A free body, no gravity, no damping: it spins (about 3 to 4 rad/s about every axis), drifts
and vibrates (modal displacements of 0.1 to 0.5 mm at t = 0, under 1 % of the part)."""
function _fem_free(; stiffening = 1, t_end = 0.1, solver = "Vern7", points = 1001)
    q0 = zeros(FEM_NM)
    q0[1], q0[2], q0[4] = 5e-4, -2.5e-4, 1.25e-4
    P0 = _fem_momentum([3.0, -2.0, 4.0, 0.1, 0.0, -0.05])
    body = _fem_body("n1", "Body"; stiffening = stiffening,
        starts = Dict{String,Any}("core/q" => _femv(q0), "core/P" => _femv(P0)))
    nodes = Any[body, bg_node("n2", "Mount", bg_ref("stdlib:spatial/LocalPose3D"))]
    conns = Any[bg_conn("c1", "signal", "n2", "g", "n1", "gA")]
    return bg_model("FemFree", nodes, conns; t_end = t_end, points = points, solver = solver,
        reltol = 1e-10, abstol = 1e-14)
end

"""
A pendulum: interface A on a compliant revolute (axis world y), released horizontal. The
fixture is soft (it sags 1.3 mm under its own weight, 1.6 % of its size): the run stops after
60 ms of the swing (0.4 mm), where the first-order stiffening is still accurate."""
function _fem_pendulum(; t_end = 0.06, solver = "Rodas5P", reltol = 1e-9, abstol = 1e-13)
    s2 = sqrt(0.5)
    kt, kr = 2.6e7, 1.0e3      # stiff for a 26 g part, but no MHz modes about its thin axis
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Axis", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = Dict{String,Any}("qw" => string(s2), "qx" => string(-s2))),
        bg_node("n3", "Hinge", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => string(kt), "kr" => string(kr))),
        # (the joint's held directions store a little strain energy; they are stiff enough that
        # it stays below 1e-6 of the swing)
        _fem_body("n4", "Body"; g0 = 9.81),
        bg_node("n5", "AxisPose", bg_ref("stdlib:spatial/LocalPose3D");
            params = Dict{String,Any}("qw" => string(s2), "qx" => string(s2))),
        bg_node("n6", "PoseA", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n7", "Free", bg_ref("stdlib:bondgraph/Se"); params = Dict{String,Any}("e" => "0.0")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "b"),
        bg_conn("c2", "bond", "n2", "a", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "A"),
        bg_conn("c4", "signal", "n5", "g", "n6", "gp"),
        bg_conn("c5", "signal", "n3", "pose", "n6", "gl"),
        bg_conn("c6", "signal", "n6", "g", "n4", "gA"),
        bg_conn("c7", "bond", "n7", "p", "n3", "drive"),
    ]
    return bg_model("FemPendulum", nodes, conns; t_end = t_end, points = 1201, solver = solver,
        reltol = reltol, abstol = abstol)
end

"""
Clamped at A: a CSpatial + RSpatial scaled to the part (each axis of the rigid part at
`fc` Hz, well above its modes, critically damped), with an optional constant wrench at B and C."""
function _fem_clamped(; q0 = zeros(FEM_NM), wB = zeros(6), wC = zeros(6), zeta = 0.0,
        stiffening = 1, t_end = 0.5, points = 2001, solver = "Rodas5P", fc = 5000.0)
    wc = 2pi * fc
    inertia = vcat(LinearAlgebra.diag(FEM_CONSTS["J0"]), fill(FEM_CONSTS["mass"], 3))
    k = inertia .* wc^2
    b = 2 .* inertia .* wc
    names_k = ("krx", "kry", "krz", "kx", "ky", "kz")
    names_b = ("brx", "bry", "brz", "bx", "by", "bz")
    nodes = Any[
        _fem_body("n1", "Body"; zeta = zeta, stiffening = stiffening,
            starts = Dict{String,Any}("core/q" => _femv(q0))),
        bg_node("n2", "Clamp", bg_ref("stdlib:multibond/CSpatial");
            params = Dict{String,Any}(p => string(v) for (p, v) in zip(names_k, k))),
        bg_node("n3", "ClampR", bg_ref("stdlib:multibond/RSpatial");
            params = Dict{String,Any}(p => string(v) for (p, v) in zip(names_b, b))),
        bg_node("n5", "Mount", bg_ref("stdlib:spatial/LocalPose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "A", "n2", "p"),
        bg_conn("c2", "bond", "n1", "A", "n3", "p"),
        bg_conn("c4", "signal", "n5", "g", "n1", "gA"),
    ]
    for (tag, port, w) in (("B", "B", wB), ("C", "C", wC))
        any(!iszero, w) || continue
        push!(nodes, bg_node("L$tag", "Load$tag", bg_ref("stdlib:multibond/ExternalWrenchSpatial")))
        push!(conns, bg_conn("cl$tag", "bond", "L$tag", "p", "n1", port))
        for (i, (p, v)) in enumerate(zip(("tx", "ty", "tz", "fx", "fy", "fz"), w))
            push!(nodes, bg_node("k$tag$i", "W$tag$i", bg_ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => string(v))))
            push!(conns, bg_conn("w$tag$i", "signal", "k$tag$i", "y", "L$tag", p))
        end
    end
    return bg_model("FemClamped", nodes, conns; t_end = t_end, points = points, solver = solver,
        reltol = 1e-9, abstol = 1e-14)
end
