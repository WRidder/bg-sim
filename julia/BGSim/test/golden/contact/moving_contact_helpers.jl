# Shared model builders of the MovingPlaneContact tests (the golden test and the C export test).
# Included by those files, not by the golden walk (the file name does not start with `test_`).
module MovingContactRigs

using ..BondGraphGolden

export MPC_R, MPC_M, MPC_J, MPC_G0, mpc_x_of_force, mpc_belt_model, mpc_clamp_model

const MPC_R = 0.025                       # ball radius (m)
const MPC_M = 0.5                         # ball mass (kg)
const MPC_J = 0.4 * MPC_M * MPC_R^2       # solid sphere
const MPC_G0 = 9.81
const MPC_K = 1.0e5                       # N/m at xref
const MPC_XREF = 1.0e-4

"""Penetration of the Hertz law `F = k x sqrt(x/xref)` for the force `F`."""
mpc_x_of_force(F; k = MPC_K, xref = MPC_XREF) = (F * sqrt(xref) / k)^(2 / 3)

_s(v) = string(Float64(v))

function _cp(; mu, k = MPC_K, c = 2.0, vs = 1.0e-3, geom...)
    d = Dict{String,Any}("k" => _s(k), "xref" => _s(MPC_XREF), "c" => _s(c), "mu" => _s(mu),
        "vs" => _s(vs), "eps" => "1.0e-6", "feps" => "1.0e-6", "r" => _s(MPC_R))
    for (key, v) in geom
        d[String(key)] = _s(v)
    end
    return d
end

function _ball!(nodes, conns, z0)
    push!(nodes, bg_node("b", "Ball", bg_ref("stdlib:spatial/RigidBody3D");
        params = Dict{String,Any}("m" => _s(MPC_M), "J" => "[$(MPC_J), $(MPC_J), $(MPC_J)]",
            "g0" => _s(MPC_G0)),
        starts = Dict{String,Any}("inertia/P" => "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]")))
    push!(nodes, bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
        starts = Dict{String,Any}("pz" => _s(z0))))
    push!(conns, bg_conn("cb1", "signal", "b", "V", "pose", "tw"))
    push!(conns, bg_conn("cb2", "signal", "pose", "g", "b", "g"))
end

function _contact!(nodes, conns, id, name, params)
    push!(nodes, bg_node("m$id", "Mount$name", bg_ref("stdlib:multibond/FixedTransform3DNeutral")))
    push!(nodes, bg_node(id, name, bg_ref("stdlib:contact/MovingPlaneContact"); params = params))
    push!(conns, bg_conn("cm$id", "bond", "b", "p", "m$id", "b"))
    push!(conns, bg_conn("cp$id", "bond", "m$id", "a", id, "p"))
    push!(conns, bg_conn("cg$id", "signal", "pose", "g", id, "g"))
end

function _const!(nodes, id, value)
    push!(nodes, bg_node(id, uppercase(id), bg_ref("stdlib:sources/Constant");
        params = Dict{String,Any}("value" => _s(value))))
end

"""
    mpc_belt_model(; V, t_belt, w1, mu, t_end)

A ball (r = 25 mm, 0.5 kg) resting on a horizontal face that starts to move along x at
`t_belt` with the speed `V` (a belt: the face is carried by the carrier, its slide is held by
a `Fixed`). The face is `2 w1` long along x and centred under the ball at the start. The
ball first slips, then rolls at 2V/7 (solid sphere), and falls off the face's back edge when
the face has moved `w1` further than the ball.
"""
function mpc_belt_model(; V = 0.2, t_belt = 0.3, w1 = 0.08, mu = 0.5, t_end = 1.2, points = 1201)
    nodes, conns = Any[], Any[]
    z0 = MPC_R - mpc_x_of_force(MPC_M * MPC_G0)
    _ball!(nodes, conns, z0)
    _contact!(nodes, conns, "c", "Belt",
        _cp(mu = mu, nx = 0, ny = 0, nz = 1, tx = 1, ty = 0, tz = 0, ax = 0, ay = 0, az = 1,
            w1 = w1, w2 = 1.0, we = 5.0e-4))
    push!(nodes, bg_node("px", "PX", bg_ref("stdlib:sources/Ramp");
        params = Dict{String,Any}("t_start" => _s(t_belt), "slope" => _s(V))))
    push!(nodes, bg_node("vx", "VX", bg_ref("stdlib:sources/Step");
        params = Dict{String,Any}("t_step" => _s(t_belt), "initial" => "0.0", "final" => _s(V))))
    _const!(nodes, "zero", 0.0)
    push!(nodes, bg_node("mp", "MuxP", bg_ref("stdlib:continuous/Mux3")))
    push!(nodes, bg_node("mv", "MuxV", bg_ref("stdlib:continuous/Mux3")))
    push!(nodes, bg_node("fix", "Fix", bg_ref("stdlib:translation/Fixed")))
    append!(conns, Any[
        bg_conn("s1", "signal", "px", "y", "mp", "u1"),
        bg_conn("s2", "signal", "zero", "y", "mp", "u2"),
        bg_conn("s3", "signal", "zero", "y", "mp", "u3"),
        bg_conn("s4", "signal", "vx", "y", "mv", "u1"),
        bg_conn("s5", "signal", "zero", "y", "mv", "u2"),
        bg_conn("s6", "signal", "zero", "y", "mv", "u3"),
        bg_conn("s7", "signal", "mp", "y", "c", "pc"),
        bg_conn("s8", "signal", "mv", "y", "c", "vc"),
        bg_conn("s9", "signal", "zero", "y", "c", "xs"),
        bg_conn("w1", "wire", "c", "j", "fix", "a"),
    ])
    return bg_model("MovingContactBelt", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-8, abstol = 1.0e-10)
end

"""
    mpc_clamp_model(; F0, t_ramp, rate, mu, t_end)

The ball held between two vertical jaw faces against gravity (no table). Both jaws are on one
slide node (their closing coordinate, as a synchronised parallel gripper): a `ForceSource`
pushes the node with `F(t) = F0 - rate max(t - t_ramp, 0)`, a 0.5 kg `Mass` gives it inertia.
Each jaw gets half the force. The jaws start at the static penetration of `F0/2`.
"""
function mpc_clamp_model(; F0 = 20.0, t_ramp = 0.2, rate = 10.0, mu = 0.5, t_end = 1.5,
    points = 1501)
    nodes, conns = Any[], Any[]
    _ball!(nodes, conns, 0.0)
    x0 = mpc_x_of_force(F0 / 2)
    for (id, name, sx) in (("ca", "JawA", 1.0), ("cb", "JawB", -1.0))
        _contact!(nodes, conns, id, name,
            _cp(mu = mu, ox = sx * MPC_R, oy = 0, oz = 0, nx = -sx, ny = 0, nz = 0,
                tx = 0, ty = 1, tz = 0, ax = -sx, ay = 0, az = 0))
    end
    push!(nodes, bg_node("car", "Carrier", bg_ref("stdlib:continuous/Mux3")))
    _const!(nodes, "zero", 0.0)
    push!(nodes, bg_node("pos", "JawPos", bg_ref("stdlib:converters/PositionSensor");
        starts = Dict{String,Any}("x" => _s(x0))))
    push!(nodes, bg_node("mass", "JawMass", bg_ref("stdlib:translation/Mass");
        params = Dict{String,Any}("m" => "0.5")))
    push!(nodes, bg_node("fs", "Push", bg_ref("stdlib:translation/ForceSource")))
    push!(nodes, bg_node("ramp", "FRamp", bg_ref("stdlib:sources/Ramp");
        params = Dict{String,Any}("t_start" => _s(t_ramp), "slope" => _s(-rate), "initial" => _s(F0))))
    push!(nodes, bg_node("fix", "Fix", bg_ref("stdlib:translation/Fixed")))
    append!(conns, Any[
        bg_conn("s1", "signal", "zero", "y", "car", "u1"),
        bg_conn("s2", "signal", "zero", "y", "car", "u2"),
        bg_conn("s3", "signal", "zero", "y", "car", "u3"),
        bg_conn("s4", "signal", "ramp", "y", "fs", "u"),
        bg_conn("w1", "wire", "fs", "b", "mass", "a"),
        bg_conn("w2", "wire", "fs", "a", "fix", "a"),
        bg_conn("w3", "wire", "mass", "b", "fix", "a"),
        bg_conn("w4", "wire", "mass", "a", "pos", "a"),
        bg_conn("w5", "wire", "mass", "a", "ca", "j"),
        bg_conn("w6", "wire", "mass", "a", "cb", "j"),
    ])
    for id in ("ca", "cb")
        append!(conns, Any[
            bg_conn("p$id", "signal", "car", "y", id, "pc"),
            bg_conn("v$id", "signal", "car", "y", id, "vc"),
            bg_conn("x$id", "signal", "pos", "y", id, "xs"),
        ])
    end
    return bg_model("MovingContactClamp", nodes, conns; t_end = t_end, points = points,
        reltol = 1.0e-8, abstol = 1.0e-10)
end

end
