# Work package J1.6: the worker protocol (plan section 3.6).
#
# The tests speak the real framing over a real localhost TCP socket: `serve` on the server
# side, a connection built here on the client side. They cover
#
#   * the frame transport (little-endian length, kind byte, truncation);
#   * every method: `ping`, `catalog.get`, `block.check`, `model.check`, `run.start`,
#     `run.cancel`, `cache.clear`, plus the error responses;
#   * REQ-1: `run.start` has written the `status: "running"` manifest with the full signal
#     list before it answers `{"accepted": true}`;
#   * concurrency: a `block.check` and a `ping` are answered while a run is simulating;
#   * the notifications (`run.phase`, `run.progress`, `run.done`, `log`) and the final
#     manifest/files of a run;
#   * the warm-up workload and the 40-line `block.check` target of plan 5.12;
#   * that logging goes to the injected stderr sink and never to stdout.

using BGSim
using BGSim: IR, Compile, Library, RunSettings
import BGSim: Worker
using JSON3
using Sockets
using Test

const WORKER_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const WORKER_FIXTURES = joinpath(WORKER_ROOT, "contracts", "fixtures")

worker_fixture(parts...) = joinpath(WORKER_FIXTURES, parts...)

function _field(obj, key::Symbol, default = nothing)
    obj === nothing && return default
    if obj isa AbstractDict
        haskey(obj, key) && return obj[key]
        haskey(obj, String(key)) && return obj[String(key)]
        return default
    end
    hasproperty(obj, key) && return getproperty(obj, key)
    return default
end

_message_method(message) =
    message isa AbstractDict ? _field(message, :method, "") : ""

_has_id(message) = message isa AbstractDict && _field(message, :id, nothing) !== nothing

mutable struct TestClient
    sock::TCPSocket
    notifications::Vector{Any}
end

TestClient(sock::TCPSocket) = TestClient(sock, Any[])

function read_message(client::TestClient)
    frame = Worker.read_frame(client.sock)
    frame === nothing && error("the worker closed the connection")
    frame.kind == Worker.KIND_JSON || error("unexpected frame kind $(frame.kind)")
    return JSON3.read(String(frame.payload))
end

"Wait for the first message matching `predicate`, keeping the others in order."
function wait_for(client::TestClient, predicate, what::AbstractString; timeout = 120.0)
    index = findfirst(predicate, client.notifications)
    index === nothing || return popat!(client.notifications, index)
    task = @async begin
        while true
            message = read_message(client)
            predicate(message) && return message
            push!(client.notifications, message)
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

wait_response(client::TestClient, id; timeout = 120.0) =
    wait_for(client, message -> _has_id(message) && _field(message, :id) == id,
        "the response to request $id"; timeout = timeout)

wait_notification(client::TestClient, method::AbstractString; timeout = 120.0) =
    wait_for(client, message -> _message_method(message) == method,
        "the $method notification"; timeout = timeout)

function send_request!(client::TestClient, id, method::AbstractString, params = NamedTuple())
    message = (; id = id, method = method, params = params)
    Worker.write_json_frame(client.sock, JSON3.write(message))
    return nothing
end

function request(client::TestClient, id, method::AbstractString, params = NamedTuple();
    timeout = 120.0)
    send_request!(client, id, method, params)
    return wait_response(client, id; timeout = timeout)
end

"Issue a request and return its `result` (or fail when it answered with an error)."
function result_of(client::TestClient, id, method::AbstractString, params = NamedTuple();
    timeout = 120.0)
    message = request(client, id, method, params; timeout = timeout)
    error_value = _field(message, :error, nothing)
    error_value === nothing || error("$method answered with an error: $error_value")
    return _field(message, :result)
end

error_of(client::TestClient, id, method::AbstractString, params = NamedTuple()) =
    _field(request(client, id, method, params), :error, nothing)

function with_test_connection(f; warmup::Bool = false, log::IO = devnull)
    listener = Sockets.listen(ip"127.0.0.1", 0)
    port = Int(Sockets.getsockname(listener)[2])
    server_task = @async begin
        sock = Sockets.accept(listener)
        Worker.serve(sock; warmup = warmup, log = log)
    end
    sock = Sockets.connect(ip"127.0.0.1", port)
    client = TestClient(sock)
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

"Load a fixture model as a mutable dict so the test can change its settings."
function mutable_model(parts...)
    return JSON3.read(read(worker_fixture(parts...), String), Dict{String,Any})
end

const MY_GAIN_SOURCE = """
@block MyGain begin
    @inputs u::Real
    @outputs y::Real
    @parameters k::Real = 2.0
    @equations y ~ k * u
end
"""

@testset "J1.6 worker protocol" begin
    @testset "frame transport" begin
        io = IOBuffer()
        Worker.write_frame(io, Worker.KIND_JSON, Vector{UInt8}(codeunits("hi")))
        bytes = take!(io)
        @test bytes[1:4] == UInt8[3, 0, 0, 0]      # length includes the kind byte
        @test bytes[5] == Worker.KIND_JSON
        @test String(bytes[6:end]) == "hi"

        frame = Worker.read_frame(IOBuffer(bytes))::Worker.Frame
        @test frame.kind == Worker.KIND_JSON
        @test String(frame.payload) == "hi"

        # An empty payload is one kind byte, never a zero length.
        empty_io = IOBuffer()
        Worker.write_frame(empty_io, Worker.KIND_BINARY, UInt8[])
        empty_bytes = take!(empty_io)
        @test empty_bytes[1:4] == UInt8[1, 0, 0, 0]
        @test Worker.read_frame(IOBuffer(empty_bytes)).payload == UInt8[]

        # A clean end of stream is `nothing`; a partial header/payload is an error.
        @test Worker.read_frame(IOBuffer(UInt8[])) === nothing
        @test_throws EOFError Worker.read_frame(IOBuffer(UInt8[1, 0]))
        @test_throws EOFError Worker.read_frame(IOBuffer(UInt8[5, 0, 0, 0, 0, 1]))
        @test_throws ArgumentError Worker.read_frame(IOBuffer(UInt8[0, 0, 0, 0]))
    end

    @testset "message shapes" begin
        result = JSON3.read(JSON3.write(Worker.result_message(17, (; ok = true))))
        @test result.id == 17
        @test result.result.ok == true
        @test !haskey(result, :method)

        failed = JSON3.read(JSON3.write(Worker.error_message(4, "boom")))
        @test failed.id == 4
        @test failed.error.message == "boom"
        @test isempty(failed.error.diagnostics)

        notice = JSON3.read(JSON3.write(Worker.notification_message(
            "run.phase", (; runId = "r1", phase = "parse", t_s = 0.0))))
        @test notice.method == "run.phase"
        @test notice.params.runId == "r1"
        @test !haskey(notice, :id)

        @test Worker.version_string() == "0.1.0"
    end

    @testset "the precompile workload's inputs" begin
        @test count(==('\n'), Worker.WARM_BLOCK_SOURCE) == 40
        checked = Compile.check_block_source(Worker.WARM_BLOCK_SOURCE; ref = "inline:warm")
        @test isempty(checked.diagnostics)
        @test checked.interface !== nothing
        @test length(checked.interface.ports) == 3
        @test length(checked.interface.parameters) == 5
        @test length(checked.interface.variables) == 4   # i, w, v (Vec{2}), helper

        md = IR.parse_model(Worker.WARM_MODEL)
        model = Compile.model_check(md)
        @test isempty(model.diagnostics)
        @test model.stats.states == 1
        @test length(model.signals) == 24
    end

    @testset "start-up warm-up" begin
        started = time_ns()
        @test Worker.warm_up!(log = devnull)
        elapsed = (time_ns() - started) / 1.0e9
        @test Worker.WARM[]
        @test elapsed < 60.0
        @test Library.cached_blocks() > 0
        @test BGSim.cache_size() >= 1

        # A second call is a no-op (the backend may connect twice after a restart).
        again = time_ns()
        @test Worker.warm_up!(log = devnull)
        @test (time_ns() - again) / 1.0e9 < 1.0
    end

    @testset "ping, catalog.get and cache.clear" begin
        with_test_connection() do client
            pong = result_of(client, 1, "ping")
            @test pong.version == "0.1.0"
            @test startswith(String(pong.julia), "1.13")
            @test pong.warm == true

            catalog = result_of(client, 2, "catalog.get", (; projectLibraryDir = nothing))
            @test catalog.language == "0.1.0"
            # The worker answers with exactly the library on disk, whatever the M2 work
            # packages have added to it (J2.7 grows this count).
            @test length(catalog.blocks) == length(Library.load_stdlib())
            @test length(catalog.junctions) == 2
            @test length(catalog.domains) == 5
            dc = only(filter(b -> b.ref == "stdlib:converters/DCMotor", catalog.blocks))
            @test length(dc.ports) == 4
            @test dc.name == "DCMotor"

            mktempdir() do dir
                lib = joinpath(dir, "library")
                mkpath(lib)
                write(joinpath(lib, "MyGain.jl"), MY_GAIN_SOURCE)
                with_project = result_of(client, 3, "catalog.get",
                    (; projectLibraryDir = lib))
                @test length(with_project.blocks) == length(Library.load_stdlib()) + 1
                mine = only(filter(b -> b.ref == "project:MyGain", with_project.blocks))
                @test mine.group == "Project"
                @test mine.path == "library/MyGain.jl"
            end

            @test Library.cached_blocks() > 0
            @test result_of(client, 4, "cache.clear").ok == true
            @test Library.cached_blocks() == 0
            @test BGSim.cache_size() == 0
        end
    end

    @testset "block.check" begin
        with_test_connection() do client
            checked = result_of(client, 10, "block.check",
                (; source = Worker.WARM_BLOCK_SOURCE, ref = "inline:check"))
            @test isempty(checked.diagnostics)
            @test checked.interface !== nothing
            @test sort(collect(keys(checked.interface))) ==
                  sort([:constants, :parameters, :inputs, :outputs, :ports,
                        :variables, :causality])
            @test length(checked.interface.ports) == 3

            broken = result_of(client, 11, "block.check",
                (; source = "@block Broken begin\n    @inputs u::Real\n", ref = "inline:broken"))
            @test length(broken.diagnostics) >= 1
            @test broken.diagnostics[1].code == "E000"
            @test broken.interface === nothing

            # The plan 5.12 target: a 40-line block below 150 ms once warm. Every call uses
            # a new ref, so every call really parses and checks (the cache is per source+ref).
            times = Float64[]
            for k in 1:5
                started = time_ns()
                result_of(client, 100 + k, "block.check",
                    (; source = Worker.WARM_BLOCK_SOURCE, ref = "inline:bench-$k"))
                push!(times, (time_ns() - started) / 1e6)
            end
            @test times[end] < 150.0
        end
    end

    @testset "model.check" begin
        with_test_connection() do client
            result = result_of(client, 20, "model.check",
                (; model = JSON3.read(read(worker_fixture("model", "valid",
                        "model.dcmotor.json"), String)),
                    projectDir = WORKER_ROOT))
            @test isempty(result.diagnostics)
            @test result.stats.states == 3
            @test result.stats.equations == 41
            @test length(result.signals) == 73
            @test length(result.domains) == 11
            @test isempty(result.causality)
            @test all(v -> v == 1.0, values(result.unitFactors))
            first_signal = result.signals[1]
            @test first_signal.id == "Step1/y"
            @test first_signal.kind == "output"
            @test first_signal.path == "Step1"
            @test first_signal.type == "Real"

            # A malformed document is a request error, not a model diagnostic.
            failed = error_of(client, 21, "model.check",
                (; model = Dict{String,Any}(), projectDir = WORKER_ROOT))
            @test failed !== nothing
            @test isempty(failed.diagnostics)
            @test !isempty(String(failed.message))

            failed = error_of(client, 22, "model.check",
                (; model = Dict{String,Any}(
                    "format" => "not.a.model", "name" => "X",
                    "diagram" => Dict{String,Any}("nodes" => Any[], "connections" => Any[]),
                ), projectDir = WORKER_ROOT))
            @test occursin("not a bgsim model", String(failed.message))
        end
    end

    @testset "unknown methods, malformed frames and binary frames" begin
        with_test_connection() do client
            failed = error_of(client, 30, "does.not.exist", (; x = 1))
            @test occursin("not implemented", String(failed.message))
            @test isempty(failed.diagnostics)

            # A binary frame is rejected cleanly and the connection stays usable.
            Worker.write_frame(client.sock, Worker.KIND_BINARY, UInt8[0x00, 0x01, 0x02])
            @test result_of(client, 31, "ping").warm == true

            # Malformed JSON is ignored.
            Worker.write_frame(client.sock, Worker.KIND_JSON,
                Vector{UInt8}(codeunits("{ this is not json")))
            @test result_of(client, 32, "ping").warm == true

            # A message without an id is a notification from the backend: ignored.
            Worker.write_json_frame(client.sock, JSON3.write((;
                method = "run.phase", params = (; runId = "x", phase = "parse", t_s = 0.0))))
            @test result_of(client, 33, "ping").warm == true

            # A request without a method gets the protocol's error shape.
            Worker.write_json_frame(client.sock, JSON3.write((; id = 34, params = (;))))
            failed = wait_response(client, 34)
            @test occursin("no method", String(failed.error.message))
        end
    end

    @testset "run.start, REQ-1 and a concurrent block.check" begin
        model = mutable_model("model", "valid", "model.rlc.iconic.json")
        points = 200_000
        model["settings"]["output"] = Dict{String,Any}(
            "mode" => "points", "points" => points,
        )
        expected_signals = length(Compile.model_check(IR.parse_model(model)).signals)
        run_id = "run-j16-long"
        run_dir = joinpath(mktempdir(), run_id)

        with_test_connection() do client
            started = time_ns()
            accepted = result_of(client, 40, "run.start", (;
                runId = run_id,
                model = model,
                projectDir = WORKER_ROOT,
                runDir = run_dir,
            ))
            @test accepted.accepted == true

            # REQ-1: the running manifest with the full signal list exists before
            # `accepted` reaches us. The run task only starts after the answer is written.
            manifest_path = joinpath(run_dir, "manifest.json")
            @test isfile(manifest_path)
            manifest = JSON3.read(read(manifest_path, String))
            @test manifest.status == "running"
            @test length(manifest.signals) == expected_signals
            @test expected_signals > 0
            @test manifest.model == "RLCSeriesIconic"
            @test occursin(r"^[0-9a-f]{64}$", String(manifest.modelHash))
            @test manifest.layout == "columnar-f64-v1"
            @test manifest.time.n == 0

            # The run is simulating now: `block.check` and `ping` must answer concurrently.
            check_started = time_ns()
            checked = result_of(client, 41, "block.check",
                (; source = Worker.WARM_BLOCK_SOURCE, ref = "inline:while-running"))
            check_ms = (time_ns() - check_started) / 1e6
            @test isempty(checked.diagnostics)
            @test check_ms < 5000.0
            @test all(m -> _message_method(m) != "run.done", client.notifications)

            @test result_of(client, 42, "ping").warm == true

            done = wait_notification(client, "run.done"; timeout = 300.0)
            @test done.params.runId == run_id
            @test done.params.status == "done"
            @test done.params.stats.states == 2
            @test done.params.stats.equations == 22
            @test isempty(done.params.diagnostics)

            final = JSON3.read(read(manifest_path, String))
            @test final.status == "done"
            @test Int(final.time.n) == points
            @test final.time.t0 == 0.0
            @test final.time.t1 == 0.01
            @test filesize(joinpath(run_dir, "stream.f64")) ==
                  points * (expected_signals + 1) * 8
            @test filesize(joinpath(run_dir, "columns.f64")) ==
                  points * (expected_signals + 1) * 8

            phases = String[]
            progress = 0
            for message in client.notifications
                method = _message_method(message)
                method == "run.phase" && push!(phases, String(message.params.phase))
                method == "run.progress" && (progress += 1)
            end
            for phase in ("parse", "flatten", "causality", "mtkcompile", "init",
                          "simulate", "write")
                @test phase in phases
            end
            @test progress >= 1
            @test progress <= 20 * ((time_ns() - started) / 1.0e9) + 5
        end
    end

    @testset "run.cancel" begin
        model = mutable_model("model", "valid", "model.rlc.iconic.json")
        points = 200_000
        model["settings"]["output"] = Dict{String,Any}(
            "mode" => "points", "points" => points,
        )
        run_id = "run-j16-cancel"
        run_dir = joinpath(mktempdir(), run_id)

        with_test_connection() do client
            @test result_of(client, 50, "run.start", (;
                runId = run_id, model = model, projectDir = WORKER_ROOT, runDir = run_dir,
            )).accepted == true

            @test result_of(client, 51, "run.cancel", (; runId = run_id)).ok == true

            done = wait_notification(client, "run.done"; timeout = 300.0)
            @test done.params.status == "cancelled"
            final = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
            @test final.status == "cancelled"
            @test Int(final.time.n) < points

            @test result_of(client, 52, "run.cancel", (; runId = "no-such-run")).ok == false
        end
    end

    @testset "a run that cannot flatten ends as failed" begin
        model = mutable_model("model", "valid", "model.rlc.iconic.json")
        model["diagram"]["nodes"][1]["block"]["ref"] = "stdlib:sources/NoSuchBlock"
        run_id = "run-j16-broken"
        run_dir = joinpath(mktempdir(), run_id)

        with_test_connection() do client
            @test result_of(client, 55, "run.start", (;
                runId = run_id, model = model, projectDir = WORKER_ROOT, runDir = run_dir,
            )).accepted == true

            # The run cannot start, so `simulate` replaces the running manifest with the
            # failed one almost immediately (the long-run test above observes the running
            # state; this one checks the failure path still carries the signal list).
            done = wait_notification(client, "run.done"; timeout = 120.0)
            @test done.params.status == "failed"
            @test any(d -> d.code == "E101", done.params.diagnostics)
            final = JSON3.read(read(joinpath(run_dir, "manifest.json"), String))
            @test final.status == "failed"
            @test length(final.signals) > 0
            @test any(d -> d.code == "E101", final.diagnostics)
        end
    end

    @testset "invalid run settings are reported as E901" begin
        model = mutable_model("model", "valid", "model.rlc.iconic.json")
        model["settings"]["t_end"] = model["settings"]["t_start"]
        with_test_connection() do client
            failed = error_of(client, 60, "run.start", (;
                runId = "run-j16-bad-settings", model = model,
                projectDir = WORKER_ROOT, runDir = joinpath(mktempdir(), "run-bad"),
            ))
            @test occursin("invalid run settings", String(failed.message))
            @test length(failed.diagnostics) == 1
            @test failed.diagnostics[1].code == "E901"
        end
    end

    @testset "logging goes to the stderr sink" begin
        buffer = IOBuffer()
        with_test_connection(log = buffer) do client
            @test result_of(client, 70, "ping").warm == true
        end
        text = String(take!(buffer))
        @test occursin("[BGSim.Worker] connected; serving frames", text)

        for name in ("server.jl", "warmup.jl", "protocol.jl")
            source = read(joinpath(@__DIR__, "..", "src", "worker", name), String)
            @test !occursin("print(stdout", source)
            @test !occursin("println(stdout", source)
        end
    end
end
