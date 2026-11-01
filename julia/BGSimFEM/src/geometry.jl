# Geometry and meshing with Gmsh (OpenCASCADE kernel): simple primitives, constructive solid
# geometry (union, cut, intersection) and STEP import, meshed with quadratic tetrahedra and
# converted to a Ferrite grid by FerriteGmsh.
#
# A geometry is a nested `Dict` (the `geometry` entry of a part spec, see `spec.jl`):
#
#   {"box":      {"corner": [x, y, z], "size": [dx, dy, dz]}}
#   {"cylinder": {"base": [x, y, z], "axis": [ax, ay, az], "radius": r}}   (axis = full length)
#   {"sphere":   {"center": [x, y, z], "radius": r}}
#   {"union":     [g1, g2, ...]}
#   {"cut":       [g1, g2, ...]}     g1 minus all the others
#   {"intersect": [g1, g2]}
#   {"step":     {"file": "part.step", "scale": 1.0}}   (lengths in the STEP file's unit,
#                                                       converted to metres by OCC; `scale`
#                                                       multiplies the imported shape)
#
# All lengths are metres.

"""
    MeshedPart

The meshed part: the Ferrite grid of quadratic tetrahedra and the Gmsh statistics."""
struct MeshedPart
    grid::Grid
    size::Float64
    order::Int
end

_vec3(v) = Float64[Float64(v[1]), Float64(v[2]), Float64(v[3])]

function _occ_shape(g::AbstractDict, base_dir::AbstractString)
    occ = gmsh.model.occ
    if haskey(g, "box")
        b = g["box"]
        c = _vec3(b["corner"])
        s = _vec3(b["size"])
        return [(3, occ.addBox(c[1], c[2], c[3], s[1], s[2], s[3]))]
    elseif haskey(g, "cylinder")
        b = g["cylinder"]
        c = _vec3(b["base"])
        a = _vec3(b["axis"])
        return [(3, occ.addCylinder(c[1], c[2], c[3], a[1], a[2], a[3], Float64(b["radius"])))]
    elseif haskey(g, "sphere")
        b = g["sphere"]
        c = _vec3(b["center"])
        return [(3, occ.addSphere(c[1], c[2], c[3], Float64(b["radius"])))]
    elseif haskey(g, "union")
        parts = [_occ_shape(x, base_dir) for x in g["union"]]
        length(parts) == 1 && return parts[1]
        out, _ = occ.fuse(parts[1], reduce(vcat, parts[2:end]))
        return out
    elseif haskey(g, "cut")
        parts = [_occ_shape(x, base_dir) for x in g["cut"]]
        length(parts) >= 2 || throw(ArgumentError("`cut` needs a shape and at least one tool"))
        out, _ = occ.cut(parts[1], reduce(vcat, parts[2:end]))
        return out
    elseif haskey(g, "intersect")
        parts = [_occ_shape(x, base_dir) for x in g["intersect"]]
        length(parts) == 2 || throw(ArgumentError("`intersect` takes two shapes"))
        out, _ = occ.intersect(parts[1], parts[2])
        return out
    elseif haskey(g, "step")
        b = g["step"]
        file = isabspath(b["file"]) ? b["file"] : joinpath(base_dir, b["file"])
        isfile(file) || throw(ArgumentError("STEP file not found: $file"))
        gmsh.option.setString("Geometry.OCCTargetUnit", "M")
        out = occ.importShapes(file)
        out = [(Int(d), Int(t)) for (d, t) in out if d == 3]
        isempty(out) && throw(ArgumentError("the STEP file has no solid: $file"))
        s = Float64(get(b, "scale", 1.0))
        s == 1.0 || occ.dilate(out, 0.0, 0.0, 0.0, s, s, s)
        if length(out) > 1
            out, _ = occ.fuse(out[1:1], out[2:end])
        end
        return out
    end
    throw(ArgumentError("unknown geometry entry with keys $(collect(keys(g)))"))
end

"""
    mesh_part(geometry; size, order = 2, base_dir = pwd(), size_min = size / 4) -> MeshedPart

Build the solid `geometry` (see the file comment) with the OpenCASCADE kernel, mesh it with
tetrahedra of target edge length `size` (metres) and element order `order` (2: ten-node
tetrahedra with curved edges on the true geometry) and return the Ferrite grid."""
function mesh_part(geometry::AbstractDict; size::Real, order::Integer = 2,
        base_dir::AbstractString = pwd(), size_min::Real = size / 4, verbose::Bool = false)
    order in (1, 2) || throw(ArgumentError("element order must be 1 or 2"))
    gmsh.initialize()
    try
        gmsh.option.setNumber("General.Terminal", verbose ? 1 : 0)
        gmsh.option.setNumber("General.Verbosity", verbose ? 5 : 1)
        gmsh.model.add("part")
        vols = _occ_shape(geometry, base_dir)
        gmsh.model.occ.removeAllDuplicates()
        gmsh.model.occ.synchronize()
        vols = gmsh.model.getEntities(3)
        isempty(vols) && throw(ArgumentError("the geometry has no volume"))
        gmsh.model.addPhysicalGroup(3, [Int(t) for (_, t) in vols], -1, "part")
        gmsh.option.setNumber("Mesh.MeshSizeMax", Float64(size))
        gmsh.option.setNumber("Mesh.MeshSizeMin", Float64(size_min))
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.optimize("Netgen")
        if order == 2
            gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
            gmsh.model.mesh.setOrder(2)
        end
        grid = FerriteGmsh.togrid(; domain = "part")
        return MeshedPart(_compact(grid), Float64(size), Int(order))
    finally
        gmsh.finalize()
    end
end

# Keep only the nodes that the cells use (Gmsh also returns the nodes of lower-dimensional
# entities), numbered in first-use order.
function _compact(grid::Grid)
    cells = getcells(grid)
    used = falses(getnnodes(grid))
    for c in cells
        for n in c.nodes
            used[n] = true
        end
    end
    all(used) && return grid
    newid = zeros(Int, length(used))
    nodes = Node{3,Float64}[]
    for (i, u) in enumerate(used)
        if u
            push!(nodes, getnodes(grid, i))
            newid[i] = length(nodes)
        end
    end
    C = eltype(cells)
    newcells = C[C(ntuple(k -> newid[c.nodes[k]], length(c.nodes))) for c in cells]
    return Grid(newcells, nodes)
end

"""
    node_coordinates(grid) -> Matrix (3 x nnodes)"""
function node_coordinates(grid::Grid)
    nodes = getnodes(grid)
    X = zeros(3, length(nodes))
    for (i, n) in enumerate(nodes)
        x = n.x
        X[1, i], X[2, i], X[3, i] = x[1], x[2], x[3]
    end
    return X
end

"""
    boundary_triangles(grid; subdivide = true) -> Vector{NTuple{3,Int}}

The boundary surface of a tetrahedral grid, outward oriented. A face that only one cell owns
is on the boundary. With quadratic tetrahedra and `subdivide`, every six-node face becomes four
triangles through its mid-edge nodes (the curved surface); otherwise one triangle of its
corners."""
function boundary_triangles(grid::Grid; subdivide::Bool = true)
    cells = getcells(grid)
    faces = ((1, 3, 2), (1, 2, 4), (2, 3, 4), (1, 4, 3))
    edges = ((1, 2), (2, 3), (3, 1), (1, 4), (2, 4), (3, 4))
    count = Dict{NTuple{3,Int},Int}()
    owner = Dict{NTuple{3,Int},Tuple{Int,Int}}()
    for (ci, c) in enumerate(cells)
        for (fi, f) in enumerate(faces)
            key = Tuple(sort([c.nodes[f[1]], c.nodes[f[2]], c.nodes[f[3]]]))
            count[key] = get(count, key, 0) + 1
            owner[key] = (ci, fi)
        end
    end
    quadratic = length(cells[1].nodes) == 10
    tris = NTuple{3,Int}[]
    for (key, n) in count
        n == 1 || continue
        ci, fi = owner[key]
        c = cells[ci].nodes
        f = faces[fi]
        a, b, d = c[f[1]], c[f[2]], c[f[3]]
        if quadratic && subdivide
            mid(i, j) = begin
                e = findfirst(x -> (x == (i, j) || x == (j, i)), edges)
                c[4 + e]
            end
            ab = mid(f[1], f[2])
            bd = mid(f[2], f[3])
            da = mid(f[3], f[1])
            push!(tris, (a, ab, da), (ab, b, bd), (da, bd, d), (ab, bd, da))
        else
            push!(tris, (a, b, d))
        end
    end
    sort!(tris)
    return tris
end

"""Nodes on the boundary surface (corner and mid-edge nodes)."""
function boundary_nodes(grid::Grid)
    s = Set{Int}()
    for t in boundary_triangles(grid; subdivide = true)
        push!(s, t...)
    end
    return s
end
