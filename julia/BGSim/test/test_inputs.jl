# X-EX1: driving parameters from a sampled trajectory, `simulate(flat; inputs)`
# (src/sim/inputs.jl), and the pass-through export input (`Export.host_inputs`).
#
# The model: an ExportInput `In` feeds an Integrator (x' = u) and a 0.1 s ZOH. The input is
# driven with u = 1 on [0, 0.1), -2 on [0.1, 0.3), 0.5 from 0.3 on (zero-order hold), so
#   x(0.2) = 0.1 - 0.2 = -0.1,  x(0.4) = 0.1 - 0.4 + 0.05 = -0.25,
# and the ZOH tick at t = 0.1 samples the value held *before* the change at 0.1 (1.0), the
# tick at 0.2 samples -2 and the tick at 0.3 samples -2 again (the change at 0.3 follows it).
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
using .BondGraphGolden

function _inputs_model(input_ref)
    return bg_model(
        "DrivenInput",
        [
            bg_node("n1", "In", bg_ref(input_ref); params = Dict{String,Any}("value" => "0.0")),
            bg_node("n2", "Int1", bg_ref("stdlib:continuous/Integrator")),
            merge(bg_node("n3", "Hold", bg_ref("stdlib:discrete/ZOH")),
                Dict{String,Any}("constants" => Dict{String,Any}("sample_period" => "0.1"))),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "signal", "n1", "y", "n3", "u"),
        ];
        t_end = 0.5, points = 51, solver = "Tsit5",
    )
end

@testset "simulate(...; inputs): zero-order hold of a sampled trajectory" begin
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(_inputs_model("stdlib:converters/ExportInput")))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    traj = Dict("In/value" => (t = [0.0, 0.1, 0.3], u = [1.0, -2.0, 0.5]))
    dir = mktempdir()
    result = BGSim.simulate(flat; run_dir = dir, inputs = traj,
        settings = Dict("t_end" => 0.5, "solver" => "Tsit5", "reltol" => 1e-10, "abstol" => 1e-12,
            "output" => Dict("mode" => "points", "points" => 51)))
    @test result.status == "done"
    cols = BondGraphGolden.bg_columns(dir)
    @test bg_value(cols, "In/y", 0.0) == 1.0          # the sample at t_start holds from row zero
    @test bg_value(cols, "In/y", 0.1) == -2.0         # right limit at the change
    @test bg_value(cols, "In/y", 0.25) == -2.0
    @test bg_value(cols, "In/y", 0.5) == 0.5
    @test isapprox(bg_value(cols, "Int1/y", 0.2), -0.1; atol = 1e-9)
    @test isapprox(bg_value(cols, "Int1/y", 0.4), -0.25; atol = 1e-9)
    # The change is recorded as a left/right pair at its instant.
    i = findall(t -> abs(t - 0.1) < 1e-12, cols["time"])
    @test length(i) == 2 && cols["In/y"][i] == [1.0, -2.0]
    # Ticks sample the value held before a change at the same instant.
    @test bg_value(cols, "Hold/y", 0.1) == 1.0
    @test bg_value(cols, "Hold/y", 0.2) == -2.0
    @test bg_value(cols, "Hold/y", 0.3) == -2.0
    @test bg_value(cols, "Hold/y", 0.4) == 0.5
    # Without inputs the marker is its constant value.
    plain = BGSim.simulate(flat; run_dir = mktempdir(), settings = Dict("t_end" => 0.5,
        "solver" => "Tsit5", "output" => Dict("mode" => "points", "points" => 51)))
    @test plain.status == "done"
    @test bg_value(BondGraphGolden.bg_columns(plain.run_dir), "Int1/y", 0.5) == 0.0

    # Changes between output points are exact stops too.
    dir2 = mktempdir()
    r2 = BGSim.simulate(flat; run_dir = dir2, inputs = Dict("In/value" => ([0.0, 0.123], [1.0, 0.0])),
        settings = Dict("t_end" => 0.5, "solver" => "Tsit5", "reltol" => 1e-10, "abstol" => 1e-12,
            "output" => Dict("mode" => "points", "points" => 51)))
    @test r2.status == "done"
    @test isapprox(bg_value(BondGraphGolden.bg_columns(dir2), "Int1/y", 0.5), 0.123; atol = 1e-9)

    @test_throws ArgumentError BGSim.simulate(flat; inputs = Dict("Nope/value" => ([0.0], [1.0])))
    @test_throws ArgumentError BGSim.simulate(flat; inputs = Dict("In/value" => ([0.1, 0.0], [1.0, 2.0])))
    @test_throws ArgumentError BGSim.simulate(flat; inputs = Dict("Hold/y" => ([0.0], [1.0])))
end

@testset "pass-through export input: host_inputs + inputs drive the marker" begin
    # The pass-through marker needs a wired input; wire a Constant into it.
    doc = _inputs_model("stdlib:converters/ExportInputPass")
    push!(doc["diagram"]["nodes"], bg_node("n4", "C1", bg_ref("stdlib:sources/Constant");
        params = Dict{String,Any}("value" => "3.0")))
    push!(doc["diagram"]["connections"], bg_conn("c3", "signal", "n4", "y", "n1", "u"))
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc))
    @test isempty([d for d in flat.diagnostics if d.severity == "error"])
    @test BGSim.Export.input_markers(flat) == ["In"]
    # In simulation it passes the Constant through.
    r = BGSim.simulate(flat; run_dir = mktempdir(), settings = Dict("t_end" => 0.5,
        "solver" => "Tsit5", "reltol" => 1e-10, "abstol" => 1e-12,
        "output" => Dict("mode" => "points", "points" => 51)))
    @test r.status == "done"
    @test isapprox(bg_value(BondGraphGolden.bg_columns(r.run_dir), "Int1/y", 0.5), 1.5; atol = 1e-9)
    # Hosted, the trajectory replaces it.
    host = BGSim.Export.host_inputs(flat)
    dir = mktempdir()
    r = BGSim.simulate(host; run_dir = dir, inputs = Dict("In/value" => ([0.0, 0.1, 0.3], [1.0, -2.0, 0.5])),
        settings = Dict("t_end" => 0.5, "solver" => "Tsit5", "reltol" => 1e-10, "abstol" => 1e-12,
            "output" => Dict("mode" => "points", "points" => 51)))
    @test r.status == "done"
    cols = BondGraphGolden.bg_columns(dir)
    @test isapprox(bg_value(cols, "Int1/y", 0.4), -0.25; atol = 1e-9)
    @test bg_value(cols, "In/u", 0.4) == 3.0          # the cut wire still records its source
end
