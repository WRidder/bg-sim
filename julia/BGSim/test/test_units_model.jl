# Work package J2.5: units at the model level (plan 5.3 and 5.6, decision D9).
#
# The acceptance tests of the work package:
#   * a Generic `C` bonded to an Electrical island reports its `c` parameter in farads and
#     its port fields in V/A, and the signal list carries the concrete units;
#   * the same `C` on Translation reports `m/N` and on Rotation `rad/(N*m)`;
#   * a signal wire from an `mm` output to an `m` input reports `unitFactors["c1"] == 0.001`
#     *and* the generated equation and the simulated columns are scaled by 0.001;
#   * an `s` output into an `m` input is E102 on that connection, and both the message and
#     the hint name both units;
#   * the adopted-domain unit environment substitutes a Generic block's declarations and
#     port fields and gives an E006 the concrete unit text (`[s*A]`, not `[flow*s]`).
#
# The builders are prefixed `_um_` because every test file is included into `Main`.
using Test
using JSON3
import BGSim
import BGSim.IR
import BGSim.Flat
import BGSim.Compile
import BGSim.Units
import BGSim: simulate, RunSettings

const UM = BGSim.Units

# ---------------------------------------------------------------------------------------
# Model document builders
# ---------------------------------------------------------------------------------------

function _um_node(id, name, block)
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(),
        "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
end

_um_ref(ref) = Dict{String,Any}("ref" => ref)
_um_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _um_conn(id, kind, from_node, from_port, to_node, to_port = nothing)
    from = Dict{String,Any}("node" => from_node)
    from_port === nothing || (from["port"] = from_port)
    to = Dict{String,Any}("node" => to_node)
    to_port === nothing || (to["port"] = to_port)
    return Dict{String,Any}("id" => id, "kind" => kind, "from" => from, "to" => to)
end

function _um_model(name, nodes, connections; t_end = 1.0, points = 2)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...],
            "connections" => Any[connections...],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "auto",
            "reltol" => 1.0e-9, "abstol" => 1.0e-11, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_um_flat(doc) = Compile.flatten(IR.parse_model(doc))
_um_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _um_diag(fm, code; connection = nothing)
    for d in fm.diagnostics
        d.code == code || continue
        connection === nothing || d.connection == connection || continue
        return d
    end
    return nothing
end

function _um_signal(fm, id)
    i = findfirst(s -> s.id == id, fm.signals)
    return i === nothing ? nothing : fm.signals[i]
end

_um_param(fm, id) = fm.parameters[findfirst(p -> p.id == id, fm.parameters)]
_um_var(fm, id) = fm.variables[findfirst(v -> v.id == id, fm.variables)]

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _um_columns(dir)
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

# A Generic `C` on a fixed 1-junction island of each domain: `fixed_port` is the port the
# fixed element exposes (`p` for `electrical/Ground`, `a` for `translation/Fixed` and
# `rotation/FixedShaft`).
function _um_c_model(name, fixed_ref, fixed_port)
    return _um_model(name, Any[
        _um_node("n1", "F1", _um_ref(fixed_ref)),
        _um_node("n2", "J1", Dict{String,Any}("junction" => "1")),
        _um_node("n3", "C1", _um_ref("stdlib:bondgraph/C")),
    ], Any[
        _um_conn("c1", "bond", "n1", fixed_port, "n2"),
        _um_conn("c2", "bond", "n2", nothing, "n3", "p"),
    ])
end

const UM_SINK = """
@block MSink begin
    @inputs u::Real, [unit = "m"]
    @outputs y::Real = 0.0, [unit = "m"]
    @equations y ~ u
end
"""

const UM_MM_SOURCE = """
@block MmOut begin
    @outputs y::Real = 0.0, [unit = "mm"]
    @equations y ~ 5.0
end
"""

const UM_S_SOURCE = """
@block SOut begin
    @outputs y::Real = 0.0, [unit = "s"]
    @equations y ~ 5.0
end
"""

@testset "J2.5 units at the model level" begin
    @testset "a C on an Electrical bond reports c in farads" begin
        fm = _um_flat(_um_c_model("COnElectrical", "stdlib:electrical/Ground", "p"))
        @test isempty(_um_errors(fm))
        @test fm.domains == Dict("c1" => "Electrical", "c2" => "Electrical")

        c = _um_param(fm, "C1/c")
        @test c.unit == UM.parse_unit("F")
        @test UM.unit_string(c.unit) == "F"
        # q = flow*s is ampere-seconds.
        @test _um_var(fm, "C1/q").unit == UM.parse_unit("A*s")
        @test _um_signal(fm, "C1/q").unit == "s*A"
        @test _um_signal(fm, "C1/p.e").unit == "V"
        @test _um_signal(fm, "C1/p.f").unit == "A"
        @test _um_signal(fm, "C1/p.P").unit == "W"
    end

    @testset "the same C on Translation and Rotation" begin
        tr = _um_flat(_um_c_model("COnTranslation", "stdlib:translation/Fixed", "a"))
        @test isempty(_um_errors(tr))
        @test tr.domains == Dict("c1" => "Translation", "c2" => "Translation")
        @test _um_param(tr, "C1/c").unit == UM.parse_unit("m/N")
        @test _um_var(tr, "C1/q").unit == UM.parse_unit("m")
        @test _um_signal(tr, "C1/p.e").unit == "N"
        @test _um_signal(tr, "C1/p.f").unit == "m/s"
        @test _um_signal(tr, "C1/p.P").unit == "W"

        rot = _um_flat(_um_c_model("COnRotation", "stdlib:rotation/FixedShaft", "a"))
        @test isempty(_um_errors(rot))
        @test rot.domains == Dict("c1" => "Rotation", "c2" => "Rotation")
        @test _um_param(rot, "C1/c").unit == UM.parse_unit("rad/(N*m)")
        @test UM.is_dimensionless(_um_var(rot, "C1/q").unit)   # flow*s = rad
        @test _um_signal(rot, "C1/p.e").unit == "J"           # N*m is dimension-based
        @test _um_signal(rot, "C1/p.f").unit == "1/s"
        @test _um_signal(rot, "C1/p.P").unit == "W"
    end

    @testset "an mm output into an m input scales by 0.001" begin
        doc = _um_model("MmToM", Any[
            _um_node("n1", "MmOut", _um_inline(UM_MM_SOURCE)),
            _um_node("n2", "MSink", _um_inline(UM_SINK)),
        ], Any[_um_conn("c1", "signal", "n1", "y", "n2", "u")]; t_end = 0.5)
        fm = _um_flat(doc)
        @test isempty(fm.diagnostics)
        @test fm.unit_factors == Dict("c1" => 0.001)
        @test _um_signal(fm, "MmOut/y").unit == "mm"
        @test _um_signal(fm, "MSink/u").unit == "m"

        # The factor is in the generated connection equation, not just in the map.
        i = findfirst(e -> Flat.flat_id(e.lhs) == "MSink/u", fm.equations)
        @test i !== nothing
        @test occursin("0.001", sprint(show, fm.equations[i]))
        @test occursin("MmOut/y", sprint(show, fm.equations[i]))

        # And the run really is scaled: 5 mm becomes 0.005 m.
        dir = mktempdir()
        result = simulate(
            fm;
            run_dir = dir,
            settings = RunSettings(
                t_end = 0.5,
                output = Dict{String,Any}("mode" => "points", "points" => 2),
            ),
        )
        @test result.status == "done"
        @test isempty(_um_errors(fm))
        columns = _um_columns(dir)
        @test isapprox(columns["MmOut/y"][1], 5.0; atol = 1e-12)
        @test isapprox(columns["MSink/u"][1], 0.005; atol = 1e-12)
        @test isapprox(columns["MSink/y"][1], 0.005; atol = 1e-12)
        @test isapprox(columns["MSink/u"][end], 0.005; atol = 1e-12)
    end

    @testset "an s output into an m input is E102 naming both units" begin
        doc = _um_model("SToM", Any[
            _um_node("n1", "SOut", _um_inline(UM_S_SOURCE)),
            _um_node("n2", "MSink", _um_inline(UM_SINK)),
        ], Any[_um_conn("c1", "signal", "n1", "y", "n2", "u")])
        fm = _um_flat(doc)
        d = _um_diag(fm, "E102"; connection = "c1")
        @test d !== nothing
        @test d.node == "n2"
        @test occursin("[s]", d.message) && occursin("[m]", d.message)
        @test occursin("[s]", d.hint) && occursin("[m]", d.hint)
        @test !haskey(fm.unit_factors, "c1")
        # A dimension mismatch must not emit a scaled connection equation.
        @test !any(e -> Flat.flat_id(e.lhs) == "MSink/u", fm.equations)
    end

    @testset "the adopted domain is the per-instance unit environment" begin
        # A Generic block with one declaration that is pseudo-dimensional and one that is
        # concrete: at Generic it is E006 with the written labels, after adoption the same
        # check names the concrete units (`[s*A]` for `flow*s` on Electrical).
        pb = BGSim.parse_block(
            """
            @block BadMix begin
                @ports p::Power{Generic}
                @parameters a::Real = 1.0, [unit = "flow*s"]
                @variables y::Real = 0.0, [unit = "m"]
                @equations p.f ~ y + a
            end
            """;
            ref = "inline:badmix",
        )
        generic = UM.unit_env(pb)
        @test generic.labels[:a] == "flow*s"
        @test generic.labels[Symbol("p.e")] == "effort"

        adopted = UM.unit_env(pb, :Electrical)
        @test adopted.names[:a] == UM.parse_unit("A*s")
        @test adopted.labels[:a] == "s*A"
        @test adopted.names[Symbol("p.e")] == UM.parse_unit("V")
        @test adopted.names[Symbol("p.f")] == UM.parse_unit("A")
        @test adopted.labels[Symbol("p.e")] == "V"
        @test adopted.labels[Symbol("p.f")] == "A"

        generic_diags = UM.check_units(pb)
        @test length(generic_diags) == 1
        @test occursin("[m]", generic_diags[1].message)
        @test occursin("[flow*s]", generic_diags[1].message)

        adopted_diags = UM.check_units(pb, :Electrical)
        @test length(adopted_diags) == 1
        @test adopted_diags[1].code == "E006"
        @test occursin("[m]", adopted_diags[1].message)
        @test occursin("[s*A]", adopted_diags[1].message)
        @test !occursin("flow", adopted_diags[1].message)
        @test occursin("[m]", adopted_diags[1].hint)
        @test occursin("[s*A]", adopted_diags[1].hint)

        # The flattener's re-check of a valid Generic block on each adopted domain is clean
        # (the tests above assert `isempty(_um_errors(fm))`; this pins the call's seam).
        @test isempty(UM.check_units(BGSim.parse_block(
            "@block Cx begin\n  @ports p::Power{Generic}\n" *
            "  @parameters c::Real = 1.0, [unit = \"flow*s/effort\"]\n" *
            "  @variables q::Real = 0.0, [unit = \"flow*s\"]\n" *
            "  @equations begin\n    ddt(q) ~ p.f\n    p.e ~ q / c\n  end\nend\n";
            ref = "inline:cx",
        ), :Electrical))
    end
end
