# Length-prefixed frame transport of plan section 3.6.
#
# Every frame on the worker TCP socket is
#
#     u32 LE length | u8 kind | payload
#
# where `length` counts the kind byte plus the payload bytes (so it is always at
# least 1), and `kind` is 0 for a JSON message and 1 for a binary payload. This
# file is included by `worker/server.jl`; its Python counterpart is
# `backend/src/bgsim_server/worker.py` (`encode_frame` / `read_frame`).

const KIND_JSON = UInt8(0)
const KIND_BINARY = UInt8(1)

"One decoded frame: `kind` is 0 (JSON) or 1 (binary); `payload` is the raw bytes."
struct Frame
    kind::UInt8
    payload::Vector{UInt8}
end

"""
    read_frame(io) -> Union{Frame,Nothing}

Read one frame from `io`. Returns `nothing` on a clean end of stream before any
header byte, and throws `EOFError` on a truncated frame or `ArgumentError` on an
invalid length field.
"""
function read_frame(io::IO)
    header = Vector{UInt8}(undef, 4)
    nread = readbytes!(io, header, 4)
    nread == 0 && return nothing
    nread == 4 || throw(EOFError())
    length_field = UInt32(header[1]) |
                   (UInt32(header[2]) << 8) |
                   (UInt32(header[3]) << 16) |
                   (UInt32(header[4]) << 24)
    length_field >= 1 || throw(ArgumentError("invalid frame length $length_field"))
    body = Vector{UInt8}(undef, Int(length_field))
    readbytes!(io, body, length(body)) == length(body) || throw(EOFError())
    return Frame(body[1], body[2:end])
end

"""
    write_frame(io, kind, payload)

Write one frame (`u32 LE length`, kind byte, payload) and flush it.
"""
function write_frame(io::IO, kind::UInt8, payload::AbstractVector{UInt8})
    write(io, htol(UInt32(1 + length(payload))))
    write(io, kind)
    write(io, payload)
    flush(io)
    return nothing
end

"Write a JSON message (an already serialized string) as a kind-0 frame."
function write_json_frame(io::IO, message::AbstractString)
    write_frame(io, KIND_JSON, Vector{UInt8}(codeunits(message)))
    return nothing
end
