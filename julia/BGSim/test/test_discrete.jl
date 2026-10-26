# Work package J2.2: the discrete scheduler (plan section 5.9, decisions D3/D4/D18, E104/E105).
#
# Acceptance of the work package:
#   * multi-rate 1 ms / 5 ms clocks with a known integer sequence, through the real pipeline
#     (`parse -> flatten -> lower -> simulate`);
#   * a ZOH with exact values (a held output does not move between ticks);
#   * E105 detection for a signal cycle between partitions, and `previous(x)` breaking it;
#   * a discrete PI against a hand-computed sequence over 10 ticks, bit-exact (`==`);
#   * E104 for a period that is not a whole number of nanoseconds;
#   * the held outputs are MTK parameters (D4), not continuous unknowns.
#
# Every model is built as a `bgsim.model` document with inline blocks and simulated through
# `BGSim.simulate`, so the parser, the flattener, the MTK lowering, the generated step
# functions and the recorder are all exercised.

using Test
using BGSim
import BGSim.IR
import BGSim.Flat
import BGSim.Compile
import JSON3
import ModelingToolkit

# ---------------------------------------------------------------------------------------
# Model document helpers (unique names: the whole suite runs in one module)
# ---------------------------------------------------------------------------------------

function _disc_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params,
        "constants" => Dict{String,Any}(),
        "starts" => starts,
    )
end

_disc_ref(ref) = Dict{String,Any}("ref" => ref)
_disc_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _disc_conn(id, from_node, from_port, to_node, to_port)
    return Dict{String,Any}(
        "id" => id,
        "kind" => "signal",
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
end

function _disc_settings(; t_start = 0.0, t_end = 1.0, points = 11, solver = "auto",
    reltol = 1.0e-9, abstol = 1.0e-11)
    return Dict{String,Any}(
        "t_start" => t_start,
        "t_end" => t_end,
        "solver" => solver,
        "reltol" => reltol,
        "abstol" => abstol,
        "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => points),
        "event_limit" => 10000,
    )
end

function _disc_model(name, nodes, connections; kwargs...)
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
        "settings" => _disc_settings(; kwargs...),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_disc_flat(doc) = Compile.flatten(IR.parse_model(doc))
_disc_codes(fm) = [d.code for d in fm.diagnostics]
_disc_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _disc_run(doc)
    flat = _disc_flat(doc)
    dir = mktempdir()
    result = simulate(
        flat;
        run_dir = dir,
        run_id = "discrete-test",
        settings = BGSim.RunSettings(doc["settings"]),
    )
    return flat, result, dir
end

"""The run folder's columns as `(time, Dict(id => values))`."""
function _disc_columns(dir)
    manifest = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsignals + 1)
    columns = reshape(reinterpret(Float64, raw), (n, nsignals + 1))
    values = Dict{String,Vector{Float64}}(
        String(signal.id) => collect(columns[:, j + 1]) for
        (j, signal) in enumerate(manifest.signals)
    )
    return collect(columns[:, 1]), values
end

# The last row recorded at `t` (a tick that changed a held output writes a left and a right
# row at the same time, so the grid value is the right-hand one).
function _disc_at(time, values, id, t)
    rows = findall(==(t), time)
    isempty(rows) && error("no row at t = $t")
    return values[id][rows[end]]
end

function _disc_sequence(time, values, id, times)
    return Float64[_disc_at(time, values, id, t) for t in times]
end

# ---------------------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------------------

const _DISC_FAST = """
@block FastCount begin
    @outputs n::Real = 0.0
    @discrete Ts = 1e-3 begin
        n = n + 1
    end
end
"""

const _DISC_SLOW = """
@block SlowCount begin
    @outputs m::Real = 0.0
    @discrete Ts = 5e-3 begin
        m = m + 1
    end
end
"""

const _DISC_OFFSET = """
@block OffsetCount begin
    @outputs k::Real = 0.0
    @discrete Ts = 2e-3, [offset = 1e-3] begin
        k = k + 1
    end
end
"""

const _DISC_SAMPLER = """
@block Sampler begin
    @inputs u::Real
    @outputs y::Real = 0.0
    @discrete Ts = 5e-3 begin
        y = hold(u)
    end
end
"""

const _DISC_PING = """
@block Ping begin
    @inputs v::Real
    @outputs x::Real = 0.0
    @discrete Ts = 1e-3 begin
        x = v + 1.0
    end
end
"""

const _DISC_PING_PREVIOUS = """
@block PingPrevious begin
    @inputs v::Real
    @outputs x::Real = 0.0
    @discrete Ts = 1e-3 begin
        x = previous(v) + 1.0
    end
end
"""

const _DISC_PI_EXACT = """
@block DiscretePIExact begin
    @parameters begin
        Kp::Real = 0.5
        Ki::Real = 0.25
    end
    @inputs e::Real
    @outputs u::Real = 0.0
    @variables i::Real = 0.0
    @discrete Ts = 0.125 begin
        i = i + Ts * e
        u = Kp * e + Ki * i
    end
end
"""

const _DISC_PI = """
@block DiscretePI begin
    @parameters begin
        Kp::Real = 2.0
        Ki::Real = 0.5
    end
    @inputs e::Real
    @outputs u::Real = 0.0
    @variables i::Real = 0.0
    @discrete Ts = 0.1 begin
        i = i + Ts * e
        u = Kp * e + Ki * i
    end
end
"""

const _DISC_TWO_SCOPES = """
@block TwoRates begin
    @outputs slow::Real = 0.0
    @outputs fast::Real = 0.0
    @discrete Ts = 5e-3 begin
        slow = slow + fast
    end
    @discrete Ts = 1e-3 begin
        fast = fast + 1.0
    end
end
"""

const _DISC_BAD_CLOCK = """
@block BadClock begin
    @outputs y::Real = 0.0
    @discrete Ts = 1.0 / 3.0 begin
        y = y + 1.0
    end
end
"""

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J2.2 discrete scheduler" begin
    # -----------------------------------------------------------------------------------
    @testset "multi-rate 1 ms / 5 ms integer sequence" begin
        @test isempty(check_block(parse_block(_DISC_FAST; ref = "inline:fast")))
        doc = _disc_model(
            "MultiRate",
            [
                _disc_node("n1", "F1", _disc_inline(_DISC_FAST)),
                _disc_node("n2", "S1", _disc_inline(_DISC_SLOW)),
            ],
            Any[];
            t_end = 0.02, points = 21,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"

        # The compiled schedule: the base tick is the gcd of the two periods, every period is
        # a whole multiple of it and the ticks start after `t_start`.
        schedule = BGSim.discrete_schedule(flat; t_start = 0.0, t_end = 0.02)
        @test schedule.base_ns == 1_000_000
        @test length(schedule.partitions) == 2
        @test schedule.tick_times[1] == 0.001
        @test schedule.tick_times[2] == 0.002
        @test length(schedule.tick_times) == 20
        @test schedule.due[1] == [1]          # only the 1 ms clock at 1 ms
        @test schedule.due[5] == [1, 2]       # both clocks at 5 ms (topological order)

        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 0.02; length = 21))
        # 20 fast ticks + 4 slow ticks (coinciding) every changed tick adds one extra row to
        # the 21 grid rows: the left limit shares the grid row at 1 ms steps.
        @test length(time) == 41
        @test _disc_sequence(time, values, "F1/n", grid) ==
              Float64.(collect(0:20))
        @test _disc_sequence(time, values, "S1/m", grid) ==
              Float64[0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4]

        # A tick that changes a held output is a left/right pair at the same `t`; the 1 ms
        # clock changed at 1 ms and the 5 ms clock ticked there too.
        at_one = values["F1/n"][findall(==(0.001), time)]
        @test at_one == [0.0, 1.0]
        at_five = values["S1/m"][findall(==(0.005), time)]
        @test at_five == [0.0, 1.0]
    end

    # -----------------------------------------------------------------------------------
    @testset "offset clock" begin
        doc = _disc_model(
            "OffsetClock",
            [_disc_node("n1", "O1", _disc_inline(_DISC_OFFSET))],
            Any[];
            t_end = 0.006, points = 7,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        schedule = BGSim.discrete_schedule(flat; t_start = 0.0, t_end = 0.006)
        @test schedule.tick_times == [0.001, 0.003, 0.005]
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 0.006; length = 7))
        @test _disc_sequence(time, values, "O1/k", grid) ==
              Float64[0, 1, 1, 2, 2, 3, 3]
    end

    # -----------------------------------------------------------------------------------
    @testset "ZOH with exact values" begin
        doc = _disc_model(
            "ZeroOrderHold",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "2.5"),
                ),
                _disc_node("n2", "S1", _disc_inline(_DISC_SAMPLER)),
            ],
            [_disc_conn("c1", "n1", "y", "n2", "u")];
            t_end = 0.02, points = 21,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 0.02; length = 21))
        # The sampled value is 2.5 exactly (the Constant's parameter), and the held output is
        # constant between 5 ms ticks: the exact ZOH staircase.
        @test _disc_sequence(time, values, "S1/y", grid) ==
              Float64[0, 0, 0, 0, 0, 2.5, 2.5, 2.5, 2.5, 2.5,
                      2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]
        # `hold(u)` samples the continuous input; the input itself stays 2.5 all along.
        @test all(==(2.5), values["S1/u"])
        # Exactly one changed tick (at 5 ms), so one extra row at that time.
        @test length(time) == 22
        rows = findall(==(0.005), time)
        @test values["S1/y"][rows] == [0.0, 2.5]
    end

    # -----------------------------------------------------------------------------------
    @testset "E105: a cycle without previous" begin
        doc = _disc_model(
            "PingPong",
            [
                _disc_node("n1", "P1", _disc_inline(_DISC_PING)),
                _disc_node("n2", "P2", _disc_inline(_DISC_PING)),
            ],
            [_disc_conn("c1", "n1", "x", "n2", "v"),
             _disc_conn("c2", "n2", "x", "n1", "v")];
            t_end = 0.01, points = 11,
        )
        flat = _disc_flat(doc)
        e105 = [d for d in flat.diagnostics if d.code == "E105"]
        @test length(e105) == 1
        @test e105[1].severity == "error"
        @test occursin("P1 @discrete[1]", e105[1].message)
        @test occursin("P2 @discrete[1]", e105[1].message)
        @test occursin("->", e105[1].message)
        @test occursin("previous", e105[1].hint)
        @test e105[1].path == "P1" || e105[1].path == "P2"

        _, result, _ = _disc_run(doc)
        @test result.status == "failed"
        @test any(d -> d.code == "E105", result.diagnostics)
    end

    # -----------------------------------------------------------------------------------
    @testset "previous breaks the cycle" begin
        doc = _disc_model(
            "PreviousCycle",
            [
                _disc_node("n1", "P1", _disc_inline(_DISC_PING)),
                _disc_node("n2", "P2", _disc_inline(_DISC_PING_PREVIOUS)),
            ],
            [_disc_conn("c1", "n1", "x", "n2", "v"),
             _disc_conn("c2", "n2", "x", "n1", "v")];
            t_end = 0.005, points = 6,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        # P2 reads `previous(v)`, so P2 runs before P1 (P1 -> P2 is the only edge) and the
        # two sequences are the odd and the even numbers.
        schedule = BGSim.discrete_schedule(flat; t_start = 0.0, t_end = 0.005)
        @test [s.partition.path for s in schedule.partitions] == ["P2", "P1"]
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 0.005; length = 6))
        @test _disc_sequence(time, values, "P2/x", grid) ==
              Float64[0, 1, 3, 5, 7, 9]
        @test _disc_sequence(time, values, "P1/x", grid) ==
              Float64[0, 2, 4, 6, 8, 10]
    end

    # -----------------------------------------------------------------------------------
    @testset "discrete PI bit-exact over 10 ticks (exact binary clocks)" begin
        doc = _disc_model(
            "PIExact",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0"),
                ),
                _disc_node("n2", "PI", _disc_inline(_DISC_PI_EXACT)),
            ],
            [_disc_conn("c1", "n1", "y", "n2", "e")];
            t_end = 1.25, points = 11,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"

        # The generated statements are `i = i + (Ts * e)` then `u = (Kp * e) + (Ki * i)`,
        # executed once per tick in that order (no reassociation, no FMA). With Ts = 0.125,
        # e = 1.0, Kp = 0.5 and Ki = 0.25 every product is exact in binary, so the hand
        # computation is the literal decimal sequence below.
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 1.25; length = 11))
        i_seq = _disc_sequence(time, values, "PI/i", grid)
        u_seq = _disc_sequence(time, values, "PI/u", grid)
        @test i_seq == Float64[0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0,
                               1.125, 1.25]
        @test u_seq == Float64[0.0, 0.53125, 0.5625, 0.59375, 0.625, 0.65625, 0.6875,
                               0.71875, 0.75, 0.78125, 0.8125]
        # Bit-exact, not approximate: `===` compares the IEEE bits of the Float64.
        @test u_seq[11] === 0.8125
    end

    # -----------------------------------------------------------------------------------
    @testset "discrete PI bit-exact over 10 ticks (rounding clock)" begin
        doc = _disc_model(
            "PIRounding",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0"),
                ),
                _disc_node("n2", "PI", _disc_inline(_DISC_PI)),
            ],
            [_disc_conn("c1", "n1", "y", "n2", "e")];
            t_end = 1.0, points = 11,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 1.0; length = 11))
        i_seq = _disc_sequence(time, values, "PI/i", grid)
        u_seq = _disc_sequence(time, values, "PI/u", grid)

        # Hand computation of the same ten ticks, in the documented operation order:
        #   i_k = i_{k-1} + (0.1 * 1.0)
        #   u_k = (2.0 * 1.0) + (0.5 * i_k)
        # Ts = 0.1 is not a binary fraction, so this sequence exercises the rounding of the
        # generated arithmetic (0.1 + 0.1 + 0.1 is 0.30000000000000004).
        hand_i = Float64[]
        acc = 0.0
        for _ in 1:10
            acc = acc + 0.1 * 1.0
            push!(hand_i, acc)
        end
        hand_u = Float64[2.0 * 1.0 + 0.5 * value for value in hand_i]
        @test i_seq[2:end] == hand_i
        @test u_seq[2:end] == hand_u
        @test u_seq[11] === 2.5
        # The literals of the first three steps, written out, so the test does not only
        # compare two implementations of the same loop.
        @test i_seq[2] == 0.1
        @test i_seq[3] == 0.2
        @test i_seq[4] == 0.30000000000000004
        @test u_seq[2] == 2.05
        @test u_seq[3] == 2.1

        # A second run of the same flat model is the parameter-only path: the structural cache
        # is hit, only the problem is remade, and the held values restart at their starts.
        dir2 = mktempdir()
        again = simulate(
            flat;
            run_dir = dir2,
            run_id = "discrete-again",
            settings = BGSim.RunSettings(doc["settings"]),
        )
        @test again.status == "done"
        time2, values2 = _disc_columns(dir2)
        @test _disc_sequence(time2, values2, "PI/u", grid) == u_seq
        @test BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0).cache_hit
    end

    # -----------------------------------------------------------------------------------
    @testset "two @discrete scopes in one block" begin
        doc = _disc_model(
            "TwoScopes",
            [_disc_node("n1", "T1", _disc_inline(_DISC_TWO_SCOPES))],
            Any[];
            t_end = 0.01, points = 11,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        schedule = BGSim.discrete_schedule(flat; t_start = 0.0, t_end = 0.01)
        # `slow` reads the held `fast` value directly, so the 1 ms partition runs first even
        # though its scope comes second in the source.
        @test [s.partition.label for s in schedule.partitions] ==
              ["T1 @discrete[2]", "T1 @discrete[1]"]
        time, values = _disc_columns(dir)
        grid = collect(range(0.0, 0.01; length = 11))
        @test _disc_sequence(time, values, "T1/fast", grid) ==
              Float64.(collect(0:10))
        # At 5 ms: fast is already 5 (same tick), so slow = 0 + 5; at 10 ms: 5 + 10.
        @test _disc_sequence(time, values, "T1/slow", grid) ==
              Float64[0, 0, 0, 0, 0, 5, 5, 5, 5, 5, 15]
    end

    # -----------------------------------------------------------------------------------
    @testset "E104: a period that is not a whole number of nanoseconds" begin
        doc = _disc_model(
            "BadClock",
            [_disc_node("n1", "B1", _disc_inline(_DISC_BAD_CLOCK))],
            Any[];
            t_end = 1.0, points = 3,
        )
        flat = _disc_flat(doc)
        e104 = [d for d in flat.diagnostics if d.code == "E104"]
        @test length(e104) == 1
        @test e104[1].severity == "error"
        @test e104[1].hint == "use a period that is a whole number of nanoseconds"
        @test occursin("nanosecond", e104[1].message)
        @test e104[1].path == "B1"
        @test e104[1].scope == "@discrete"
        # The held output is still a parameter, so the invalid clock does not add an E103.
        @test !("E103" in _disc_codes(flat))
        @test haskey(Dict(p.id => p for p in flat.parameters), "B1/y")

        _, result, _ = _disc_run(doc)
        @test result.status == "failed"
        @test any(d -> d.code == "E104", result.diagnostics)
    end

    # -----------------------------------------------------------------------------------
    @testset "held outputs are MTK parameters and discrete signals (D4)" begin
        doc = _disc_model(
            "Parameterheld",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0"),
                ),
                _disc_node("n2", "PI", _disc_inline(_DISC_PI)),
            ],
            [_disc_conn("c1", "n1", "y", "n2", "e")];
            t_end = 1.0, points = 11,
        )
        flat = _disc_flat(doc)
        @test isempty(_disc_errors(flat))
        variables = Set(v.id for v in flat.variables)
        parameters = Dict(p.id => p for p in flat.parameters)
        @test !("PI/i" in variables)
        @test !("PI/u" in variables)
        @test haskey(parameters, "PI/i")
        @test haskey(parameters, "PI/u")
        @test parameters["PI/i"].attrs[:kind] === :discrete
        @test parameters["PI/i"].value == 0.0
        @test length(flat.discrete) == 1

        signals = Dict(String(s.id) => s for s in flat.signals)
        @test signals["PI/i"].kind == "discrete"
        @test signals["PI/u"].kind == "discrete"
        @test signals["PI/i"].path == "PI"

        # The compiled system knows them as (discrete) parameters, never as unknowns.
        lowered = BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0)
        @test ModelingToolkit.isparameter(lowered.model.params["PI/i"])
        @test !haskey(lowered.model.vars, "PI/i")
        @test any(
            x -> BGSim.signal_name(x) == "PI/i",
            ModelingToolkit.parameters(lowered.model.system),
        )

        # The structural key does not depend on a compile counter (temporary slots are
        # deterministic), so a re-flatten gives the same hash and can hit the cache.
        @test BGSim.compile_key(flat) == BGSim.compile_key(_disc_flat(doc))
    end

    # -----------------------------------------------------------------------------------
    @testset "a start override initialises a held value" begin
        doc = _disc_model(
            "HeldStart",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "1.0"),
                ),
                _disc_node(
                    "n2", "PI", _disc_inline(_DISC_PI);
                    starts = Dict{String,Any}("i" => "2.0"),
                ),
            ],
            [_disc_conn("c1", "n1", "y", "n2", "e")];
            t_end = 0.1, points = 2,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(_disc_errors(flat))
        @test result.status == "done"
        parameters = Dict(p.id => p for p in flat.parameters)
        @test parameters["PI/i"].value == 2.0
        time, values = _disc_columns(dir)
        # The first execution at 0.1 s starts from i = 2.0: i = 2.0 + 0.1, u = 2 + 0.5 * i.
        @test values["PI/i"][end] == 2.0 + 0.1 * 1.0
        @test values["PI/u"][end] == 2.0 + 0.5 * (2.0 + 0.1 * 1.0)
    end

    # -----------------------------------------------------------------------------------
    @testset "a model without @discrete has no scheduler and no extra rows" begin
        doc = _disc_model(
            "ContinuousOnly",
            [
                _disc_node(
                    "n1", "C1", _disc_ref("stdlib:sources/Constant");
                    params = Dict{String,Any}("value" => "3.0"),
                ),
            ],
            Any[];
            t_end = 1.0, points = 11,
        )
        flat, result, dir = _disc_run(doc)
        @test isempty(flat.discrete)
        @test result.status == "done"
        time, _ = _disc_columns(dir)
        @test time == collect(range(0.0, 1.0; length = 11))
        # The empty-schedule target list is exactly the old continuous grid.
        targets = BGSim.discrete_targets(collect(range(0.0, 1.0; length = 11)), nothing)
        @test length(targets) == 10
        @test all(t -> t.grid && !t.tick, targets)
    end
end
