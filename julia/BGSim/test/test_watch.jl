# Work package J4.3: the watch pool, `debug.evaluate` and `debug.values` (plan 5.13,
# decisions D22 and D27).
#
#   * the `watch` expression scope: E001 to E006 with `scope = "watch"`, context-relative names,
#     the D19 condition normalization;
#   * a watch on the dc-motor current pauses within 1e-8 s of the crossing time of a
#     tight-tolerance reference solve; the current is an eliminated variable (not an unknown of
#     the compiled system);
#   * `hitCount`, disabled watches, the 16-slot limit, continuing past a crossing;
#   * adding, changing and removing watches while paused never causes a spurious pause (50
#     random changes, fixed seed);
#   * `debug.evaluate` and `debug.values` at a pause;
#   * a value that jumps at a step boundary (a tick, an `@events` affect, a kink) fires its watch
#     once, `>` and `>=` differ on a discrete value, a watch mixing continuous and discrete
#     signals counts one hit per crossing, and re-arming and live edits never fire one.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Units
using Random: Xoshiro, rand, randperm

const _WT_EXAMPLES = normpath(joinpath(@__DIR__, "..", "..", "..", "examples"))
const _WT_SCIML = BGSim.ModelingToolkit.SciMLBase

struct _WtModel
    flat::Any
    settings::BGSim.RunSettings
end

function _wt_load(dir, file)
    project = joinpath(_WT_EXAMPLES, dir)
    md = IR.parse_model(joinpath(project, "models", file))
    flat = Compile.flatten(md; project_dir = project)
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"])
    return _WtModel(flat, BGSim.RunSettings(md.settings))
end

# A harmonic oscillator: x = sin(w t), z = cos(w t); x crosses 1/2 upward at t = 1/12 + k.
function _wt_oscillator(; t_end = 3.0, reltol = 1.0e-9, abstol = 1.0e-10)
    source = """
    @block Osc begin
        @parameters begin
            w::Real = 6.283185307179586, [unit = "rad/s"]
        end
        @variables begin
            x::Real = 0.0
            z::Real = 1.0
        end
        @equations begin
            ddt(x) ~ w * z
            ddt(z) ~ -w * x
        end
    end
    """
    node = Dict{String,Any}(
        "id" => "n1", "name" => "Plant",
        "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => source)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(), "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
    doc = Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => "Osc",
        "diagram" => Dict{String,Any}(
            "nodes" => Any[node], "connections" => Any[], "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "Rodas5P", "reltol" => reltol,
            "abstol" => abstol, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => 301),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
    md = IR.parse_model(doc)
    return _WtModel(Compile.flatten(md), BGSim.RunSettings(md.settings))
end

mutable struct _WtRun
    ctx::DebugCtx
    task::Task
    paused::Channel{Any}
    dir::String
end

_wt_cancel_cb() = () -> (yield(); false)

function _wt_spawn(m::_WtModel; settings = m.settings, kwargs...)
    paused = Channel{Any}(Inf)
    ctx = DebugCtx(; on_paused = info -> put!(paused, info), kwargs...)
    dir = mktempdir()
    task = Threads.@spawn simulate(
        m.flat; run_dir = dir, run_id = "wt", settings = settings, debug = ctx,
        cancel = _wt_cancel_cb(),
    )
    Threads.@spawn begin
        try
            wait(task)
        catch
        end
        put!(paused, :finished)
    end
    return _WtRun(ctx, task, paused, dir)
end

function _wt_next(run::_WtRun; seconds = 240)
    timer = Timer(_ -> close(run.paused), seconds)
    try
        return take!(run.paused)
    finally
        close(timer)
    end
end

_wt_result(run::_WtRun) = fetch(run.task)

# Continue through every pause of a run: its `PausedInfo`s with `ids` read at each, in order.
function _wt_pauses(run::_WtRun; ids = String[])
    out = NamedTuple[]
    while true
        info = _wt_next(run)
        info === :finished && return out
        values = isempty(ids) ? Dict{String,Float64}() : debug_values(run.ctx, ids).values
        push!(out, (; info, values))
        debug_continue!(run.ctx)
    end
end

# Upward crossings of `level` by `row -> value` in the rows of a watch-free run of `m`.
function _wt_rows(m::_WtModel, ids)
    dir = mktempdir()
    result = simulate(m.flat; run_dir = dir, run_id = "rows", settings = m.settings)
    @assert result.status == "done"
    names = String[String(s.id) for s in result.signals]
    raw = collect(reinterpret(Float64, read(joinpath(dir, "columns.f64"))))
    rows = reshape(raw, :, length(names) + 1)
    return Dict(id => rows[:, findfirst(==(id), names) + 1] for id in ids)
end

# Cancel a paused run and wait for it to end.
function _wt_stop!(run::_WtRun)
    debug_cancel!(run.ctx)
    while true
        _wt_next(run) === :finished && break
    end
    return _wt_result(run)
end

_wt_watch(id, expr; context = nothing, enabled = true, hit = nothing) = Dict{String,Any}(
    "id" => id, "enabled" => enabled, "kind" => "watch",
    "watch" => Dict{String,Any}("expr" => expr, "context" => context),
    "hitCount" => hit,
)

const _WT_DC = _wt_load("dc-motor", "iconic.bgmodel.json")
const _WT_TOUR = _wt_load("debug-tour", "debug-tour.bgmodel.json")
const _WT_BALL = _wt_load("bouncing-ball", "bouncing-ball.bgmodel.json")

# A continuous ramp and a tick counter with a temporary (`w`), for the statement-pause tests.
const _WT_RAMP = """
@block Ramp begin
    @outputs x::Real
    @variables s::Real = 0.0
    @equations begin
        ddt(s) ~ 1.0
        x ~ s
    end
end
"""

const _WT_COUNTER = """
@block TickCounter begin
    @variables k::Int = 0
    @outputs begin
        y::Real = 0.0
        d::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        k += 1
        y = 2.0 * k
        w = y + 1.0
        d = w - previous(y)
    end
end
"""

function _wt_counter_model(; ramp::Bool = true)
    node(id, name, source) = Dict{String,Any}(
        "id" => id, "name" => name,
        "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => source)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(), "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
    doc = Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => "Counter",
        "diagram" => Dict{String,Any}(
            "nodes" => ramp ? Any[node("ramp", "Ramp", _WT_RAMP), node("cnt", "Cnt", _WT_COUNTER)] :
                       Any[node("cnt", "Cnt", _WT_COUNTER)],
            "connections" => Any[], "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => 0.02, "solver" => "Rodas5P", "reltol" => 1.0e-8,
            "abstol" => 1.0e-10, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => 21),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
    md = IR.parse_model(doc)
    flat = Compile.flatten(md)
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"])
    return _WtModel(flat, BGSim.RunSettings(md.settings))
end

# The time at which `id` rises through `level` in a tight-tolerance solve of the same problem
# (reltol = abstol = 1e-12), by bisection on the dense output.
function _wt_reference_crossing(m::_WtModel, id, level, t0, t1)
    lowered = lower_model(m.flat; t_start = m.settings.t_start, t_end = m.settings.t_end)
    alg = BGSim.solver_algorithm(m.settings.solver, lowered.model)
    sol = _WT_SCIML.solve(lowered.problem, alg; abstol = 1.0e-12, reltol = 1.0e-12, dense = true)
    sym = lowered.model.vars[id]
    f(t) = Float64(sol(t; idxs = sym)) - level
    @assert f(t0) < 0 < f(t1) "the signal does not cross $level between $t0 and $t1"
    lo, hi = t0, t1
    for _ in 1:200
        mid = (lo + hi) / 2
        f(mid) < 0 ? (lo = mid) : (hi = mid)
    end
    return (lo + hi) / 2, f(t0), f(t1)
end

@testset "watch pool, evaluate and values (J4.3)" begin
    @testset "the watch scope: parse, check and the D19 condition" begin
        scope = WatchScope(
            Dict(
                "Motor1/i" => Units.parse_unit("A"), "Motor1/p.e" => Units.parse_unit("V"),
                "Motor1/R" => Units.parse_unit("Ohm"), "i" => nothing, "flag" => nothing,
            );
            types = Dict("flag" => :Bool), context = "Motor1",
        )
        function check(text; scope = scope)
            expr, d = parse_watch(text)
            expr === nothing && return (nothing, d)
            resolved, _, _, d2 = check_watch(expr, scope)
            return (resolved, d2)
        end
        # A signal literal, a context-relative name, and the model-level fallback.
        r, d = check("s\"Motor1/i\" > 5")
        @test isempty(d)
        @test r isa BGSim.Comparison && r.lhs isa SignalRef && r.lhs.id == "Motor1/i"
        r, d = check("i > 5")      # `Motor1/i` is found first
        @test isempty(d) && r.lhs.id == "Motor1/i"
        r, d = check("i > 5"; scope = WatchScope(Dict("i" => nothing, "Motor1/i" => nothing)))
        @test isempty(d) && r.lhs.id == "i"      # no context: a model-level id
        r, d = check("i > 5"; scope = WatchScope(Dict("i" => nothing); context = "Motor1"))
        @test isempty(d) && r.lhs.id == "i"
        r, d = check("R * 2 > 1")
        @test isempty(d)
        @test BGSim.signal_refs(r) == ["Motor1/R"]
        # Errors are the language diagnostics with scope = "watch".
        for (text, code) in (
            ("", "E001"), ("s\"Motor1/i\" >", "E001"), ("a; b", "E001"),
            ("v[1] > 0", "E001"), ("1 < x < 3", "E001"), ("\"text\"", "E001"),
            ("@foo(1)", "E001"), ("s\"Motor1/i\" % 2 > 0", "E002"),
            ("nosuchfunction(1)", "E002"), ("ddt(s\"Motor1/i\") > 0", "E002"),
            ("s\"Motor1/nope\" > 5", "E003"), ("nope > 5", "E003"),
            ("sin(1, 2) > 0", "E004"), ("s\"Motor1/i\" + (1 > 2) > 0", "E004"),
            ("1 && 2", "E004"), ("ifelse(1, 2, 3) > 0", "E004"), ("flag + 1 > 0", "E004"),
            ("s\"Motor1/i\" > s\"Motor1/p.e\"", "E006"),
            ("s\"Motor1/i\" + s\"Motor1/R\" > 0", "E006"),
        )
            resolved, d = check(text)
            @test resolved === nothing
            @test !isempty(d)
            @test d[1].code == code
            @test all(x -> x.scope == "watch", d)
            @test all(x -> x.severity == "error", d)
        end
        # Quantities of one unit, literals and dimensionless arguments are fine.
        for text in ("s\"Motor1/i\" > 5", "s\"Motor1/i\" - 5 > 0.5", "abs(s\"Motor1/i\") > 5",
            "max(s\"Motor1/i\", 1) > 5", "s\"Motor1/R\" * s\"Motor1/i\" > s\"Motor1/p.e\"",
            "sin(t) > 0", "flag && s\"Motor1/i\" > 5", "t >= 0.5", "ifelse(flag, 1, 2) > 1")
            resolved, d = check(text)
            @test isempty(d)
            @test resolved !== nothing
        end
        # D19: `a > b` -> a - b, `a < b` -> b - a, `&&` the minimum, `||` the maximum, `!` negates.
        cond(text) = begin
            e, _ = parse_watch(text)
            resolved, _, _, _ = check_watch(e, scope)
            c, d = watch_condition(resolved)
            @test isempty(d)
            return sprint(show, c)
        end
        @test cond("s\"Motor1/i\" > 5") == "(s\"Motor1/i\" - 5)"
        @test cond("s\"Motor1/i\" >= 5") == "(s\"Motor1/i\" - 5)"
        @test cond("s\"Motor1/i\" < 5") == "(5 - s\"Motor1/i\")"
        @test cond("s\"Motor1/i\" > 5 && t < 1") == "min((s\"Motor1/i\" - 5), (1 - t))"
        @test cond("s\"Motor1/i\" > 5 || t < 1") == "max((s\"Motor1/i\" - 5), (1 - t))"
        @test cond("!(s\"Motor1/i\" > 5)") == "(-(s\"Motor1/i\" - 5))"
        @test cond("s\"Motor1/i\" - 5") == "(s\"Motor1/i\" - 5)"
        expr, _ = parse_watch("s\"Motor1/i\" != 5")
        resolved, _, _, _ = check_watch(expr, scope)
        c, d = watch_condition(resolved)
        @test c === nothing && d[1].code == "E004" && d[1].scope == "watch"
    end

    @testset "dc-motor: a watch on the current pauses at the reference crossing" begin
        m = _WT_DC
        # The current is an eliminated (observed) variable of the compiled system.
        lowered = lower_model(m.flat; t_start = m.settings.t_start, t_end = m.settings.t_end)
        sys = lowered.model.system
        current = lowered.model.vars["Motor1/i"]
        @test !any(u -> isequal(u, current), BGSim.ModelingToolkit.unknowns(sys))
        @test any(eq -> isequal(eq.lhs, current), BGSim.ModelingToolkit.observed(sys))
        tref, f0, f1 = _wt_reference_crossing(m, "Motor1/i", 5.0, 0.01, 0.0112)
        @test f0 < 0 < f1                 # the current really crosses 5 A
        run = _wt_spawn(m; breakpoints = [_wt_watch("w1", "s\"Motor1/i\" > 5")])
        info = _wt_next(run)
        @test info isa NamedTuple
        @test info.reason == "breakpoint"
        @test info.breakpointId == "w1"
        @test info.frame === nothing
        @test info.location.scope == "watch"
        @test abs(info.t - tref) < 1.0e-8
        println("  dc-motor watch pause: t = ", info.t, "  reference = ", tref,
            "  |error| = ", abs(info.t - tref))
        # The paused state is the crossing: i = 5 A (to the solver tolerance).
        v = debug_values(run.ctx, ["Motor1/i", "Motor1/gyrator/n.f", "Motor1/shaft.f"])
        @test v.t == info.t
        @test v.values["Motor1/i"] ≈ 5.0 atol = 1.0e-5
        @test v.values["Motor1/i"] == v.values["Motor1/gyrator/n.f"]
        @test is_paused(run.ctx)
        @test only(run.ctx.statuses).verified
        manifest = BGSim.JSON3.read(read(joinpath(run.dir, "manifest.json"), String))
        @test manifest.status == "paused"
        @test manifest.debug.pauses[1].reason == "breakpoint"
        debug_continue!(run.ctx)
        # No second pause: the current does not rise through 5 A again.
        @test _wt_next(run) === :finished
        @test _wt_result(run).status == "done"
    end

    @testset "watches on a state and on other eliminated variables" begin
        m = _WT_DC
        lowered = lower_model(m.flat; t_start = m.settings.t_start, t_end = m.settings.t_end)
        sys = lowered.model.system
        for id in ("Motor1/shaft.f", "Motor1/p.e", "Motor1/rotor/w", "Motor1/gyrator/n.f")
            eliminated = id in ("Motor1/shaft.f", "Motor1/p.e")
            @test any(u -> isequal(u, lowered.model.vars[id]), BGSim.ModelingToolkit.unknowns(sys)) !=
                  eliminated
        end
        # The shaft speed (an alias of the rotor state) rises through 5 rad/s; so does the state.
        times = Float64[]
        for id in ("Motor1/shaft.f", "Motor1/rotor/w")
            run = _wt_spawn(m; breakpoints = [_wt_watch("w", "s\"$id\" > 5")])
            info = _wt_next(run)
            @test info.reason == "breakpoint"
            push!(times, info.t)
            @test debug_values(run.ctx, [id]).values[id] ≈ 5.0 atol = 1.0e-5
            _wt_stop!(run)
        end
        @test times[1] ≈ times[2] atol = 1.0e-12
    end

    @testset "oscillator: hitCount, disabled watches, continue, conditions" begin
        m = _wt_oscillator()
        # x = sin(2 pi t) rises through 1/2 at 1/12 + k.
        run = _wt_spawn(m; breakpoints = [_wt_watch("w", "s\"Plant/x\" > 0.5")])
        times = Float64[]
        for k in 0:2
            info = _wt_next(run)
            @test info.reason == "breakpoint"
            @test info.breakpointId == "w"
            push!(times, info.t)
            @test info.t ≈ 1 / 12 + k atol = 1.0e-7
            @test watch_hits(run.ctx) == Dict("w" => k + 1)
            debug_continue!(run.ctx)
        end
        @test _wt_next(run) === :finished     # the 4th crossing would be at 3.0833 > t_end
        @test issorted(times) && allunique(times)

        # hitCount = 2: the first crossing does not pause, the second does.
        run = _wt_spawn(m; breakpoints = [_wt_watch("w", "s\"Plant/x\" > 0.5"; hit = 2)])
        info = _wt_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "w"
        @test info.t ≈ 1 + 1 / 12 atol = 1.0e-7
        @test watch_hits(run.ctx)["w"] == 2
        debug_continue!(run.ctx)
        @test _wt_next(run) === :finished     # no third pause (hits == 2 only once)

        # Disabled watches never fire; the enabled one does.
        run = _wt_spawn(m; breakpoints = [
            _wt_watch("off", "s\"Plant/x\" > 0.1"; enabled = false),
            _wt_watch("on", "s\"Plant/x\" > 0.5"),
            _wt_watch("off2", "s\"Plant/z\" < 0.0"; enabled = false),
        ])
        info = _wt_next(run)
        @test info.breakpointId == "on"
        @test info.t ≈ 1 / 12 atol = 1.0e-7
        @test all(s -> s.verified, run.ctx.statuses)
        # Enabling a watch while paused makes it fire at its own crossing:
        # z = cos(2 pi t) falls through 0 (z < 0.0 rises as -z) at t = 1/4.
        bps = [
            _wt_watch("off", "s\"Plant/x\" > 0.1"; enabled = false),
            _wt_watch("on", "s\"Plant/x\" > 0.5"),
            _wt_watch("off2", "s\"Plant/z\" < 0.0"; enabled = true),
        ]
        statuses = debug_set_breakpoints!(run.ctx, bps)
        @test all(s -> s.verified, statuses)
        debug_continue!(run.ctx)
        info = _wt_next(run)
        @test info.breakpointId == "off2"
        @test info.t ≈ 0.25 atol = 1.0e-7
        _wt_stop!(run)

        # `<`, `&&`, `||`, a bare real expression and `t`.
        for (expr, texpect) in (
            ("s\"Plant/x\" < -0.5", 7 / 12),                      # (-0.5 - x) rises
            ("s\"Plant/x\" > 0.5 && s\"Plant/z\" > 0", 1 / 12),
            ("s\"Plant/z\" < 0 || s\"Plant/x\" < -2", 0.25),      # max(-z, -2 - x)
            ("s\"Plant/x\" - 0.5", 1 / 12),                       # a bare real expression
            ("t >= 0.7", 0.7),
            ("s\"Plant/w\" * t > 2", 2 / (2 * pi)),               # a parameter and t
        )
            run = _wt_spawn(m; breakpoints = [_wt_watch("c", expr)])
            info = _wt_next(run)
            @test info isa NamedTuple
            info isa NamedTuple && @test info.t ≈ texpect atol = 1.0e-6
            _wt_stop!(run)
        end
    end

    @testset "statuses: syntax, names, the 16-slot limit" begin
        m = _wt_oscillator()
        wrong = [
            _wt_watch("e1", "s\"Plant/x\" >"),
            _wt_watch("e3", "s\"Plant/nope\" > 1"),
            _wt_watch("e4", "sin(1, 2) > 0"),
            _wt_watch("ok", "s\"Plant/x\" > 0.5"),
        ]
        # Before the run only the syntax can be checked.
        ctx0 = DebugCtx()
        pre = debug_set_breakpoints!(ctx0, wrong)
        @test [s.verified for s in pre] == [false, true, true, true]
        @test pre[1].diagnostics[1].code == "E001" && pre[1].diagnostics[1].scope == "watch"
        run = _wt_spawn(m; pause_on_entry = true, breakpoints = wrong)
        info = _wt_next(run)
        @test info.reason == "entry"
        st = run.ctx.statuses
        @test [s.verified for s in st] == [false, false, false, true]
        @test st[1].diagnostics[1].code == "E001"
        @test st[2].diagnostics[1].code == "E003"
        @test st[3].diagnostics[1].code == "E004"
        @test all(s -> all(d -> d.scope == "watch", s.diagnostics), st)

        # 17 enabled watches: the first 16 keep their slots, the 17th is refused.
        many = [_wt_watch("m$i", "s\"Plant/x\" > $(0.05 * i)") for i in 1:17]
        st = debug_set_breakpoints!(run.ctx, many)
        @test all(s -> s.verified, st[1:16])
        @test !st[17].verified
        @test occursin("at most 16 watch breakpoints", st[17].diagnostics[1].message)
        @test st[17].diagnostics[1].severity == "error"
        pool = watch_pool(run.ctx)
        @test count(!isnothing, pool.bp_ids) == 16
        @test pool.bp_ids[1:16] == ["m$i" for i in 1:16]
        # A disabled 17th watch is no problem; disabling one of the 16 frees its slot.
        many[3] = _wt_watch("m3", "s\"Plant/x\" > 0.15"; enabled = false)
        st = debug_set_breakpoints!(run.ctx, many)
        @test all(s -> s.verified, st)
        @test count(!isnothing, pool.bp_ids) == 16
        # The refused watch is not in the pool; the other 16 pause in order of their level.
        debug_continue!(run.ctx)
        info = _wt_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "m1"
        _wt_stop!(run)

        # The same before the run starts (statuses come with the running run).
        run = _wt_spawn(m; pause_on_entry = true, breakpoints = many)
        _wt_next(run)
        @test all(s -> s.verified, run.ctx.statuses)
        @test count(!isnothing, watch_pool(run.ctx).bp_ids) == 16
        _wt_stop!(run)
    end

    @testset "changing the pool while paused never causes a spurious pause" begin
        m = _wt_oscillator(; t_end = 1.0)
        # x = sin(2 pi t). "true" watches are positive for the whole run, "false" watches never
        # reach their threshold in the run, "genuine" rises through 1/2 at t = 1/12 exactly once.
        always_true = ["s\"Plant/x\" > -10", "s\"Plant/z\" > -5", "s\"Plant/w\" > 1",
            "s\"Plant/x\" > s\"Plant/z\" - 10"]
        always_false = ["s\"Plant/x\" > 5", "s\"Plant/z\" > 2", "s\"Plant/w\" > 100",
            "s\"Plant/x\" > s\"Plant/z\" + 10"]
        genuine = "s\"Plant/x\" > 0.5"
        rng = Xoshiro(20261030)
        run = _wt_spawn(m; pause_on_entry = true)
        @test _wt_next(run).reason == "entry"
        t_now = 0.0
        genuine_seen = 0
        spurious = 0
        for step in 1:50
            n = rand(rng, 0:6)
            exprs = String[]
            for _ in 1:n
                kind = rand(rng, 1:3)
                push!(exprs, kind == 1 ? rand(rng, always_true) :
                             kind == 2 ? rand(rng, always_false) : genuine)
            end
            # the same ids come back with other expressions (changed watches, removed ones)
            t_next = t_now + 0.0173
            if t_now < 1 / 12 <= t_next && !(genuine in exprs)
                push!(exprs, genuine)      # the step that contains the real crossing
                n += 1
            end
            ids = ["b$j" for j in 1:n]
            bps = [
                _wt_watch(ids[j], exprs[j]; enabled = rand(rng, Bool) || exprs[j] == genuine)
                for j in eachindex(ids)
            ]
            statuses = debug_set_breakpoints!(run.ctx, bps)
            @test all(s -> s.verified, statuses)
            t_next >= 1.0 && break
            debug_run_to!(run.ctx, t_next)
            info = _wt_next(run)
            info isa NamedTuple || (@test false; break)
            if info.reason == "breakpoint"
                # Only the genuine crossing at 1/12 is allowed, once.
                enabled_genuine = [b["id"] for b in bps if b["watch"]["expr"] == genuine && b["enabled"]]
                if info.breakpointId in enabled_genuine && abs(info.t - 1 / 12) < 1.0e-6
                    genuine_seen += 1
                else
                    spurious += 1
                    @info "spurious pause" step info.t info.breakpointId
                end
                # go on to the time stop
                debug_run_to!(run.ctx, t_next)
                info = _wt_next(run)
                info isa NamedTuple || (@test false; break)
            end
            if info.reason != "time"
                spurious += 1
                @info "unexpected pause" step info.reason info.t
            end
            t_now = info.t
        end
        @test spurious == 0
        @test genuine_seen == 1       # the one crossing at 1/12 was found and no other
        _wt_stop!(run)
    end

    @testset "debug.evaluate and debug.values at a pause" begin
        m = _WT_DC
        run = _wt_spawn(m; pause_on_entry = true)
        @test _wt_next(run).reason == "entry"
        ctx = run.ctx
        ev(text, context = nothing) = debug_evaluate(ctx, text, context)
        r = ev("s\"Motor1/R\"")
        @test r.value == 2.0 && r.type == "Real" && r.size == Int[] && r.unit == "Ohm"
        @test isempty(r.diagnostics)
        @test ev("s\"Motor1/R\" * 3 + 1").value == 7.0
        @test ev("R + 1", "Motor1").value == 3.0              # context-relative
        @test ev("2 * 3 + 1").value == 7 && ev("2 * 3 + 1").type == "Int"
        @test ev("t").value == 0.0 && ev("t").unit == "s"
        b = ev("s\"Motor1/R\" > 1")
        @test b.value === true && b.type == "Bool" && b.unit === nothing
        @test ev("sqrt(16.0) + abs(-1.0)").value == 5.0
        @test ev("s\"Motor1/R\" > 1 && s\"Motor1/R\" < 1").value === false
        @test abs(ev("s\"Motor1/i\"").value) < 1.0e-12 && ev("s\"Motor1/i\"").unit == "A"
        # Errors: E003 unknown name, E004 type, E002 whitelist, E006 units, with scope "watch"
        # and a null (zero) value.
        for (text, code) in (("nope + 1", "E003"), ("s\"Motor1/nope\"", "E003"),
            ("sin(1, 2)", "E004"), ("1 +", "E001"), ("foo(1)", "E002"),
            ("s\"Motor1/R\" + s\"Motor1/i\"", "E006"), ("1 / 0", "E004"))
            r = ev(text)
            @test r.value == 0.0 && r.type == "Real" && r.size == Int[]
            @test r.diagnostics[1].code == code
            @test all(d -> d.scope == "watch", r.diagnostics)
        end
        # Values.
        v = debug_values(ctx, ["Motor1/R", "Motor1/i", "Motor1/rotor/w"])
        @test v.t == 0.0
        @test v.values == Dict("Motor1/R" => 2.0, "Motor1/i" => 0.0, "Motor1/rotor/w" => 0.0)
        @test_throws ArgumentError debug_values(ctx, ["Motor1/nope"])
        debug_continue!(ctx)
        @test _wt_next(run) === :finished
        # A command on a run that is not paused fails.
        @test_throws DebugStateError debug_evaluate(ctx, "1 + 1")
        @test_throws DebugStateError debug_values(ctx, ["Motor1/R"])
    end

    @testset "debug.evaluate at a statement pause sees the frame's locals (D27)" begin
        m = _wt_counter_model()
        line = findfirst(l -> occursin("d = w -", l), split(_WT_COUNTER, '\n'))
        bp = Dict{String,Any}(
            "id" => "line", "enabled" => true, "kind" => "line", "hitCount" => 3,
            "line" => Dict{String,Any}("ref" => "inline:cnt", "line" => line, "path" => nothing),
        )
        run = _wt_spawn(m; breakpoints = [bp])
        info = _wt_next(run)
        @test info isa NamedTuple && info.reason == "breakpoint" && info.frame !== nothing
        ctx = run.ctx
        # The third tick: k = 3, y = 2 k = 6, w = y + 1 = 7.
        ev(text, context = nothing) = debug_evaluate(ctx, text, context)
        r = ev("w")
        @test r.value == 7.0 && r.type == "Real" && isempty(r.diagnostics)
        r = ev("w * k + 1.0")
        @test r.value == 22.0
        r = ev("k")
        @test r.value == 3 && r.type == "Int"
        @test ev("w > 5").value === true
        @test ev("w > 5 && k == 2").value === false
        @test ev("t").value ≈ info.t atol = 1.0e-12                # the tick time, from the frame
        # Signals are still reachable by id, next to the locals.
        @test ev("s\"Ramp/s\" + w").value ≈ info.t + 7.0 atol = 1.0e-6
        @test debug_values(ctx, ["Ramp/s"]).values["Ramp/s"] ≈ info.t atol = 1.0e-6
        r = ev("nope + w")
        @test r.diagnostics[1].code == "E003" && r.diagnostics[1].scope == "watch"
        @test r.value == 0.0
        debug_continue!(ctx)
        _wt_stop!(run)
    end

    @testset "debug-tour: a watch on a signal that only changes at a tick" begin
        m = _WT_TOUR
        # c = z - 0.1 is -0.00203 before the tick at 0.6 s and +0.00727
        # after it, so the solver never sees a sign change inside a step.
        run = _wt_spawn(m; breakpoints = [_wt_watch("z", "s\"Ctrl/z\" > 0.1")])
        info = _wt_next(run)
        @test info isa NamedTuple
        @test info.reason == "breakpoint" && info.breakpointId == "z"
        @test info.t ≈ 0.6 atol = 1.0e-9
        @test info.tick == 60
        @test info.frame === nothing && info.location.scope == "watch"
        @test all(s -> s.verified, run.ctx.statuses)
        @test debug_values(run.ctx, ["Ctrl/z"]).values["Ctrl/z"] ≈ 0.10727 atol = 1.0e-4
        @test debug_evaluate(run.ctx, "s\"Ctrl/z\" > 0.1").value === true
        debug_continue!(run.ctx)
        rest = _wt_pauses(run; ids = ["Ctrl/z"])
        @test all(p -> p.values["Ctrl/z"] > 0.1, rest)
        @test watch_hits(run.ctx)["z"] == 1 + length(rest)
        @test _wt_result(run).status == "done"

        # A held output, at a tick.
        run = _wt_spawn(m; breakpoints = [_wt_watch("u", "s\"Ctrl/u\" > 16")])
        pauses = _wt_pauses(run; ids = ["Ctrl/u"])
        @test !isempty(pauses)
        @test all(p -> p.values["Ctrl/u"] > 16, pauses)
        @test all(p -> abs(p.info.t / 0.01 - round(p.info.t / 0.01)) < 1.0e-7, pauses)

        # The continuous control keeps its located crossing.
        run = _wt_spawn(m; breakpoints = [_wt_watch("y", "s\"Pos/y\" > 0.5")])
        pauses = _wt_pauses(run; ids = ["Pos/y"])
        @test pauses[1].info.t ≈ 0.7933869 atol = 1.0e-5
        @test pauses[1].values["Pos/y"] ≈ 0.5 atol = 1.0e-9

        # A mix: every upward crossing of the sum, whether a tick or the motion carries it
        # across, is one hit. The rows of a watch-free run give the reference count.
        rows = _wt_rows(m, ["Ctrl/z", "Pos/y"])
        sum_rows = rows["Ctrl/z"] .+ rows["Pos/y"]
        expected = count(i -> sum_rows[i - 1] <= 0.7 && sum_rows[i] > 0.7, 2:length(sum_rows))
        @test expected >= 1
        run = _wt_spawn(m; breakpoints = [_wt_watch("mix", "s\"Ctrl/z\" + s\"Pos/y\" > 0.7")])
        pauses = _wt_pauses(run; ids = ["Ctrl/z", "Pos/y"])
        @test length(pauses) == expected
        @test watch_hits(run.ctx)["mix"] == expected
        @test all(p -> p.values["Ctrl/z"] + p.values["Pos/y"] >= 0.7 - 1.0e-9, pauses)
        @test issorted([p.info.t for p in pauses])
        @test pauses[1].info.t < 1.0                  # the first crossing, not a later one
    end

    @testset "discrete values: the truth of the comparison decides, not the sign" begin
        m = _wt_counter_model()
        for (expr, k) in (
            ("s\"Cnt/k\" > 5", 6), ("s\"Cnt/k\" >= 5", 5), ("s\"Cnt/k\" == 5", 5),
            ("s\"Cnt/k\" > 5 && s\"Cnt/y\" >= 14", 7),   # the second part decides, at k = 7
            ("s\"Cnt/k\" < 3 || s\"Cnt/k\" > 8", 9),     # true at the start: false, then true
            ("s\"Cnt/y\" - 8", 4),                       # a bare real expression: reaches zero
        )
            run = _wt_spawn(m; breakpoints = [_wt_watch("c", expr)])
            pauses = _wt_pauses(run; ids = ["Cnt/k"])
            @test length(pauses) == 1
            @test pauses[1].info.t ≈ k * 1.0e-3 atol = 1.0e-9
            @test pauses[1].values["Cnt/k"] == k
            @test pauses[1].info.tick == k
        end
        for expr in (
            "s\"Cnt/k\" < 3",        # true from the start, then false: no upward crossing
            "s\"Cnt/k\" >= 0",       # true all along
            "s\"Cnt/y\" == 5",       # y is even: it jumps past 5, so `==` never holds
            "s\"Cnt/k\" < 0",        # never true
        )
            run = _wt_spawn(m; breakpoints = [_wt_watch("c", expr)])
            @test isempty(_wt_pauses(run))
            @test watch_hits(run.ctx)["c"] == 0
        end

        # Two watches at one tick: one pause, both counted.
        run = _wt_spawn(m; breakpoints = [
            _wt_watch("a", "s\"Cnt/k\" > 5"), _wt_watch("b", "s\"Cnt/k\" >= 6"),
        ])
        pauses = _wt_pauses(run)
        @test length(pauses) == 1 && pauses[1].info.breakpointId == "a"
        @test watch_hits(run.ctx) == Dict("a" => 1, "b" => 1)

        # A tick that fires a watch reports the breakpoint, not the step.
        run = _wt_spawn(m; breakpoints = [_wt_watch("k", "s\"Cnt/k\" >= 1")], pause_on_entry = true)
        @test _wt_next(run).reason == "entry"
        debug_step!(run.ctx, "tick")
        info = _wt_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "k" && info.tick == 1
        _wt_stop!(run)

        # A model without continuous state has no solver steps at all, only its ticks.
        s = _wt_counter_model(; ramp = false)
        run = _wt_spawn(s; breakpoints = [_wt_watch("c", "s\"Cnt/k\" > 5")])
        pauses = _wt_pauses(run)
        @test length(pauses) == 1
        @test pauses[1].info.t ≈ 6.0e-3 atol = 1.0e-9
    end

    @testset "a mix of continuous and discrete signals: one hit per crossing" begin
        m = _wt_counter_model()
        # 1000 x - y / 2 = 1000 t - k rises through 0.5 inside each tick and falls at the tick.
        rising = "1000 * s\"Ramp/x\" - 0.5 * s\"Cnt/y\" > 0.5"
        run = _wt_spawn(m; breakpoints = [_wt_watch("up", rising)])
        pauses = _wt_pauses(run)
        @test length(pauses) == 20
        @test all(i -> isapprox(pauses[i].info.t, (i - 0.5) * 1.0e-3; atol = 1.0e-8), 1:20)
        @test watch_hits(run.ctx)["up"] == 20

        # y / 2 - 1000 x = k - 1000 t falls inside each tick and rises at the tick.
        jumping = "0.5 * s\"Cnt/y\" - 1000 * s\"Ramp/x\" > -0.75"
        run = _wt_spawn(m; breakpoints = [_wt_watch("up", jumping)])
        pauses = _wt_pauses(run)
        @test length(pauses) == 20
        @test all(i -> isapprox(pauses[i].info.t, i * 1.0e-3; atol = 1.0e-9), 1:20)
        @test watch_hits(run.ctx)["up"] == 20

        # hitCount counts both kinds of crossing per watch.
        run = _wt_spawn(m; breakpoints = [_wt_watch("up", jumping; hit = 3)])
        pauses = _wt_pauses(run)
        @test length(pauses) == 1
        @test pauses[1].info.t ≈ 3.0e-3 atol = 1.0e-9
        @test watch_hits(run.ctx)["up"] == 20

        # The motion reaches the level on the tick and the tick lifts it past: the step ends on
        # the root and the jump follows at the same instant, one crossing.
        run = _wt_spawn(m; breakpoints = [
            _wt_watch("both", "s\"Ramp/x\" + 1.0e-9 * s\"Cnt/y\" > 0.005000008"),
        ])
        pauses = _wt_pauses(run)
        @test length(pauses) == 1
        @test pauses[1].info.t ≈ 0.005 atol = 1.0e-8
        @test watch_hits(run.ctx)["both"] == 1
    end

    @testset "jumps of other kinds: an @events affect and a kink" begin
        # The limit switch latches in an event affect, a jump of the state.
        run = _wt_spawn(_WT_TOUR; breakpoints = [_wt_watch("latch", "s\"Limit/latch\" > 0.5")])
        pauses = _wt_pauses(run; ids = ["Limit/latch", "Pos/y"])
        @test length(pauses) == 1
        @test pauses[1].info.t ≈ 1.09365 atol = 1.0e-3
        @test pauses[1].values["Limit/latch"] == 1.0
        @test pauses[1].values["Pos/y"] ≈ 1.2 atol = 1.0e-6

        # The reinit of the bounce turns v positive in one instant.
        run = _wt_spawn(_WT_BALL; breakpoints = [_wt_watch("up", "s\"Ball1/v\" > 0")])
        info = _wt_next(run)
        @test info isa NamedTuple && info.reason == "breakpoint"
        @test info.t ≈ sqrt(2 / 9.81) atol = 1.0e-6
        @test debug_values(run.ctx, ["Ball1/v"]).values["Ball1/v"] > 0
        _wt_stop!(run)

        # The source steps at the instant of the model's own kink callback, which used to win.
        run = _wt_spawn(_WT_DC; breakpoints = [_wt_watch("e", "s\"Motor1/p.e\" > 6")])
        pauses = _wt_pauses(run; ids = ["Motor1/p.e"])
        @test !isempty(pauses)
        @test pauses[1].info.t ≈ 0.01 atol = 1.0e-9
        @test pauses[1].values["Motor1/p.e"] > 6
    end

    @testset "discrete watches re-arm from the current state and survive a list change" begin
        m = _wt_counter_model()
        k5 = _wt_watch("a", "s\"Cnt/k\" > 5")
        run = _wt_spawn(m; breakpoints = [k5])
        @test _wt_next(run).breakpointId == "a"       # k = 6
        # Added while paused: `b` is already true, so it never fires; `c` fires at its crossing.
        list = [k5, _wt_watch("b", "s\"Cnt/k\" > 3"), _wt_watch("c", "s\"Cnt/k\" > 8")]
        @test all(s -> s.verified, debug_set_breakpoints!(run.ctx, list))
        @test watch_hits(run.ctx)["a"] == 1           # an unchanged watch keeps its count
        debug_continue!(run.ctx)
        info = _wt_next(run)
        @test info.breakpointId == "c"
        @test info.t ≈ 9.0e-3 atol = 1.0e-9
        # Changed while paused: `a` is false again and counts from zero, `c` is true.
        list = [
            _wt_watch("a", "s\"Cnt/k\" > 10"), _wt_watch("b", "s\"Cnt/k\" > 3"),
            _wt_watch("c", "s\"Cnt/k\" > 2"),
        ]
        debug_set_breakpoints!(run.ctx, list)
        @test watch_hits(run.ctx) == Dict("a" => 0, "b" => 0, "c" => 0)
        debug_continue!(run.ctx)
        info = _wt_next(run)
        @test info.breakpointId == "a"
        @test info.t ≈ 11.0e-3 atol = 1.0e-9
        debug_continue!(run.ctx)
        @test _wt_next(run) === :finished
        @test watch_hits(run.ctx) == Dict("a" => 1, "b" => 0, "c" => 0)

        # At a statement pause of the crossing tick the value is not published yet: setting the
        # list again must not lose the crossing of the unchanged watch.
        line = findfirst(l -> occursin("d = w -", l), split(_WT_COUNTER, '\n'))
        statement = Dict{String,Any}(
            "id" => "line", "enabled" => true, "kind" => "line", "hitCount" => 6,
            "line" => Dict{String,Any}("ref" => "inline:cnt", "line" => line, "path" => nothing),
        )
        run = _wt_spawn(m; breakpoints = [statement, k5])
        info = _wt_next(run)
        @test info.breakpointId == "line" && info.frame !== nothing
        debug_set_breakpoints!(run.ctx, [k5])
        debug_continue!(run.ctx)
        info = _wt_next(run)
        @test info.breakpointId == "a"
        @test info.t ≈ 6.0e-3 atol = 1.0e-9
        _wt_stop!(run)
    end

    @testset "a live edit is not a crossing" begin
        m = _wt_oscillator(; t_end = 0.3)
        run = _wt_spawn(m; breakpoints = [_wt_watch("w", "s\"Plant/w\" > 7")], pause_on_entry = true)
        @test _wt_next(run).reason == "entry"
        @test debug_set_parameter!(run.ctx, "Plant/w", 8.0).ok
        debug_continue!(run.ctx)
        @test _wt_next(run) === :finished
        @test watch_hits(run.ctx)["w"] == 0

        run = _wt_spawn(m; breakpoints = [_wt_watch("x", "s\"Plant/x\" > 2")], pause_on_entry = true)
        @test _wt_next(run).reason == "entry"
        @test debug_set_state!(run.ctx, "Plant/x", 3.0).ok
        debug_continue!(run.ctx)
        @test _wt_next(run) === :finished
    end

    @testset "an edit at a watch pause on a tick replays bit for bit" begin
        m = _WT_TOUR
        run = _wt_spawn(m; breakpoints = [_wt_watch("z", "s\"Ctrl/z\" > 0.1"; hit = 1)])
        info = _wt_next(run)
        @test info.reason == "breakpoint"
        @test debug_set_parameter!(run.ctx, "Ctrl/aw", 1.0).ok
        @test run.ctx.edits[1].position.at == "target"
        debug_continue!(run.ctx)
        _wt_pauses(run)
        dir = mktempdir()
        result = replay_run(run.dir; flat = m.flat, run_dir = dir, run_id = "replay")
        @test result.status == "done"
        @test read(joinpath(dir, "columns.f64")) == read(joinpath(run.dir, "columns.f64"))
    end

    @testset "the pool is installed in a debug run and costs nothing visible" begin
        m = _WT_DC
        run = _wt_spawn(m; pause_on_entry = true)
        _wt_next(run)
        pool = watch_pool(run.ctx)
        @test pool isa BGSim.WatchPool
        @test length(pool.fns) == 16 && all(isnothing, pool.fns)
        @test pool.active == 0
        _wt_stop!(run)
    end
end

