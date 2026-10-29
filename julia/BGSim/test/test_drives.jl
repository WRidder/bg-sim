# Work packages J-MB11/J-MB12: electric and current-controlled drives and their tests
# (plan 6, Phase D). `stdlib/drives/` holds composites of the documented electrical/rotation
# primitives only: `ElectricDrive`, `CurrentControlledDrive`, `Gearbox`, `ReactionWheel`.
#
#   * locked rotor: the current step reaches `(u/R_w)(1 - e^-1)` at `tau = L/R_w` and settles
#     at `u/R_w`; the torque tap is `k_t i`;
#   * no load, zero friction: the speed settles at `u/k_t`, on a free shaft and on a planar
#     joint carrying a body;
#   * power balance of a driven gearbox load: `E_el = E_R + E_b + E_L + E_J + E_mech`, with the
#     energies integrated inside the model;
#   * reflected rotor inertia: a torque step on the gearbox output accelerates it by
#     `T / (J_L + N^2 J_m)`;
#   * reaction wheel on a planar pivot with gravity off: the housing sees `-tau`, the total
#     angular momentum of body plus wheel stays zero;
#   * every block is catalog-clean and every model is error-free.
#
# Tolerances: relative 1e-9 for algebraic identities, 1e-6 for integrated trajectories over
# 10 s (Rodas5P, reltol 1e-10, abstol 1e-12). A locked rotor is derivative-causal on the
# rotor inertia (the shaft flow is imposed), so the locked models use a `SpeedSource` at zero
# speed and the documented W201 of that structure is asserted, not hidden.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

_dr_p(d...) = Dict{String,Any}(d...)
_dr_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_dr_codes(result) = [d.code for d in result.diagnostics]

const _DR_DRIVE_REFS = ["stdlib:drives/CurrentControlledDrive", "stdlib:drives/ElectricDrive",
    "stdlib:drives/Gearbox", "stdlib:drives/ReactionWheel"]

"""Run a model document through the real pipeline and assert it is error-free."""
function _dr_run(doc)
    columns, result, flat = bg_run(doc)
    @test result.status == "done"
    @test isempty(_dr_errors(result))
    return columns, result, flat
end

"""The drive's own parameters as node params."""
_dr_drive_params(; R = 2.0, L = 0.01, k = 0.1, J = 1e-3, b = 0.0) = _dr_p("R_w" => string(R),
    "L" => string(L), "k_t" => string(k), "J_m" => string(J), "b_m" => string(b))

_dr_const(id, name, v) = bg_node(id, name, bg_ref("stdlib:sources/Constant");
    params = _dr_p("value" => string(v)))

# ---------------------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------------------

"""Locked rotor: `ElectricDrive` against a zero-speed `SpeedSource`."""
function _dr_locked(; u = 12.0, R = 2.0, L = 0.5, k = 0.1, t_end = 10.0, points = 4001)
    return bg_model("Locked", [
            _dr_const("n1", "V", u),
            bg_node("n2", "Drv", bg_ref("stdlib:drives/ElectricDrive");
                params = _dr_drive_params(R = R, L = L, k = k)),
            bg_node("n3", "Lock", bg_ref("stdlib:rotation/SpeedSource")),
            _dr_const("n4", "Zero", 0.0),
        ], [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "shaft", "n3", "a"),
            bg_conn("c3", "signal", "n4", "y", "n3", "u"),
        ]; t_end = t_end, points = points, reltol = 1e-10, abstol = 1e-12)
end

"""No load, zero friction: the shaft meets a zero-torque source on a fixed frame."""
function _dr_noload(; u = 12.0, R = 2.0, L = 0.01, k = 0.1, J = 1e-3)
    return bg_model("NoLoad", [
            _dr_const("n1", "V", u),
            bg_node("n2", "Drv", bg_ref("stdlib:drives/ElectricDrive");
                params = _dr_drive_params(R = R, L = L, k = k, J = J)),
            bg_node("n3", "Free", bg_ref("stdlib:rotation/TorqueSource");
                params = _dr_p("T" => "0.0")),
            _dr_const("n4", "One", 1.0),
            bg_node("n5", "Frame", bg_ref("stdlib:rotation/FixedShaft")),
        ], [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "shaft", "n3", "a"),
            bg_conn("c3", "signal", "n4", "y", "n3", "u"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
        ]; t_end = 10.0, points = 1001, reltol = 1e-10, abstol = 1e-12)
end

const _DR_PIVOT = _dr_p("rx" => "0.0", "ry" => "0.0", "kt" => "1.0e8", "bt" => "0.0",
    "k" => "0.0", "b" => "0.0", "qrest" => "0.0", "q0" => "0.0")

"""Planar nodes and connections of a free-swinging body (gravity off) on a compliant pivot:
`World -> Joint -> Link -> Body`, with the pose chain `Body.g` needs. `Joint.drive` is the
body's rotation axis."""
function _dr_body(; m = 1.0, J = 0.05, y = -0.5)
    nodes = Any[
        bg_node("b1", "World", bg_ref("stdlib:multibond/GroundPlanar")),
        bg_node("b2", "Joint", bg_ref("stdlib:planar/Revolute2DCompliant"); params = _DR_PIVOT),
        bg_node("b3", "Link", bg_ref("stdlib:planar/FixedJoint2D");
            params = _dr_p("x" => "0.0", "y" => string(y), "theta" => "0.0")),
        bg_node("b4", "Body", bg_ref("stdlib:planar/RigidBody2D");
            params = _dr_p("m" => string(m), "J" => string(J), "g0" => "0.0")),
        bg_node("b5", "Local", bg_ref("stdlib:planar/LocalPose2D");
            params = _dr_p("x" => "0.0", "y" => string(y), "theta" => "0.0")),
        bg_node("b6", "Compose", bg_ref("stdlib:multibond/ComposePose2D")),
    ]
    conns = Any[
        bg_conn("k1", "bond", "b1", "p", "b2", "parent"),
        bg_conn("k2", "bond", "b2", "child", "b3", "parent"),
        bg_conn("k3", "bond", "b3", "child", "b4", "p"),
        bg_conn("k4", "signal", "b2", "pose", "b6", "gp"),
        bg_conn("k5", "signal", "b5", "g", "b6", "gl"),
        bg_conn("k6", "signal", "b6", "g", "b4", "g"),
    ]
    return nodes, conns
end

"""`ElectricDrive` on the joint axis of a free body: the body is the whole load."""
function _dr_joint_noload(; u = 12.0, k = 0.2, J_m = 1e-3, J = 2e-3, m = 0.01)
    nodes, conns = _dr_body(m = m, J = J, y = -0.1)
    push!(nodes, _dr_const("d1", "V", u))
    push!(nodes, bg_node("d2", "Drv", bg_ref("stdlib:drives/ElectricDrive");
        params = _dr_drive_params(k = k, J = J_m)))
    push!(conns, bg_conn("e1", "signal", "d1", "y", "d2", "u"))
    # The shaft is elastic: a rotor inertia rigidly bonded to a joint that imposes the flow
    # would be derivative-causal (W201, index raised), so the drive reaches the joint through
    # a stiff damped shaft, as a real drive does.
    push!(nodes, bg_node("d3", "Shaft", bg_ref("stdlib:rotation/ElasticShaft");
        params = _dr_p("k" => "1.0e4", "d" => "2.0")))
    push!(conns, bg_conn("e2", "wire", "d2", "shaft", "d3", "a"))
    push!(conns, bg_conn("e3", "wire", "d3", "b", "b2", "drive"))
    return bg_model("JointDrive", nodes, conns; t_end = 10.0, points = 1001,
        reltol = 1e-10, abstol = 1e-12)
end

const _DR_PB = (R = 2.0, L = 0.02, k = 0.1, J = 1e-3, b = 2e-4, N = 5.0, JL = 5e-3, dL = 3e-3)

"""The driven load of the power-balance test and its in-model energy integrals:
`Drv -> Gearbox(N) -> (J_L, d_L)`, with `E_el = int P_el`, `E_R = int R i^2`,
`E_b = int b w^2`, `E_mech = int P_mech` computed by `Integrator`s of the model."""
function _dr_balance(; p = _DR_PB)
    return bg_model("Balance", [
            bg_node("n1", "V", bg_ref("stdlib:sources/Sine");
                params = _dr_p("amplitude" => "12.0", "frequency" => "3.0", "offset" => "6.0")),
            bg_node("n2", "Drv", bg_ref("stdlib:drives/ElectricDrive");
                params = _dr_drive_params(R = p.R, L = p.L, k = p.k, J = p.J, b = p.b)),
            bg_node("n3", "Gear", bg_ref("stdlib:drives/Gearbox"); params = _dr_p("N" => string(p.N))),
            bg_node("n4", "Load", bg_ref("stdlib:rotation/Inertia"); params = _dr_p("J" => string(p.JL))),
            bg_node("n5", "LoadDamp", bg_ref("stdlib:rotation/RotationalDamper");
                params = _dr_p("d" => string(p.dL))),
            bg_node("n6", "Frame", bg_ref("stdlib:rotation/FixedShaft")),
            bg_node("n7", "IEl", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n8", "IMech", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n9", "SqI", bg_ref("stdlib:continuous/Product")),
            bg_node("n10", "SqW", bg_ref("stdlib:continuous/Product")),
            bg_node("n11", "IR", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n12", "IB", bg_ref("stdlib:continuous/Integrator")),
            bg_node("n13", "GR", bg_ref("stdlib:continuous/Gain"); params = _dr_p("k" => string(p.R))),
            bg_node("n14", "GB", bg_ref("stdlib:continuous/Gain"); params = _dr_p("k" => string(p.b))),
        ], [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "shaft", "n3", "a"),
            bg_conn("c3", "wire", "n3", "b", "n4", "a"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
            bg_conn("c5", "wire", "n4", "b", "n6", "a"),
            bg_conn("c6", "wire", "n5", "b", "n6", "a"),
            bg_conn("c7", "signal", "n2", "P_el", "n7", "u"),
            bg_conn("c8", "signal", "n2", "P_mech", "n8", "u"),
            bg_conn("c9", "signal", "n2", "i", "n9", "u1"),
            bg_conn("c10", "signal", "n2", "i", "n9", "u2"),
            bg_conn("c11", "signal", "n2", "w", "n10", "u1"),
            bg_conn("c12", "signal", "n2", "w", "n10", "u2"),
            bg_conn("c13", "signal", "n9", "y", "n13", "u"),
            bg_conn("c14", "signal", "n10", "y", "n14", "u"),
            bg_conn("c15", "signal", "n13", "y", "n11", "u"),
            bg_conn("c16", "signal", "n14", "y", "n12", "u"),
        ]; t_end = 10.0, points = 1001, reltol = 1e-10, abstol = 1e-12)
end
"""Reflected inertia: `CurrentControlledDrive` (zero current) -> `Gearbox(N)` -> optional load
inertia `J_L`, with a constant torque at the output. `TorqueSource` has `a.e = T u`, the effort
*into* the port, so a negative `T` accelerates the shaft in the positive direction."""
function _dr_reflected(; N = 7.0, J_m = 2e-3, J_L = 5e-3, T = -0.4, load = true)
    nodes = Any[
        _dr_const("n1", "Iref", 0.0),
        bg_node("n2", "Drv", bg_ref("stdlib:drives/CurrentControlledDrive");
            params = _dr_p("k_t" => "0.1", "J_m" => string(J_m), "b_m" => "0.0")),
        bg_node("n3", "Gear", bg_ref("stdlib:drives/Gearbox"); params = _dr_p("N" => string(N))),
        bg_node("n5", "Frame", bg_ref("stdlib:rotation/FixedShaft")),
        bg_node("n6", "Push", bg_ref("stdlib:rotation/TorqueSource"); params = _dr_p("T" => string(T))),
        _dr_const("n7", "One", 1.0),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "i_ref"),
        bg_conn("c2", "wire", "n2", "shaft", "n3", "a"),
        bg_conn("c5", "wire", "n3", "b", "n6", "a"),
        bg_conn("c6", "wire", "n6", "b", "n5", "a"),
        bg_conn("c7", "signal", "n7", "y", "n6", "u"),
    ]
    if load
        push!(nodes, bg_node("n4", "Load", bg_ref("stdlib:rotation/Inertia");
            params = _dr_p("J" => string(J_L))))
        push!(conns, bg_conn("c3", "wire", "n3", "b", "n4", "a"))
        push!(conns, bg_conn("c4", "wire", "n4", "b", "n5", "a"))
    end
    return bg_model("Reflected", nodes, conns; t_end = 1.0, points = 101,
        reltol = 1e-10, abstol = 1e-12)
end

"""`CurrentControlledDrive` on a free shaft with a constant current reference."""
function _dr_ccd(; i_ref = 2.0, k = 0.1, J = 2e-3, b = 0.0)
    return bg_model("CurrentDrive", [
            _dr_const("n1", "Iref", i_ref),
            bg_node("n2", "Drv", bg_ref("stdlib:drives/CurrentControlledDrive");
                params = _dr_p("k_t" => string(k), "J_m" => string(J), "b_m" => string(b))),
            bg_node("n3", "Free", bg_ref("stdlib:rotation/TorqueSource"); params = _dr_p("T" => "0.0")),
            _dr_const("n4", "One", 1.0),
            bg_node("n5", "Frame", bg_ref("stdlib:rotation/FixedShaft")),
        ], [
            bg_conn("c1", "signal", "n1", "y", "n2", "i_ref"),
            bg_conn("c2", "wire", "n2", "shaft", "n3", "a"),
            bg_conn("c3", "signal", "n4", "y", "n3", "u"),
            bg_conn("c4", "wire", "n3", "b", "n5", "a"),
        ]; t_end = 10.0, points = 1001, reltol = 1e-10, abstol = 1e-12)
end

const _DR_RW = (R = 2.0, L = 0.02, k = 0.1, Jw = 2e-3, m = 1.0, J = 0.05, y = -0.5)

"""Reaction wheel on a free body: `Joint.drive` is the body's rotation axis, the wheel's
`housing` port is wired to it, and the drive runs from a voltage step at 0.5 s. The pivot is
stiff (`kt = 1e10`): the momentum error of the compliant pivot scales as `1/kt`. With
`fixed_housing` the wheel sits on a clamped housing instead (no body)."""
function _dr_wheel(; p = _DR_RW, u = 6.0, t_end = 10.0, points = 1001, fixed_housing = false)
    nodes, conns = fixed_housing ? (Any[], Any[]) : _dr_body(m = p.m, J = p.J, y = p.y)
    fixed_housing || (nodes[2]["params"]["kt"] = "1.0e10")
    push!(nodes, bg_node("w1", "Volts", bg_ref("stdlib:sources/Step");
        params = _dr_p("t_step" => "0.5", "initial" => "0.0", "final" => string(u))))
    push!(nodes, bg_node("w2", "RW", bg_ref("stdlib:drives/ReactionWheel");
        params = _dr_p("R_w" => string(p.R), "L" => string(p.L), "k_t" => string(p.k),
            "J_w" => string(p.Jw), "b_m" => "0.0")))
    push!(conns, bg_conn("e1", "signal", "w1", "y", "w2", "u"))
    if fixed_housing
        push!(nodes, bg_node("w3", "Frame", bg_ref("stdlib:rotation/FixedShaft")))
        push!(conns, bg_conn("e2", "wire", "w2", "housing", "w3", "a"))
    else
        push!(conns, bg_conn("e2", "wire", "w2", "housing", "b2", "drive"))
    end
    return bg_model("Wheel", nodes, conns; t_end = t_end, points = points,
        reltol = 1e-10, abstol = 1e-12)
end

_dr_check(doc) = Compile.model_check(IR.parse_model(doc))

"""Largest relative deviation `max |a - b| / max |b|`."""
_dr_rel(a, b) = maximum(abs.(a .- b)) / maximum(abs.(b))

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J-MB11/J-MB12 drives" begin
    @testset "the drives group is catalog-clean" begin
        blocks = Dict(b.ref => b for b in Library.load_stdlib())
        for ref in _DR_DRIVE_REFS
            b = blocks[ref]
            @test b.group == "Drives"
            @test isempty(b.diagnostics)
            @test !isempty(b.description)
            @test !isempty(b.icon)
        end
        ed = blocks["stdlib:drives/ElectricDrive"]
        @test [(p.name, p.domain) for p in ed.interface.ports] == [("shaft", "Rotation")]
        @test [(i.name, i.unit) for i in ed.interface.inputs] == [("u", "V")]
        @test [(o.name, o.unit) for o in ed.interface.outputs] ==
              [("i", "A"), ("w", "rad/s"), ("tau", "N*m"), ("P_el", "W"), ("P_mech", "W")]
        @test [p.name for p in ed.interface.parameters] == ["R_w", "L", "k_t", "J_m", "b_m"]
        rw = blocks["stdlib:drives/ReactionWheel"]
        @test [(p.name, p.domain) for p in rw.interface.ports] == [("housing", "Rotation")]
        gb = blocks["stdlib:drives/Gearbox"]
        @test [(p.name, p.domain) for p in gb.interface.ports] ==
              [("a", "Rotation"), ("b", "Rotation")]
        for doc in (_dr_locked(), _dr_noload(), _dr_joint_noload(), _dr_balance(),
            _dr_reflected(), _dr_ccd(), _dr_wheel())
            @test isempty(_dr_errors(_dr_check(doc)))
        end
    end

    @testset "locked rotor: current step L/R_w and steady u/R_w" begin
        u, R, L, k = 12.0, 2.0, 0.5, 0.1
        columns, result, _ = _dr_run(_dr_locked(u = u, R = R, L = L, k = k))
        # The locked rotor is derivative-causal on the rotor inertia: exactly this W201.
        @test _dr_codes(result) == ["W201"]
        t = columns["time"]
        i = columns["Drv/isense/y"]
        exact = (u / R) .* (1 .- exp.(-t .* R ./ L))
        @test _dr_rel(i, exact) <= 1e-9
        j = findfirst(x -> abs(x - L / R) <= 1e-9, t)
        @test j !== nothing
        @test isapprox(i[j], (u / R) * (1 - exp(-1)); rtol = 1e-9)
        @test isapprox(i[end], u / R; rtol = 1e-9)
        # `tau = k_t i` at the shaft, the shaft does not move, and `P_el = u i`.
        @test _dr_rel(columns["Drv/tsense/y"], k .* i) <= 1e-9
        @test maximum(abs.(columns["Drv/wsense/y"])) <= 1e-12
        @test _dr_rel(columns["Drv/pel/y"], u .* i) <= 1e-9
        @test maximum(abs.(columns["Drv/pmech/y"])) <= 1e-9
        println("J-MB12 locked: i(L/R)/(u/R) = ", i[j] / (u / R), " (1 - e^-1 = ", 1 - exp(-1),
            "), max rel error vs analytic ", _dr_rel(i, exact))
    end

    @testset "no load, no friction: speed u/k_t" begin
        u, k = 12.0, 0.1
        columns, result, _ = _dr_run(_dr_noload(u = u, k = k))
        @test isempty(_dr_codes(result))
        w = columns["Drv/wsense/y"]
        @test isapprox(w[end], u / k; rtol = 1e-9)
        @test abs(columns["Drv/isense/y"][end]) <= 1e-9
        @test abs(columns["Drv/tsense/y"][end]) <= 1e-9
        println("J-MB12 no-load: w(10 s) = ", w[end], " vs u/k_t = ", u / k)

        # The same drive on a planar joint carrying a body (through its elastic shaft).
        columns, result, _ = _dr_run(_dr_joint_noload(u = u, k = 0.2))
        @test isempty(_dr_codes(result))
        @test isapprox(columns["Joint/qdout"][end], u / 0.2; rtol = 1e-9)
        @test isapprox(columns["Drv/wsense/y"][end], u / 0.2; rtol = 1e-9)
    end

    @testset "current-controlled drive: torque k_t i_ref, rotor inertia, viscous loss" begin
        i_ref, k, J = 2.0, 0.1, 2e-3
        columns, result, _ = _dr_run(_dr_ccd(i_ref = i_ref, k = k, J = J))
        @test isempty(_dr_codes(result))
        t = columns["time"]
        # Frictionless: constant acceleration k i_ref / J_m.
        @test _dr_rel(columns["Drv/wsense/y"], (k * i_ref / J) .* t) <= 1e-9
        @test _dr_rel(columns["Drv/tmotor/y"], fill(k * i_ref, length(t))) <= 1e-9
        @test _dr_rel(columns["Drv/isense/y"], fill(i_ref, length(t))) <= 1e-9
        # Viscous loss: first order to k i_ref / b_m with time constant J_m / b_m.
        b = 0.01
        columns, _, _ = _dr_run(_dr_ccd(i_ref = i_ref, k = k, J = J, b = b))
        t = columns["time"]
        exact = (k * i_ref / b) .* (1 .- exp.(-t .* b ./ J))
        @test _dr_rel(columns["Drv/wsense/y"], exact) <= 1e-9
    end

    @testset "power balance: electrical in = mechanical out + losses + stored" begin
        p = _DR_PB
        columns, result, _ = _dr_run(_dr_balance())
        # The rotor inertia and the load inertia are rigidly coupled through the gearbox: the
        # derivative-causal pair is the only diagnostic (DAE index reduction handles it).
        @test _dr_codes(result) == ["W201"]
        i = columns["Drv/isense/y"]
        w = columns["Drv/wsense/y"]
        e_el = columns["IEl/y"]
        e_mech = columns["IMech/y"]
        e_r = columns["IR/y"]
        e_b = columns["IB/y"]
        stored = 0.5 * p.L .* i .^ 2 .+ 0.5 * p.J .* w .^ 2
        residual = e_el .- (e_r .+ e_b .+ e_mech .+ stored)
        relres = maximum(abs.(residual)) / maximum(abs.(e_el))
        @test relres <= 1e-6
        # The test is not vacuous: every term of the budget is of the size of the supply.
        @test maximum(e_r) > 0.05 * maximum(e_el)
        @test maximum(e_b) > 1e-3 * maximum(e_el)
        @test maximum(e_mech) > 0.05 * maximum(e_el)
        @test maximum(stored) > 1e-3 * maximum(e_el)
        # The ideal gearbox passes power through unchanged, and its rate and torque ratios
        # are `N`: algebraic identities.
        pm = columns["Drv/pmech/y"]
        @test _dr_rel(columns["Gear/power/y"], pm) <= 1e-9
        @test _dr_rel(columns["Gear/sense_a/y"], p.N .* columns["Gear/sense_b/y"]) <= 1e-9
        @test _dr_rel(columns["Gear/torque_b/y"], p.N .* columns["Drv/tsense/y"]) <= 1e-9
        println("J-MB12 power balance: max |E_el - sum| / max E_el = ", relres,
            " (E_el = ", e_el[end], " J)")
    end

    @testset "reflected rotor inertia N^2 J_m" begin
        ratios = Float64[]
        for N in (3.0, 7.0)
            J_m, T = 2e-3, 0.4
            # No load inertia: the output sees exactly N^2 J_m, and no W201 (J_m is the only
            # storage).
            columns, result, _ = _dr_run(_dr_reflected(N = N, J_m = J_m, T = -T, load = false))
            @test isempty(_dr_codes(result))
            t = columns["time"]
            wb = columns["Gear/sense_b/y"]
            jeff = T .* t[2:end] ./ wb[2:end]
            @test maximum(abs.(jeff ./ (N^2 * J_m) .- 1)) <= 1e-9
            push!(ratios, jeff[end] / (N^2 * J_m))
            @test _dr_rel(columns["Gear/sense_a/y"], N .* wb) <= 1e-9
        end
        # With a load inertia the effective inertia is `J_L + N^2 J_m`; the rigid coupling of
        # the two inertias is a derivative-causal pair, documented as the only diagnostic.
        N, J_m, J_L, T = 7.0, 2e-3, 5e-3, 0.4
        columns, result, _ = _dr_run(_dr_reflected(N = N, J_m = J_m, J_L = J_L, T = -T))
        @test _dr_codes(result) == ["W201"]
        t = columns["time"]
        wb = columns["Gear/sense_b/y"]
        jeff = T .* t[2:end] ./ wb[2:end]
        @test maximum(abs.(jeff ./ (J_L + N^2 * J_m) .- 1)) <= 1e-9
        println("J-MB12 reflected inertia: J_eff / (N^2 J_m) = ", ratios, "; with load ",
            jeff[end] / (J_L + N^2 * J_m))
    end

    @testset "reaction wheel: housing sees -tau, total angular momentum conserved" begin
        p = _DR_RW
        JA = p.J + p.m * p.y^2           # body inertia about the pivot
        columns, result, _ = _dr_run(_dr_wheel())
        @test isempty(_dr_codes(result))
        qd = columns["Joint/qdout"]
        ww = columns["RW/wsense/y"]
        wh = columns["RW/hsense/y"]
        tau = columns["RW/tgain/y"]
        i = columns["RW/isense/y"]
        hw = columns["RW/hgain/y"]
        t = columns["time"]
        # The housing port carries the body's own rate, and the algebraic taps are exact.
        @test maximum(abs.(wh .- qd)) <= 1e-9
        @test _dr_rel(tau, p.k .* i) <= 1e-9
        @test _dr_rel(hw, p.Jw .* ww) <= 1e-9
        # Momentum about the pivot: body J_A qd plus wheel J_w w_w, zero at rest.
        h = JA .* qd .+ p.Jw .* ww
        drift = maximum(abs.(h)) / maximum(abs.(hw))
        @test drift <= 1e-6
        # The wheel really exchanges momentum, the body recoils the opposite way, and the
        # back-EMF follows the rate relative to the housing: steady `w_w - qd = u / k_t`.
        @test maximum(abs.(hw)) > 0.1
        @test qd[end] < -0.3
        @test ww[end] > 50.0
        @test isapprox(ww[end] - qd[end], 6.0 / p.k; rtol = 1e-9)
        rel = ww .- qd
        angle = sum(0.5 .* (t[2:end] .- t[1:(end - 1)]) .* (rel[2:end] .+ rel[1:(end - 1)]))
        @test isapprox(columns["RW/relative/phi"][end], angle; rtol = 1e-5)
        # Control: a clamped housing is the fixed-stator drive, speed `u / k_t` absolute.
        columns, result, _ = _dr_run(_dr_wheel(fixed_housing = true))
        @test isapprox(columns["RW/wsense/y"][end], 6.0 / p.k; rtol = 1e-9)
        println("J-MB12 reaction wheel: max |H| / max |H_w| = ", drift, ", max |H| = ",
            maximum(abs.(h)), ", wheel rate ", ww[end], ", body rate ", qd[end])
    end
end
