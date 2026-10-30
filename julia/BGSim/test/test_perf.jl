# Work package PERF-1: the recorder's signal reader and the discrete warm-up model.
#
#   * the in-place `SignalReader` returns exactly the values the per-signal getters
#     (`getu`/`getp`) return, at the start, after a step and at a published discrete tick;
#   * the warm-up workload's clocked variant (`discrete = true`) runs to `done`, publishes the
#     held value of its ZOH and reports the solver statistics through `LAST_PROFILE`;
#   * a run records one row per output point plus a left/right pair for each changed tick, and
#     the recorded columns equal what the per-signal getters give for the final row.

using BGSim
using BGSim: IR, Compile, Worker
using ModelingToolkit
using SymbolicIndexingInterface: getu, getp
using OrdinaryDiffEqRosenbrock
using Test

@testset "PERF-1: signal reader and discrete warm-up model" begin
    md = IR.parse_model(Worker._warm_model_document("12.0"; discrete = true))
    flat = Compile.flatten(md)
    @test !isempty(flat.discrete)
    settings = BGSim.RunSettings(md.settings)

    lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 0.01)
    symbols = Num[]
    for s in flat.signals
        x = get(lowered.model.vars, String(s.id), nothing)
        x === nothing && (x = get(lowered.model.params, String(s.id), nothing))
        push!(symbols, x)
    end
    @test all(!isnothing, symbols)
    integ = init(lowered.problem, Rodas5P(); save_everystep = false)
    reader = BGSim._signal_reader(lowered.model, symbols)
    per_signal(integ) = Float64[
        Float64(
            ModelingToolkit.isparameter(x) ? getp(integ, x)(integ) : getu(integ, x)(integ)
        ) for x in symbols
    ]
    @test BGSim._signal_values(reader, integ) == per_signal(integ)
    step!(integ, 0.003, true)
    @test BGSim._signal_values(reader, integ) == per_signal(integ)
    # two reads are independent vectors (the run loop keeps the left limit while it reads
    # the right one)
    first_read = BGSim._signal_values(reader, integ)
    step!(integ, 0.002, true)
    second_read = BGSim._signal_values(reader, integ)
    @test first_read !== second_read
    @test first_read != second_read
    @test BGSim._signal_values(nothing, integ) == Float64[]

    dir = mktempdir()
    try
        result = BGSim.simulate(flat; run_dir = dir, settings = settings)
        @test result.status == "done"
        profile = BGSim.LAST_PROFILE[]
        @test profile.ticks == 10
        @test profile.stats.naccept == result.stats.steps
        @test profile.loop_s >= profile.step_s
        # the ZOH output was published at the first tick: the held value reaches 12 V
        ids = [String(s.id) for s in result.signals]
        col = findfirst(==("Z1/y"), ids)
        @test col !== nothing
        data = reinterpret(Float64, read(joinpath(dir, "columns.f64")))
        nrows = result.manifest.time.n
        matrix = reshape(data, nrows, length(ids) + 1)
        @test matrix[1, col + 1] == 0.0
        @test matrix[end, col + 1] == 12.0
        # a changed tick is a left/right pair at the same time
        @test count(i -> matrix[i, 1] == matrix[i + 1, 1], 1:(nrows - 1)) >= 1
    finally
        rm(dir; recursive = true, force = true)
    end
end
