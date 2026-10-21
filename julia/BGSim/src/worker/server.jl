# The worker TCP server (plan section 3.6, milestone M0.4).
#
# The backend listens on a random localhost port, starts this process with
# `BGSIM_PORT=<port>` and the worker connects back and serves length-prefixed
# frames (`worker/protocol.jl`). This build answers `ping` and `cache.clear`; the
# catalog, check and run methods arrive with the compiler and simulator
# milestones. stdout/stderr are logs only (captured by the backend into
# `backend/logs/worker.log`) and are never protocol.
#
# Entry point (spawned by the backend, plan section 6):
#
#     julia --project=julia/BGSim --threads=2 -e "using BGSim; BGSim.Worker.main()"

module Worker

using Sockets
using JSON3

include("protocol.jl")

const BUILD_VERSION = "0.1.0"

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

"Log one line to stderr (the backend captures stderr into worker.log)."
function log_line(args...)
    println(stderr, "[BGSim.Worker] ", args...)
    flush(stderr)
    return nothing
end

"A successful response: `{ \"id\": id, \"result\": result }` (plan 3.6)."
result_message(id, result) = JSON3.write((; id = id, result = result))

"An error response: `{ \"id\": id, \"error\": { \"message\", \"diagnostics\" } }` (plan 3.6)."
error_message(id, message) =
    JSON3.write((; id = id, error = (; message = string(message), diagnostics = Any[])))

"""
    handle_request(id, method, params) -> String

Answer one request and return the JSON response text. `params` is not used yet;
the ping answers with the build stamp, the Julia version and `warm = true` (this
build has no background warm-up workload of its own).
"""
function handle_request(id, method, params)
    if method == "ping"
        return result_message(
            id, (; version = version_string(), julia = string(VERSION), warm = true)
        )
    elseif method == "cache.clear"
        return result_message(id, (; ok = true))
    elseif method === nothing
        return error_message(id, "request has no method")
    else
        return error_message(
            id, "method $(method) is not implemented by this worker build (M0.4)"
        )
    end
end

"Handle one decoded JSON frame: answer requests, log anything else."
function handle_json(sock::IO, payload::Vector{UInt8})
    message = try
        JSON3.read(String(payload))
    catch err
        log_line("ignoring malformed JSON frame: ", sprint(showerror, err))
        return nothing
    end
    if !(message isa JSON3.Object) || !haskey(message, :id)
        log_line("ignoring message without an id (the backend does not notify us yet)")
        return nothing
    end
    id = message[:id]
    method = get(message, :method, nothing)
    params = get(message, :params, nothing)
    answer = try
        handle_request(id, method, params)
    catch err
        error_message(id, "internal worker error: " * sprint(showerror, err))
    end
    write_json_frame(sock, answer)
    return nothing
end

"Handle one frame. Binary frames are rejected cleanly: this build sends none."
function handle_frame(sock::IO, frame::Frame)
    if frame.kind == KIND_BINARY
        log_line(
            "rejecting binary frame (", length(frame.payload), " bytes): not used by this build"
        )
        return nothing
    end
    return handle_json(sock, frame.payload)
end

"Serve frames until the backend closes the connection."
function serve(sock::TCPSocket)
    while true
        frame = read_frame(sock)
        frame === nothing && break
        handle_frame(sock, frame)
    end
    return nothing
end

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
    log_line("connecting to 127.0.0.1:", port, " (julia ", VERSION, ")")
    sock = try
        connect(ip"127.0.0.1", port)
    catch err
        log_line("connect failed: ", sprint(showerror, err))
        return 1
    end
    log_line("connected; serving frames")
    try
        serve(sock)
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
