# Output: the reduced-model file (JSON, format `bgsim.modal-body` version 1, read by the BGSim
# compiler for `stdlib:spatial/ModalBody3D`) and the visual mesh with the mode shapes (a GLB
# whose mesh carries one morph target per mode, read by the 3D viewer's `mode-shapes`
# binding).

const FORMAT = "bgsim.modal-body"
const FORMAT_VERSION = 1

_rows(A::AbstractMatrix) = [collect(A[i, :]) for i in axes(A, 1)]

"""
    modal_body_dict(r; glb = nothing, mesh_info = Dict()) -> Dict

The reduced model as the JSON document (see `docs/modal-body-format.md`)."""
function modal_body_dict(r::ReducedModel; glb = nothing, visual = nothing, mesh_info = Dict{String,Any}())
    ifs = Any[]
    for (j, f) in enumerate(r.interfaces)
        push!(ifs, Dict{String,Any}(
            "name" => f.name,
            "position" => f.position,
            "quaternion" => rot_to_quat(f.rotation),
            "nodes" => length(f.nodes),
            "translation" => _rows(r.PT[j]),
            "rotation" => _rows(r.PR[j]),
        ))
    end
    d = Dict{String,Any}(
        "format" => FORMAT,
        "version" => FORMAT_VERSION,
        "name" => r.name,
        "generator" => "BGSimFEM (Ferrite, Gmsh; Craig-Bampton)",
        "units" => "SI: m, kg, s. Modal coordinates in m (each mode scaled to a largest nodal translation of 1).",
        "frame" => "reference frame R = the frame of interface 1; every vector and tensor is in R",
        "reference_in_part" => Dict("position" => r.frame_position, "quaternion" => rot_to_quat(r.frame_rotation)),
        "material" => Dict("E" => r.material.E, "nu" => r.material.nu, "rho" => r.material.rho),
        "mesh" => mesh_info,
        "nm" => r.nm,
        "fixed_interface_modes" => r.nf,
        "mass" => r.mass,
        "first_moment" => r.S0,
        "inertia" => _rows(r.J0),
        "modal_mass" => r.mk,
        "modal_stiffness" => r.kk,
        "frequency_hz" => frequencies_hz(r),
        "mode_kind" => r.mode_kind,
        "St" => _rows(r.St),
        "Sr" => _rows(r.Sr),
        "J1" => _rows(r.J1),
        "E" => Dict(COMP6_NAMES[c] => _rows(r.E[c]) for c in 1:6),
        "interfaces" => ifs,
        "stiffening" => r.stiffening === nothing ? nothing :
            Dict(k => [_rows(g) for g in v] for (k, v) in r.stiffening),
        "validation" => r.validation,
    )
    glb === nothing || (d["visual"] = merge(Dict{String,Any}("glb" => glb), something(visual, Dict{String,Any}())))
    return d
end

"""Write the reduced model to `path` (JSON)."""
function write_modal_body(path::AbstractString, r::ReducedModel; kwargs...)
    mkpath(dirname(abspath(path)))
    d = modal_body_dict(r; kwargs...)
    open(path, "w") do io
        JSON3.write(io, d; allow_inf = false)
        println(io)
    end
    return path
end

# ---------------------------------------------------------------------------------------
# Visual mesh: surface triangles, crease-split normals, mode shapes per vertex
# ---------------------------------------------------------------------------------------

"""
    VisualMesh

Surface triangles over `positions` (3 x nv, R coordinates), with per-vertex normals and the
mode shapes per vertex (`modes[k]` is 3 x nv, displacement per unit modal coordinate).
`corner` maps a vertex to the incident triangles whose normals it averages."""
struct VisualMesh
    positions::Matrix{Float64}
    normals::Matrix{Float64}
    triangles::Vector{NTuple{3,Int}}
    modes::Vector{Matrix{Float64}}
    normal_deltas::Vector{Matrix{Float64}}
end

function _face_normals(P, tris)
    N = zeros(3, length(tris))
    for (t, (a, b, c)) in enumerate(tris)
        N[:, t] = cross(P[:, b] - P[:, a], P[:, c] - P[:, a])   # area weighted
    end
    return N
end

function _split_corners(P, tris; crease_deg = 35.0)
    N = _face_normals(P, tris)
    incident = [Int[] for _ in axes(P, 2)]
    for (t, tri) in enumerate(tris), v in tri
        push!(incident[v], t)
    end
    cc = cosd(crease_deg)
    unit(x) = (n = norm(x); n > 0 ? x ./ n : x)
    key = Dict{Tuple{Int,Vector{Int}},Int}()
    groups = Vector{Tuple{Int,Vector{Int}}}()
    newtris = NTuple{3,Int}[]
    for (t, tri) in enumerate(tris)
        nt = unit(N[:, t])
        ids = Int[]
        for v in tri
            set = sort!([s for s in incident[v] if dot(unit(N[:, s]), nt) >= cc])
            k = get!(key, (v, set)) do
                push!(groups, (v, set))
                length(groups)
            end
            push!(ids, k)
        end
        push!(newtris, (ids[1], ids[2], ids[3]))
    end
    return groups, newtris
end

function _group_normals(P, tris, groups)
    N = _face_normals(P, tris)
    out = zeros(3, length(groups))
    for (g, (_, set)) in enumerate(groups)
        n = sum(N[:, s] for s in set)
        out[:, g] = n ./ max(norm(n), 1e-300)
    end
    return out
end

"""
    visual_mesh(P, tris, modes) -> VisualMesh

Surface `tris` over node positions `P` (3 x n) with nodal mode shapes `modes[k]` (3 x n): the
vertices are split at creases (35 degrees) so flat faces stay flat, and each mode gets the
linearised change of the vertex normals per unit modal coordinate."""
function visual_mesh(P::AbstractMatrix, tris::Vector{NTuple{3,Int}}, modes::Vector{<:AbstractMatrix})
    used = sort!(unique(reduce(vcat, [collect(t) for t in tris])))
    remap = Dict(v => i for (i, v) in enumerate(used))
    Pu = P[:, used]
    tu = [(remap[a], remap[b], remap[c]) for (a, b, c) in tris]
    groups, newtris = _split_corners(Pu, tu)
    vid = [g[1] for g in groups]
    N0 = _group_normals(Pu, tu, groups)
    ext = maximum(maximum(Pu; dims = 2) - minimum(Pu; dims = 2))
    vmodes = Matrix{Float64}[]
    dN = Matrix{Float64}[]
    for U in modes
        Uu = U[:, used]
        s = maximum(abs, Uu)
        ε = s > 0 ? 1e-5 * ext / s : 1.0
        Nε = _group_normals(Pu .+ ε .* Uu, tu, groups)
        push!(vmodes, Uu[:, vid])
        push!(dN, (Nε .- N0) ./ ε)
    end
    return VisualMesh(Pu[:, vid], N0, newtris, vmodes, dN)
end

# ---------------------------------------------------------------------------------------
# GLB (glTF 2.0 binary) with morph targets
# ---------------------------------------------------------------------------------------

function _pad4!(io::IOBuffer, byte::UInt8)
    while position(io) % 4 != 0
        write(io, byte)
    end
end

"""
    write_glb(path, vm; color = (0.75, 0.77, 0.8, 1.0), frequencies = Float64[], name = "part")

One node, one mesh, one primitive (POSITION, NORMAL, uint32 indices) with one morph target
(POSITION and NORMAL deltas) per mode. Coordinates are the body's reference frame R in metres,
Z-up as the SDF scene (the viewer loads GLBs without an axis conversion)."""
function write_glb(path::AbstractString, vm::VisualMesh; color = (0.75, 0.77, 0.8, 1.0),
        frequencies = Float64[], name::AbstractString = "part")
    nv = size(vm.positions, 2)
    bin = IOBuffer()
    views = Any[]
    accessors = Any[]
    function add_view(data::Vector{T}, target) where {T}
        _pad4!(bin, 0x00)
        off = position(bin)
        write(bin, data)
        v = Dict{String,Any}("buffer" => 0, "byteOffset" => off, "byteLength" => sizeof(data))
        target === nothing || (v["target"] = target)
        push!(views, v)
        return length(views) - 1
    end
    function add_vec3(M::AbstractMatrix; minmax = false)
        data = Float32.(vec(M))
        v = add_view(data, 34962)
        a = Dict{String,Any}("bufferView" => v, "componentType" => 5126, "count" => size(M, 2), "type" => "VEC3")
        if minmax
            a["min"] = [Float64(minimum(Float32.(M[i, :]))) for i in 1:3]
            a["max"] = [Float64(maximum(Float32.(M[i, :]))) for i in 1:3]
        end
        push!(accessors, a)
        return length(accessors) - 1
    end
    pos = add_vec3(vm.positions; minmax = true)
    nor = add_vec3(vm.normals)
    idx = UInt32[]
    for (a, b, c) in vm.triangles
        push!(idx, UInt32(a - 1), UInt32(b - 1), UInt32(c - 1))
    end
    iv = add_view(idx, 34963)
    push!(accessors, Dict{String,Any}("bufferView" => iv, "componentType" => 5125, "count" => length(idx), "type" => "SCALAR"))
    ia = length(accessors) - 1
    targets = Any[]
    for k in eachindex(vm.modes)
        tp = add_vec3(vm.modes[k]; minmax = true)
        tn = add_vec3(vm.normal_deltas[k])
        push!(targets, Dict("POSITION" => tp, "NORMAL" => tn))
    end
    _pad4!(bin, 0x00)
    nm = length(vm.modes)
    prim = Dict{String,Any}("attributes" => Dict("POSITION" => pos, "NORMAL" => nor), "indices" => ia,
        "material" => 0, "mode" => 4)
    nm > 0 && (prim["targets"] = targets)
    mesh = Dict{String,Any}("name" => name, "primitives" => [prim])
    if nm > 0
        mesh["weights"] = zeros(nm)
        mesh["extras"] = Dict("targetNames" => ["mode $k" for k in 1:nm])
    end
    gltf = Dict{String,Any}(
        "asset" => Dict("version" => "2.0", "generator" => "BGSimFEM",
            "extras" => Dict("bgsim" => Dict("kind" => "modal-body", "modes" => nm, "frequency_hz" => frequencies,
                "frame" => "body reference frame R (interface 1), metres, Z-up"))),
        "scene" => 0,
        "scenes" => [Dict("nodes" => [0])],
        "nodes" => [Dict("name" => name, "mesh" => 0)],
        "meshes" => [mesh],
        "materials" => [Dict("name" => name, "pbrMetallicRoughness" => Dict("baseColorFactor" => collect(color),
            "metallicFactor" => 0.3, "roughnessFactor" => 0.6), "doubleSided" => false)],
        "buffers" => [Dict("byteLength" => position(bin))],
        "bufferViews" => views,
        "accessors" => accessors,
    )
    json = Vector{UInt8}(JSON3.write(gltf))
    while length(json) % 4 != 0
        push!(json, UInt8(' '))
    end
    binbytes = take!(bin)
    total = 12 + 8 + length(json) + 8 + length(binbytes)
    mkpath(dirname(abspath(path)))
    open(path, "w") do io
        write(io, UInt32(0x46546C67), UInt32(2), UInt32(total))
        write(io, UInt32(length(json)), UInt32(0x4E4F534A))
        write(io, json)
        write(io, UInt32(length(binbytes)), UInt32(0x004E4942))
        write(io, binbytes)
    end
    return path
end

"""
    read_glb(path) -> (json::Dict, bin::Vector{UInt8})"""
function read_glb(path::AbstractString)
    bytes = read(path)
    reinterpret(UInt32, bytes[1:4])[1] == 0x46546C67 || error("not a GLB file")
    jl = reinterpret(UInt32, bytes[13:16])[1]
    json = JSON3.read(String(bytes[21:(20 + jl)]), Dict{String,Any})
    bl = reinterpret(UInt32, bytes[(21 + jl):(24 + jl)])[1]
    bin = bytes[(29 + jl):(28 + jl + bl)]
    return json, bin
end
