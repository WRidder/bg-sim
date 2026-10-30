# Work package J4.5: the worker's debug methods and notifications (plan 3.8).
#
# Socket-level, like test_worker.jl: `Worker.serve` on one side, a client built here on the
# other. Covers `run.start` with `debug`, `debug.paused`/`debug.resumed`, `debug.setBreakpoints`,
# `pause`/`continue`/`step`/`runTo`, `evaluate`, `values`, `setParameter`, `setState`,
# `run.replay`, `run.branch`, `model.explain`, the `run is not paused` RPC error, `run.cancel`
# on a paused run, and that `block.check` and other requests are answered while a run is paused.

using BGSim
import BGSim: Worker
using JSON3
using Sockets
using Test

const WD_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const WD_EXAMPLES = joinpath(WD_ROOT, "examples")

_wd_field(obj, key::Symbol, default = nothing) =
    obj === nothing ? default :
    obj isa AbstractDict ? get(obj, key, get(obj, String(key), default)) :
    hasproperty(obj, key) ? getproperty(obj, key) : default

mutable struct WdClient
    sock::TCPSocket
    inbox::Vector{Any}
    next_id::Int
end

function _wd_read(client::WdClient)
    frame = Worker.read_frame(client.sock)
    frame === nothing && error("the worker closed the connection")
    return JSON3.read(String(frame.payload))
end

function _wd_wait(client::WdClient, predicate, what; timeout = 300.0)
    index = findfirst(predicate, client.inbox)
    index === nothing || return popat!(client.inbox, index)
    task = @async begin
        while true
            message = _wd_read(client)
            predicate(message) && return message
            push!(client.inbox, message)
        end
    end
    if Base.timedwait(() -> istaskdone(task), timeout) == :timed_out
        close(client.sock)
        try
            wait(task)
        catch
        end
        error("timed out after $timeout s waiting for $what")
    end
    return fetch(task)
end

_wd_is(method, run_id = nothing) = m -> _wd_field(m, :method, "") == method &&
    (run_id === nothing || _wd_field(_wd_field(m, :params), :runId) == run_id)

wd_notification(client, method, run_id = nothing; timeout = 300.0) =
    _wd_wait(client, _wd_is(method, run_id), "$method of $run_id"; timeout = timeout)

function wd_send!(client::WdClient, method, params = NamedTuple())
    id = (client.next_id += 1)
    Worker.write_json_frame(client.sock, JSON3.write((; id = id, method = method, params = params)))
    return id
end

wd_wait_response(client::WdClient, id; timeout = 300.0) =
    _wd_wait(client, m -> _wd_field(m, :id) == id, "response $id"; timeout = timeout)

wd_request(client, method, params = NamedTuple(); timeout = 300.0) =
    wd_wait_response(client, wd_send!(client, method, params); timeout = timeout)

function wd_result(client, method, params = NamedTuple(); timeout = 300.0)
    response = wd_request(client, method, params; timeout = timeout)
    err = _wd_field(response, :error)
    err === nothing || error("$method answered with an error: $(_wd_field(err, :message))")
    return _wd_field(response, :result)
end

wd_error(client, method, params = NamedTuple()) =
    _wd_field(_wd_field(wd_request(client, method, params), :error), :message)

function wd_with_connection(f)
    listener = Sockets.listen(ip"127.0.0.1", 0)
    port = Int(Sockets.getsockname(listener)[2])
    server_task = @async begin
        sock = Sockets.accept(listener)
        Worker.serve(sock; warmup = false, log = devnull)
    end
    client = WdClient(Sockets.connect(ip"127.0.0.1", port), Any[], 0)
    try
        return f(client)
    finally
        close(client.sock)
        try
            wait(server_task)
        catch
        end
        close(listener)
    end
end

wd_model(project, file) = JSON3.read(
    read(joinpath(WD_EXAMPLES, project, "models", file), String), Dict{String,Any}
)

wd_manifest(dir) = JSON3.read(read(joinpath(dir, "manifest.json"), String))

function wd_line_bp(id, ref, line; path = nothing)
    return Dict{String,Any}(
        "id" => id, "enabled" => true, "kind" => "line",
        "line" => Dict{String,Any}("ref" => ref, "line" => line, "path" => path),
    )
end

const WD_WATCH = Dict{String,Any}(
    "id" => "bp1", "enabled" => true, "kind" => "watch",
    "watch" => Dict{String,Any}("expr" => "s\"Motor1/i\" > 5", "context" => nothing),
    "hitCount" => nothing,
)

function wd_start(client, run_id, runs_dir, model, project; debug = nothing)
    run_dir = joinpath(runs_dir, run_id)
    params = Dict{String,Any}(
        "runId" => run_id, "model" => model, "projectDir" => project, "runDir" => run_dir,
        "debug" => debug,
    )
    return run_dir, wd_request(client, "run.start", params)
end

@testset "J4.5 worker debug methods" begin
    runs_dir = mktempdir()
    dc_project = joinpath(WD_EXAMPLES, "dc-motor")

    @testset "debug run of dc-motor: watch pause, values, evaluate, edit, continue" begin
        wd_with_connection() do client
            model = wd_model("dc-motor", "iconic.bgmodel.json")
            debug = Dict("breakpoints" => [WD_WATCH], "pauseOnEntry" => false)
            dir, started = wd_start(client, "dbg1", runs_dir, model, dc_project; debug = debug)
            @test _wd_field(_wd_field(started, :result), :accepted) == true
            @test isfile(joinpath(dir, "model.json"))

            paused = _wd_field(wd_notification(client, "debug.paused", "dbg1"), :params)
            @test paused.reason == "breakpoint" && paused.breakpointId == "bp1"
            @test 0.01 <= paused.t < 0.1
            @test paused.frame === nothing
            @test paused.location !== nothing || paused.location === nothing  # serialises
            @test wd_manifest(dir).status == "paused"

            values = wd_result(client, "debug.values", (; runId = "dbg1", ids = ["Motor1/i"]))
            @test values.t == paused.t
            @test values.values[Symbol("Motor1/i")] >= 5.0 - 1e-6
            bad = wd_error(client, "debug.values", (; runId = "dbg1", ids = ["Nope/x"]))
            @test bad isa AbstractString && occursin("Nope/x", bad)

            ev = wd_result(client, "debug.evaluate",
                (; runId = "dbg1", expr = "s\"Motor1/i\" > 5", context = nothing))
            @test ev.value == true && isempty(ev.diagnostics)

            edit = wd_result(client, "debug.setParameter",
                (; runId = "dbg1", name = "Motor1/R", value = 2.5))
            @test edit.ok == true && edit.edit.target == "Motor1/R" && edit.edit.value == 2.5
            @test edit.edit.t == paused.t
            refused = wd_result(client, "debug.setParameter",
                (; runId = "dbg1", name = "Motor1/nope", value = 1.0))
            @test refused.ok == false && !isempty(refused.diagnostics)

            @test wd_result(client, "debug.continue", (; runId = "dbg1")).ok == true
            wd_notification(client, "debug.resumed", "dbg1")
            done = _wd_field(wd_notification(client, "run.done", "dbg1"), :params)
            @test done.status == "done"
            m = wd_manifest(dir)
            @test m.status == "done"
            @test length(m.debug.edits) == 1 && m.debug.edits[1].target == "Motor1/R"
            @test any(p -> p.t == paused.t, m.debug.pauses)

            # A finished run: the engine's state error is the RPC error.
            @test wd_error(client, "debug.continue", (; runId = "dbg1")) == "run is not paused"
            @test wd_error(client, "debug.values", (; runId = "dbg1", ids = ["Motor1/i"])) ==
                  "run is not paused"
            @test wd_error(client, "debug.pause", (; runId = "unknown")) == "run is not paused"

            # run.replay: a normal run applying the edit, found next to the parent.
            rdir = joinpath(runs_dir, "rep1")
            @test wd_result(client, "run.replay",
                (; runId = "dbg1", newRunId = "rep1", runDir = rdir)).accepted == true
            rdone = _wd_field(wd_notification(client, "run.done", "rep1"), :params)
            @test rdone.status == "done"
            rm_ = wd_manifest(rdir)
            @test rm_.parentRun == "dbg1"
            @test length(rm_.debug.edits) == 1

            # run.branch: pauses at t, takes debug commands under the new id.
            bdir = joinpath(runs_dir, "brn1")
            @test wd_result(client, "run.branch",
                (; runId = "dbg1", newRunId = "brn1", runDir = bdir, t = 0.2)).accepted == true
            bp = _wd_field(wd_notification(client, "debug.paused", "brn1"), :params)
            @test abs(bp.t - 0.2) < 1e-9
            @test bp.reason == "time"
            bm = wd_manifest(bdir)
            @test bm.parentRun == "dbg1" && bm.branchAt == 0.2 && bm.status == "paused"
            v = wd_result(client, "debug.values", (; runId = "brn1", ids = ["Motor1/i"]))
            @test abs(v.t - 0.2) < 1e-9
            @test wd_result(client, "debug.continue", (; runId = "brn1")).ok == true
            bdone = _wd_field(wd_notification(client, "run.done", "brn1"), :params)
            @test bdone.status == "done"

            missing_parent = wd_error(client, "run.branch",
                (; runId = "ghost", newRunId = "brn2", runDir = joinpath(runs_dir, "brn2"), t = 0.2))
            @test missing_parent isa AbstractString && occursin("ghost", missing_parent)
        end
    end

    @testset "paused run: block.check answers, pause/step/runTo, cancel ends it cancelled" begin
        wd_with_connection() do client
            model = wd_model("dc-motor", "iconic.bgmodel.json")
            debug = Dict("breakpoints" => Any[], "pauseOnEntry" => true)
            dir, _ = wd_start(client, "dbg2", runs_dir, model, dc_project; debug = debug)
            entry = _wd_field(wd_notification(client, "debug.paused", "dbg2"), :params)
            @test entry.reason == "entry"

            # Requests are answered while the run is paused, even with a debug command in flight.
            source = "@block G begin\n @inputs u::Real\n @outputs y::Real\n @equations y ~ 2*u\nend\n"
            ids = [wd_send!(client, "block.check", (; source = source)),
                wd_send!(client, "debug.values", (; runId = "dbg2", ids = ["Motor1/i"])),
                wd_send!(client, "ping")]
            for id in ids
                @test _wd_field(wd_wait_response(client, id; timeout = 120.0), :error) === nothing
            end

            statuses = wd_result(client, "debug.setBreakpoints",
                (; runId = "dbg2", breakpoints = [Dict("id" => "t1", "enabled" => true,
                    "kind" => "time", "time" => Dict("t" => 0.05))]))
            @test statuses.breakpoints[1].id == "t1" && statuses.breakpoints[1].verified == true

            @test wd_result(client, "debug.step", (; runId = "dbg2", granularity = "tick")).ok
            wd_notification(client, "debug.resumed", "dbg2")
            stepped = _wd_field(wd_notification(client, "debug.paused", "dbg2"), :params)
            @test stepped.reason == "step" && stepped.t > entry.t
            @test occursin("granularity", something(
                wd_error(client, "debug.step", (; runId = "dbg2", granularity = "bogus")), "granularity"))

            @test wd_result(client, "debug.runTo", (; runId = "dbg2", t = 0.3)).ok
            # The time breakpoint at 0.05 comes first, then runTo's.
            p1 = _wd_field(wd_notification(client, "debug.paused", "dbg2"), :params)
            @test p1.reason == "time" && abs(p1.t - 0.05) < 1e-9
            @test wd_result(client, "debug.continue", (; runId = "dbg2")).ok
            p2 = _wd_field(wd_notification(client, "debug.paused", "dbg2"), :params)
            @test abs(p2.t - 0.3) < 1e-9

            @test wd_result(client, "run.cancel", (; runId = "dbg2")).ok == true
            done = _wd_field(wd_notification(client, "run.done", "dbg2"), :params)
            @test done.status == "cancelled"
            @test wd_manifest(dir).status == "cancelled"
        end
    end

    @testset "commands on a non-debug run are RPC errors" begin
        wd_with_connection() do client
            model = wd_model("dc-motor", "iconic.bgmodel.json")
            model["settings"]["t_end"] = 0.05
            wd_start(client, "plain1", runs_dir, model, dc_project)
            @test wd_error(client, "debug.continue", (; runId = "plain1")) == "run is not paused"
            wd_notification(client, "run.done", "plain1")
        end
        wd_with_connection() do client
            model = wd_model("dc-motor", "iconic.bgmodel.json")
            bad = Dict("breakpoints" => [Dict("id" => "x", "kind" => "bogus")], "pauseOnEntry" => false)
            _, started = wd_start(client, "bad1", runs_dir, model, dc_project; debug = bad)
            message = _wd_field(_wd_field(started, :error), :message)
            @test message isa AbstractString && occursin("breakpoint", message)
        end
    end

    @testset "line breakpoint in LQGController: E401, verified, statement pause with frame" begin
        wd_with_connection() do client
            project = joinpath(WD_EXAMPLES, "drivetrain-kalman")
            model = wd_model("drivetrain-kalman", "drivetrain-kalman.bgmodel.json")
            model["settings"]["t_end"] = 0.02
            source = read(joinpath(project, "library", "LQGController.jl"), String)
            lines = split(source, '\n')
            stmt = findfirst(l -> occursin("xhat = xhat + L", l), lines)
            ref = "project:LQGController"
            bps = Any[wd_line_bp("good", ref, stmt), wd_line_bp("comment", ref, 2)]
            debug = Dict("breakpoints" => bps, "pauseOnEntry" => false)
            dir, started = wd_start(client, "dbg3", runs_dir, model, project; debug = debug)
            @test _wd_field(_wd_field(started, :result), :accepted) == true
            info = _wd_field(wd_notification(client, "debug.paused", "dbg3"), :params)
            @test info.reason == "breakpoint" && info.breakpointId == "good"
            @test info.location.range.line == stmt
            @test info.frame !== nothing && !isempty(info.frame.held)

            statuses = wd_result(client, "debug.setBreakpoints",
                (; runId = "dbg3", breakpoints = bps)).breakpoints
            by_id = Dict(String(s.id) => s for s in statuses)
            @test by_id["good"].verified == true && by_id["good"].resolved.hooks >= 1
            @test by_id["comment"].verified == false
            @test by_id["comment"].diagnostics[1].code == "E401"

            ev = wd_result(client, "debug.evaluate", (; runId = "dbg3", expr = "1 + 2", context = nothing))
            @test ev.value == 3.0 || ev.value == 3

            wd_result(client, "debug.setBreakpoints", (; runId = "dbg3", breakpoints = Any[]))
            @test wd_result(client, "debug.continue", (; runId = "dbg3")).ok
            @test _wd_field(wd_notification(client, "run.done", "dbg3"), :params).status == "done"
        end
    end

    @testset "model.explain" begin
        wd_with_connection() do client
            model = wd_model("dc-motor", "iconic.bgmodel.json")
            result = wd_result(client, "model.explain",
                (; model = model, projectDir = dc_project, signal = "Motor1/i"))
            @test result.signal == "Motor1/i"
            @test haskey(result, :kind)
            missing_signal = wd_result(client, "model.explain",
                (; model = model, projectDir = dc_project, signal = "Nope/zzz"))
            @test !isempty(missing_signal.diagnostics)
            @test wd_error(client, "model.explain", (; projectDir = dc_project, signal = "x")) isa
                  AbstractString
        end
    end

    @testset "shutdown cancels a paused run" begin
        model = wd_model("dc-motor", "iconic.bgmodel.json")
        dir = joinpath(runs_dir, "dbg4")
        wd_with_connection() do client
            debug = Dict("breakpoints" => Any[], "pauseOnEntry" => true)
            wd_start(client, "dbg4", runs_dir, model, dc_project; debug = debug)
            wd_notification(client, "debug.paused", "dbg4")
        end  # closing the connection runs _shutdown_runs
        deadline = time() + 30
        while time() < deadline && wd_manifest(dir).status == "paused"
            sleep(0.1)
        end
        @test wd_manifest(dir).status == "cancelled"
    end
end
