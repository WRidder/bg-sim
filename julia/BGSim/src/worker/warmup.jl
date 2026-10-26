# The worker's PrecompileTools workload and its start-up warm-up (plan 2.1, 5.12).
#
# Two layers:
#
# * `@compile_workload` runs during package precompilation and compiles the paths of
#   `ping`, `catalog.get`, `block.check`, `model.check` and a tiny two-run `simulate`, so the
#   first real request of every method is warm.
# * `warm_up!` runs in the worker process right after it connects. It repeats the same calls
#   (catalog, block check, model check, and a tiny RC model twice with a changed parameter to
#   warm `remake`), then sets `WARM[] = true`; `ping` reports `warm = false` until then and
#   the backend reports `warming` (plan 3.7).
#
# The RC model is built here instead of read from `contracts/fixtures`: the package must
# precompile without the repository's fixture tree, and a five-node model with wires, a
# signal connection and an electrical ground touches every flattening pass.

"""
    WARM_BLOCK_SOURCE

A 40-line block with ports, a vector variable, constants, parameters, states and
algebraic variables. It is the input of the precompile workload's `block.check` and of the
warm-up, so the as-you-type path is compiled for a representative block shape.
"""
const WARM_BLOCK_SOURCE = """
# A representative block for the worker's precompile and warm-up workload.
# It is exactly 40 lines long (`test/test_worker.jl` asserts the count).
# It exercises power ports, a signal input and output, a structural constant,
# parameters with units and attributes, states, a vector variable and plain
# algebraic variables: exactly the shapes the editor's as-you-type check sees.
@block WorkerWarmup begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        shaft::Power{Rotation}
    end
    @inputs u::Real
    @outputs y::Real
    @constants N::Int = 2
    @parameters begin
        R::Real = 2.0, [unit = "Ohm", min = 0, description = "Winding resistance"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Winding inductance"]
        k::Real = 0.05, [unit = "N*m/A", description = "Torque constant"]
        J::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        d::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Damping"]
    end
    @variables begin
        i::Real = 0.0, [unit = "A", state = :prefer, description = "Current"]
        w::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Speed"]
        v::Vec{N}, [unit = "V"]
        helper::Real
    end
    # The equations mix port flows and efforts, state derivatives and algebraic relations.
    @equations begin
        i ~ p.f
        p.f + n.f ~ 0.0
        p.e - n.e ~ R * i + L * ddt(i) + k * w
        w ~ shaft.f
        shaft.e ~ k * i + J * ddt(w) + d * w
        y ~ i
        helper ~ u * k
        v[1] ~ p.e
        v[2] ~ n.e
    end
end
"""

"""
    _warm_model_document(final = "12.0") -> Dict{String,Any}

The five-node RC model of `warm_up!`: a step drives a voltage source, which feeds a resistor
and capacitor to ground. `final` is a parameter value, so two documents with different
`final`s share one structural compile key and the second run exercises `remake` (NOTES.md,
API surprise 8).
"""
function _warm_model_document(final::AbstractString = "12.0")
    node(id, name, ref, params = Dict{String,Any}()) = Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => Dict{String,Any}("ref" => ref),
        "params" => params,
        "constants" => Dict{String,Any}(),
        "starts" => Dict{String,Any}(),
    )
    conn(id, kind, from_node, from_port, to_node, to_port) = Dict{String,Any}(
        "id" => id,
        "kind" => kind,
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => "WorkerWarmupRC",
        "diagram" => Dict{String,Any}(
            "nodes" => Any[
                node(
                    "n1", "Step1", "stdlib:sources/Step",
                    Dict{String,Any}(
                        "t_step" => "0.0", "initial" => "0.0", "final" => final,
                    ),
                ),
                node("n2", "V1", "stdlib:electrical/VoltageSource",
                    Dict{String,Any}("V" => "1.0")),
                node("n3", "R1", "stdlib:electrical/Resistor",
                    Dict{String,Any}("R" => "1000.0")),
                node("n4", "C1", "stdlib:electrical/Capacitor",
                    Dict{String,Any}("C" => "1e-6")),
                node("n5", "G1", "stdlib:electrical/Ground"),
            ],
            "connections" => Any[
                conn("c1", "signal", "n1", "y", "n2", "u"),
                conn("c2", "wire", "n2", "p", "n3", "p"),
                conn("c3", "wire", "n3", "n", "n4", "p"),
                conn("c4", "wire", "n4", "n", "n5", "p"),
                conn("c5", "wire", "n2", "n", "n5", "p"),
            ],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0,
            "t_end" => 0.01,
            "solver" => "auto",
            "reltol" => 1e-6,
            "abstol" => 1e-8,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => 3),
            "event_limit" => 10000,
        ),
    )
end

const WARM_MODEL = _warm_model_document("12.0")

"True once the start-up warm-up has completed (`ping.warm`)."
const WARM = Ref(false)

"True while the start-up warm-up runs (guards against a second workload)."
const WARM_STARTED = Ref(false)
const WARM_LOCK = ReentrantLock()

"Flatten and simulate one warm-up model into `dir` (three output points)."
function _warm_run!(dir::AbstractString, final::AbstractString)
    md = IR.parse_model(_warm_model_document(final))
    flat = Compile.flatten(md)
    settings = RunSettings(md.settings)
    return simulate(flat; run_dir = dir, run_id = "warmup-" * final, settings = settings)
end

"""
    _warm_wire_shapes()

Call `catalog.get`, `block.check` and `model.check` and serialise the **response
envelopes** exactly as `send!` does. Serialising a result alone is not enough: JSON3
specialises `write` on the concrete `(; id, result)` wrapper, and the first wire answer of a
method otherwise pays that compilation (measured: 0.2–2 s for `model.check`). The run
notifications are warmed the same way.
"""
function _warm_wire_shapes()
    catalog = Library.catalog()
    checked = _block_check_result(WARM_BLOCK_SOURCE, "project:WorkerWarmup")
    checked_model = _model_check_result(IR.parse_model(WARM_MODEL))
    # The worker receives its model as a JSON3.Object (the frame decoder's type), not as
    # the Dict the literal above is. `IR.parse_model` specialises on the input type, so the
    # JSON3 path must be warmed too or the first model.check/run.start pays ~1 s of codegen.
    json_model = JSON3.read(JSON3.write(WARM_MODEL))
    checked_json_model = _model_check_result(_parse_model_document(json_model, "model.check"))
    JSON3.write(result_message(
        1, (; version = version_string(), julia = string(VERSION), warm = false)))
    JSON3.write(result_message(2, catalog))
    JSON3.write(result_message(3, checked))
    JSON3.write(result_message(4, checked_model))
    JSON3.write(result_message(5, checked_json_model))
    JSON3.write(result_message(6, (; accepted = true)))
    JSON3.write(result_message(7, (; ok = true)))
    JSON3.write(error_message(7, "warm"))
    JSON3.write(notification_message(
        "run.phase", (; runId = "r", phase = "parse", t_s = 0.0)))
    JSON3.write(notification_message(
        "run.progress", (; runId = "r", t = 0.0, rows = 0)))
    JSON3.write(notification_message("run.done", (;
        runId = "r",
        status = "done",
        stats = (; compile_s = 0.0, sim_s = 0.0, steps = 0, events = 0, states = 0,
            equations = 0),
        diagnostics = Any[],
    )))
    JSON3.write(notification_message("log", (; level = "info", message = "warm")))
    return nothing
end

@setup_workload begin
    @compile_workload begin
        # ping, catalog.get, block.check, model.check and every notification envelope.
        _warm_wire_shapes()

        # run.start: the full run folder (running manifest, stream, columns, final
        # manifest) and a parameter-only second run through the compile cache.
        dir = mktempdir()
        try
            _warm_run!(dir, "12.0")
            _warm_run!(dir, "6.0")
        finally
            rm(dir; recursive = true, force = true)
        end
    end
end

"""
    warm_up!(; log = stderr, notify = nothing) -> Bool

Run the start-up workload in this process: catalog, a block check, a model check and the RC
model twice (the second with a changed parameter, which warms `remake`). Sets `WARM[]` when
it is done. `notify(level, message)` is called for the backend's `log` notification.
"""
function warm_up!(; log::IO = stderr, notify = nothing)
    already_started = lock(WARM_LOCK) do
        started = WARM_STARTED[]
        WARM_STARTED[] = true
        started
    end
    already_started && return WARM[]
    started = time_ns()
    emit = function (level, message)
        log_line(log, level, ": ", message)
        notify === nothing || notify(level, message)
        return nothing
    end
    emit("info", "warm-up started")
    try
        _warm_wire_shapes()
        dir = mktempdir()
        try
            _warm_run!(dir, "12.0")
            _warm_run!(dir, "6.0")
        finally
            rm(dir; recursive = true, force = true)
        end
    catch err
        message = "warm-up failed: " * sprint(showerror, err)
        log_line(log, message)
        notify === nothing || notify("error", message)
        # Do not leave the backend in "warming" forever: requests still work, only the
        # first one of each method pays its JIT. The failure is in the log and in a `log`
        # notification.
        WARM[] = true
        return false
    end
    WARM[] = true
    elapsed = (time_ns() - started) / 1.0e9
    emit("info", "warm-up finished in " * string(round(elapsed; digits = 2)) * " s")
    return true
end

"Start `warm_up!` on its own task so `ping` keeps answering while it runs (plan 2.1)."
function _start_warmup(conn)
    task = Threads.@spawn begin
        try
            warm_up!(
                log = conn.log,
                notify = (level, message) -> notify!(
                    conn, "log", (; level = level, message = message)
                ),
            )
        catch err
            log_line(conn.log, "warm-up crashed: ", sprint(showerror, err))
            WARM[] = true
        end
    end
    errormonitor(task)
    return nothing
end
