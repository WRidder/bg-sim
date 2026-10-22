# The recorder (plan section 5.10) and the run manifest (plan section 3.5).
#
# One run folder holds three files:
#
#   stream.f64    row-major [t, v1 ... vn] little-endian Float64 rows, appended while the
#                 simulation runs and flushed at least every 100 ms;
#   columns.f64   the time column followed by one column per signal in manifest order, each
#                 with n values (the playback file of the spec);
#   manifest.json written with status "running" and the full signal list before the first
#                 row (REQ-1), then rewritten atomically (temp file + rename) with the final
#                 status and stats.
#
# Bool and Int values are stored as Float64. Duplicate times are allowed: J2.3 records every
# event instant twice, as left and right limits, so a step renders as a vertical edge.
#
# The recorder never evaluates a signal itself. `simulate` hands it one getter per signal,
# built once from the integrator (`getu`/`getp` of `SymbolicIndexingInterface`), and the
# recorder only stores numbers.

import JSON3
import Dates

"""
    RunSettings(t_start, t_end, solver, reltol, abstol, max_step, output, event_limit)

The plan 3.3 model settings, normalised and validated. `RunSettings(settings)` accepts a
`Dict`, a JSON3 object or a `NamedTuple`; `RunSettings(; ...)` uses the defaults
(`0.0` to `1.0`, solver `"auto"`, `1e-6`/`1e-8`, 1000 output points, 10000 events).
"""
struct RunSettings
    t_start::Float64
    t_end::Float64
    solver::String
    reltol::Float64
    abstol::Float64
    max_step::Union{Nothing,Float64}
    output::NamedTuple
    event_limit::Int
end

function _setting(container, name::AbstractString, default)
    container === nothing && return default
    if container isa NamedTuple
        key = Symbol(name)
        return haskey(container, key) ? container[key] : default
    end
    if container isa AbstractDict
        haskey(container, name) && return container[name]
        key = Symbol(name)
        haskey(container, key) && return container[key]
        return default
    end
    # JSON3.Object and other symbol-keyed containers.
    key = Symbol(name)
    return haskey(container, key) ? container[key] : default
end

function _normalize_output(raw, t_start::Float64, t_end::Float64)
    mode = String(_setting(raw, "mode", "points"))
    if mode == "interval"
        interval = Float64(_setting(raw, "interval", 0.0))
        interval > 0 || throw(ArgumentError("output.interval must be positive"))
        return (mode = "interval", interval = interval)
    elseif mode == "points"
        points = Int(_setting(raw, "points", 1000))
        points >= 2 || throw(ArgumentError("output.points must be at least 2"))
        return (mode = "points", points = points)
    end
    throw(ArgumentError("output.mode must be \"points\" or \"interval\", not \"$mode\""))
end

function RunSettings(settings)
    settings isa RunSettings && return settings
    t_start = Float64(_setting(settings, "t_start", 0.0))
    t_end = Float64(_setting(settings, "t_end", 1.0))
    solver = String(_setting(settings, "solver", "auto"))
    reltol = Float64(_setting(settings, "reltol", 1.0e-6))
    abstol = Float64(_setting(settings, "abstol", 1.0e-8))
    max_step_raw = _setting(settings, "max_step", nothing)
    max_step = max_step_raw === nothing ? nothing : Float64(max_step_raw)
    output = _normalize_output(_setting(settings, "output", nothing), t_start, t_end)
    event_limit = Int(_setting(settings, "event_limit", 10000))

    t_end > t_start || throw(ArgumentError("t_end must be greater than t_start"))
    reltol > 0 || throw(ArgumentError("reltol must be positive"))
    abstol > 0 || throw(ArgumentError("abstol must be positive"))
    max_step === nothing || max_step > 0 ||
        throw(ArgumentError("max_step must be positive when set"))
    event_limit >= 0 || throw(ArgumentError("event_limit must be non-negative"))
    return RunSettings(t_start, t_end, solver, reltol, abstol, max_step, output, event_limit)
end

RunSettings(;
    t_start = 0.0,
    t_end = 1.0,
    solver = "auto",
    reltol = 1.0e-6,
    abstol = 1.0e-8,
    max_step = nothing,
    output = nothing,
    event_limit = 10000,
) = RunSettings(Dict{String,Any}(
    "t_start" => t_start,
    "t_end" => t_end,
    "solver" => solver,
    "reltol" => reltol,
    "abstol" => abstol,
    "max_step" => max_step,
    "output" => output,
    "event_limit" => event_limit,
))

"""    to_namedtuple(settings) -> NamedTuple

The plan 3.3 settings object, ready for the run manifest."""
function to_namedtuple(s::RunSettings)
    return (
        t_start = s.t_start,
        t_end = s.t_end,
        solver = s.solver,
        reltol = s.reltol,
        abstol = s.abstol,
        max_step = s.max_step,
        output = s.output,
        event_limit = s.event_limit,
    )
end

"""
    output_grid(settings) -> Vector{Float64}

The rows' times. `points` mode is exactly `points` equally spaced values from `t_start` to
`t_end` inclusive; `interval` mode starts at `t_start`, takes steps of `interval` and always
includes `t_end`.
"""
function output_grid(s::RunSettings)
    if s.output.mode == "points"
        return collect(range(s.t_start, s.t_end; length = s.output.points))
    end
    interval = s.output.interval
    count = floor(Int, (s.t_end - s.t_start) / interval)
    times = Float64[s.t_start + k * interval for k in 0:count]
    tolerance = 1.0e-12 * max(1.0, abs(s.t_end))
    if isempty(times) || times[end] < s.t_end - tolerance
        push!(times, s.t_end)
    elseif times[end] > s.t_end
        times[end] = s.t_end
    end
    return times
end

# ---------------------------------------------------------------------------------------
# Manifest pieces
# ---------------------------------------------------------------------------------------

_iso_now() = Dates.format(Dates.now(Dates.UTC), "yyyy-mm-ddTHH:MM:SSZ")

"""    signal_entries(signals) -> Vector{NamedTuple}

The plan 3.5 manifest signal entries, in recording order. Every entry carries the four
required fields plus `unit` (which may be `nothing`). A signal without an instance path is a
programming error: the schema requires a non-empty path.
"""
function signal_entries(signals)
    out = NamedTuple[]
    for s in signals
        s.path === nothing &&
            throw(ArgumentError("recorded signal `$(s.id)` has no instance path"))
        push!(out, (
            id = String(s.id),
            unit = s.unit === nothing ? nothing : String(s.unit),
            kind = String(s.kind),
            path = String(s.path),
            type = String(s.type),
        ))
    end
    return out
end

_diag_entries(diagnostics) = [to_namedtuple(d) for d in diagnostics]

_zero_stats(states::Integer, equations::Integer) = (
    compile_s = 0.0,
    sim_s = 0.0,
    steps = 0,
    events = 0,
    states = Int(states),
    equations = Int(equations),
)

function _manifest(; id, model, model_hash, status, settings, stats, signals, time,
    diagnostics, created = nothing)
    return (
        id = String(id),
        model = String(model),
        modelHash = String(model_hash),
        created = created === nothing ? _iso_now() : String(created),
        status = String(status),
        settings = settings,
        stats = stats,
        signals = signals,
        time = time,
        diagnostics = diagnostics,
        layout = "columnar-f64-v1",
    )
end

"""
    write_manifest_atomic(path, manifest)

Write `manifest` to `path` through `path * ".tmp"` and rename it into place, so a live
reader never sees a half-written JSON document (REQ-1).
"""
function write_manifest_atomic(path::AbstractString, manifest)
    temp = path * ".tmp"
    open(temp, "w") do io
        JSON3.write(io, manifest)
        write(io, '\n')
    end
    try
        Base.Filesystem.rename(temp, path)
    catch
        isfile(path) && rm(path; force=true)
        Base.Filesystem.rename(temp, path)
    end
    return nothing
end

# ---------------------------------------------------------------------------------------
# The recorder
# ---------------------------------------------------------------------------------------

"""
    Recorder

The open run files. `columns[1]` is the time column; `columns[j+1]` is signal `j` in manifest
order. `stream` receives the same values row by row, so the live tail and the playback file
cannot disagree.
"""
mutable struct Recorder
    dir::String
    stream::IOStream
    columns::Vector{Vector{Float64}}
    nsignals::Int
    nrows::Int
    capacity::Int
    last_flush_ns::UInt64
    first_row_ns::UInt64
    manifest::NamedTuple
end

"""    open_recorder(run_dir, run_id, model, model_hash, settings, signals, diagnostics;
                    capacity, states, equations) -> Recorder

Create the run folder, open `stream.f64` and write the `status: "running"` manifest with the
**full** signal list (REQ-1) before any data row exists.
"""
function open_recorder(
    run_dir::AbstractString,
    run_id::AbstractString,
    model::AbstractString,
    model_hash::AbstractString,
    settings::RunSettings,
    signals,
    diagnostics;
    capacity::Integer,
    states::Integer,
    equations::Integer,
    created = nothing,
)
    mkpath(run_dir)
    entries = signal_entries(signals)
    cap = max(16, Int(capacity))
    columns = [zeros(Float64, cap) for _ in 1:(length(entries) + 1)]
    stream = open(joinpath(run_dir, "stream.f64"), "w")
    manifest = _manifest(
        id = run_id,
        model = model,
        model_hash = model_hash,
        status = "running",
        settings = to_namedtuple(settings),
        stats = _zero_stats(states, equations),
        signals = entries,
        time = (n = 0, t0 = settings.t_start, t1 = settings.t_end),
        diagnostics = _diag_entries(diagnostics),
        created = created,
    )
    write_manifest_atomic(joinpath(run_dir, "manifest.json"), manifest)
    return Recorder(
        String(run_dir), stream, columns, length(entries), 0, cap, time_ns(), 0,
        manifest,
    )
end

# Explicit little-endian Float64, independent of the host byte order.
_write_f64_le(io::IO, value::Float64) = write(io, htol(reinterpret(UInt64, value)))

"""
    record_row!(rec, t, values)

Append one row `[t, values...]` to `stream.f64` and to the in-memory columns. Duplicate `t`
values are accepted (events are recorded as left and right limits). The stream is flushed at
most every 100 ms.
"""
function record_row!(rec::Recorder, t::Real, values)
    length(values) == rec.nsignals || throw(ArgumentError(
        "expected $(rec.nsignals) signal values, got $(length(values))"
    ))
    if rec.nrows == rec.capacity
        newcap = max(16, 2 * rec.capacity)
        for col in rec.columns
            resize!(col, newcap)
        end
        rec.capacity = newcap
    end
    rec.nrows += 1
    tf = Float64(t)
    rec.columns[1][rec.nrows] = tf
    _write_f64_le(rec.stream, tf)
    for j in 1:rec.nsignals
        value = Float64(values[j])
        rec.columns[j + 1][rec.nrows] = value
        _write_f64_le(rec.stream, value)
    end
    now = time_ns()
    rec.first_row_ns == 0 && (rec.first_row_ns = now)
    if now - rec.last_flush_ns >= 100_000_000
        flush(rec.stream)
        rec.last_flush_ns = now
    end
    return nothing
end

"""    flush_recorder!(rec)

Flush the stream now (the run loop calls this at its 100 ms cadence and on cancellation)."""
function flush_recorder!(rec::Recorder)
    flush(rec.stream)
    rec.last_flush_ns = time_ns()
    return nothing
end

function _write_columns(path::AbstractString, columns, nrows::Int)
    open(path, "w") do io
        buffer = Vector{UInt64}(undef, nrows)
        for column in columns
            for i in 1:nrows
                buffer[i] = htol(reinterpret(UInt64, column[i]))
            end
            write(io, buffer)
        end
    end
    return nothing
end

"""
    finish_recorder!(rec, status, stats, diagnostics) -> NamedTuple

Flush and close the stream, write `columns.f64`, then rewrite the manifest atomically with
the final status, stats, row count and diagnostics. Returns the final manifest.
"""
function finish_recorder!(rec::Recorder, status::AbstractString, stats, diagnostics)
    flush(rec.stream)
    close(rec.stream)
    _write_columns(joinpath(rec.dir, "columns.f64"), rec.columns, rec.nrows)
    n = rec.nrows
    t0 = n == 0 ? rec.manifest.time.t0 : rec.columns[1][1]
    t1 = n == 0 ? rec.manifest.time.t1 : rec.columns[1][n]
    manifest = merge(rec.manifest, (
        status = String(status),
        stats = stats,
        time = (n = n, t0 = t0, t1 = t1),
        diagnostics = _diag_entries(diagnostics),
    ))
    write_manifest_atomic(joinpath(rec.dir, "manifest.json"), manifest)
    return manifest
end
