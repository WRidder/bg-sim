# Work package J-EX11: export scoped to a subsystem (plan/EXPORT_PLAN.md).
#
# `Export.scope_document` turns one subsystem into the exported model: its signal ports become
# ExportInput/ExportOutput markers, a power port gets an adapter that imposes the chosen
# variable and measures the conjugate, and everything outside the subsystem is dropped.
#   * the interface is exactly the subsystem's ports (`u`, `y`, `p_e` in, `p_f` out);
#   * an element outside the scope (here an `@events` test harness) does not reach the export;
#   * a bad scope (missing, not a subsystem, a power port without a choice) is E112;
#   * in C, the lag output and the resistor flow (`p_f = p_e / r`) are the analytic values.

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden
import BGSim.IR
import BGSim.Compile

const _SC = BGSim.Export

const _SC_LAG = """
@block Lag begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.01, [unit = "s"]
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ x
    end
end
"""

# A test harness outside the scope: a sawtooth with an event, which the export never sees.
const _SC_HARNESS = """
@block Saw begin
    @outputs y::Real
    @variables s::Real = 0.0
    @equations ddt(s) ~ 1.0
    @events begin
        s > 0.05 => begin
            reinit(s, 0.0)
        end
    end
    @equations y ~ s
end
"""

function _sc_model()
    inner = Dict{String,Any}(
        "nodes" => Any[
            bg_node("s1", "Lag", Dict{String,Any}("inline" => Dict{String,Any}("source" => _SC_LAG))),
            bg_node("s2", "Load", bg_ref("stdlib:bondgraph/R"); params = Dict{String,Any}("r" => "2.0")),
        ],
        "connections" => Any[],
        "subsystemPorts" => Any[],
        "annotations" => Any[],
    )
    ports = Any[
        Dict{String,Any}("name" => "u", "kind" => "signal", "direction" => "input", "type" => "Real",
            "size" => Any[1], "node" => "s1", "port" => "u"),
        Dict{String,Any}("name" => "y", "kind" => "signal", "direction" => "output", "type" => "Real",
            "size" => Any[1], "node" => "s1", "port" => "y"),
        Dict{String,Any}("name" => "p", "kind" => "power", "size" => Any[1], "node" => "s2", "port" => "p"),
    ]
    plant = bg_node("n2", "Plant", Dict{String,Any}("subsystem" => Dict{String,Any}("ports" => ports, "diagram" => inner)))
    nodes = Any[
        bg_node("n1", "Src", bg_ref("stdlib:sources/Constant"); params = Dict{String,Any}("k" => "2.0")),
        plant,
        bg_node("n3", "Drive", bg_ref("stdlib:bondgraph/Se"); params = Dict{String,Any}("e" => "3.0")),
        bg_node("n4", "Harness", Dict{String,Any}("inline" => Dict{String,Any}("source" => _SC_HARNESS))),
    ]
    conns = Any[
        bg_conn("c1", "signal", "n1", "y", "n2", "u"),
        bg_conn("c2", "bond", "n3", "p", "n2", "p"),
    ]
    return bg_model("ScopeModel", nodes, conns; t_end = 0.1, points = 11)
end

_sc_codes(diags) = Set(d.code for d in diags)

@testset "export scope (J-EX11)" begin
    doc = _sc_model()

    @testset "bad scopes are E112" begin
        d, diags = _SC.scope_document(doc, "Nope")
        @test d === nothing && "E112" in _sc_codes(diags)
        d, diags = _SC.scope_document(doc, "Src")                 # not a subsystem
        @test d === nothing && "E112" in _sc_codes(diags)
        d, diags = _SC.scope_document(doc, "Plant")               # p needs effort or flow
        @test d === nothing && "E112" in _sc_codes(diags)
        @test any(occursin("`p`", x.message) for x in diags)
        @test isempty(Compile.flatten(IR.parse_model(doc)).diagnostics |> ds -> filter(x -> x.severity == "error", ds))
    end

    scoped, diags = _SC.scope_document(doc, "Plant";
        power_inputs = Dict("p" => "effort"), input_values = Dict("u" => 2.0, "p" => 3.0))

    @testset "the scoped document" begin
        @test isempty(diags)
        names = Set(String(n["name"]) for n in scoped["diagram"]["nodes"])
        @test names == Set(["Plant", "u", "y", "p_port", "p_e", "p_f"])
        @test !("Harness" in names) && !("Src" in names)
        @test scoped["name"] == "ScopeModel_Plant"
        @test scoped["settings"]["t_end"] == 0.1
    end

    @testset "flow into the subsystem in both bond orientations, and imposed flow" begin
        flowing(s) = begin
            dir = mktempdir()
            BGSim.simulate(Compile.flatten(IR.parse_model(s)); run_dir = dir,
                settings = Dict{String,Any}("t_end" => 0.01, "output" => Dict("mode" => "points", "points" => 3)))
            BondGraphGolden.bg_columns(dir)["p_port/y"][end]
        end
        @test flowing(scoped) ≈ 1.5
        flipped = deepcopy(doc)
        c = flipped["diagram"]["connections"][2]
        c["from"], c["to"] = c["to"], c["from"]
        s2, _ = _SC.scope_document(flipped, "Plant"; power_inputs = Dict("p" => "effort"),
            input_values = Dict("p" => 3.0))
        @test flowing(s2) ≈ 1.5
        s3, _ = _SC.scope_document(doc, "Plant"; power_inputs = Dict("p" => "flow"),
            input_values = Dict("p" => 1.5))
        @test flowing(s3) ≈ 3.0                                 # the effort r * f
    end

    @testset "exports with the subsystem's ports as the interface" begin
        dir = mktempdir()
        flat = Compile.flatten(IR.parse_model(scoped))
        @test isempty(filter(x -> x.severity == "error", flat.diagnostics))
        r = _SC.export_model(flat, dir; settings = _SC.ExportSettings(t_end = 0.1))
        @test r.ok
        @test !("W209" in _sc_codes(r.diagnostics))
        rep = r.report
        @test Set(i["name"] for i in rep["inputs"]) == Set(["u", "p_e"])
        @test Set(o["name"] for o in rep["outputs"]) == Set(["y", "p_f"])
        @test Dict(i["name"] => i["start"] for i in rep["inputs"]) == Dict("u" => 2.0, "p_e" => 3.0)

        cc = Sys.which("gcc")
        if cc === nothing
            @info "export scope: no gcc on PATH, the compile-and-run check is skipped"
        else
            src = joinpath(dir, "sources")
            exe = joinpath(dir, Sys.iswindows() ? "check.exe" : "check")
            files = [joinpath(src, f) for f in ("model.c", "bg_solver.c", "fmi2_cs.c")]
            @test success(`$cc -std=c11 -O2 -I $src $(joinpath(_SC.RUNTIME_DIR, "alloc_check.c")) $files -o $exe -lm`)
            per = round(Int, rep["step"] / rep["dt"])
            out = read(`$exe $per 100`, String)
            @test occursin("after instantiate 0", out)
            y0 = parse(Float64, match(r"y\[0\] = (\S+)", out).captures[1])
            first_out = rep["outputs"][1]["name"]
            # The harness prints the first output: the lag at t = 0.1 s, or the flow into the
            # subsystem, 3 / 2 (positive: the resistor absorbs power).
            expected = first_out == "y" ? 2.0 * (1 - exp(-0.1 / 0.01)) : 1.5
            @test isapprox(y0, expected; rtol = 1e-6)
        end
    end
end
