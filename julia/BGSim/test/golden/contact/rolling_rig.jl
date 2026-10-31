# Shared rig of the RollingDisk and Rotor3D tests (golden/contact/test_RollingDisk.jl,
# golden/spatial/test_Rotor3D.jl, test_export_rolling.jl).
#
# A wheel is a `RigidBody3D` (body frame at the centre, axle = body z) whose pose comes from a
# `PoseIntegrator3D` on its twist; its port is bonded straight to a `RollingDisk` on a
# `ContactSurface` (the plane z = 0) and, optionally, to a `Rotor3D` driven by an effort source.
# The start pose is the axle along world +y rotated about world x by `lean`, so body x is the
# rolling direction and the body twist of a wheel rolling at `v` is `w = v/R` about body z.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden
using LinearAlgebra

const _RR_G0 = 9.81
const _RR_K = 1.0e6
const _RR_XREF = 1.0e-3
const _RR_EPS = 1.0e-6

_rr_d(kv...) = Dict{String,Any}(kv...)
_rr_vec(v) = "[" * join(string.(Float64.(collect(v))), ", ") * "]"

"""Static smooth penetration of the Hertz spring under the force `F`, as the signed `delta`
(inverse of `F = k x sqrt(x/xref)` and `x = (d + sqrt(d^2 + eps^2))/2`)."""
function _rr_delta(F; k = _RR_K)
    x = (F / k * sqrt(_RR_XREF))^(2 / 3)
    return x - _RR_EPS^2 / (4x)
end

"""
    _rr_wheel(; R, m, J, v, w, P0, lean, rotor, h0, tau, tau_input, outputs, mu, c, bsp, crown,
              t_end, points)

The wheel rig as a model document. The wheel starts at the static penetration of its weight
(`m g`). The start momentum is `P0` when given, else the rolling twist `w = v/R` about the
axle and the velocity `v` along body x (plus the rotor's axial momentum `h0`, which lives in
the `Rotor3D` and not in the body). `tau` is the rotor torque (an `Se`), or the value of an
`ExportInput` named "tau" when `tau_input` is set; `outputs` lists `(name, block, port)` that
become `ExportOutput`s.
"""
function _rr_wheel(; R = 0.2, m = 2.0, J = (0.02, 0.02, 0.04), v = 1.0, w = v / R, P0 = nothing,
    lean = 0.0, rotor = false, Ja = 0.003, h0 = 0.0, tau = 0.0, tau_input = false, outputs = (),
    mu = 0.8, c = 2.0, bsp = 0.0, crown = 0.0, t_end = 1.0, points = 201, reltol = 1.0e-9,
    abstol = 1.0e-11, name = "RollingRig")
    th = -pi / 2 + lean
    q = (cos(th / 2), sin(th / 2), 0.0, 0.0)
    delta = _rr_delta(m * _RR_G0)
    pz = R * cos(lean) + crown - delta          # the crown tube's lowest point on the plane
    P = P0 === nothing ? (0.0, 0.0, J[3] * w, m * v, 0.0, 0.0) : P0
    nodes = Any[
        bg_node("b", "Wheel", bg_ref("stdlib:spatial/RigidBody3D");
            params = _rr_d("m" => string(m), "J" => _rr_vec(J), "g0" => string(_RR_G0)),
            starts = _rr_d("inertia/P" => _rr_vec(P))),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = _rr_d("qw" => string(q[1]), "qx" => string(q[2]), "qy" => string(q[3]),
                "qz" => string(q[4]), "px" => "0.0", "py" => "0.0", "pz" => string(pz))),
        bg_node("s", "Floor", bg_ref("stdlib:contact/ContactSurface")),
        bg_node("c", "Tyre", bg_ref("stdlib:contact/RollingDisk");
            params = _rr_d("radius" => string(R), "crown" => string(crown), "k" => string(_RR_K),
                "xref" => string(_RR_XREF), "c" => string(c), "mu" => string(mu),
                "bsp" => string(bsp), "eps" => string(_RR_EPS))),
    ]
    conns = Any[
        bg_conn("c1", "signal", "b", "V", "pose", "tw"),
        bg_conn("c2", "signal", "pose", "g", "b", "g"),
        bg_conn("c3", "bond", "b", "p", "c", "p"),
        bg_conn("c4", "signal", "pose", "g", "c", "g"),
        bg_conn("c5", "signal", "s", "o", "c", "o"),
        bg_conn("c6", "signal", "s", "fr", "c", "fr"),
    ]
    if rotor
        push!(nodes, bg_node("r", "Rotor", bg_ref("stdlib:spatial/Rotor3D");
            params = _rr_d("Ja" => string(Ja)), starts = _rr_d("h" => string(h0))))
        push!(conns, bg_conn("c7", "bond", "b", "p", "r", "p"))
        if tau_input
            push!(nodes, bg_node("ti", "tau", bg_ref("stdlib:converters/ExportInput");
                params = _rr_d("value" => string(tau))))
            push!(nodes, bg_node("se", "Motor", bg_ref("stdlib:bondgraph/MSe")))
            push!(conns, bg_conn("c8", "signal", "ti", "y", "se", "u"))
        else
            push!(nodes, bg_node("se", "Motor", bg_ref("stdlib:bondgraph/Se"); params = _rr_d("e" => string(tau))))
        end
        push!(conns, bg_conn("c9", "bond", "se", "p", "r", "drive"))
    end
    for (k, (oname, blk, port)) in enumerate(outputs)
        push!(nodes, bg_node("o$k", oname, bg_ref("stdlib:converters/ExportOutput")))
        push!(conns, bg_conn("co$k", "signal", blk, port, "o$k", "u"))
    end
    return bg_model(name, nodes, conns; t_end = t_end, points = points, reltol = reltol, abstol = abstol)
end

"""Cumulative integral on a uniform grid (Simpson on pairs of cells, fourth order)."""
function _rr_cumint(t, y)
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

"""Mechanical energy of the wheel body (kinetic from the recorded momentum and twist, plus
gravity) at every sample."""
function _rr_body_energy(cols, m)
    n = length(cols["time"])
    return [0.5 * sum(cols["Wheel/inertia/P[$k]"][i] * cols["Pose/tw[$k]"][i] for k in 1:6) +
            m * _RR_G0 * cols["Pose/pz"][i] for i in 1:n]
end
