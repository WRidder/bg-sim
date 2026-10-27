# Work package J2.6: the textual subsystems `@components` / `@connections` (decision D5)
# and the spec's `GearWithBacklash` composite.
#
# The acceptance of the work package:
#   * the spec's `@block GearWithBacklash` parses and checks clean, and its interface is
#     `a`/`b` on `Power{Rotation}`;
#   * `@components` declares internal instances (block name + parameter overrides) and
#     `@connections` wires internal ports and exposes the composite's boundary ports; the
#     flattening prefix is `<Instance>/<child>` and composites nest;
#   * a model built from the text composite and the same structure built from a model-JSON
#     subsystem flatten to the same equations and simulate bit-identically on the same
#     solver;
#   * `GearWithBacklash` simulates, and its dead-zone spring transmits no torque inside the
#     gap and the full stiffness outside it (static operating points, exact numbers), with
#     the energy behaviour of an ordinary C element plus a damper.
#
# Every helper here is `_comp_`-prefixed: the test files of all work packages share `Main`.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Flat
import JSON3

# ---------------------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------------------

const _COMP_PROJ = joinpath(@__DIR__, "fixtures", "components")
const _COMP_LIB = joinpath(_COMP_PROJ, "library")
const _COMP_GAP = 0.01
const _COMP_K = 1.0e4
const _COMP_D = 5.0

function _comp_settings(t_end; solver = "Rodas5P", reltol = 1.0e-7, abstol = 1.0e-10,
    points = 501)
    return Dict{String,Any}(
        "t_start" => 0.0, "t_end" => t_end, "solver" => solver, "reltol" => reltol,
        "abstol" => abstol, "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => points),
        "event_limit" => 10000,
    )
end

function _comp_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => Dict{String,Any}(), "starts" => starts,
    )
end

_comp_ref(ref) = Dict{String,Any}("ref" => ref)
_comp_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _comp_conn(id, kind, from_node, from_port, to_node, to_port)
    return Dict{String,Any}(
        "id" => id, "kind" => kind,
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
end

function _comp_model(name, nodes, connections; t_end = 1.0, solver = "Rodas5P",
    points = 501)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...], "connections" => Any[connections...],
            "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => _comp_settings(t_end; solver = solver, points = points),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
end

_comp_flat(doc) = Compile.flatten(IR.parse_model(doc); project_dir = _COMP_PROJ)
_comp_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _comp_has(diagnostics, code, needle)
    return any(d -> d.code == code && occursin(needle, d.message), diagnostics)
end

function _comp_diag(fm, code)
    return findfirst(d -> d.code == code, fm.diagnostics)
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _comp_columns(dir)
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

function _comp_run(fm; t_end = 1.0, solver = "Rodas5P", reltol = 1.0e-7,
    abstol = 1.0e-10, points = 501)
    dir = mktempdir()
    result = simulate(
        fm; run_dir = dir,
        settings = _comp_settings(t_end; solver = solver, reltol = reltol,
            abstol = abstol, points = points),
    )
    return result, dir
end

"""The spec's dead-zone law, for the constitutive residual checks."""
function _comp_torque(phi, w; k = _COMP_K, d = _COMP_D, gap = _COMP_GAP)
    if phi > gap / 2
        return max(k * (phi - gap / 2) + d * w, 0.0)
    elseif phi < -gap / 2
        return min(k * (phi + gap / 2) + d * w, 0.0)
    end
    return 0.0
end

"""A driven `GearWithBacklash` model: a flow source at the input, an inertia at the output."""
function _comp_drive(g1block; f = -0.3)
    return _comp_model(
        "GearDrive",
        Any[
            _comp_node("n1", "Sf1", _comp_ref("stdlib:bondgraph/Sf");
                params = Dict("f" => string(f))),
            _comp_node("n2", "G1", g1block),
            _comp_node("n3", "J1", _comp_ref("stdlib:rotation/Inertia");
                params = Dict("J" => "0.01")),
            _comp_node("n4", "F1", _comp_ref("stdlib:rotation/FixedShaft")),
        ],
        Any[
            _comp_conn("c1", "bond", "n1", "p", "n2", "a"),
            _comp_conn("c2", "wire", "n2", "b", "n3", "a"),
            _comp_conn("c3", "wire", "n3", "b", "n4", "a"),
        ];
        t_end = 0.5,
    )
end

"""The same structure as `_comp_drive(project:GearWithBacklash)`, built with a model-JSON
subsystem node instead of the text composite (the equivalence target)."""
function _comp_json_subsystem_g1()
    gear = _comp_node("g1", "gear", _comp_ref("project:LossyGear");
        params = Dict("n" => "10.0", "eta" => "0.9"))
    play = _comp_node("p1", "play", _comp_ref("project:GearBacklash");
        params = Dict("k" => "1e4", "d" => "5.0", "gap" => "0.01"))
    ports = Any[
        Dict{String,Any}("name" => "a", "kind" => "power", "domain" => "Rotation",
            "size" => Any[], "node" => "g1", "port" => "a"),
        Dict{String,Any}("name" => "b", "kind" => "power", "domain" => "Rotation",
            "size" => Any[], "node" => "p1", "port" => "b"),
    ]
    diagram = Dict{String,Any}(
        "nodes" => Any[gear, play],
        "connections" => Any[_comp_conn("ic1", "wire", "g1", "b", "p1", "a")],
    )
    return Dict{String,Any}(
        "subsystem" => Dict{String,Any}("ports" => ports, "diagram" => diagram),
    )
end

_comp_block(source) = parse_block(source; filename = "inline", ref = "inline:test")

# ---------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------

@testset "J2.6 textual subsystems and composites" begin
    @testset "the spec's GearWithBacklash parses and checks clean" begin
        blocks = Dict(b.name => b for b in Library.load_project_library(_COMP_LIB))
        for name in (:GearBacklash, :LossyGear, :GearWithBacklash)
            @test haskey(blocks, name)
            @test isempty(blocks[name].diagnostics)
            @test !Library.has_errors(blocks[name])
        end

        gwb = blocks[:GearWithBacklash]
        @test gwb.interface.ports == [
            (name = "a", domain = "Rotation", size = Int[]),
            (name = "b", domain = "Rotation", size = Int[]),
        ]
        @test isempty(gwb.interface.parameters)
        @test isempty(gwb.interface.variables)
        pb = gwb.ast
        @test scopes(pb) == [:ports, :components, :connections]

        comps = components(pb)
        @test [component_name(c) for c in comps] == [:gear, :play]
        @test [component_block(c) for c in comps] == [:LossyGear, :GearBacklash]
        @test [first.(component_kwargs(c)) for c in comps] == [[:n, :eta], [:k, :d, :gap]]
        # The override expressions are the defaults-scope AST, not text.
        kw = component_kwargs(comps[1])
        @test first(kw[1]) === :n
        @test last(kw[1]) isa BGSim.Lit
        @test last(kw[1]).value == 10.0

        conns = connections(pb)
        @test [(portref_instance(connect_from(c)), portref_port(connect_from(c)),
                portref_instance(connect_to(c)), portref_port(connect_to(c)))
               for c in conns] == [
            (nothing, :a, :gear, :a),
            (:gear, :b, :play, :a),
            (:play, :b, nothing, :b),
        ]

        # GearBacklash carries the spec's three parameters and five equations.
        gb = blocks[:GearBacklash]
        @test [p.name for p in gb.interface.parameters] == ["k", "d", "gap"]
        @test length(gb.interface.variables) == 3
        @test length(block_equations(gb.ast)) == 5
    end

    @testset "negative: @components / @connections shape" begin
        # A one-entry scope body is accepted, like the declaration scopes.
        pb = _comp_block("@block A begin\n    @components g = Gain()\nend\n")
        @test length(components(pb)) == 1
        @test component_block(only(components(pb))) === :Gain

        # A malformed component entry is E001.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g
            @connections connect(a, a)
        end
        """))
        @test _comp_has(d, "E001", "entry is `name = BlockName")

        # Positional arguments are refused (a component parameter is named).
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain(2.0)
            @connections connect(a, g.a)
        end
        """))
        @test _comp_has(d, "E001", "named parameter overrides only")

        # Unknown component in a connect.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain()
            @connections connect(a, zz.a)
        end
        """))
        @test _comp_has(d, "E003", "unknown component `zz`")

        # Unknown component in @observables.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain()
            @connections connect(a, g.a)
            @observables x = zz.y
        end
        """))
        @test _comp_has(d, "E003", "unknown component `zz`")

        # A component name collides with a declaration (here a port).
        d = check_block(_comp_block("""
        @block A begin
            @ports gear::Power{Rotation}
            @components gear = Gain()
            @connections connect(gear, gear.u)
        end
        """))
        @test _comp_has(d, "E003", "collides")

        # A component name is declared twice.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components begin
                g = Gain()
                g = Gain()
            end
            @connections connect(a, g.a)
        end
        """))
        @test _comp_has(d, "E003", "declared twice")

        # A port connected to itself.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain()
            @connections connect(g.a, g.a)
        end
        """))
        @test _comp_has(d, "E003", "connected to itself")

        # A composite port that is not exposed by any connect.
        d = check_block(_comp_block("""
        @block A begin
            @ports begin
                a::Power{Rotation}
                b::Power{Rotation}
            end
            @components g = Gain()
            @connections connect(a, g.a)
        end
        """))
        @test _comp_has(d, "E003", "`b` of `A` is not connected")

        # A composite port exposed twice.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain()
            @connections begin
                connect(a, g.a)
                connect(a, g.b)
            end
        end
        """))
        @test _comp_has(d, "E003", "more than one")

        # Two ports of the block itself cannot be connected.
        d = check_block(_comp_block("""
        @block A begin
            @ports begin
                a::Power{Rotation}
                b::Power{Rotation}
            end
            @components g = Gain()
            @connections begin
                connect(a, b)
                connect(g.a, g.b)
            end
        end
        """))
        @test _comp_has(d, "E001", "joins two ports")

        # A composite may declare parameters (J2.6b), but no variables/equations of its own.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @parameters n::Real = 2.0
            @variables x::Real = 0.0
            @components g = Gain()
            @connections connect(a, g.a)
            @equations x ~ 0.0
        end
        """))
        @test !_comp_has(d, "E001", "cannot declare `@parameters`")
        @test _comp_has(d, "E001", "cannot declare `@variables`")
        @test _comp_has(d, "E001", "cannot declare `@equations`")

        # A composite parameter may be aliased into a component parameter.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @parameters n::Real = 2.0
            @components g = Gain(k = n)
            @connections connect(a, g.a)
        end
        """))
        @test isempty(d)

        # A parameter override is a constant expression in the defaults scope.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @components g = Gain(k = nope)
            @connections connect(a, g.a)
        end
        """))
        @test _comp_has(d, "E003", "not declared")

        # @connections without @components.
        d = check_block(_comp_block("""
        @block A begin
            @ports a::Power{Rotation}
            @connections connect(a, a)
        end
        """))
        @test _comp_has(d, "E003", "no `@components`")
    end

    @testset "negative: instantiation of a composite" begin
        # Unknown block name of a component: E101 with the component's path.
        fm = _comp_flat(_comp_model(
            "Unknown",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @ports a::Power{Rotation}
                @components g = Nope()
                @connections connect(a, g.a)
            end
            """))],
            Any[],
        ))
        e = _comp_diag(fm, "E101")
        @test e !== nothing
        @test occursin("unknown block `Nope`", fm.diagnostics[e].message)
        @test fm.diagnostics[e].path == "C1/g"

        # Unknown port of a known component: E102 with the component's path.
        fm = _comp_flat(_comp_model(
            "UnknownPort",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @ports a::Power{Rotation}
                @components g = Gain()
                @connections connect(a, g.zzz)
            end
            """))],
            Any[],
        ))
        e = _comp_diag(fm, "E102")
        @test e !== nothing
        @test occursin("has no port `zzz`", fm.diagnostics[e].message)
        @test fm.diagnostics[e].path == "C1/g"

        # A signal face that exposes a power port: E102 from the boundary kind check.
        fm = _comp_flat(_comp_model(
            "BadFace",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @outputs y::Real
                @components play = GearBacklash()
                @connections connect(y, play.a)
            end
            """))],
            Any[],
        ))
        @test _comp_has(fm.diagnostics, "E102", "does not match the internal")

        # An observable target that the component does not declare: E102 at instantiation.
        fm = _comp_flat(_comp_model(
            "BadObservable",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @ports begin
                    a::Power{Electrical}
                    b::Power{Electrical}
                end
                @components r = Resistor()
                @connections begin
                    connect(a, r.p)
                    connect(b, r.n)
                end
                @observables x = r.zzz
            end
            """))],
            Any[],
        ))
        e = _comp_diag(fm, "E102")
        @test e !== nothing
        @test occursin("no variable `zzz`", fm.diagnostics[e].message)
        @test fm.diagnostics[e].path == "C1/r"

        # A power face of the wrong domain than the internal port it exposes.
        fm = _comp_flat(_comp_model(
            "BadDomain",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @ports begin
                    a::Power{Electrical}
                    b::Power{Electrical}
                end
                @components play = GearBacklash()
                @connections begin
                    connect(a, play.a)
                    connect(play.b, b)
                end
            end
            """))],
            Any[],
        ))
        @test _comp_has(fm.diagnostics, "E102", "declares Electrical")

        # An internal connection between two concrete domains is a wire and E102.
        fm = _comp_flat(_comp_model(
            "MixDomains",
            Any[_comp_node("n1", "C1", _comp_inline("""
            @block C begin
                @ports begin
                    a::Power{Rotation}
                    b::Power{Rotation}
                end
                @components begin
                    r = Resistor(R = 1.0)
                    i = Inertia(J = 0.01)
                end
                @connections begin
                    connect(a, r.p)
                    connect(r.n, i.a)
                    connect(i.b, b)
                end
            end
            """))],
            Any[],
        ))
        @test _comp_has(fm.diagnostics, "E102", "domain mismatch")

        # A composite that contains itself is refused instead of recursing.
        dir = mktempdir()
        mkpath(joinpath(dir, "library"))
        write(joinpath(dir, "library", "Loop.jl"), """
        @block Loop begin
            @ports a::Power{Rotation}
            @components self = Loop()
            @connections connect(a, self.a)
        end
        """)
        fm = Compile.flatten(
            IR.parse_model(_comp_model(
                "LoopModel",
                Any[_comp_node("n1", "L1", _comp_ref("project:Loop"))],
                Any[],
            ));
            project_dir = dir,
        )
        @test _comp_has(fm.diagnostics, "E101", "contains itself")
    end

    @testset "flattening: <Instance>/<child> prefixes and boundary ports" begin
        fm = _comp_flat(_comp_drive(_comp_ref("project:GearWithBacklash")))
        @test isempty(fm.diagnostics)
        ids = Set(v.id for v in fm.variables)
        @test "G1/gear/a.e" in ids
        @test "G1/gear/b.e" in ids
        @test "G1/play/phi" in ids
        @test "G1/play/T" in ids
        # The composite's own face is not a flat variable: it *is* the internal port.
        @test "G1/a.e" ∉ ids
        @test "G1/b.f" ∉ ids
        # Five block instances: Sf1, G1/gear, G1/play, J1, F1. The composite is not an instance.
        @test length(fm.instances) == 5
        @test fm.stats.nodes == 5
        # The outer bond lands on the internal gear port (J1.4's subsystem behaviour).
        @test any(
            c -> c.id == "c1" && c.to_path == "G1/gear" && c.to_port === :a,
            fm.connections,
        )
        @test any(
            c -> c.from_path == "G1/play" && c.from_port === :b &&
                 c.to_path == "J1" && c.to_port === :a,
            fm.connections,
        )

        # Nested composites: an inline wrapper around the project composite.
        wrap = _comp_inline("""
        @block Wrap begin
            @ports begin
                a::Power{Rotation}
                b::Power{Rotation}
            end
            @components inner = GearWithBacklash()
            @connections begin
                connect(a, inner.a)
                connect(inner.b, b)
            end
        end
        """)
        fmw = _comp_flat(_comp_drive(wrap; f = -0.3))
        @test isempty(fmw.diagnostics)
        wid = Set(v.id for v in fmw.variables)
        @test "G1/inner/gear/a.e" in wid
        @test "G1/inner/play/phi" in wid
        result, _ = _comp_run(fmw; t_end = 0.05, points = 51)
        @test result.status == "done"

        # Signal faces: @inputs/@outputs expose internal inputs/outputs of components.
        sig = _comp_inline("""
        @block SigWrap begin
            @inputs u::Real
            @outputs y::Real
            @components begin
                g1 = Gain(k = 2.0)
                g2 = Gain(k = 3.0)
            end
            @connections begin
                connect(u, g1.u)
                connect(g1.y, g2.u)
                connect(g2.y, y)
            end
        end
        """)
        fms = _comp_flat(_comp_model(
            "SigFace",
            Any[
                _comp_node("n1", "C1", _comp_ref("stdlib:sources/Constant");
                    params = Dict("value" => "1.0")),
                _comp_node("n2", "W1", sig),
            ],
            Any[_comp_conn("c1", "signal", "n1", "y", "n2", "u")];
            t_end = 0.01,
        ))
        @test isempty(fms.diagnostics)
        eqs = [(Flat.flat_id(e.lhs), Flat.flat_id(e.rhs)) for e in fms.equations]
        @test ("W1/g1/u", "C1/y") in eqs
        @test ("W1/g2/u", "W1/g1/y") in eqs
        result, dir = _comp_run(fms; t_end = 0.01, points = 11)
        @test result.status == "done"
        cols = _comp_columns(dir)
        @test all(cols["W1/g2/y"] .== 6.0)

        # A component parameter may be an expression over the composite's `@constants`; it is
        # folded at instantiation and is the value the internal block sees (n = 2 * 2 = 4).
        const_case = _comp_inline("""
        @block ConstCase begin
            @ports begin
                a::Power{Rotation}
                b::Power{Rotation}
            end
            @constants gain::Real = 2.0
            @components gear = IdealGear(n = 2.0 * gain)
            @connections begin
                connect(a, gear.a)
                connect(gear.b, b)
            end
        end
        """)
        fmc = _comp_flat(_comp_model(
            "ConstCase",
            Any[
                _comp_node("n1", "Sf1", _comp_ref("stdlib:bondgraph/Sf");
                    params = Dict("f" => "-0.4")),
                _comp_node("n2", "W1", const_case),
                _comp_node("n3", "J1", _comp_ref("stdlib:rotation/Inertia");
                    params = Dict("J" => "0.01")),
                _comp_node("n4", "F1", _comp_ref("stdlib:rotation/FixedShaft")),
            ],
            Any[
                _comp_conn("c1", "bond", "n1", "p", "n2", "a"),
                _comp_conn("c2", "wire", "n2", "b", "n3", "a"),
                _comp_conn("c3", "wire", "n3", "b", "n4", "a"),
            ];
            t_end = 0.05,
        ))
        @test isempty(fmc.diagnostics)
        @test any(p -> p.id == "W1/gear/n" && p.value == 4.0, fmc.parameters)
        result, dir = _comp_run(fmc; t_end = 0.05, points = 51)
        @test result.status == "done"
        cols = _comp_columns(dir)
        # 0.4 rad/s in, ratio 4, so the output turns at 0.1 rad/s.
        @test isapprox(cols["J1/w"][end], 0.1; atol = 1e-12)
    end

    @testset "GearBacklash: dead zone and contact stiffness (static)" begin
        function static_model(phi0, fb)
            return _comp_model(
                "PlayStatic",
                Any[
                    _comp_node("n1", "SfA", _comp_ref("stdlib:bondgraph/Sf");
                        params = Dict("f" => "0.0")),
                    _comp_node("n2", "P1", _comp_ref("project:GearBacklash");
                        params = Dict("k" => "1e4", "d" => "5.0", "gap" => "0.01"),
                        starts = Dict("phi" => string(phi0))),
                    _comp_node("n3", "SfB", _comp_ref("stdlib:bondgraph/Sf");
                        params = Dict("f" => string(fb))),
                ],
                Any[
                    _comp_conn("c1", "bond", "n1", "p", "n2", "a"),
                    _comp_conn("c2", "bond", "n3", "p", "n2", "b"),
                ];
                t_end = 0.01,
            )
        end
        for (phi0, fb, expected) in (
            (0.0, 0.0, 0.0),        # dead centre
            (0.004, 0.0, 0.0),      # inside the gap: no torque at all
            (-0.004, 0.0, 0.0),
            (0.02, 0.0, 150.0),     # contact: k * (phi - gap/2)
            (-0.02, 0.0, -150.0),
            (0.02, 0.1, 150.5),     # contact plus damping d * w
        )
            fm = _comp_flat(static_model(phi0, fb))
            @test isempty(fm.diagnostics)
            result, dir = _comp_run(fm; t_end = 0.01, reltol = 1e-10, abstol = 1e-12,
                points = 11)
            @test result.status == "done"
            cols = _comp_columns(dir)
            @test cols["P1/T"][1] == expected
            @test cols["P1/a.e"][1] == expected
            @test cols["P1/b.e"][1] == -expected
            # w = a.f - b.f = 0 - (-fb) = fb, so `phi` ramps at `fb` (and stands still for 0).
            @test isapprox(cols["P1/phi"][end], phi0 + fb * 0.01; atol = 1e-12)
            for i in eachindex(cols["time"])
                @test cols["P1/T"][i] ==
                      _comp_torque(cols["P1/phi"][i], cols["P1/w"][i])
            end
            if fb == 0.0
                # With both ports held still the operating point stands: every sample.
                @test all(cols["P1/T"] .== expected)
                @test all(cols["P1/a.e"] .== expected)
                @test all(cols["P1/b.e"] .== -expected)
            end
        end
    end

    @testset "GearBacklash: energy behaviour" begin
        function energy_model(d)
            return _comp_model(
                "PlayEnergy",
                Any[
                    _comp_node("n1", "SfA", _comp_ref("stdlib:bondgraph/Sf");
                        params = Dict("f" => "0.0")),
                    _comp_node("n2", "P1", _comp_ref("project:GearBacklash");
                        params = Dict("k" => "1e4", "d" => d, "gap" => "0.01"),
                        starts = Dict("phi" => "0.02")),
                    _comp_node("n3", "J1", _comp_ref("stdlib:rotation/Inertia");
                        params = Dict("J" => "0.01")),
                    _comp_node("n4", "F1", _comp_ref("stdlib:rotation/FixedShaft")),
                ],
                Any[
                    _comp_conn("c1", "bond", "n1", "p", "n2", "a"),
                    _comp_conn("c2", "wire", "n2", "b", "n3", "a"),
                    _comp_conn("c3", "wire", "n3", "b", "n4", "a"),
                ],
            )
        end
        function energy(cols)
            return [
                0.5 * 0.01 * cols["J1/w"][i]^2 +
                0.5 * _COMP_K * max(abs(cols["P1/phi"][i]) - _COMP_GAP / 2, 0.0)^2
                for i in eachindex(cols["time"])
            ]
        end

        # d = 0: an ordinary C element. The potential at phi = 0.02 (x = 0.015) is
        # 0.5 * 1e4 * 0.015^2 = 1.125 J, and it must stay there (the input is fixed, so no
        # work crosses the boundary). 1 ms is a quarter of the 6.3 ms contact period.
        fm = _comp_flat(energy_model("0.0"))
        @test isempty(fm.diagnostics)
        result, dir = _comp_run(fm; t_end = 0.001, reltol = 1e-10, abstol = 1e-12)
        @test result.status == "done"
        @test isempty(result.diagnostics)
        cols = _comp_columns(dir)
        e = energy(cols)
        @test e[1] == 1.125
        @test maximum(abs.(e .- e[1])) < 1.0e-9
        # The stored energy is the spring's: T = k * x on every sample.
        for i in eachindex(cols["time"])
            @test isapprox(
                cols["P1/T"][i],
                _COMP_K * (cols["P1/phi"][i] - _COMP_GAP / 2);
                atol = 1e-9, rtol = 1e-9,
            )
        end

        # d = 5: the damper dissipates; the same initial energy decays monotonically.
        fm = _comp_flat(energy_model("5.0"))
        @test isempty(fm.diagnostics)
        result, dir = _comp_run(fm; t_end = 0.01, reltol = 1e-10, abstol = 1e-12)
        @test result.status == "done"
        @test isempty(result.diagnostics)
        cols = _comp_columns(dir)
        e = energy(cols)
        @test e[1] == 1.125
        @test e[end] < 0.1 * e[1]
        @test maximum(diff(e)) <= 1e-12
    end

    @testset "text composite == model-JSON subsystem, bit for bit" begin
        text = _comp_flat(_comp_drive(_comp_ref("project:GearWithBacklash")))
        json = _comp_flat(_comp_drive(_comp_json_subsystem_g1()))
        @test isempty(text.diagnostics)
        @test isempty(json.diagnostics)

        @test [v.id for v in text.variables] == [v.id for v in json.variables]
        @test [p.id for p in text.parameters] == [p.id for p in json.parameters]
        @test [p.value for p in text.parameters] == [p.value for p in json.parameters]
        @test [(sprint(show, e.lhs), sprint(show, e.rhs)) for e in text.equations] ==
              [(sprint(show, e.lhs), sprint(show, e.rhs)) for e in json.equations]
        @test [s.id for s in text.signals] == [s.id for s in json.signals]
        # The structural hash is the same, which is exactly "the same structure".
        @test compile_key(text) == compile_key(json)

        rt, text_dir = _comp_run(text; t_end = 0.5)
        rj, json_dir = _comp_run(json; t_end = 0.5)
        @test rt.status == "done"
        @test rj.status == "done"
        ct = _comp_columns(text_dir)
        cj = _comp_columns(json_dir)
        @test keys(ct) == keys(cj)
        @test ct["time"] == cj["time"]
        # Bit for bit on the same solver and settings, every recorded column.
        @test all(ct[id] == cj[id] for id in keys(ct))
    end

    @testset "GearWithBacklash: the composite simulates through the gap and into contact" begin
        fm = _comp_flat(_comp_drive(_comp_ref("project:GearWithBacklash")))
        result, dir = _comp_run(fm; t_end = 0.5)
        @test result.status == "done"
        @test isempty(result.diagnostics)
        cols = _comp_columns(dir)
        # Event rows (contact instants) are recorded twice, so there are at least 501 rows.
        @test length(cols["time"]) >= 501
        @test length(cols["time"]) == Int(result.time.n)

        phi = cols["G1/play/phi"]
        w = cols["G1/play/w"]
        t = cols["G1/play/T"]
        # The input is 0.3 rad/s through a 10:1 gear, so the output side moves at 0.03 rad/s
        # and the backlash is taken up within the run: phi reaches the gap edge, contact
        # transmits a torque (~0.216 N*m peak) and the play falls back into the gap.
        @test 0.005 < maximum(phi) < 0.0055
        @test maximum(t) > 0.2
        @test minimum(t) >= 0.0
        # Every sample obeys the spec's dead-zone law exactly (the golden number).
        for i in eachindex(phi)
            @test cols["G1/play/T"][i] == _comp_torque(phi[i], w[i])
        end
        @test isapprox(maximum(t), 0.21638545146325042; rtol = 1e-3)
        # Inside the gap the transmitted torque is exactly zero.
        for i in eachindex(phi)
            abs(phi[i]) <= _COMP_GAP / 2 && @test t[i] == 0.0
        end
        # The gear's efficiency is part of the composite: the input torque is T_out/(n*eta).
        i = argmax(t)
        @test isapprox(
            cols["G1/gear/a.e"][i], t[i] / (10.0 * 0.9); rtol = 1e-6, atol = 1e-9,
        )
    end
end
