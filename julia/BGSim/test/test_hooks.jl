# Work package J4.2: statement hooks and line breakpoints (plan 5.13, decisions D20 and D21).
#
# Acceptance of the work package, through the real pipeline (`parse -> flatten -> lower ->
# simulate` with `debug = DebugCtx`), driven from a spawned task like test_debug.jl:
#
#   * a breakpoint on an `LQGController` line pauses at every tick of that partition, and the
#     frame's `xhat` equals the value a normal run recorded (see `_hk_recorded_before`);
#   * in a block with a tick counter `k`, the condition `k == 5` pauses only at the fifth tick,
#     and `hitCount = 3` only at the third hit;
#   * a breakpoint on an `@equations` line gives E401, one in a block the model does not use
#     gives W401;
#   * continuing through 100 hits leaves `columns.f64` bit-identical to a normal run.
#
# Plus: the normal run's generated step expression is unchanged, the hook table of
# `LQGController`, step `statement` (consecutive statements, across ticks), disabled
# breakpoints, `path`-restricted breakpoints, conditions that do not compile, the frame and
# `paused_frame`, and cancel at a statement pause.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

const _HK_EXAMPLES = normpath(joinpath(@__DIR__, "..", "..", "..", "examples"))

# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------

# A yielding cancel callback, like the worker's: it lets the controlling task run while the
# run task steps.
_hk_cancel_cb() = () -> (yield(); false)

mutable struct _HkRun
    ctx::DebugCtx
    task::Task
    paused::Channel{Any}
    dir::String
end

function _hk_spawn(flat, settings; kwargs...)
    paused = Channel{Any}(Inf)
    ctx = DebugCtx(; on_paused = info -> put!(paused, info), kwargs...)
    dir = mktempdir()
    task = Threads.@spawn simulate(
        flat; run_dir = dir, run_id = "hk", settings = settings, debug = ctx,
        cancel = _hk_cancel_cb(),
    )
    Threads.@spawn begin
        try
            wait(task)
        catch
        end
        put!(paused, :finished)
    end
    return _HkRun(ctx, task, paused, dir)
end

# The next notification (a NamedTuple) or `:finished`; fails instead of hanging.
function _hk_next(run::_HkRun; seconds = 240)
    timer = Timer(_ -> close(run.paused), seconds)
    try
        return take!(run.paused)
    finally
        close(timer)
    end
end

_hk_result(run::_HkRun) = fetch(run.task)

function _hk_normal(flat, settings)
    dir = mktempdir()
    result = simulate(flat; run_dir = dir, run_id = "hk", settings = settings)
    return result, dir
end

_hk_manifest(dir) = JSON3.read(read(joinpath(dir, "manifest.json"), String))

# Continue through every remaining pause; returns the infos.
function _hk_finish!(run::_HkRun)
    infos = Any[]
    while true
        info = _hk_next(run)
        info === :finished && return infos
        push!(infos, info)
        debug_continue!(run.ctx)
    end
end

function _hk_valid_files(dir)
    manifest = _hk_manifest(dir)
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    @test filesize(joinpath(dir, "columns.f64")) == 8 * n * (nsignals + 1)
    @test filesize(joinpath(dir, "stream.f64")) == 8 * n * (nsignals + 1)
    return manifest
end

"""The run folder's columns as `(time, Dict(id => values))`."""
function _hk_columns(dir)
    manifest = _hk_manifest(dir)
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    raw = read(joinpath(dir, "columns.f64"))
    columns = reshape(reinterpret(Float64, raw), (n, nsignals + 1))
    values = Dict{String,Vector{Float64}}(
        String(signal.id) => collect(columns[:, j + 1]) for
        (j, signal) in enumerate(manifest.signals)
    )
    return collect(columns[:, 1]), values
end

# What a frame at tick time `t` shows for a held value: its value before this tick ran. A
# normal run recorded that value in the last row before `t` (rows between ticks carry the held
# value unchanged; the first tick sees the start value in row zero).
function _hk_recorded_before(time, values, id, t)
    rows = findall(<(t - 1.0e-12), time)
    return values[id][last(rows)]
end

function _hk_line_bp(id, ref, line; path = nothing, enabled = true, condition = nothing,
    hit = nothing)
    bp = Dict{String,Any}(
        "id" => id, "enabled" => enabled, "kind" => "line",
        "line" => Dict{String,Any}("ref" => ref, "line" => line, "path" => path),
    )
    condition === nothing || (bp["condition"] = condition)
    hit === nothing || (bp["hitCount"] = hit)
    return bp
end

# Line number (1-based) of the first line of `src` that contains `needle`.
function _hk_line(src, needle)
    for (i, line) in enumerate(split(src, '\n'))
        occursin(needle, line) && return i
    end
    error("`$needle` is not in the source")
end

_hk_frame_entry(entries, name) = only(e for e in entries if e.name == name)

# Every notification until the run ends (after a cancel, a pause may already be queued).
function _hk_drain!(run::_HkRun)
    infos = Any[]
    while true
        info = _hk_next(run)
        info === :finished && return infos
        push!(infos, info)
    end
end

# The debug variant's expression without its hook statements.
_hk_strip_hooks(ex) = ex

function _hk_strip_hooks(ex::Expr)
    args = Any[]
    for a in ex.args
        a isa Expr && a.head === :if && occursin("dbg", string(a.args[1])) && continue
        push!(args, _hk_strip_hooks(a))
    end
    return Expr(ex.head, args...)
end

# ---------------------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------------------

function _hk_node(id, name, block)
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(), "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
end

_hk_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _hk_conn(id, from_node, from_port, to_node, to_port)
    return Dict{String,Any}(
        "id" => id, "kind" => "signal",
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
end

function _hk_settings(; t_end = 0.02, points = 21)
    return Dict{String,Any}(
        "t_start" => 0.0, "t_end" => t_end, "solver" => "Rodas5P", "reltol" => 1.0e-8,
        "abstol" => 1.0e-10, "max_step" => nothing,
        "output" => Dict{String,Any}("mode" => "points", "points" => points),
        "event_limit" => 10000,
    )
end

function _hk_doc(name, nodes, connections; kwargs...)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...], "connections" => Any[connections...],
            "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => _hk_settings(; kwargs...), "plots" => Any[], "scene" => nothing,
        "bindings" => Any[],
    )
end

# A continuous source with `@equations` and `@events` (E401 targets), two stdlib quantizers
# (two instances of one block) and a tick counter with a temporary and `previous`.
const _HK_RAMP = """
@block Ramp begin
    @outputs x::Real
    @variables s::Real = 0.0
    @equations begin
        ddt(s) ~ 1.0
        x ~ s
    end
    @events begin
        s > 0.0105 => begin
            reinit(s, 0.0)
        end
    end
end
"""

const _HK_COUNTER = """
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

const _HK_QUANTIZER = "stdlib:discrete/Quantizer"

function _hk_model()
    doc = _hk_doc(
        "Hooks",
        [
            _hk_node("ramp", "Ramp", _hk_inline(_HK_RAMP)),
            _hk_node("q1", "Q1", Dict{String,Any}("ref" => _HK_QUANTIZER)),
            _hk_node("q2", "Q2", Dict{String,Any}("ref" => _HK_QUANTIZER)),
            _hk_node("cnt", "Cnt", _hk_inline(_HK_COUNTER)),
        ],
        [
            _hk_conn("c1", "ramp", "x", "q1", "u"),
            _hk_conn("c2", "ramp", "x", "q2", "u"),
        ],
    )
    flat = Compile.flatten(IR.parse_model(doc))
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"]) string(flat.diagnostics)
    return flat, BGSim.RunSettings(doc["settings"])
end

const _HK_FLAT, _HK_SETTINGS = _hk_model()
const _HK_COUNTER_REF = "inline:cnt"
const _HK_RAMP_REF = "inline:ramp"

function _hk_kalman()
    project = joinpath(_HK_EXAMPLES, "drivetrain-kalman")
    md = IR.parse_model(joinpath(project, "models", "drivetrain-kalman.bgmodel.json"))
    flat = Compile.flatten(md; project_dir = project)
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"])
    # 0.2 s: 200 ticks of the 1 ms controller, output grid every 0.5 ms.
    settings = BGSim.RunSettings(
        t_start = 0.0, t_end = 0.2, solver = "auto", reltol = 1.0e-8, abstol = 1.0e-10,
        output = Dict("mode" => "points", "points" => 401), event_limit = 10000,
    )
    source = read(joinpath(project, "library", "LQGController.jl"), String)
    return flat, settings, source
end

const _HK_KALMAN, _HK_KALMAN_SETTINGS, _HK_LQG_SRC = _hk_kalman()
const _HK_LQG_REF = "project:LQGController"

@testset "statement hooks and line breakpoints (J4.2)" begin
    @testset "the normal run's step expression is unchanged" begin
        part = only(p for p in _HK_FLAT.discrete if p.ref == _HK_COUNTER_REF)
        held = Dict{String,Int}(id => i for (i, id) in enumerate(part.writes))
        inputs = Dict{String,Int}()
        params = Dict{String,Int}()
        helpers = BGSim.DiscreteRuntime
        normal = Compile.step_expression(part, held, inputs, params, helpers)
        @test normal.head === :->
        @test normal.args[1] == Expr(:tuple, :dstate, :inputs, :params, :t)
        @test !occursin("dbg", string(normal))
        emit = Compile.DebugEmit(:hook, :stepping)
        debug = Compile.step_expression(part, held, inputs, params, helpers; debug = emit)
        @test debug.args[1] == Expr(:tuple, :dstate, :inputs, :params, :t, :dbg)
        # The debug variant is the normal expression plus the hook statements.
        @test _hk_strip_hooks(debug.args[2]) == normal.args[2]
        @test length(emit.sites) == 4
        # Without a debug context the schedule holds the plain generated functions.
        schedule = BGSim.discrete_schedule(_HK_FLAT; t_end = 0.01)
        @test !any(sp -> sp.step isa DebugStep, schedule.partitions)
        ctx = DebugCtx()
        hooks = HookState(ctx)
        debug_schedule = BGSim.discrete_schedule(_HK_FLAT; t_end = 0.01, debug = hooks)
        @test all(sp -> sp.step isa DebugStep, debug_schedule.partitions)
        @test length(hooks.emit.sites) == 4 + 2 * 1
        @test length(hooks.armed) == length(hooks.emit.sites)
        @test !any(hooks.armed)
    end

    @testset "the hook table of LQGController" begin
        ctx = DebugCtx()
        hooks = HookState(ctx)
        BGSim.discrete_schedule(_HK_KALMAN; t_end = 0.01, debug = hooks)
        sites = [s for s in hooks.emit.sites if s.ref == _HK_LQG_REF]
        lines = [_hk_line(_HK_LQG_SRC, n) for n in (
            "y = theta_m", "xhat = xhat + L", "z += Ts * (w_ref - xhat[4])  ",
            "v = -dot", "u = clamp", "if abs(v)", "z -= Ts", "xhat = Phi", "w_load_hat = ",
        )]
        @test [s.range.line for s in sites] == lines
        @test [s.kind for s in sites] ==
              [:assign, :assign, :assign, :assign, :assign, :if, :assign, :assign, :assign]
        @test all(s -> s.path == "LQG" && s.scope == "@discrete", sites)
        # The broadcast `xhat = ...` over five elements is one statement, one hook.
        @test count(s -> s.range.line == _hk_line(_HK_LQG_SRC, "xhat = xhat + L"), sites) == 1
        # Temporaries assigned so far, in first-assignment order.
        @test [first.(s.temps) for s in sites] == [
            String[], ["y"], ["y"], ["y"], ["y", "v"], ["y", "v"], ["y", "v"], ["y", "v"],
            ["y", "v"],
        ]
        # An `if` hook spans from the keyword to the end of its condition.
        if_site = sites[6]
        @test if_site.range.line == if_site.range.endLine
        # The quantizer next to it has its own hook.
        quantizer = [s for s in hooks.emit.sites if s.ref == _HK_QUANTIZER]
        @test length(quantizer) == 1 && quantizer[1].range.line == 7
    end

    @testset "a breakpoint on an LQGController line pauses at every tick (acceptance)" begin
        flat, settings = _HK_KALMAN, _HK_KALMAN_SETTINGS
        _, normal_dir = _hk_normal(flat, settings)
        time, values = _hk_columns(normal_dir)
        line = _hk_line(_HK_LQG_SRC, "xhat = xhat + L")
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("bp1", _HK_LQG_REF, line)])
        n = 40
        for i in 1:n
            info = _hk_next(run)
            @test info !== :finished
            info === :finished && break
            t_i = i * 1.0e-3
            @test info.reason == "breakpoint"
            @test info.breakpointId == "bp1"
            @test abs(info.t - t_i) < 1.0e-12
            @test info.tick == i - 1            # ticks executed so far
            @test info.location.path == "LQG"
            @test info.location.ref == _HK_LQG_REF
            @test info.location.scope == "@discrete"
            @test info.location.range.line == line
            xhat = _hk_frame_entry(info.frame.held, "xhat")
            @test xhat.type == "Real"
            @test xhat.size == [5]
            # The frame shows xhat before the statement at that line runs, i.e. as the previous
            # tick left it. That is what a normal run recorded in the last row before t_i
            # (and, when the tick changed it, in the left row at t_i).
            for j in 1:5
                @test xhat.value[j] == _hk_recorded_before(time, values, "LQG/xhat[$j]", t_i)
            end
            z = _hk_frame_entry(info.frame.held, "z")
            @test z.value == _hk_recorded_before(time, values, "LQG/z", t_i)
            @test [e.name for e in info.frame.locals] == ["y"]   # assigned on line 39
            # Leave the rest of the run alone after the last pause.
            i == n && debug_set_breakpoints!(run.ctx, [])
            debug_continue!(run.ctx)
        end
        @test _hk_next(run) === :finished
        @test _hk_result(run).status == "done"
    end

    @testset "continuing through 100 hits keeps columns.f64 bit-identical" begin
        flat, settings = _HK_KALMAN, _HK_KALMAN_SETTINGS
        _, normal_dir = _hk_normal(flat, settings)
        line = _hk_line(_HK_LQG_SRC, "xhat = Phi")
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("bp1", _HK_LQG_REF, line)])
        for i in 1:100
            info = _hk_next(run)
            @test info !== :finished
            info === :finished && break
            @test info.tick == i - 1
            # The time update sees the measurement-updated xhat, not the recorded one.
            @test info.location.range.line == line
            i == 100 && debug_set_breakpoints!(run.ctx, [])
            debug_continue!(run.ctx)
        end
        @test _hk_next(run) === :finished
        result = _hk_result(run)
        @test result.status == "done"
        @test read(joinpath(run.dir, "columns.f64")) == read(joinpath(normal_dir, "columns.f64"))
        manifest = _hk_valid_files(run.dir)
        @test length(manifest.debug.pauses) == 100
        @test all(p -> p.reason == "breakpoint", manifest.debug.pauses)
    end

    @testset "conditions, hit counts and the frame" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        _, normal_dir = _hk_normal(flat, settings)
        line = _hk_line(_HK_COUNTER, "y = 2.0 * k")
        wline = _hk_line(_HK_COUNTER, "d = w -")
        bps = [
            _hk_line_bp("cond", _HK_COUNTER_REF, line; condition = "k == 5"),
            _hk_line_bp("hit", _HK_COUNTER_REF, wline; hit = 3),
        ]
        run = _hk_spawn(flat, settings; breakpoints = bps)
        # The hit-count breakpoint comes first (third tick), then the condition (fifth).
        info = _hk_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "hit"
        @test info.tick == 2 && abs(info.t - 3.0e-3) < 1e-12
        frame = info.frame
        @test [e.name for e in frame.locals] == ["w"]
        w = _hk_frame_entry(frame.locals, "w")
        @test w.type == "Real" && w.size == Int[] && w.value == 7.0     # y = 2*3, w = y + 1
        k = _hk_frame_entry(frame.held, "k")
        @test k.type == "Int" && k.value == 3
        @test _hk_frame_entry(frame.held, "y").value == 6.0
        # `previous(y)`: y as the previous tick left it.
        prev = _hk_frame_entry(frame.previous, "y")
        @test prev.value == 4.0
        # `paused_frame` keeps the raw values and the name environment for evaluate (D27).
        pf = with_paused(s -> paused_frame(s.ctx), run.ctx)
        @test pf isa PausedFrame
        @test pf.env[:w] == 7.0 && pf.env[:k] == 3 && abs(pf.env[:t] - info.t) < 1e-12
        @test pf.env[:Ts] == 1.0e-3 && pf.env[:y] == 6.0
        @test pf.site.range.line == wline
        expr = BGSim.declarations(
            BGSim.parse_block("@block B begin\n @parameters c::Real = w * k + 1.0\nend\n"),
            :parameters,
        )[1].default
        @test BGSim.eval_const(expr, pf.env) == 22.0
        @test paused_frame(run.ctx) isa PausedFrame
        debug_continue!(run.ctx)
        info = _hk_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "cond"
        @test info.tick == 4 && abs(info.t - 5.0e-3) < 1e-12
        @test _hk_frame_entry(info.frame.held, "k").value == 5
        debug_continue!(run.ctx)
        # No other tick pauses: k == 5 holds once, and the third hit only once.
        @test _hk_next(run) === :finished
        @test _hk_result(run).status == "done"
        @test paused_frame(run.ctx) === nothing
        @test read(joinpath(run.dir, "columns.f64")) == read(joinpath(normal_dir, "columns.f64"))
        manifest = _hk_valid_files(run.dir)
        @test [p.reason for p in manifest.debug.pauses] == ["breakpoint", "breakpoint"]
    end

    @testset "E401, W401 and conditions that do not compile" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        eq_line = _hk_line(_HK_RAMP, "ddt(s) ~ 1.0")
        ev_line = _hk_line(_HK_RAMP, "reinit(s, 0.0)")
        decl_line = _hk_line(_HK_RAMP, "@variables s")
        count_line = _hk_line(_HK_COUNTER, "y = 2.0 * k")
        bps = [
            _hk_line_bp("eq", _HK_RAMP_REF, eq_line),
            _hk_line_bp("ev", _HK_RAMP_REF, ev_line),
            _hk_line_bp("decl", _HK_RAMP_REF, decl_line),
            _hk_line_bp("blank", _HK_COUNTER_REF, _hk_line(_HK_COUNTER, "@discrete") + 99),
            _hk_line_bp("head", _HK_COUNTER_REF, _hk_line(_HK_COUNTER, "@discrete")),
            _hk_line_bp("unused", "project:Unused", 3),
            _hk_line_bp("nopath", _HK_QUANTIZER, 7; path = "Nope"),
            _hk_line_bp("syntax", _HK_COUNTER_REF, count_line; condition = "k =="),
            _hk_line_bp("scope", _HK_COUNTER_REF, count_line; condition = "nothere > 1"),
            _hk_line_bp("later", _HK_COUNTER_REF, count_line; condition = "w > 1"),
            _hk_line_bp("fn", _HK_COUNTER_REF, count_line; condition = "frobnicate(k) > 1"),
            _hk_line_bp("good", _HK_COUNTER_REF, count_line; condition = "k > 1 && y >= 0"),
        ]
        run = _hk_spawn(flat, settings; pause_on_entry = true)
        @test _hk_next(run).reason == "entry"
        st = Dict(s.id => s for s in debug_set_breakpoints!(run.ctx, bps))

        for id in ("eq", "decl")
            @test !st[id].verified
            @test st[id].resolved.hooks == 0
            d = only(st[id].diagnostics)
            @test d.code == "E401" && d.severity == "error"
            @test d.hint == "equations do not execute in order; add a watch breakpoint on a signal instead"
            @test d.block == _HK_RAMP_REF
            @test d.source.ref == _HK_RAMP_REF && d.source.range.line == (id == "eq" ? eq_line : decl_line)
        end
        @test only(st["eq"].diagnostics).scope == "@equations"
        @test only(st["decl"].diagnostics).scope == "@variables"
        d = only(st["ev"].diagnostics)
        @test d.code == "E401" && d.scope == "@events"
        @test occursin("event breakpoint", d.hint)
        d = only(st["head"].diagnostics)
        @test d.code == "E401" && d.scope == "@discrete"
        @test occursin("assignment", d.hint)
        d = only(st["blank"].diagnostics)
        @test d.code == "E401" && d.scope === nothing
        @test occursin("no statement on line", d.message)

        d = only(st["unused"].diagnostics)
        @test !st["unused"].verified && st["unused"].resolved.hooks == 0
        @test d.code == "W401" && d.severity == "warning" && d.block == "project:Unused"
        @test occursin("not used in this model", d.message)
        @test occursin("instantiate project:Unused", d.hint)
        d = only(st["nopath"].diagnostics)
        @test !st["nopath"].verified && d.code == "W401" && d.path == "Nope"
        @test occursin("Q1", d.hint) && occursin("Q2", d.hint)

        # Conditions: parse errors E001, unknown names E003, unsupported calls E004.
        for (id, code) in (("syntax", "E001"), ("scope", "E003"), ("later", "E003"),
            ("fn", "E004"))
            @test !st[id].verified
            d = only(st[id].diagnostics)
            @test d.code == code && d.scope == "breakpoint condition"
        end
        @test only(st["later"].diagnostics).message ==
              "`w` is not in scope at line $count_line of Cnt"
        @test st["good"].verified && st["good"].resolved.hooks == 1
        @test st["good"].resolved.paths == ["Cnt"]
        @test isempty(st["good"].diagnostics)
        # A bad breakpoint arms nothing: only "good" can pause.
        @test count(identity, run.ctx.ext[:hooks].armed) == 1

        # The statuses have the contract shape of a BreakpointStatus.
        for s in values(st)
            @test keys(s) == (:id, :verified, :resolved, :diagnostics)
            @test keys(s.resolved) == (:hooks, :paths)
        end
        debug_cancel!(run.ctx)
        _hk_drain!(run)
    end

    @testset "disabled breakpoints never fire" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        _, normal_dir = _hk_normal(flat, settings)
        line = _hk_line(_HK_COUNTER, "y = 2.0 * k")
        bps = [
            _hk_line_bp("off", _HK_COUNTER_REF, line; enabled = false),
            _hk_line_bp("off2", _HK_QUANTIZER, 7; enabled = false),
        ]
        run = _hk_spawn(flat, settings; breakpoints = bps)
        @test _hk_next(run) === :finished
        @test _hk_result(run).status == "done"
        @test !any(run.ctx.ext[:hooks].armed)
        # Still verified: the line exists, the breakpoint is just off.
        @test all(s -> s.verified && s.resolved.hooks >= 1, run.ctx.statuses)
        @test read(joinpath(run.dir, "columns.f64")) == read(joinpath(normal_dir, "columns.f64"))

        # Disabling a live breakpoint while paused takes effect immediately.
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("on", _HK_COUNTER_REF, line)])
        @test _hk_next(run).breakpointId == "on"
        debug_set_breakpoints!(run.ctx, [_hk_line_bp("on", _HK_COUNTER_REF, line; enabled = false)])
        debug_continue!(run.ctx)
        @test _hk_next(run) === :finished
    end

    @testset "a path-restricted breakpoint fires only for that instance" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        both = _hk_spawn(
            flat, settings; breakpoints = [_hk_line_bp("all", _HK_QUANTIZER, 7)]
        )
        @test _hk_next(both).location.path == "Q1"
        debug_continue!(both.ctx)
        @test _hk_next(both).location.path == "Q2"
        st = only(both.ctx.statuses)
        @test st.verified && st.resolved.hooks == 2 && sort(st.resolved.paths) == ["Q1", "Q2"]
        debug_cancel!(both.ctx)
        _hk_drain!(both)
        @test _hk_result(both).status == "cancelled"

        one = _hk_spawn(
            flat, settings; breakpoints = [_hk_line_bp("q2", _HK_QUANTIZER, 7; path = "Q2")]
        )
        for tick in 1:4
            info = _hk_next(one)
            @test info.location.path == "Q2" && info.breakpointId == "q2"
            @test info.tick == tick - 1
            debug_continue!(one.ctx)
        end
        st = only(one.ctx.statuses)
        @test st.resolved.hooks == 1 && st.resolved.paths == ["Q2"]
        debug_cancel!(one.ctx)
        _hk_drain!(one)
        @test _hk_result(one).status == "cancelled"
    end

    @testset "step statement visits consecutive statements and crosses into the next tick" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        _, normal_dir = _hk_normal(flat, settings)
        run = _hk_spawn(flat, settings; pause_on_entry = true)
        @test _hk_next(run).reason == "entry"
        sites = with_paused(s -> copy(s.ctx.ext[:hooks].emit.sites), run.ctx)
        per_tick = length(sites)
        @test per_tick == 6        # 1 + 1 (quantizers) + 4 (counter)
        seen = Any[]
        for _ in 1:(2 * per_tick + 1)
            debug_step!(run.ctx, "statement")
            info = _hk_next(run)
            @test info.reason == "step"
            @test info.breakpointId === nothing
            @test info.frame !== nothing
            push!(seen, info)
        end
        for (i, info) in enumerate(seen)
            site = sites[mod1(i, per_tick)]
            @test info.location.path == site.path
            @test info.location.ref == site.ref
            @test info.location.range.line == site.range.line
            @test info.tick == (i - 1) ÷ per_tick       # the tick the statement belongs to
        end
        # Statements of the counter come in source order within the tick.
        counter_lines = [
            i.location.range.line for i in seen[1:per_tick] if i.location.path == "Cnt"
        ]
        @test counter_lines == sort(counter_lines) && length(counter_lines) == 4
        # Continuing from a statement pause finishes the statement and the tick normally.
        debug_continue!(run.ctx)
        @test _hk_next(run) === :finished
        @test _hk_result(run).status == "done"
        @test read(joinpath(run.dir, "columns.f64")) == read(joinpath(normal_dir, "columns.f64"))
        manifest = _hk_valid_files(run.dir)
        @test count(p -> p.reason == "step", manifest.debug.pauses) == 2 * per_tick + 1
        # An unsupported granularity is refused; the statement one is supported.
        @test "statement" in BGSim.STEP_GRANULARITIES
    end

    @testset "step statement from a breakpoint pause, then from a tick pause" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        line = _hk_line(_HK_COUNTER, "k += 1")
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("bp", _HK_COUNTER_REF, line)])
        info = _hk_next(run)
        @test info.reason == "breakpoint"
        debug_step!(run.ctx, "statement")
        info = _hk_next(run)
        @test info.reason == "step" && info.location.range.line == line + 1
        debug_set_breakpoints!(run.ctx, [])
        debug_step!(run.ctx, "tick")
        info = _hk_next(run)
        @test info.reason == "step" && info.frame === nothing && info.location === nothing
        # A statement step from the tick pause pauses at the first hook of the next tick.
        debug_step!(run.ctx, "statement")
        info = _hk_next(run)
        @test info.reason == "step" && info.frame !== nothing
        @test info.tick == 1
        debug_cancel!(run.ctx)
        _hk_drain!(run)
    end

    @testset "an @events firing between ticks is recorded once around statement pauses" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        normal, normal_dir = _hk_normal(flat, settings)
        @test normal.stats.events >= 1          # the ramp restarts at t = 0.0105
        line = _hk_line(_HK_COUNTER, "y = 2.0 * k")
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("bp", _HK_COUNTER_REF, line)])
        infos = _hk_finish!(run)
        @test length(infos) == 20
        @test _hk_result(run).status == "done"
        @test read(joinpath(run.dir, "columns.f64")) == read(joinpath(normal_dir, "columns.f64"))
    end

    @testset "cancel at a statement pause ends cancelled with valid files" begin
        flat, settings = _HK_FLAT, _HK_SETTINGS
        line = _hk_line(_HK_COUNTER, "y = 2.0 * k")
        run = _hk_spawn(flat, settings; breakpoints = [_hk_line_bp("bp", _HK_COUNTER_REF, line)])
        info = _hk_next(run)
        @test info.reason == "breakpoint"
        debug_cancel!(run.ctx)
        @test isempty(_hk_drain!(run))
        @test _hk_result(run).status == "cancelled"
        manifest = _hk_valid_files(run.dir)
        @test manifest.status == "cancelled"
        @test length(manifest.debug.pauses) == 1
        @test paused_frame(run.ctx) === nothing
    end

    @testset "breakpoints set before the run bind when it starts" begin
        ctx = DebugCtx()
        pending = debug_set_breakpoints!(ctx, [_hk_line_bp("early", _HK_COUNTER_REF, 10)])
        @test !only(pending).verified && isempty(only(pending).diagnostics)
        # A line breakpoint needs `ref` and `line`.
        @test_throws ArgumentError parse_breakpoint(Dict(
            "id" => "x", "kind" => "line", "line" => Dict("line" => 3),
        ))
        @test_throws ArgumentError parse_breakpoint(Dict(
            "id" => "x", "kind" => "line", "line" => Dict("ref" => "a", "line" => 0),
        ))
    end
end
