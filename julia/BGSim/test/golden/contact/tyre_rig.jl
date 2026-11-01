# Shared rigs of the Tyre and TerrainSurface tests (golden/contact/test_Tyre.jl,
# golden/contact/test_TerrainSurface.jl, test_export_tyre.jl).
#
# * `_ty_kinematic`: the tyre on a prescribed carrier motion (an `SfSpatial` imposes the carrier
#   twist, an `Sf` the wheel spin relative to the carrier), so the slips are set exactly and the
#   steady state is the Magic Formula of the block's header.
# * `_ty_wheel`: a free wheel: a `RigidBody3D` carrier (mass, transverse inertia) with a
#   `Rotor3D` (axial inertia) and the `Tyre`, the rotor's drive and the tyre's spin on one
#   1-junction, on the flat `ContactSurface` or a `TerrainSurface`.
#
# The carrier frame has its origin at the wheel centre and z along the axle: the start
# orientation is Rx(-90 deg), so body x = world x (rolling direction), body z = world y.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const _TY_G0 = 9.81
_ty_d(kv...) = Dict{String,Any}(kv...)
_ty_vec(v) = "[" * join(string.(Float64.(collect(v))), ", ") * "]"

const _TY_VEC6 = """
@block TyVec6 begin
    @parameters begin
        c1::Real = 0.0
        c2::Real = 0.0
        c3::Real = 0.0
        c4::Real = 0.0
        c5::Real = 0.0
        c6::Real = 0.0
    end
    @outputs y::Vec{6}
    @equations begin
        y[1] ~ c1
        y[2] ~ c2
        y[3] ~ c3
        y[4] ~ c4
        y[5] ~ c5
        y[6] ~ c6
    end
end
"""

"""Default parameters of the stdlib Tyre (keep in sync with stdlib/contact/Tyre.jl)."""
const _TY_P = (R0 = 0.3, kz = 2.5e5, cz = 500.0, Fz0 = 3000.0, mux = 1.0, muy = 1.0, dmu = -0.1,
    Kx = 20.0, Cx = 1.6, Ex = 0.0, Ky = 20.0, Ky2 = 2.0, Cy = 1.4, Ey = 0.0, cx = 3.0e5, cy = 1.5e5,
    dx = 1500.0, dy = 1000.0, frr = 0.012, wrr = 1.0, vN = 0.2, seps = 1.0e-3)

"""Steady-state tyre forces (Fx, Fy) at load Fz and slips kappa, s_y = tan(alpha), written
from the formulas (not from the block): Magic Formula per direction, combined by normalised
slip."""
function _ty_forces(Fz, kappa, sy; p = _TY_P, mus = 1.0)
    dfz = (Fz - p.Fz0) / p.Fz0
    sc = max(1 + p.dmu * dfz, 0.1)
    mx = mus * p.mux * sc
    my = mus * p.muy * sc
    Tx = tan(pi / (2 * p.Cx))
    Ty = tan(pi / (2 * p.Cy))
    Bx = p.Kx / (p.Cx * mx)
    By = p.Ky * p.Fz0 * sin(2 * atan(Fz / (p.Ky2 * p.Fz0))) / (p.Cy * my * Fz)
    nx = kappa / (Tx / Bx)
    ny = sy / (Ty / By)
    S = sqrt(nx^2 + ny^2 + p.seps^2)
    X = Tx * S
    Y = Ty * S
    Fx0 = mx * Fz * sin(p.Cx * atan(X - p.Ex * (X - atan(X))))
    Fy0 = my * Fz * sin(p.Cy * atan(Y - p.Ey * (Y - atan(Y))))
    return Fx0 * nx / S, Fy0 * ny / S
end

const _TY_Q_AXLE = (cos(-pi / 4), sin(-pi / 4), 0.0, 0.0)   # Rx(-90 deg): body z = world y

"""
    _ty_kinematic(; vx, vy, w_rel, z, mus, t_end, points)

The tyre on a prescribed motion: the carrier moves at (vx, vy) (world x, y) with its centre at
height `z` over the plane z = 0, and the wheel spins at `w_rel` relative to the carrier
(forward rolling positive)."""
function _ty_kinematic(; vx = 20.0, vy = 0.0, w_rel = 20.0 / 0.288, z = 0.288, mus = 1.0, t_end = 1.0,
    points = 101, name = "TyreKinematic")
    # SfSpatial imposes its flow on the bond to the tyre port; the tyre's port flow is minus
    # the carrier twist (bond from the source to the tyre), and the body frame is the carrier
    # frame: body x = world x, body y = -world z, body z = world y.
    nodes = Any[
        bg_node("v", "Twist", _ty_d("inline" => _ty_d("source" => _TY_VEC6));
            params = _ty_d("c4" => string(vx), "c5" => "0.0", "c6" => string(vy))),
        bg_node("sf", "Carrier", bg_ref("stdlib:multibond/SfSpatial")),
        bg_node("ws", "Spin", bg_ref("stdlib:bondgraph/Sf"); params = _ty_d("f" => string(-w_rel))),
        bg_node("g", "Pose", bg_ref("stdlib:spatial/LocalPose3D");
            params = _ty_d("qw" => string(_TY_Q_AXLE[1]), "qx" => string(_TY_Q_AXLE[2]), "qy" => "0.0",
                "qz" => "0.0", "x" => "0.0", "y" => "0.0", "z" => string(z))),
        bg_node("s", "Floor", bg_ref("stdlib:contact/ContactSurface")),
        bg_node("m", "Mu", bg_ref("stdlib:sources/Constant"); params = _ty_d("value" => string(mus))),
        bg_node("t", "Tyre", bg_ref("stdlib:contact/Tyre")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "v", "y", "sf", "u"),
        bg_conn("c2", "bond", "sf", "p", "t", "p"),
        bg_conn("c3", "bond", "ws", "p", "t", "spin"),
        bg_conn("c4", "signal", "g", "g", "t", "g"),
        bg_conn("c5", "signal", "s", "o", "t", "o"),
        bg_conn("c6", "signal", "s", "fr", "t", "fr"),
        bg_conn("c7", "signal", "m", "y", "t", "mus"),
    ]
    return bg_model(name, nodes, conns; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""
    _ty_wheel(; m, J, Ja, v, slope, frr, t_end, points, outputs, brake_input)

A free wheel of mass `m` (carrier transverse inertia `J`, rotor axial inertia `Ja`) rolling at
`v` along world x. On the flat floor (`slope = 0`, a ContactSurface) or on the plane
z = slope x (a TerrainSurface), started at the static deflection under its weight. `outputs`
lists `(name, node, port)` that become ExportOutputs; `brake_input` adds an ExportInput named
"brake" (a torque on the spin junction through an MSe)."""
function _ty_wheel(; m = 300.0, J = (8.0, 8.0, 0.5), Ja = 1.2, v = 10.0, slope = 0.0, frr = 0.012,
    t_end = 2.0, points = 201, outputs = (), brake_input = false, name = "TyreWheel")
    p = _TY_P
    gam = atan(slope)
    Fz = m * _TY_G0 * cos(gam)
    Rl = p.R0 - Fz / p.kz
    w = v / Rl
    # wheel centre on the normal through the origin, the axle along world y
    px = -Rl * sin(gam)
    pz = Rl * cos(gam)
    nodes = Any[
        bg_node("b", "Carrier", bg_ref("stdlib:spatial/RigidBody3D");
            params = _ty_d("m" => string(m), "J" => _ty_vec(J), "g0" => string(_TY_G0)),
            starts = _ty_d("inertia/P" => _ty_vec((0.0, 0.0, 0.0, m * v, 0.0, 0.0)))),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = _ty_d("qw" => string(_TY_Q_AXLE[1]), "qx" => string(_TY_Q_AXLE[2]), "qy" => "0.0",
                "qz" => "0.0", "px" => string(px), "py" => "0.0", "pz" => string(pz))),
        bg_node("r", "Wheel", bg_ref("stdlib:spatial/Rotor3D"); params = _ty_d("Ja" => string(Ja)),
            starts = _ty_d("h" => string(Ja * w))),
        bg_node("t", "Tyre", bg_ref("stdlib:contact/Tyre"); params = _ty_d("frr" => string(frr))),
        bg_node("j", "Spin", _ty_d("junction" => "1")),
        bg_node("m", "Mu", bg_ref("stdlib:sources/Constant"); params = _ty_d("value" => "1.0")),
    ]
    conns = Any[
        bg_conn("c1", "signal", "b", "V", "pose", "tw"),
        bg_conn("c2", "signal", "pose", "g", "b", "g"),
        bg_conn("c3", "bond", "b", "p", "r", "p"),
        bg_conn("c4", "bond", "b", "p", "t", "p"),
        bg_conn("c5", "signal", "pose", "g", "t", "g"),
        bg_conn("c6", "bond", "j", nothing, "r", "drive"),
        bg_conn("c7", "bond", "j", nothing, "t", "spin"),
        bg_conn("c8", "signal", "m", "y", "t", "mus"),
    ]
    if slope == 0.0
        push!(nodes, bg_node("s", "Floor", bg_ref("stdlib:contact/ContactSurface")))
    else
        push!(nodes, bg_node("s", "Floor", bg_ref("stdlib:contact/TerrainSurface");
            params = _ty_d("sx" => string(slope), "a" => "[0.0, 0.0]")))
        push!(conns, bg_conn("c9", "signal", "pose", "g", "s", "g"))
    end
    push!(conns, bg_conn("c10", "signal", "s", "o", "t", "o"))
    push!(conns, bg_conn("c11", "signal", "s", "fr", "t", "fr"))
    if brake_input
        push!(nodes, bg_node("bi", "brake", bg_ref("stdlib:converters/ExportInput"); params = _ty_d("value" => "0.0")))
        push!(nodes, bg_node("bs", "Brake", bg_ref("stdlib:bondgraph/MSe")))
        push!(conns, bg_conn("c12", "signal", "bi", "y", "bs", "u"))
        push!(conns, bg_conn("c13", "bond", "bs", "p", "j", nothing))
    end
    for (k, (oname, blk, port)) in enumerate(outputs)
        push!(nodes, bg_node("o$k", oname, bg_ref("stdlib:converters/ExportOutput")))
        push!(conns, bg_conn("co$k", "signal", blk, port, "o$k", "u"))
    end
    return bg_model(name, nodes, conns; t_end = t_end, points = points, reltol = 1.0e-9, abstol = 1.0e-11)
end

"""Cumulative trapezoid integral."""
function _ty_cumint(t, y)
    out = zeros(length(t))
    for i in 2:length(t)
        out[i] = out[i - 1] + 0.5 * (t[i] - t[i - 1]) * (y[i] + y[i - 1])
    end
    return out
end
