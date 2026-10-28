# Work package J-MB4: the minimal planar multibond vertical slice (plan 6, row J-MB4).
#
# The acceptance is the Gate A pendulum:
#   * `GroundPlanar -> Revolute2D -> FixedTransform2D -> 1-junction -> IPlanar +
#     GravityPlanar + CoriolisPlanar` through `simulate` and the worker `run.start` path;
#   * the physical period within 1e-5 (finite-amplitude corrected), the `2π√(L/g)` check
#     within 1e-3, energy constant over 10 s, and the stable equilibrium;
#   * every new block passes the plan 9.1 four checks and the catalog is clean.
#
# The joint is the compliant-pivot Mode A joint: exact rotation, compliant translation at
# the pivot. All storage stays integral, so the 3-DOF inertia keeps all three momenta
# differential and there is no W201 in model.check or the run. The block's algebraic
# quantities (qdot, fs, Vrel, and the algebraic q = q0 + int(qdot)) are explicit functions
# of the states; the only hidden states are the int integrals, d and P, so mtkcompile
# reaches an index-0 ODE with no dummy derivatives (checked by the absent W201).
#
# All helpers are `_mb4_`-prefixed: the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Flat
import BGSim.Units
import JSON3
using Sockets
import BGSim: Worker

const _MB4_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _MB4_FIXTURE = joinpath(@__DIR__, "fixtures", "multibond", "pendulum.json")
const _MB4_L = 0.5
const _MB4_M = 1.0
const _MB4_J = 1.0e-4
const _MB4_G = 9.81
const _MB4_KT = 1.0e8
const _MB4_L_EFF = _MB4_L + _MB4_M * _MB4_G * cos(0.01) / _MB4_KT

const _MB4_T_SIMPLE = 2 * pi * sqrt(_MB4_L / _MB4_G)
const _MB4_T_RAW =
    2 * pi * sqrt((_MB4_J + _MB4_M * _MB4_L^2) / (_MB4_M * _MB4_G * _MB4_L))
const _MB4_T_LINEAR =
    2 * pi * sqrt((_MB4_J + _MB4_M * _MB4_L_EFF^2) / (_MB4_M * _MB4_G * _MB4_L_EFF))
const _MB4_T_AMP = _MB4_T_LINEAR * (1 + 0.01^2 / 16)
const _MB4_SWING = _MB4_M * _MB4_G * _MB4_L * (1 - cos(0.01))

# ---------------------------------------------------------------------------------------
# Model-document builders
# ---------------------------------------------------------------------------------------

_mb4_load() = JSON3.read(read(_MB4_FIXTURE, String), Dict{String,Any})

function _mb4_settings(; t_end = 4.0, points = 4001, reltol = 1.0e-9, abstol = 1.0e-11)
    return BGSim.RunSettings(
        t_start = 0.0, t_end = t_end, solver = "auto", reltol = reltol, abstol = abstol,
        output = Dict{String,Any}("mode" => "points", "points" => points),
    )
end

function _mb4_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => Dict{String,Any}(), "starts" => starts,
    )
end

_mb4_ref(ref) = Dict{String,Any}("ref" => ref)
_mb4_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _mb4_conn(id, kind, from_node, from_port, to_node, to_port = nothing)
    function ep(node, port)
        port === nothing && return Dict{String,Any}("node" => node)
        return Dict{String,Any}("node" => node, "port" => port)
    end
    return Dict{String,Any}("id" => id, "kind" => kind,
        "from" => ep(from_node, from_port), "to" => ep(to_node, to_port))
end

function _mb4_doc(name, nodes, connections; t_end = 0.01, points = 2,
    reltol = 1.0e-9, abstol = 1.0e-11)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...], "connections" => Any[connections...],
            "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "auto",
            "reltol" => reltol, "abstol" => abstol, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
end

function _mb4_vec_source(values; name = "VecSource")
    eqs = join(["y[$k] ~ $(values[k])" for k in 1:3], "\n            ")
    return """
    @block $name begin
        @outputs y::Vec{3}
        @equations begin
            $eqs
        end
    end
    """
end

_mb4_flat(doc) = Compile.flatten(IR.parse_model(doc))
_mb4_check(doc) = Compile.model_check(IR.parse_model(doc))
_mb4_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mb4_has(result, code) = any(d -> d.code == code, result.diagnostics)

function _mb4_run(doc; t_end = 0.01, points = 2, reltol = 1.0e-9, abstol = 1.0e-11)
    flat = _mb4_flat(doc)
    dir = mktempdir()
    result = simulate(flat; run_dir = dir,
        settings = _mb4_settings(t_end = t_end, points = points, reltol = reltol,
            abstol = abstol))
    return result, dir
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _mb4_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsig + 1)
    columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(columns[:, 1]))
    for (j, signal) in enumerate(m.signals)
        out[String(signal.id)] = collect(columns[:, j + 1])
    end
    return out
end

function _mb4_upward_crossings(t, y)
    out = Float64[]
    for i in 1:(length(y) - 1)
        if y[i] < 0 && y[i + 1] >= 0
            push!(out, t[i] + (t[i + 1] - t[i]) * (-y[i]) / (y[i + 1] - y[i]))
        end
    end
    return out
end

_mb4_field(obj, key::Symbol, default = nothing) =
    obj isa AbstractDict ? get(obj, key, get(obj, String(key), default)) : default

"""The released-from-rest initial pivot deflection in the child frame at q0."""
function _mb4_d0(q0; kt = _MB4_KT)
    d1 = -_MB4_M * _MB4_G * _MB4_J / (_MB4_J + _MB4_M * _MB4_L^2) * sin(q0) / kt
    d2 = -_MB4_M * _MB4_G * cos(q0) / kt
    return [d1, d2]
end

function _mb4_parse_vec(text)
    nums = split(replace(String(text), "[" => "", "]" => ""), ",")
    return [parse(Float64, strip(s)) for s in nums]
end

# ---------------------------------------------------------------------------------------
# Element checks (plan 9.1)
# ---------------------------------------------------------------------------------------

@testset "J-MB4 planar multibond primitive slice" begin
    @testset "the catalog: block.check clean, balanced, per-component units" begin
        blocks = Dict(b.ref => b for b in Library.load_stdlib())
        refs = [
            "stdlib:multibond/ComposePose2D",
            "stdlib:multibond/CoriolisPlanar",
            "stdlib:multibond/DePlanar",
            "stdlib:multibond/DfPlanar",
            "stdlib:multibond/FixedTransform2D",
            "stdlib:multibond/GravityPlanar",
            "stdlib:multibond/GroundPlanar",
            "stdlib:multibond/IPlanar",
            "stdlib:multibond/Revolute2D",
            "stdlib:multibond/ScrewTF",
            "stdlib:multibond/SePlanar",
            "stdlib:multibond/SfPlanar",
            "stdlib:multibond/TFAd",
        ]
        for ref in refs
            b = blocks[ref]
            @test b.group == "Multibond"
            @test isempty(check_block(b.ast))       # 0 errors and 0 warnings (no W204)
            bal = block_balance(b.ast)
            @test bal.unknowns == bal.equations
            planar = any(p -> p.domain == "Planar", b.interface.ports)
            if planar
                @test b.interface.dimension == 2
            else
                @test get(b.interface, :dimension, nothing) === nothing
            end
            for p in b.interface.ports
                @test haskey(p, :frame)
            end
        end

        # Every Planar port has the authoritative per-component units (D-MB2/D-MB10).
        e = ["N*m", "N", "N"]
        f = ["rad/s", "m/s", "m/s"]
        for ref in refs
            b = blocks[ref]
            env = Units.unit_env(b.ast)
            for p in b.interface.ports
                p.domain == "Planar" || continue
                for k in 1:3
                    @test env.labels[Symbol(p.name, ".e[", string(k), "]")] == e[k]
                    @test env.labels[Symbol(p.name, ".f[", string(k), "]")] == f[k]
                end
            end
            @test isempty([d for d in check_block(b.ast) if d.code == "E006"])
        end

        # The frame contract: transforms are the only two-frame bridges; the single-port
        # primitives declare their own frame; the joint is frame-neutral.
        @test [p.frame for p in blocks["stdlib:multibond/FixedTransform2D"].interface.ports] ==
              ["world", "body"]
        @test [p.frame for p in blocks["stdlib:multibond/TFAd"].interface.ports] ==
              ["world", "body"]
        @test [p.frame for p in blocks["stdlib:multibond/GroundPlanar"].interface.ports] ==
              ["world"]
        @test [p.frame for p in blocks["stdlib:multibond/IPlanar"].interface.ports] ==
              ["body"]
        @test all(p -> p.frame === nothing,
            blocks["stdlib:multibond/Revolute2D"].interface.ports)
    end

    @testset "IPlanar: momentum, flow and the Pm tap" begin
        source = _mb4_vec_source((1.0, 2.0, 3.0))
        doc = _mb4_doc(
            "IPlanarConstitutive",
            Any[
                _mb4_node("n1", "U", _mb4_inline(source)),
                _mb4_node("n2", "E", _mb4_ref("stdlib:multibond/SePlanar")),
                _mb4_node("n3", "B", _mb4_ref("stdlib:multibond/IPlanar");
                    params = Dict{String,Any}("J" => "0.5", "m" => "2.0")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n2", "u"),
                _mb4_conn("c2", "bond", "n2", "p", "n3", "p"),
            ];
            t_end = 0.1, points = 11,
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc; t_end = 0.1, points = 11)
        @test result.status == "done"
        @test !_mb4_has(result, "W201")
        data = _mb4_columns(dir)
        t = data["time"]
        for (k, ek) in enumerate((1.0, 2.0, 3.0))
            # ddt(P[k]) = p.e[k], so P[k] = e[k]*t.
            @test all(isapprox.(data["B/P[$k]"], ek .* t; atol = 1e-12))
            @test all(isapprox.(data["B/Pm[$k]"], data["B/P[$k]"]; atol = 1e-14))
            @test all(isapprox.(data["B/p.f[$k]"], data["B/P[$k]"] ./ (k == 1 ? 0.5 : 2.0);
                atol = 1e-12))
        end
        @test isapprox(data["B/p.f[1]"][end], 1.0 * 0.1 / 0.5; atol = 1e-12)
        @test isapprox(data["B/p.f[2]"][end], 2.0 * 0.1 / 2.0; atol = 1e-12)
    end

    @testset "CoriolisPlanar: free-body integration against an independent RK4" begin
        # dP/dt = ad(V)^T P with V = M^-1 P. The block's 1-junction port effort is
        # e = -ad(f)^T P (the same sign convention as GravityPlanar), so the inertia gets
        # +ad(V)^T P. The reference is a small independent RK4 in the test.
        function ref_rhs(P, J, m)
            V = (P[1] / J, P[2] / m, P[3] / m)
            ω, vx, vy = V
            return [vy * P[2] - vx * P[3], ω * P[3], -ω * P[2]]
        end
        function ref_rk4(P0, J, m, t_end, dt)
            n = round(Int, t_end / dt)
            P = collect(float.(P0))
            for _ in 1:n
                k1 = ref_rhs(P, J, m)
                k2 = ref_rhs(P .+ (dt / 2) .* k1, J, m)
                k3 = ref_rhs(P .+ (dt / 2) .* k2, J, m)
                k4 = ref_rhs(P .+ dt .* k3, J, m)
                P = P .+ (dt / 6) .* (k1 .+ 2 .* k2 .+ 2 .* k3 .+ k4)
            end
            return P
        end

        J, m = 0.5, 2.0
        for (index, P0) in enumerate(([0.3, 1.0, 0.5], [-1.2, 0.4, 2.0],
            [2.5, -0.7, 0.9]))
            doc = _mb4_doc(
                "FreeBodyCoriolis$(index)",
                Any[
                    _mb4_node("n1", "J1", Dict{String,Any}("junction" => "1")),
                    _mb4_node("n2", "B", _mb4_ref("stdlib:multibond/IPlanar");
                        params = Dict{String,Any}("J" => string(J), "m" => string(m)),
                        starts = Dict{String,Any}(
                            "P" => "[$(P0[1]), $(P0[2]), $(P0[3])]")),
                    _mb4_node("n3", "C", _mb4_ref("stdlib:multibond/CoriolisPlanar")),
                    _mb4_node("n4", "Theta", _mb4_ref("stdlib:continuous/Integrator")),
                ],
                Any[
                    _mb4_conn("c1", "bond", "n2", "p", "n1"),
                    _mb4_conn("c2", "bond", "n3", "p", "n1"),
                    _mb4_conn("c3", "signal", "n2", "Pm", "n3", "P"),
                    _mb4_conn("c4", "signal", "n2", "wout", "n4", "u"),
                ];
                t_end = 2.0, points = 2001,
            )
            @test isempty(_mb4_errors(_mb4_check(doc)))
            result, dir = _mb4_run(doc; t_end = 2.0, points = 2001)
            @test result.status == "done"
            @test !_mb4_has(result, "W201")
            data = _mb4_columns(dir)
            P_end = [data["B/P[$k]"][end] for k in 1:3]
            P_ref = ref_rk4(P0, J, m, 2.0, 1.0e-5)
            rel = maximum(abs.(P_end .- P_ref)) / max(1.0, maximum(abs, P_ref))
            @test rel <= 1.0e-6
            @test rel <= 1.0e-9            # measured ~4e-14
            # Convention-independent check: with no external wrench the world linear
            # momentum m R(theta) [vx, vy] and the angular momentum about the CoM are
            # constant. theta is integrated from the body angular rate.
            theta = data["Theta/y"]
            vx = data["B/p.f[2]"]
            vy = data["B/p.f[3]"]
            px = m .* (cos.(theta) .* vx .- sin.(theta) .* vy)
            py = m .* (sin.(theta) .* vx .+ cos.(theta) .* vy)
            Lz = data["B/P[1]"]
            pscale = max(1.0, maximum(abs, px), maximum(abs, py))
            @test maximum(abs.(px .- px[1])) / pscale <= 1.0e-6
            @test maximum(abs.(py .- py[1])) / pscale <= 1.0e-6
            @test maximum(abs.(Lz .- Lz[1])) / max(1.0, maximum(abs, Lz)) <= 1.0e-6
            println("J-MB4 Coriolis free-body relative error = ", rel,
                ", world momentum drift = ",
                max(maximum(abs.(px .- px[1])), maximum(abs.(py .- py[1]))) / pscale)
        end

        # The instantaneous constitutive relation and e . f = 0 on a driven Sf bond.
        V = (0.7, -1.3, 0.4)
        P = (2.0, -0.5, 1.1)
        flow = _mb4_vec_source(V; name = "FlowSource")
        momentum = _mb4_vec_source(P; name = "MomentumSource")
        doc = _mb4_doc(
            "CoriolisIdentity",
            Any[
                _mb4_node("n1", "V", _mb4_inline(flow)),
                _mb4_node("n2", "P", _mb4_inline(momentum)),
                _mb4_node("n3", "F", _mb4_ref("stdlib:multibond/SfPlanar")),
                _mb4_node("n4", "C", _mb4_ref("stdlib:multibond/CoriolisPlanar")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb4_conn("c2", "signal", "n2", "y", "n4", "P"),
                _mb4_conn("c3", "bond", "n3", "p", "n4", "p"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        e = [data["C/p.e[$k]"][1] for k in 1:3]
        fr = [data["C/p.f[$k]"][1] for k in 1:3]
        @test fr == -[V...]
        @test e[1] ≈ fr[2] * P[3] - fr[3] * P[2]
        @test e[2] ≈ -fr[1] * P[3]
        @test e[3] ≈ fr[1] * P[2]
        @test abs(sum(e[k] * fr[k] for k in 1:3)) <= 1e-12 * max(1.0, maximum(abs, e))
    end

    @testset "SePlanar / SfPlanar / GroundPlanar: source and zero relations" begin
        # Ground (flow source, f = 0) against an effort source on a direct bond: the Ground
        # fixes the bond flow to zero and passes the effort through.
        W = (2.0, -1.0, 0.5)
        doc = _mb4_doc(
            "GroundSource",
            Any[
                _mb4_node("n1", "U", _mb4_inline(_mb4_vec_source(W))),
                _mb4_node("n2", "G", _mb4_ref("stdlib:multibond/GroundPlanar")),
                _mb4_node("n3", "E", _mb4_ref("stdlib:multibond/SePlanar")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb4_conn("c2", "bond", "n2", "p", "n3", "p"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        for k in 1:3
            @test data["G/p.f[$k]"][1] == 0.0
            @test data["E/p.f[$k]"][1] == 0.0
            @test data["G/p.e[$k]"][1] ≈ W[k]
            @test data["E/p.e[$k]"][1] ≈ W[k]
        end
    end

    @testset "DePlanar and DfPlanar: the sensor relations" begin
        # De: an effort source and a De on a 0-junction. The De imposes zero flow and reads
        # the common effort; the source supplies zero flow.
        W = (2.0, -1.0, 0.5)
        de_doc = _mb4_doc(
            "DeSensor",
            Any[
                _mb4_node("n1", "U", _mb4_inline(_mb4_vec_source(W))),
                _mb4_node("n2", "J", Dict{String,Any}("junction" => "0")),
                _mb4_node("n3", "E", _mb4_ref("stdlib:multibond/SePlanar")),
                _mb4_node("n4", "D", _mb4_ref("stdlib:multibond/DePlanar")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb4_conn("c2", "bond", "n3", "p", "n2"),
                _mb4_conn("c3", "bond", "n4", "p", "n2"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(de_doc)))
        result, dir = _mb4_run(de_doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        @test all(all(data["D/p.f[$k]"] .== 0.0) for k in 1:3)
        for k in 1:3
            @test data["D/y[$k]"][1] ≈ W[k]
            @test data["D/p.e[$k]"][1] ≈ W[k]
        end

        # Df: a flow source and a Df on a 0-junction. The Df imposes zero effort and reads
        # the junction flow, which is the negative of the source flow.
        V = (0.3, -0.2, 0.1)
        df_doc = _mb4_doc(
            "DfSensor",
            Any[
                _mb4_node("n1", "V", _mb4_inline(_mb4_vec_source(V))),
                _mb4_node("n2", "J", Dict{String,Any}("junction" => "0")),
                _mb4_node("n3", "S", _mb4_ref("stdlib:multibond/SfPlanar")),
                _mb4_node("n4", "D", _mb4_ref("stdlib:multibond/DfPlanar")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb4_conn("c2", "bond", "n3", "p", "n2"),
                _mb4_conn("c3", "bond", "n4", "p", "n2"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(df_doc)))
        result, dir = _mb4_run(df_doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        @test all(all(data["D/p.e[$k]"] .== 0.0) for k in 1:3)
        for k in 1:3
            @test data["D/y[$k]"][1] == data["D/p.f[$k]"][1]
            @test isapprox(data["D/y[$k]"][1], -V[k]; atol = 1e-14)
        end
    end

    @testset "TFAd and FixedTransform2D: power continuity and the adjoint" begin
        function transform_model(name; tfad::Bool)
            E = (1.0, 2.0, 3.0)
            F = (0.5, -0.25, 0.75)
            pose = _mb4_vec_source((0.4, 0.3, -0.2); name = "PoseSource")
            nodes = Any[
                _mb4_node("n1", "E", _mb4_inline(_mb4_vec_source(E; name = "EffortSource"))),
                _mb4_node("n2", "F", _mb4_inline(_mb4_vec_source(F; name = "FlowSource"))),
                _mb4_node("n3", "Se", _mb4_ref("stdlib:multibond/SePlanar")),
                _mb4_node("n4", "Sf", _mb4_ref("stdlib:multibond/SfPlanar")),
                _mb4_node("n5", "T",
                    tfad ? _mb4_ref("stdlib:multibond/TFAd") :
                    _mb4_ref("stdlib:multibond/FixedTransform2D");
                    params = tfad ? Dict{String,Any}() :
                             Dict{String,Any}("x" => "0.3", "y" => "-0.2", "theta" => "0.4")),
            ]
            conns = Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb4_conn("c2", "signal", "n2", "y", "n4", "u"),
                _mb4_conn("c3", "bond", "n3", "p", "n5", "a"),
                _mb4_conn("c4", "bond", "n5", "b", "n4", "p"),
            ]
            if tfad
                push!(nodes, _mb4_node("n6", "G", _mb4_inline(pose)))
                push!(conns, _mb4_conn("c5", "signal", "n6", "y", "n5", "g"))
            end
            return _mb4_doc(name, nodes, conns)
        end

        for (name, tfad) in (("TFAdPower", true), ("FixedTransformPower", false))
            doc = transform_model(name; tfad = tfad)
            @test isempty(_mb4_errors(_mb4_check(doc)))
            result, dir = _mb4_run(doc)
            @test result.status == "done"
            data = _mb4_columns(dir)
            ae = [data["T/a.e[$k]"][1] for k in 1:3]
            af = [data["T/a.f[$k]"][1] for k in 1:3]
            be = [data["T/b.e[$k]"][1] for k in 1:3]
            bf = [data["T/b.f[$k]"][1] for k in 1:3]
            @test isapprox(sum(ae[k] * af[k] + be[k] * bf[k] for k in 1:3), 0.0;
                atol = 1e-12)
            theta, x, y = 0.4, 0.3, -0.2
            c, s = cos(theta), sin(theta)
            A = [1.0 0.0 0.0; y c -s; -x s c]
            @test isapprox(af, -A * bf; atol = 1e-12)
            @test isapprox(ae, transpose(inv(A)) * be; atol = 1e-12)
        end
    end

    @testset "ScrewTF: S = [1, ry, -rx] and power continuity" begin
        E = (2.0, -1.0, 0.5)
        v = 0.7
        rx, ry = 0.25, -0.4
        doc = _mb4_doc(
            "ScrewPower",
            Any[
                _mb4_node("n1", "E", _mb4_inline(_mb4_vec_source(E; name = "EffortSource"))),
                _mb4_node("n2", "Se", _mb4_ref("stdlib:multibond/SePlanar")),
                _mb4_node("n3", "T", _mb4_ref("stdlib:multibond/ScrewTF");
                    params = Dict{String,Any}("rx" => string(rx), "ry" => string(ry))),
                _mb4_node("n4", "Sf", _mb4_ref("stdlib:bondgraph/Sf");
                    params = Dict{String,Any}("f" => string(v))),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n2", "u"),
                _mb4_conn("c2", "bond", "n2", "p", "n3", "a"),
                _mb4_conn("c3", "bond", "n3", "b", "n4", "p"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        ae = [data["T/a.e[$k]"][1] for k in 1:3]
        af = [data["T/a.f[$k]"][1] for k in 1:3]
        be = data["T/b.e"][1]
        bf = data["T/b.f"][1]
        S = [1.0, ry, -rx]
        @test bf ≈ -v
        @test isapprox(af, S .* bf; atol = 1e-12)
        @test isapprox(be, -sum(S[k] * ae[k] for k in 1:3); atol = 1e-12)
        @test isapprox(sum(ae[k] * af[k] for k in 1:3) + be * bf, 0.0; atol = 1e-12)
    end

    @testset "ComposePose2D: the SE(2) product by hand" begin
        gp = (0.37, 0.4, -0.2)
        gl = (-0.11, 0.25, 0.6)
        doc = _mb4_doc(
            "ComposeHand",
            Any[
                _mb4_node("n1", "P", _mb4_inline(_mb4_vec_source(gp; name = "Parent"))),
                _mb4_node("n2", "L", _mb4_inline(_mb4_vec_source(gl; name = "Local"))),
                _mb4_node("n3", "C", _mb4_ref("stdlib:multibond/ComposePose2D")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n3", "gp"),
                _mb4_conn("c2", "signal", "n2", "y", "n3", "gl"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        c, s = cos(gp[1]), sin(gp[1])
        expected = [gp[1] + gl[1],
            gp[2] + c * gl[2] - s * gl[3],
            gp[3] + s * gl[2] + c * gl[3]]
        got = [data["C/g[$k]"][1] for k in 1:3]
        @test isapprox(got, expected; atol = 1e-14)
    end

    @testset "GravityPlanar: the wrench against a hand calculation" begin
        theta, x, y = 0.31, 0.4, -0.5
        m, g0 = 1.7, 9.81
        doc = _mb4_doc(
            "GravityHand",
            Any[
                _mb4_node("n1", "G", _mb4_inline(
                    _mb4_vec_source((theta, x, y); name = "PoseSource"))),
                _mb4_node("n2", "W", _mb4_ref("stdlib:multibond/GravityPlanar");
                    params = Dict{String,Any}("m" => string(m), "g0" => string(g0))),
                _mb4_node("n3", "D", _mb4_ref("stdlib:multibond/DePlanar")),
            ],
            Any[
                _mb4_conn("c1", "signal", "n1", "y", "n2", "g"),
                _mb4_conn("c2", "bond", "n2", "p", "n3", "p"),
            ],
        )
        @test isempty(_mb4_errors(_mb4_check(doc)))
        result, dir = _mb4_run(doc)
        @test result.status == "done"
        data = _mb4_columns(dir)
        e = [data["W/p.e[$k]"][1] for k in 1:3]
        physical = [0.0, -sin(theta) * m * g0, -cos(theta) * m * g0]
        @test isapprox(e, -physical; atol = 1e-12)
        for k in 1:3
            @test data["D/y[$k]"][1] ≈ e[k]
        end
    end

    @testset "signal wiring probe: a composite can carry q through ComposePose2D" begin
        # J-MB4 records whether a composite joint can wire its pose. The signal path works
        # (J2.6): scalar q -> PoseFromQ -> ComposePose2D -> GravityPlanar.g, exposed as a
        # composite output. The native joint is still shipped because the transform
        # primitives declare fixed frame names and the 3-port causality is per-port, which
        # a composite cannot express; J-MB6 owns the replacement. NOTES.md records this.
        mktempdir() do dir
            lib = joinpath(dir, "library")
            mkpath(lib)
            write(joinpath(lib, "PoseFromQ.jl"), """
            @block PoseFromQ begin
                @inputs q::Real
                @outputs g::Vec{3}
                @parameters begin
                    rx::Real = 0.0, [unit = "m", description = "Axis x"]
                    ry::Real = 0.0, [unit = "m", description = "Axis y"]
                end
                @equations begin
                    g[1] ~ q
                    g[2] ~ rx
                    g[3] ~ ry
                end
            end
            """)
            write(joinpath(lib, "LocalPose2D.jl"), """
            @block LocalPose2D begin
                @parameters begin
                    x::Real = 0.0, [unit = "m", description = "Local x"]
                    y::Real = 0.0, [unit = "m", description = "Local y"]
                    theta::Real = 0.0, [unit = "rad", description = "Local angle"]
                end
                @outputs g::Vec{3}
                @equations begin
                    g[1] ~ theta
                    g[2] ~ x
                    g[3] ~ y
                end
            end
            """)
            composite = """
            @block PoseProbe begin
                @inputs q::Real
                @outputs g::Vec{3}
                @components begin
                    pose = PoseFromQ()
                    compose = ComposePose2D()
                    place = LocalPose2D(y = -0.5)
                    gravity = GravityPlanar()
                    sensor = DePlanar()
                end
                @connections begin
                    connect(q, pose.q)
                    connect(pose.g, compose.gp)
                    connect(place.g, compose.gl)
                    connect(compose.g, gravity.g)
                    connect(gravity.p, sensor.p)
                    connect(compose.g, g)
                end
            end
            """
            doc = _mb4_doc(
                "PoseProbeModel",
                Any[
                    _mb4_node("n1", "C", _mb4_ref("stdlib:sources/Constant");
                        params = Dict{String,Any}("value" => "0.2")),
                    _mb4_node("n2", "W", _mb4_inline(composite)),
                ],
                Any[_mb4_conn("c1", "signal", "n1", "y", "n2", "q")],
            )
            flat = Compile.flatten(IR.parse_model(doc); project_dir = dir)
            @test isempty(flat.diagnostics)
            vids = Set(v.id for v in flat.variables)
            @test "W/pose/g[1]" in vids
            @test "W/compose/gp[1]" in vids
            @test "W/gravity/g[1]" in vids
            @test "W/compose/g[1]" in vids
        end
    end

    # -----------------------------------------------------------------------------------
    # The Gate A pendulum
    # -----------------------------------------------------------------------------------

    @testset "the pendulum model: check, SCAP and the composed pose" begin
        doc = _mb4_load()
        # The fixture starts d at the released-from-rest value, not the held static one.
        dstart = _mb4_parse_vec(doc["diagram"]["nodes"][2]["starts"]["d"])
        d0 = _mb4_d0(0.01)
        @test isapprox(dstart[1], d0[1]; rtol = 1e-12, atol = 1e-18)
        @test isapprox(dstart[2], d0[2]; rtol = 1e-12, atol = 1e-18)
        result = _mb4_check(doc)
        @test isempty(_mb4_errors(result))
        @test !_mb4_has(result, "W201")
        @test !_mb4_has(result, "W202")
        for code in ("E101", "E102", "E103", "E106")
            @test !_mb4_has(result, code)
        end
        flat = _mb4_flat(doc)
        @test isempty(flat.diagnostics)
        ids = Set(s.id for s in flat.signals)
        for id in ("Joint/qout", "Joint/qdout", "Joint/pose[1]", "Joint/dout[1]",
            "Joint/Vrelout[2]", "Compose/g[1]", "Compose/g[3]", "Gravity/g[1]",
            "Body/P[1]", "Body/Pm[1]", "Body/p.e[1]", "Body/p.e[2]", "Body/p.f[3]",
            "Coriolis/p.e[1]", "Coriolis/p.e[2]")
            @test id in ids
        end
        # The flat graph contains only documented primitives.
        raw_refs = Set(n["block"]["ref"] for n in doc["diagram"]["nodes"]
                       if haskey(n["block"], "ref"))
        @test raw_refs == Set([
            "stdlib:multibond/GroundPlanar", "stdlib:multibond/Revolute2D",
            "stdlib:multibond/FixedTransform2D", "stdlib:multibond/IPlanar",
            "stdlib:multibond/GravityPlanar", "stdlib:multibond/CoriolisPlanar",
            "stdlib:multibond/ComposePose2D", "stdlib:bondgraph/Se",
        ])
    end

    @testset "pendulum period: physical and simple references" begin
        BGSim.clear_compile_cache!()
        doc = _mb4_load()
        result, dir = _mb4_run(doc; t_end = 4.0, points = 4001)
        @test result.status == "done"
        @test isempty(_mb4_errors(result))
        for code in ("E101", "E102", "E103", "E106", "E900", "E901", "W201")
            @test !_mb4_has(result, code)
        end
        data = _mb4_columns(dir)
        q = data["Joint/qout"]
        @test isapprox(q[1], 0.01; atol = 1e-9)
        crossings = _mb4_upward_crossings(data["time"], q)
        @test length(crossings) >= 3
        period = crossings[2] - crossings[1]
        @test isapprox(period, _MB4_T_AMP; rtol = 1.0e-5)
        @test isapprox(period, _MB4_T_SIMPLE; rtol = 1.0e-3)
        # The CoM x crossing gives the same period (the WP allows either).
        gx = data["Compose/g[2]"]
        xcross = _mb4_upward_crossings(data["time"], gx)
        @test length(xcross) >= 3
        @test isapprox(xcross[2] - xcross[1], period; rtol = 1e-6)
        println("J-MB4 pendulum period = ", period, " s (raw physical ",
            _MB4_T_RAW, " s, L_eff physical ", _MB4_T_LINEAR, " s, amplitude ",
            _MB4_T_AMP, " s, simple ", _MB4_T_SIMPLE, " s; 4 s steps ",
            result.stats.steps, ", sim ", result.stats.sim_s, " s)")
    end

    @testset "pendulum energy constant over 10 s" begin
        BGSim.clear_compile_cache!()
        doc = _mb4_load()
        result, dir = _mb4_run(doc; t_end = 10.0, points = 10001)
        @test result.status == "done"
        @test !_mb4_has(result, "W201")
        data = _mb4_columns(dir)
        q = data["Joint/qout"]
        d1 = data["Joint/dout[1]"]
        d2 = data["Joint/dout[2]"]
        KE = 0.5 .* (data["Body/P[1]"] .^ 2 ./ _MB4_J .+
                     data["Body/P[2]"] .^ 2 ./ _MB4_M .+
                     data["Body/P[3]"] .^ 2 ./ _MB4_M)
        # The actual CoM height includes the compliant pivot deflection d in the child
        # frame: h = gy + sin(q) d1 + cos(q) d2.
        h = data["Compose/g[3]"] .+ sin.(q) .* d1 .+ cos.(q) .* d2
        Es = 0.5 * _MB4_KT .* (d1 .^ 2 .+ d2 .^ 2)
        E = KE .+ _MB4_M * _MB4_G .* h .+ Es
        drift = maximum(abs.(E .- E[1]))
        @test drift <= 1.0e-6 * _MB4_SWING
        println("J-MB4 pendulum energy drift over 10 s = ", drift,
            " J (swing ", _MB4_SWING, " J, ratio ", drift / _MB4_SWING,
            "; steps ", result.stats.steps, ", sim ", result.stats.sim_s,
            " s, fast mode ", sqrt(_MB4_KT / _MB4_M), " rad/s)")
    end

    @testset "pendulum returns from q0 = 0.01 and rests at q = 0" begin
        BGSim.clear_compile_cache!()
        doc = _mb4_load()
        result, dir = _mb4_run(doc; t_end = 2.0, points = 2001)
        @test result.status == "done"
        data = _mb4_columns(dir)
        q = data["Joint/qout"]
        @test q[2] < q[1]                       # gravity pulls back toward zero
        @test minimum(q) < 0.0                  # it crosses the bottom
        @test maximum(abs.(q)) ≈ 0.01 rtol = 1.0e-3
        println("J-MB4 q0=0.01 max|q| = ", maximum(abs.(q)))

        doc0 = _mb4_load()
        doc0["diagram"]["nodes"][2]["params"]["q0"] = "0.0"
        d00 = _mb4_d0(0.0)
        doc0["diagram"]["nodes"][2]["starts"]["d"] = "[$(d00[1]), $(d00[2])]"
        result0, dir0 = _mb4_run(doc0; t_end = 2.0, points = 2001)
        @test result0.status == "done"
        data0 = _mb4_columns(dir0)
        @test maximum(abs.(data0["Joint/qout"])) < 1.0e-6
        println("J-MB4 equilibrium max|q| = ", maximum(abs.(data0["Joint/qout"])))
    end

    @testset "joint and Coriolis power identities on the run" begin
        BGSim.clear_compile_cache!()
        doc = _mb4_load()
        result, dir = _mb4_run(doc; t_end = 2.0, points = 2001)
        @test result.status == "done"
        data = _mb4_columns(dir)
        for i in eachindex(data["time"])
            jp = sum(data["Joint/parent.e[$k]"][i] * data["Joint/parent.f[$k]"][i]
                     for k in 1:3)
            jc = sum(data["Joint/child.e[$k]"][i] * data["Joint/child.f[$k]"][i]
                     for k in 1:3)
            jd = data["Joint/drive.e"][i] * data["Joint/drive.f"][i]
            v2 = data["Joint/Vrelout[2]"][i]
            v3 = data["Joint/Vrelout[3]"][i]
            spring = _MB4_KT * (data["Joint/dout[1]"][i] * v2 +
                                data["Joint/dout[2]"][i] * v3)
            # bt = 0 in the fixture; keep the damping term explicit.
            damp = 0.0
            @test abs(jp + jc + jd - spring - damp) <= 1.0e-9 *
                  max(1.0, abs(jp), abs(jc), abs(jd), abs(spring))
            la = sum(data["Link/a.e[$k]"][i] * data["Link/a.f[$k]"][i] for k in 1:3)
            lb = sum(data["Link/b.e[$k]"][i] * data["Link/b.f[$k]"][i] for k in 1:3)
            @test abs(la + lb) <= 1.0e-9 * max(1.0, abs(la), abs(lb))
            ce = sum(data["Coriolis/p.e[$k]"][i] * data["Coriolis/p.f[$k]"][i]
                     for k in 1:3)
            @test abs(ce) <= 1.0e-9 * max(1.0, abs(jp), abs(jc))
        end
    end

    # -----------------------------------------------------------------------------------
    # The worker run.start path (the same entry points as test_worker.jl)
    # -----------------------------------------------------------------------------------

    @testset "the pendulum runs through worker run.start" begin
        BGSim.clear_compile_cache!()
        mktempdir() do tmp
            listener = Sockets.listen(ip"127.0.0.1", 0)
            port = Int(Sockets.getsockname(listener)[2])
            server = @async begin
                sock = Sockets.accept(listener)
                Worker.serve(sock; log = devnull)
            end
            sock = Sockets.connect(ip"127.0.0.1", port)
            notes = Any[]
            function read_message()
                frame = Worker.read_frame(sock)
                frame === nothing && error("worker closed")
                return JSON3.read(String(frame.payload))
            end
            function wait_for(pred; timeout = 300.0)
                task = @async begin
                    while true
                        message = read_message()
                        pred(message) && return message
                        push!(notes, message)
                    end
                end
                if Base.timedwait(() -> istaskdone(task), timeout) == :timed_out
                    error("timed out waiting for the worker")
                end
                return fetch(task)
            end
            try
                run_id = "mb4-pendulum"
                run_dir = joinpath(tmp, run_id)
                doc = _mb4_load()
                Worker.write_json_frame(sock, JSON3.write((; id = 1, method = "run.start",
                    params = (; runId = run_id, model = doc, runDir = run_dir,
                        projectDir = _MB4_ROOT))))
                answer = wait_for(m -> _mb4_field(m, :id, nothing) == 1)
                @test answer.result.accepted == true
                @test isfile(joinpath(run_dir, "manifest.json"))
                running = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
                @test running.status == "running"
                done = wait_for(m -> _mb4_field(m, :method, "") == "run.done")
                @test done.params.status == "done"
                @test isempty([d for d in done.params.diagnostics
                               if d.severity == "error"])
                @test !any(d -> _mb4_field(d, :code, "") == "W201",
                    done.params.diagnostics)
                final = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
                @test final.status == "done"
                @test Int(final.time.n) == 4001
                data = _mb4_columns(run_dir)
                crossings = _mb4_upward_crossings(data["time"], data["Joint/qout"])
                @test length(crossings) >= 3
                period = crossings[2] - crossings[1]
                @test isapprox(period, _MB4_T_AMP; rtol = 1.0e-5)
                println("J-MB4 worker-run period = ", period, " s")
            finally
                close(sock)
                try
                    wait(server)
                catch
                end
                close(listener)
            end
        end
    end
end
