# The worker TCP server (plan section 3.6).
#
# The backend listens on a random localhost port, starts this process with
# `BGSIM_PORT=<port>` and the worker connects back and serves length-prefixed frames
# (`worker/protocol.jl`). The methods are the plan 3.6 set:
#
#   ping, catalog.get, block.check, model.check, run.start, run.cancel, cache.clear
#
# and the notifications are `run.phase`, `run.progress`, `run.done` and `log`. Every request
# is handled on its own Julia task, so `block.check` is served while a run is simulating; the
# run task yields at every integrator step (through its cancellation callback), which lets
# requests interleave even on a single thread. Socket writes are serialized by one lock, so
# concurrent answers cannot interleave inside a frame.
#
# `run.start` parses and flattens the model and writes the `status: "running"` manifest with
# the full signal list *before* it answers `{"accepted": true}` (REQ-1); the run itself then
# continues on its own task and streams `run.phase`/`run.progress`/`run.done`.
#
# stdout is never written: all logging goes to stderr (the backend captures it in
# `backend/logs/worker.log`). stdout/stderr are not protocol.
#
# Entry point (spawned by the backend, plan section 6):
#
#     julia --project=julia/BGSim --threads=2 -e "using BGSim; BGSim.Worker.main()"

module Worker

using Sockets

import JSON3
import PrecompileTools: @setup_workload, @compile_workload

import ..BGSim
import ..BGSim: IR, Compile, Library, RunSettings, simulate, diag, to_namedtuple,
    clear_compile_cache!

include("protocol.jl")

const BUILD_VERSION = "0.1.0"
const DEFAULT_BLOCK_REF = "inline:x"

#: At most 20 `run.progress` notifications per second (plan 3.6). `simulate` already reports
#: at a 100 ms cadence; this is the protocol-level guarantee if that cadence changes.
const PROGRESS_MIN_INTERVAL_NS = 50_000_000

# ---------------------------------------------------------------------------------------
# Logging (stderr only)
# ---------------------------------------------------------------------------------------

"Log one line to `io` (normally stderr, the backend's worker log). Never writes stdout."
function log_line(io::IO, args...)
    println(io, "[BGSim.Worker] ", args...)
    flush(io)
    return nothing
end

log_line(args...) = log_line(stderr, args...)

"""
    version_string()

The BGSim package version, or the M0.4 build stamp when the package has no version.
"""
function version_string()
    version = try
        pkgversion(parentmodule(@__MODULE__))
    catch
        nothing
    end
    return version === nothing ? BUILD_VERSION : string(version)
end

# ---------------------------------------------------------------------------------------
# Protocol values
# ---------------------------------------------------------------------------------------

"""
    RpcError(message; diagnostics = [])

A request-level error: the worker answers `{"id": id, "error": {"message", "diagnostics"}}`
exactly as the plan 3.6 contract prescribes. `diagnostics` entries are already in the plan
3.4 JSON shape.
"""
struct RpcError <: Exception
    message::String
    diagnostics::Vector{Any}
end

RpcError(message::AbstractString) = RpcError(String(message), Any[])

Base.showerror(io::IO, err::RpcError) = print(io, err.message)

"""
    Deferred(result, after)

A request answer that must reach the socket *before* `after()` runs. `run.start` uses it so
`{"accepted": true}` is written before the first run notification (plan 3.6).
"""
struct Deferred
    result::Any
    after::Function
end

"A successful response: `{ \"id\": id, \"result\": result }` (plan 3.6)."
result_message(id, result) = (; id = id, result = result)

"An error response: `{ \"id\": id, \"error\": { \"message\", \"diagnostics\" } }` (plan 3.6)."
function error_message(id, message::AbstractString; diagnostics = Any[])
    return (; id = id, error = (; message = String(message), diagnostics = diagnostics))
end

"One notification: `{ \"method\": ..., \"params\": ... }` (no `id`, plan 3.6)."
notification_message(method::AbstractString, params) = (; method = String(method), params = params)

# ---------------------------------------------------------------------------------------
# JSON helpers (JSON3.Object and plain Dict both work)
# ---------------------------------------------------------------------------------------

function _jsonfield(obj, key::Symbol, default = nothing)
    obj === nothing && return default
    if obj isa AbstractDict
        haskey(obj, key) && return obj[key]
        haskey(obj, String(key)) && return obj[String(key)]
        return default
    end
    hasproperty(obj, key) && return getproperty(obj, key)
    return default
end

function _required_string(params, key::Symbol, method::AbstractString)
    value = _jsonfield(params, key, nothing)
    value === nothing && throw(RpcError("`$method` requires the `$key` parameter"))
    value isa AbstractString ||
        throw(RpcError("`$method` parameter `$key` must be a string"))
    return String(value)
end

function _optional_string(params, key::Symbol, default::Union{Nothing,String} = nothing)
    value = _jsonfield(params, key, nothing)
    value === nothing && return default
    value isa AbstractString ||
        throw(RpcError("parameter `$key` must be a string or null"))
    return String(value)
end

# ---------------------------------------------------------------------------------------
# The method results (converted to the contract shapes here, once)
# ---------------------------------------------------------------------------------------

function _block_check_result(source::AbstractString, ref::AbstractString)
    result = Compile.check_block_source(source; ref = ref)
    return (
        diagnostics = Any[to_namedtuple(d) for d in result.diagnostics],
        interface = result.interface,
    )
end

function _model_check_result(md::IR.ModelDoc; project_dir = nothing)
    result = Compile.model_check(md; project_dir = project_dir)
    return (
        diagnostics = Any[to_namedtuple(d) for d in result.diagnostics],
        domains = result.domains,
        causality = result.causality,
        frames = result.frames,
        multibond = result.multibond,
        unitFactors = result.unitFactors,
        signals = result.signals,
        stats = result.stats,
    )
end

function _parse_model_document(value, method::AbstractString)
    value isa AbstractDict ||
        throw(RpcError("`$method` requires a model document object"))
    try
        return IR.parse_model(value)
    catch err
        err isa ArgumentError || rethrow()
        throw(RpcError("`$method`: " * err.msg))
    end
end

function _run_settings(md::IR.ModelDoc)
    try
        return RunSettings(md.settings)
    catch err
        message = "invalid run settings: " * sprint(showerror, err)
        throw(RpcError(message, Any[to_namedtuple(diag("E901", message))]))
    end
end

function _zero_run_stats(flat)
    return (
        compile_s = 0.0,
        sim_s = 0.0,
        steps = 0,
        events = 0,
        states = Int(flat.stats.states),
        equations = Int(flat.stats.equations),
    )
end

"""Write the `status: "running"` manifest with the full signal list (REQ-1).

`run.start` calls this before it answers `accepted`, using the same document shape as the
recorder's `open_recorder`; `simulate` rewrites it (still `running`) a moment later and then
with the final status.
"""
function _write_running_manifest(flat, settings::RunSettings, run_id::AbstractString,
    run_dir::AbstractString, model_hash::AbstractString)
    mkpath(run_dir)
    manifest = BGSim._manifest(
        id = run_id,
        model = flat.name,
        model_hash = model_hash,
        status = "running",
        settings = to_namedtuple(settings),
        stats = _zero_run_stats(flat),
        signals = BGSim.signal_entries(flat.signals),
        time = (n = 0, t0 = settings.t_start, t1 = settings.t_end),
        diagnostics = BGSim._diag_entries(flat.diagnostics),
    )
    BGSim.write_manifest_atomic(joinpath(String(run_dir), "manifest.json"), manifest)
    return manifest
end

function _write_failed_manifest(flat, settings::RunSettings, run_id::AbstractString,
    run_dir::AbstractString, model_hash::AbstractString, diagnostics)
    manifest = BGSim._manifest(
        id = run_id,
        model = flat.name,
        model_hash = model_hash,
        status = "failed",
        settings = to_namedtuple(settings),
        stats = _zero_run_stats(flat),
        signals = BGSim.signal_entries(flat.signals),
        time = (n = 0, t0 = settings.t_start, t1 = settings.t_end),
        diagnostics = BGSim._diag_entries(diagnostics),
    )
    BGSim.write_manifest_atomic(joinpath(String(run_dir), "manifest.json"), manifest)
    return manifest
end

# The precompile workload and the start-up warm-up live next to the server. They need the
# result helpers above, so they are included after them.
include("warmup.jl")

# ---------------------------------------------------------------------------------------
# The connection
# ---------------------------------------------------------------------------------------

mutable struct Connection
    sock::TCPSocket
    lock::ReentrantLock
    log::IO
end

Connection(sock::TCPSocket, log::IO = stderr) = Connection(sock, ReentrantLock(), log)

"Write one JSON message under the connection's lock (frames never interleave)."
function send!(conn::Connection, message)
    lock(conn.lock) do
        write_json_frame(conn.sock, JSON3.write(message))
    end
    return nothing
end

"Send one notification; a dead backend is not an error of the run."
function notify!(conn::Connection, method::AbstractString, params)
    try
        send!(conn, notification_message(method, params))
    catch err
        log_line(conn.log, "could not send ", method, ": ", sprint(showerror, err))
    end
    return nothing
end

"Log to stderr and tell the backend about it (`log` notification, plan 3.6)."
function log_event(conn::Connection, level::AbstractString, message::AbstractString)
    log_line(conn.log, level, ": ", message)
    notify!(conn, "log", (; level = String(level), message = String(message)))
    return nothing
end

# ---------------------------------------------------------------------------------------
# The run registry
# ---------------------------------------------------------------------------------------

mutable struct RunHandle
    id::String
    cancel::Threads.Atomic{Bool}
    task::Union{Task,Nothing}
end

const RUNS = Dict{String,RunHandle}()
const RUNS_LOCK = ReentrantLock()

"All live run handles (a snapshot, so the lock is not held while waiting)."
function _live_runs()
    return lock(RUNS_LOCK) do
        collect(values(RUNS))
    end
end

# ---------------------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------------------

function _dispatch(conn::Connection, method::AbstractString, params)
    if method == "ping"
        return (; version = version_string(), julia = string(VERSION), warm = WARM[])
    elseif method == "catalog.get"
        dir = _optional_string(params, :projectLibraryDir, nothing)
        if dir !== nothing && isempty(dir)
            dir = nothing
        end
        return Library.catalog(dir)
    elseif method == "block.check"
        source = _jsonfield(params, :source, nothing)
        source isa AbstractString ||
            throw(RpcError("`block.check` requires the `source` string parameter"))
        ref = _optional_string(params, :ref, DEFAULT_BLOCK_REF)
        return _block_check_result(String(source), ref)
    elseif method == "model.check"
        value = _jsonfield(params, :model, nothing)
        md = _parse_model_document(value, "model.check")
        project_dir = _optional_string(params, :projectDir, nothing)
        return _model_check_result(md; project_dir = project_dir)
    elseif method == "run.start"
        return _run_start(conn, params)
    elseif method == "run.cancel"
        return _run_cancel(params)
    elseif method == "cache.clear"
        Library.clear_cache()
        clear_compile_cache!()
        log_line(conn.log, "caches cleared")
        return (; ok = true)
    end
    throw(RpcError("method `$method` is not implemented"))
end

# ---------------------------------------------------------------------------------------
# run.start / run.cancel
# ---------------------------------------------------------------------------------------

function _run_start(conn::Connection, params)
    run_id = _required_string(params, :runId, "run.start")
    run_dir = _required_string(params, :runDir, "run.start")
    project_dir = _optional_string(params, :projectDir, nothing)
    model_value = _jsonfield(params, :model, nothing)
    md = _parse_model_document(model_value, "run.start")
    settings = _run_settings(md)

    log_line(conn.log, "run ", run_id, " preparing `", md.name, "`")
    flat = Compile.flatten(md; project_dir = project_dir)
    model_hash = BGSim.compile_key(flat)

    # REQ-1: the live tail needs the signal list before the first data row. Flattening gives
    # it, so the worker can write the running manifest and only then accept the run.
    try
        _write_running_manifest(flat, settings, run_id, run_dir, model_hash)
    catch err
        throw(RpcError(
            "could not prepare the run folder `$run_dir`: " * sprint(showerror, err)
        ))
    end

    handle = RunHandle(run_id, Threads.Atomic{Bool}(false), nothing)
    lock(RUNS_LOCK) do
        haskey(RUNS, run_id) && throw(RpcError("run `$run_id` is already running"))
        RUNS[run_id] = handle
    end

    return Deferred(
        (; accepted = true),
        () -> _spawn_run(conn, handle, flat, settings, run_dir, model_hash),
    )
end

function _run_cancel(params)
    run_id = _required_string(params, :runId, "run.cancel")
    handle = lock(RUNS_LOCK) do
        get(RUNS, run_id, nothing)
    end
    handle === nothing && return (; ok = false)
    handle.cancel[] = true
    return (; ok = true)
end

function _spawn_run(conn::Connection, handle::RunHandle, flat, settings::RunSettings,
    run_dir::AbstractString, model_hash::AbstractString)
    run_id = handle.id
    log_event(conn, "info", "run $run_id started for `$(flat.name)`")
    # These stages already ran inside `run.start` (they give REQ-1 the signal list); report
    # them now so the plan 3.6 phase sequence stays accepted-then-notifications.
    for phase in ("parse", "flatten", "causality")
        notify!(conn, "run.phase", (; runId = run_id, phase = phase, t_s = 0.0))
    end

    last_progress_ns = Ref(UInt64(0))
    progress = function (t, rows)
        now = time_ns()
        if last_progress_ns[] != 0 && now - last_progress_ns[] < PROGRESS_MIN_INTERVAL_NS
            return nothing
        end
        last_progress_ns[] = now
        notify!(conn, "run.progress",
            (; runId = run_id, t = Float64(t), rows = Int(rows)))
        return nothing
    end

    task = Threads.@spawn begin
        status = "failed"
        stats = _zero_run_stats(flat)
        diagnostics = Any[]
        try
            result = simulate(
                flat;
                run_dir = run_dir,
                run_id = run_id,
                model_hash = model_hash,
                settings = settings,
                # Yielding inside the cancellation check is what lets requests (and the
                # socket reader) run while the simulation loop is stepping.
                cancel = () -> (yield(); handle.cancel[]),
                progress = progress,
                phase = (name, t_s) -> notify!(
                    conn, "run.phase",
                    (; runId = run_id, phase = String(name), t_s = Float64(t_s)),
                ),
            )
            status = result.status
            stats = result.stats
            diagnostics = Any[to_namedtuple(d) for d in result.diagnostics]
            if status == "failed"
                log_event(conn, "error", "run $run_id failed")
            else
                log_event(conn, "info", "run $run_id $status")
            end
        catch err
            message = sprint(showerror, err)
            log_line(conn.log, "run ", run_id, " crashed: ", message)
            diagnostic = diag(
                "E900", "internal worker error while running `$(flat.name)`";
                hint = message,
            )
            diagnostics = Any[to_namedtuple(diagnostic)]
            try
                _write_failed_manifest(
                    flat, settings, run_id, run_dir, model_hash, [diagnostic]
                )
            catch write_err
                log_line(
                    conn.log, "could not write the failed manifest of run ", run_id, ": ",
                    sprint(showerror, write_err),
                )
            end
        finally
            notify!(conn, "run.done",
                (; runId = run_id, status = status, stats = stats,
                    diagnostics = diagnostics))
            lock(RUNS_LOCK) do
                current = get(RUNS, run_id, nothing)
                current === handle && delete!(RUNS, run_id)
            end
        end
    end
    handle.task = task
    return nothing
end

"Cancel every live run and give the run tasks a moment to write their final state."
function _shutdown_runs()
    handles = _live_runs()
    isempty(handles) && return nothing
    for handle in handles
        handle.cancel[] = true
    end
    deadline = time_ns() + 5_000_000_000
    for handle in handles
        task = handle.task
        task === nothing && continue
        while !istaskdone(task) && time_ns() < deadline
            sleep(0.02)
        end
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Frames and requests
# ---------------------------------------------------------------------------------------

"Map an exception to the contract error payload (message plus diagnostics)."
function _error_payload(conn::Connection, err, method::AbstractString)
    if err isa RpcError
        return err.message, err.diagnostics
    end
    log_line(conn.log, "request `", method, "` failed: ", sprint(showerror, err))
    return "internal worker error in `$method`: " * sprint(showerror, err), Any[]
end

"Answer one request; a `Deferred` answer is written before its `after` runs."
function handle_request(conn::Connection, id, method::AbstractString, params)
    value = try
        _dispatch(conn, method, params)
    catch err
        if err isa Base.IOError || err isa EOFError
            log_line(conn.log, "could not answer request ", id, ": ", sprint(showerror, err))
            return nothing
        end
        message, diagnostics = _error_payload(conn, err, method)
        try
            send!(conn, error_message(id, message; diagnostics = diagnostics))
        catch send_err
            log_line(
                conn.log, "could not send the error of request ", id, ": ",
                sprint(showerror, send_err),
            )
        end
        return nothing
    end
    try
        send!(conn, result_message(id, value isa Deferred ? value.result : value))
    catch send_err
        log_line(
            conn.log, "could not answer request ", id, ": ", sprint(showerror, send_err)
        )
        return nothing
    end
    if value isa Deferred
        try
            value.after()
        catch err
            log_line(
                conn.log, "could not start the deferred answer of request ", id, ": ",
                sprint(showerror, err),
            )
        end
    end
    return nothing
end

"Handle one decoded frame: requests run on their own task, anything else is logged."
function _handle_frame(conn::Connection, frame::Frame)
    if frame.kind == KIND_BINARY
        log_line(conn.log, "rejecting binary frame (", length(frame.payload), " bytes)")
        return nothing
    end
    message = try
        JSON3.read(String(frame.payload))
    catch err
        log_line(conn.log, "ignoring malformed JSON frame: ", sprint(showerror, err))
        return nothing
    end
    if !(message isa AbstractDict)
        log_line(conn.log, "ignoring a frame that is not a JSON object")
        return nothing
    end
    id = _jsonfield(message, :id, nothing)
    if id === nothing
        log_line(conn.log, "ignoring a notification (the backend does not notify us)")
        return nothing
    end
    method_value = _jsonfield(message, :method, nothing)
    if !(method_value isa AbstractString)
        try
            send!(conn, error_message(id, "request has no method"))
        catch err
            log_line(conn.log, "could not answer request ", id, ": ", sprint(showerror, err))
        end
        return nothing
    end
    params = _jsonfield(message, :params, nothing)
    task = Threads.@spawn handle_request(conn, id, String(method_value), params)
    errormonitor(task)
    return nothing
end

"""
    serve(sock; warmup = false, log = stderr)

Serve frames until the backend closes the connection. With `warmup = true` the start-up
workload runs on its own task, so `ping` answers `warm = false` until it has finished (plan
2.1: the backend reports `warming` in the meantime).
"""
function serve(sock::TCPSocket; warmup::Bool = false, log::IO = stderr)
    conn = Connection(sock, log)
    log_line(log, "connected; serving frames")
    if warmup
        _start_warmup(conn)
    end
    try
        while true
            frame = try
                read_frame(sock)
            catch err
                log_line(log, "read failed: ", sprint(showerror, err))
                break
            end
            frame === nothing && break
            _handle_frame(conn, frame)
        end
    finally
        _shutdown_runs()
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------

function _port_from_env()::Int
    value = get(ENV, "BGSIM_PORT", "")
    isempty(value) &&
        error("BGSIM_PORT is not set: the backend must tell the worker where to connect")
    port = tryparse(Int, value)
    port === nothing && error("BGSIM_PORT is not an integer: $(value)")
    return port
end

function _main()::Int
    port = _port_from_env()
    log_line(
        "connecting to 127.0.0.1:", port, " (julia ", VERSION, ", ",
        Threads.nthreads(), " thread", Threads.nthreads() == 1 ? "" : "s", ")",
    )
    sock = try
        connect(ip"127.0.0.1", port)
    catch err
        log_line("connect failed: ", sprint(showerror, err))
        return 1
    end
    try
        serve(sock; warmup = true)
        log_line("connection closed by the backend; exiting")
        return 0
    catch err
        log_line("serving failed: ", sprint(showerror, err))
        return 1
    finally
        close(sock)
    end
end

"""
    main()

Entry point: read `BGSIM_PORT`, connect to `127.0.0.1:<port>` and serve the worker
protocol until the connection closes. Exits the process with 0 on a clean shutdown
and 1 on failure.
"""
main() = exit(_main())

end # module Worker
