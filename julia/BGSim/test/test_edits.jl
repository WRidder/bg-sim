# Work package J4.4: parameter and state edits, replay and branch (plan 5.13, D24, D25).
#
#   * dc-motor: pause with `runTo` at t = 0.2 s, change `R`, continue; replaying the run's
#     manifest writes the same `columns.f64` bytes (acceptance);
#   * a branch at t = 0.1 s matches the parent's rows before 0.1 bit for bit, then pauses; a
#     branch after an edit applies it; a replay of the branch reproduces it;
#   * `setState` works on a drivetrain-kalman plant state and on a dc-motor state; it gives
#     E402 on a model whose compiled system keeps a nonlinear algebraic loop (checked), on
#     observed signals and on aliases;
#   * edits at a tick pause, a solver-step pause, a pause request and a statement pause replay
#     bit for bit (drivetrain-kalman); an edit at a watch pause replays within tolerance;
#   * unknown parameters, held outputs and non-finite values are refused without an edit; edits
#     while the run is not paused raise `DebugStateError`; the final manifest has `debug.edits`.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim: ModelingToolkit
import JSON3

const _ED_EXAMPLES = normpath(joinpath(@__DIR__, "..", "..", "..", "examples"))

struct _EdModel
    flat::Any
    settings::BGSim.RunSettings
    project::String
    path::String
end

function _ed_model(dir, file; settings = nothing)
    project = joinpath(_ED_EXAMPLES, dir)
    path = joinpath(project, "models", file)
    md = IR.parse_model(path)
    flat = Compile.flatten(md; project_dir = project)
    @assert isempty([d for d in flat.diagnostics if d.severity == "error"])
    return _EdModel(
        flat, settings === nothing ? BGSim.RunSettings(md.settings) : settings, project, path,
    )
end

_ed_cancel() = () -> (yield(); false)

function _ed_normal(m::_EdModel)
    dir = mktempdir()
    simulate(m.flat; run_dir = dir, run_id = "ed", settings = m.settings)
    return dir
end

mutable struct _EdRun
    ctx::DebugCtx
    task::Task
    paused::Channel{Any}
    dir::String
end

function _ed_spawn(m::_EdModel; cancel = _ed_cancel(), id = "ed", kwargs...)
    paused = Channel{Any}(Inf)
    ctx = DebugCtx(; on_paused = info -> put!(paused, info), kwargs...)
    dir = mktempdir()
    task = Threads.@spawn simulate(
        m.flat; run_dir = dir, run_id = id, settings = m.settings, debug = ctx,
        cancel = cancel,
    )
    Threads.@spawn begin
        try
            wait(task)
        catch
        end
        put!(paused, :finished)
    end
    return _EdRun(ctx, task, paused, dir)
end

function _ed_next(run::_EdRun; seconds = 240)
    timer = Timer(_ -> close(run.paused), seconds)
    try
        return take!(run.paused)
    finally
        close(timer)
    end
end

# Resume the paused run and continue through every later pause until the run ends.
function _ed_finish!(run::_EdRun)
    debug_continue!(run.ctx)
    while true
        info = _ed_next(run)
        info === :finished && return fetch(run.task)
        debug_continue!(run.ctx)
    end
end

_ed_bytes(dir) = read(joinpath(dir, "columns.f64"))
_ed_manifest(dir) = JSON3.read(read(joinpath(dir, "manifest.json"), String))

# The columns as a matrix: row i is `[t, signals...]`.
function _ed_matrix(dir)
    n = Int(_ed_manifest(dir).time.n)
    ncols = length(_ed_manifest(dir).signals) + 1
    raw = reinterpret(Float64, _ed_bytes(dir))
    return reshape(collect(raw), n, ncols)
end

function _ed_replay(m::_EdModel, parent_dir; id = "replay", kwargs...)
    dir = mktempdir()
    result = replay_run(parent_dir; flat = m.flat, run_dir = dir, run_id = id, kwargs...)
    return result, dir
end

# The current value of a signal on the run task.
_ed_value(ctx, id) = with_paused(ctx) do s
    sym = get(s.lowered.vars, id, nothing)
    sym === nothing && (sym = s.lowered.params[id])
    return Float64(
        (ModelingToolkit.isparameter(sym) ?
         BGSim.getp(s.integ, sym) : BGSim.getu(s.integ, sym))(s.integ)
    )
end

# A model with a nonlinear algebraic loop that `mtkcompile` cannot eliminate: `y` has no
# closed form in `y + sin(y) = x`.
function _ed_inline_model(name, source; t_end = 1.0, points = 101)
    node = Dict{String,Any}(
        "id" => "n1", "name" => "Plant",
        "block" => Dict{String,Any}("inline" => Dict{String,Any}("source" => source)),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => Dict{String,Any}(), "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
    doc = Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[node], "connections" => Any[], "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "Rodas5P", "reltol" => 1.0e-8,
            "abstol" => 1.0e-10, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
    md = IR.parse_model(doc)
    return _EdModel(Compile.flatten(md), BGSim.RunSettings(md.settings), "", "")
end

const _ED_DC = _ed_model("dc-motor", "iconic.bgmodel.json")

# 0.2 s of drivetrain-kalman: 200 ticks of the 1 ms controller, output grid every 0.5 ms.
const _ED_KALMAN = _ed_model(
    "drivetrain-kalman", "drivetrain-kalman.bgmodel.json";
    settings = BGSim.RunSettings(
        t_start = 0.0, t_end = 0.2, solver = "auto", reltol = 1.0e-8, abstol = 1.0e-10,
        output = Dict("mode" => "points", "points" => 401), event_limit = 10000,
    ),
)

const _ED_LOOP = _ed_inline_model("Loop", """
@block Loop begin
    @parameters begin
        k::Real = 1.0
    end
    @variables begin
        x::Real = 1.0
        y::Real = 0.5
    end
    @outputs z::Real
    @equations begin
        ddt(x) ~ -k * x + y
        y + sin(y) ~ x
        z ~ x + y
    end
end
""")

@testset "edits, replay and branch (J4.4)" begin
    @testset "dc-motor: runTo 0.2, change R, continue; the replay is bit-identical (acceptance)" begin
        m = _ED_DC
        normal = _ed_bytes(_ed_normal(m))
        run = _ed_spawn(m; pause_on_entry = true)
        @test _ed_next(run).reason == "entry"
        debug_run_to!(run.ctx, 0.2)
        info = _ed_next(run)
        @test info.reason == "time"
        @test info.t == 0.2
        r0 = _ed_value(run.ctx, "Motor1/R")
        @test r0 == 2.0
        res = debug_set_parameter!(run.ctx, "Motor1/R", 3.0)
        @test res.ok && isempty(res.diagnostics)
        @test res.edit.t == 0.2 && res.edit.kind == "parameter"
        @test res.edit.target == "Motor1/R" && res.edit.value == 3.0
        @test _ed_value(run.ctx, "Motor1/R") == 3.0
        # The paused manifest already carries the edit.
        paused = _ed_manifest(run.dir)
        @test paused.status == "paused"
        @test length(paused.debug.edits) == 1
        @test paused.debug.edits[1].target == "Motor1/R"
        result = _ed_finish!(run)
        @test result.status == "done"
        parent = _ed_bytes(run.dir)
        @test parent != normal                    # the edit changed the run
        manifest = _ed_manifest(run.dir)
        @test length(manifest.debug.edits) == 1   # the final manifest has the edits
        @test manifest.debug.edits[1].value == 3.0

        replay, rdir = _ed_replay(m, run.dir)
        @test replay.status == "done"
        @test _ed_bytes(rdir) == parent           # bit-identical (acceptance)
        rm_ = _ed_manifest(rdir)
        @test rm_.parentRun == "ed"
        @test !haskey(rm_, :branchAt)
        @test length(rm_.debug.edits) == 1
        @test rm_.debug.edits[1].target == "Motor1/R" && rm_.debug.edits[1].t == 0.2
        @test rm_.status == "done"
        @test rm_.modelHash == manifest.modelHash
        # The replay is a run of its own: replaying the replay is the same again.
        again, adir = _ed_replay(m, rdir; id = "replay2")
        @test _ed_bytes(adir) == parent
        @test _ed_manifest(adir).parentRun == "replay"
    end

    @testset "replay rebuilds the model from model.json after the worker forgot it" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        write_run_model(run.dir, read(m.path, String), m.project)
        debug_run_to!(run.ctx, 0.2)
        _ed_next(run)
        @test debug_set_parameter!(run.ctx, "Motor1/L", 8.0e-4).ok
        _ed_finish!(run)
        dir = mktempdir()
        result = replay_run(run.dir; run_dir = dir, run_id = "from-file")
        @test result.status == "done"
        @test _ed_bytes(dir) == _ed_bytes(run.dir)
        @test_throws ArgumentError replay_run(
            mktempdir(); run_dir = mktempdir(), run_id = "none",
        )
    end

    @testset "a branch at 0.1 s matches the parent before 0.1, then pauses (acceptance)" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_run_to!(run.ctx, 0.2)
        _ed_next(run)
        @test debug_set_parameter!(run.ctx, "Motor1/R", 3.0).ok
        _ed_finish!(run)
        parent = _ed_matrix(run.dir)

        paused = Channel{Any}(Inf)
        ctx = DebugCtx(; on_paused = info -> put!(paused, info))
        bdir = mktempdir()
        task = Threads.@spawn branch_run(
            run.dir, 0.1; ctx = ctx, flat = m.flat, run_dir = bdir, run_id = "branch",
            cancel = _ed_cancel(),
        )
        info = take!(paused)
        @test info.reason == "time"
        @test info.t == 0.1
        @test info.runId == "branch"
        bm = _ed_manifest(bdir)
        @test bm.status == "paused"
        @test bm.parentRun == "ed"
        @test bm.branchAt == 0.1
        @test isempty(bm.debug.edits)              # the parent's edit (0.2) is after the branch
        # The rows on disk at the pause are the parent's rows, bit for bit.
        stream = reshape(collect(reinterpret(Float64, read(joinpath(bdir, "stream.f64")))),
            Int(size(parent, 2)), :)'
        k = count(<(0.1), parent[:, 1])
        @test size(stream, 1) >= k
        @test stream[1:k, :] == parent[1:k, :]
        @test stream[end, 1] < 0.1 + 1.0e-12
        # The branch continues as an ordinary debug session and ends.
        debug_continue!(ctx)
        result = fetch(task)
        @test result.status == "done"
        branch = _ed_matrix(bdir)
        @test branch[1:k, :] == parent[1:k, :]
        @test _ed_manifest(bdir).branchAt == 0.1
        # Without an edit the run after the pause is still the parent's before the edit.
        k2 = count(<(0.2), parent[:, 1])
        @test maximum(abs.(branch[1:k2, 2:end] .- parent[1:k2, 2:end])) < 1.0e-5
        # A replay of the branch's manifest reproduces the branch (its time stop is in `pauses`).
        again, adir = _ed_replay(m, bdir; id = "branch-replay")
        @test _ed_bytes(adir) == _ed_bytes(bdir)
        @test _ed_manifest(adir).parentRun == "branch"
        @test_throws ArgumentError branch_run(
            run.dir, 5.0; flat = m.flat, run_dir = mktempdir(), run_id = "late",
        )
    end

    @testset "a branch after an edit applies it" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_run_to!(run.ctx, 0.2)
        _ed_next(run)
        @test debug_set_parameter!(run.ctx, "Motor1/R", 3.0).ok
        _ed_finish!(run)
        parent = _ed_matrix(run.dir)

        paused = Channel{Any}(Inf)
        ctx = DebugCtx(; on_paused = info -> put!(paused, info))
        bdir = mktempdir()
        task = Threads.@spawn branch_run(
            run.dir, 0.3; ctx = ctx, flat = m.flat, run_dir = bdir, run_id = "branch",
            cancel = _ed_cancel(),
        )
        info = take!(paused)
        @test info.reason == "time" && info.t == 0.3
        bm = _ed_manifest(bdir)
        @test length(bm.debug.edits) == 1
        @test bm.debug.edits[1].target == "Motor1/R" && bm.debug.edits[1].t == 0.2
        @test _ed_value(ctx, "Motor1/R") == 3.0
        # A new edit in the branch (a different value) is recorded after the replayed one.
        res = debug_set_parameter!(ctx, "Motor1/R", 4.0)
        @test res.ok && res.edit.t == 0.3
        debug_continue!(ctx)
        @test fetch(task).status == "done"
        branch = _ed_matrix(bdir)
        k = count(<(0.3), parent[:, 1])
        @test branch[1:k, :] == parent[1:k, :]      # includes the replayed edit at 0.2
        bm = _ed_manifest(bdir)
        @test [e.value for e in bm.debug.edits] == [3.0, 4.0]
        @test branch != parent
        # The branch's manifest reproduces the branch, both edits included.
        again, adir = _ed_replay(m, bdir; id = "branch-replay")
        @test _ed_bytes(adir) == _ed_bytes(bdir)
    end

    @testset "setState: a dc-motor state, bit-identical replay" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_step!(run.ctx, "tick")
        info = _ed_next(run)
        @test info.reason == "step"
        w = _ed_value(run.ctx, "Motor1/rotor/w")
        res = debug_set_state!(run.ctx, "Motor1/rotor/w", w + 7.5)
        @test res.ok && res.edit.kind == "state" && res.edit.target == "Motor1/rotor/w"
        @test _ed_value(run.ctx, "Motor1/rotor/w") == w + 7.5
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        @test parent != _ed_bytes(_ed_normal(m))
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent
        # A dc-motor alias and an observed signal are not differential states (E402).
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        bad = debug_set_state!(run.ctx, "Motor1/i", 1.0)
        @test !bad.ok && bad.edit === nothing
        @test bad.diagnostics[1].code == "E402"
        @test occursin("not a differential state", bad.diagnostics[1].message)
        @test !isempty(bad.diagnostics[1].hint)
        @test isempty(run.ctx.edits)
        debug_cancel!(run.ctx)
        _ed_next(run)
    end

    @testset "setState gives E402 on a nonlinear algebraic loop (checked)" begin
        m = _ED_LOOP
        lowered = BGSim.lower_model(m.flat; t_start = 0.0, t_end = 1.0).model
        # The compiled system really keeps an algebraic equation that depends on the state.
        @test lowered.algebraic
        sys = lowered.system
        algebraic = [
            eq for eq in ModelingToolkit.equations(sys) if begin
                names = Set{String}()
                Compile._collect_differentials!(names, eq.lhs)
                isempty(names)
            end
        ]
        @test length(algebraic) == 1
        @test any(u -> BGSim.signal_name(u) == "Plant/x", ModelingToolkit.unknowns(sys))
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        bad = debug_set_state!(run.ctx, "Plant/x", 2.0)
        @test !bad.ok && bad.edit === nothing
        d = bad.diagnostics[1]
        @test d.code == "E402" && d.severity == "error"
        @test occursin("algebraic", d.message)
        @test occursin("parameter", d.hint)
        @test isempty(run.ctx.edits)
        # A parameter of the same model can be changed (D24), also on a DAE.
        ok = debug_set_parameter!(run.ctx, "Plant/k", 2.0)
        @test ok.ok
        @test _ed_value(run.ctx, "Plant/x") == 1.0
        _ed_finish!(run)
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == _ed_bytes(run.dir)
    end

    @testset "drivetrain-kalman: setState on a plant state, bit-identical replay" begin
        m = _ED_KALMAN
        # The plant has an algebraic equation (a dummy derivative) that does not depend on any
        # differential state, so a state edit keeps the system consistent.
        lowered = BGSim.lower_model(m.flat; t_start = 0.0, t_end = 0.2).model
        @test lowered.algebraic
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_step!(run.ctx, "tick")
        info = _ed_next(run)
        @test info.reason == "step" && info.tick == 1
        q = _ed_value(run.ctx, "C1/q")
        res = debug_set_state!(run.ctx, "C1/q", q + 1.0e-3)
        @test res.ok
        @test res.edit.t == info.t && res.edit.kind == "state"
        @test _ed_value(run.ctx, "C1/q") == q + 1.0e-3
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        @test parent != _ed_bytes(_ed_normal(m))
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent
        # A held discrete output of the controller and an observed signal are refused.
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        @test debug_set_state!(run.ctx, "LQG/xhat[1]", 1.0).diagnostics[1].code == "E402"
        debug_cancel!(run.ctx)
        _ed_next(run)
    end

    @testset "edits at a tick, a solver-step and a pause-request pause replay bit-identically" begin
        m = _ED_KALMAN
        # tick pause
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_step!(run.ctx, "tick")
        _ed_next(run)
        debug_step!(run.ctx, "tick")
        info = _ed_next(run)
        @test info.reason == "step" && info.tick == 2
        res = debug_set_parameter!(run.ctx, "D1/r", 0.9 * _ed_value(run.ctx, "D1/r"))
        @test res.ok && endswith(res.edit.var"$comment", "at=target")
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        @test parent != _ed_bytes(_ed_normal(m))
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent

        # solver-step pauses, two edits (a parameter and a state) at different steps
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        for _ in 1:3
            debug_step!(run.ctx, "solverStep")
            @test _ed_next(run).reason == "step"
        end
        res = debug_set_parameter!(run.ctx, "C2/c", 1.1 * _ed_value(run.ctx, "C2/c"))
        @test res.ok && endswith(res.edit.var"$comment", "at=step")
        for _ in 1:4
            debug_step!(run.ctx, "solverStep")
            _ed_next(run)
        end
        @test debug_set_state!(run.ctx, "C3/q", _ed_value(run.ctx, "C3/q") + 1.0e-4).ok
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent
        @test length(_ed_manifest(rdir).debug.edits) == 2

        # a pause request (honoured at the first checkpoint after the resume), then an edit
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        for _ in 1:2
            debug_step!(run.ctx, "tick")
            _ed_next(run)
        end
        debug_continue!(run.ctx)
        debug_pause!(run.ctx)
        info = _ed_next(run)
        @test info !== :finished && info.reason == "pause"
        @test debug_set_parameter!(run.ctx, "D2/r", 1.2 * _ed_value(run.ctx, "D2/r")).ok
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        @test parent != _ed_bytes(_ed_normal(m))
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent

        # a time pause (runTo) next to the ticks
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_run_to!(run.ctx, 0.0503)
        info = _ed_next(run)
        @test info.reason == "time"
        @test debug_set_parameter!(run.ctx, "D3/r", 1.3 * _ed_value(run.ctx, "D3/r")).ok
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent
    end

    @testset "an edit at an entry pause replays bit-identically" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        res = debug_set_parameter!(run.ctx, "Motor1/J", 2.0e-5)
        @test res.ok && endswith(res.edit.var"$comment", "at=entry")
        _ed_finish!(run)
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == _ed_bytes(run.dir)
    end

    @testset "an edit at a statement pause replays bit-identically" begin
        m = _ED_KALMAN
        source = read(joinpath(m.project, "library", "LQGController.jl"), String)
        line = first(i for (i, l) in enumerate(split(source, '\n')) if occursin("xhat = xhat + L", l))
        bp = Dict{String,Any}(
            "id" => "bp1", "enabled" => true, "kind" => "line",
            "line" => Dict{String,Any}("ref" => "project:LQGController", "line" => line, "path" => nothing),
            "hitCount" => 5,
        )
        run = _ed_spawn(m; breakpoints = [bp])
        info = _ed_next(run)
        @test info.reason == "breakpoint" && info.location.range.line == line
        res = debug_set_parameter!(run.ctx, "D1/r", 1.25 * _ed_value(run.ctx, "D1/r"))
        @test res.ok && endswith(res.edit.var"$comment", "at=statement")
        _ed_finish!(run)
        parent = _ed_bytes(run.dir)
        @test parent != _ed_bytes(_ed_normal(m))
        _, rdir = _ed_replay(m, run.dir)
        @test _ed_bytes(rdir) == parent
    end

    @testset "an edit at a watch pause replays within the solver tolerances" begin
        m = _ED_DC
        watch = Dict{String,Any}(
            "id" => "w1", "enabled" => true, "kind" => "watch",
            "watch" => Dict{String,Any}("expr" => "s\"Motor1/i\" > 5.0", "context" => nothing),
            "hitCount" => nothing,
        )
        run = _ed_spawn(m; breakpoints = [watch])
        info = _ed_next(run)
        @test info.reason == "breakpoint" && info.breakpointId == "w1"
        @test debug_set_parameter!(run.ctx, "Motor1/R", 2.5).ok
        _ed_finish!(run)
        parent = _ed_matrix(run.dir)
        _, rdir = _ed_replay(m, run.dir)
        replay = _ed_matrix(rdir)
        @test size(replay) == size(parent)
        @test replay[:, 1] == parent[:, 1]
        # Not bit-identical in general (the watch pause is a located crossing, not a step end of
        # the replay), but equal within the run's tolerances (reltol 1e-6, abstol 1e-8).
        scale = maximum(abs, parent[:, 2:end]; dims = 1)
        err = maximum(abs.(replay[:, 2:end] .- parent[:, 2:end]) ./ max.(scale, 1.0e-8))
        @test err < 1.0e-5
        println("  watch-pause replay: max relative column error = ", err)
    end

    @testset "refused edits leave no edit behind" begin
        m = _ED_KALMAN
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        unknown = debug_set_parameter!(run.ctx, "D1/nope", 1.0)
        @test !unknown.ok && unknown.edit === nothing
        @test unknown.diagnostics[1].code == "E003"
        @test occursin("D1/nope", unknown.diagnostics[1].message)
        @test !isempty(unknown.diagnostics[1].hint)
        held = debug_set_parameter!(run.ctx, "LQG/xhat[1]", 1.0)
        @test !held.ok && held.diagnostics[1].code == "E402"
        @test occursin("read-only", held.diagnostics[1].message)
        signal = debug_set_parameter!(run.ctx, "C1/q", 1.0)    # a state is not a parameter
        @test !signal.ok && signal.diagnostics[1].code == "E003"
        @test occursin("setState", signal.diagnostics[1].hint)
        for bad in (NaN, Inf, -Inf)
            r = debug_set_parameter!(run.ctx, "D1/r", bad)
            @test !r.ok && r.diagnostics[1].code == "E004"
        end
        @test !debug_set_state!(run.ctx, "C1/q", NaN).ok
        @test debug_set_state!(run.ctx, "No/such", 1.0).diagnostics[1].code == "E003"
        @test isempty(run.ctx.edits)
        @test isempty(_ed_manifest(run.dir).debug.edits)
        debug_cancel!(run.ctx)
        _ed_next(run)
    end

    @testset "edits while the run is not paused raise DebugStateError" begin
        m = _ED_DC
        # before the run exists
        ctx = DebugCtx()
        @test_throws DebugStateError debug_set_parameter!(ctx, "Motor1/R", 3.0)
        @test_throws DebugStateError debug_set_state!(ctx, "Motor1/rotor/w", 1.0)
        # while it runs (a slow cancel callback keeps it running)
        run = _ed_spawn(m; cancel = () -> (sleep(0.001); false))
        t0 = time()
        while run.ctx.state[] != BGSim._STATE_RUNNING && time() - t0 < 60
            sleep(0.01)
        end
        @test_throws DebugStateError debug_set_parameter!(run.ctx, "Motor1/R", 3.0)
        @test_throws DebugStateError debug_set_state!(run.ctx, "Motor1/rotor/w", 1.0)
        debug_cancel!(run.ctx)
        while _ed_next(run) !== :finished
        end
        # after it finished
        @test_throws DebugStateError debug_set_parameter!(run.ctx, "Motor1/R", 3.0)
        @test isempty(run.ctx.edits)
    end

    @testset "a replay never pauses and needs a fresh context" begin
        m = _ED_DC
        run = _ed_spawn(m; pause_on_entry = true)
        _ed_next(run)
        debug_run_to!(run.ctx, 0.2)
        _ed_next(run)
        @test debug_set_parameter!(run.ctx, "Motor1/R", 3.0).ok
        _ed_finish!(run)
        parent = BGSim.load_parent_run(run.dir)
        @test length(parent.edits) == 1 && parent.edits[1].at === :step
        @test [p.reason for p in parent.pauses] == ["entry", "time"]
        ctx = BGSim.prepare_replay!(DebugCtx(), parent)
        @test_throws ArgumentError BGSim.prepare_replay!(ctx, parent)
        used = DebugCtx()
        simulate(m.flat; run_dir = mktempdir(), run_id = "x", settings = m.settings, debug = used)
        @test_throws ArgumentError BGSim.prepare_replay!(used, parent)
        # A model that is not the parent's (a parameter the edit names is missing) fails loudly.
        other = _ED_LOOP
        @test_throws ErrorException replay_run(
            run.dir; flat = other.flat, run_dir = mktempdir(), run_id = "wrong",
            settings = other.settings,
        )
    end
end
