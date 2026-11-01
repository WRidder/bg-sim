# Attachment interfaces: a set of FE nodes rigidly tied (RBE2, multipoint constraint) to an
# interface frame with 6 degrees of freedom (3 translations, 3 small rotations).
#
#   u_node = u_I + theta_I x (x_node - p_I)
#
# An interface is given in the part's coordinates by its frame (origin `position`, orientation
# `quaternion` (w, x, y, z) or two axes) and a node selection:
#
#   {"sphere":   {"center": [x, y, z], "radius": r}}
#   {"box":      {"min": [x, y, z], "max": [x, y, z]}}
#   {"cylinder": {"base": [x, y, z], "axis": [ax, ay, az], "radius": r}}   nodes within r of the
#                                                                          segment base..base+axis
#   "surface": true (default)   only nodes on the boundary surface
#
# The first interface defines the body's reference frame R: the reduction runs in R
# coordinates, and the reduced model is "clamped" at interface 1 (Craig–Bampton with the
# reference interface fixed, the floating frame attached to it).

"""
    Interface(name, position, rotation, nodes)

`rotation` is the 3x3 rotation of the interface frame (columns = its axes) and `position` its
origin, both in the coordinates the grid has at the time (part or R); `nodes` the tied nodes."""
struct Interface
    name::String
    position::Vector{Float64}
    rotation::Matrix{Float64}
    nodes::Vector{Int}
end

function quat_to_rot(q)
    w, x, y, z = q ./ sqrt(sum(abs2, q))
    return [1 - 2(y^2 + z^2) 2(x * y - w * z) 2(x * z + w * y);
            2(x * y + w * z) 1 - 2(x^2 + z^2) 2(y * z - w * x);
            2(x * z - w * y) 2(y * z + w * x) 1 - 2(x^2 + y^2)]
end

function rot_to_quat(R)
    t = R[1, 1] + R[2, 2] + R[3, 3]
    if t > 0
        s = 0.5 / sqrt(t + 1)
        q = [0.25 / s, (R[3, 2] - R[2, 3]) * s, (R[1, 3] - R[3, 1]) * s, (R[2, 1] - R[1, 2]) * s]
    elseif R[1, 1] > R[2, 2] && R[1, 1] > R[3, 3]
        s = 2 * sqrt(1 + R[1, 1] - R[2, 2] - R[3, 3])
        q = [(R[3, 2] - R[2, 3]) / s, 0.25s, (R[1, 2] + R[2, 1]) / s, (R[1, 3] + R[3, 1]) / s]
    elseif R[2, 2] > R[3, 3]
        s = 2 * sqrt(1 + R[2, 2] - R[1, 1] - R[3, 3])
        q = [(R[1, 3] - R[3, 1]) / s, (R[1, 2] + R[2, 1]) / s, 0.25s, (R[2, 3] + R[3, 2]) / s]
    else
        s = 2 * sqrt(1 + R[3, 3] - R[1, 1] - R[2, 2])
        q = [(R[2, 1] - R[1, 2]) / s, (R[1, 3] + R[3, 1]) / s, (R[2, 3] + R[3, 2]) / s, 0.25s]
    end
    q[1] < 0 && (q .*= -1)
    return q ./ sqrt(sum(abs2, q))
end

function _frame_rotation(d::AbstractDict)
    if haskey(d, "quaternion")
        return quat_to_rot(Float64.(collect(d["quaternion"])))
    elseif haskey(d, "x") && haskey(d, "z")
        x = Float64.(collect(d["x"]))
        z = Float64.(collect(d["z"]))
        x ./= norm(x)
        z = z .- dot(z, x) .* x
        z ./= norm(z)
        y = cross(z, x)
        return hcat(x, y, z)
    end
    return Matrix{Float64}(I, 3, 3)
end

function _select_nodes(X::AbstractMatrix, sel::AbstractDict, surface::Union{Nothing,Set{Int}})
    pick = Int[]
    for i in axes(X, 2)
        surface === nothing || i in surface || continue
        x = X[:, i]
        ok = if haskey(sel, "sphere")
            s = sel["sphere"]
            norm(x .- _vec3(s["center"])) <= Float64(s["radius"])
        elseif haskey(sel, "box")
            s = sel["box"]
            lo, hi = _vec3(s["min"]), _vec3(s["max"])
            all(lo .<= x .<= hi)
        elseif haskey(sel, "cylinder")
            s = sel["cylinder"]
            b, a = _vec3(s["base"]), _vec3(s["axis"])
            t = clamp(dot(x .- b, a) / dot(a, a), 0.0, 1.0)
            norm(x .- (b .+ t .* a)) <= Float64(s["radius"])
        else
            throw(ArgumentError("unknown node selection $(collect(keys(sel)))"))
        end
        ok && push!(pick, i)
    end
    return pick
end

"""
    make_interfaces(grid, specs) -> Vector{Interface}

The interfaces of the part spec (part coordinates). Each needs at least three non-collinear
nodes, and no node may belong to two interfaces."""
function make_interfaces(grid::Grid, specs::AbstractVector)
    X = node_coordinates(grid)
    surf = boundary_nodes(grid)
    out = Interface[]
    seen = Set{Int}()
    for (k, s) in enumerate(specs)
        name = String(get(s, "name", string('A' + k - 1)))
        p = _vec3(s["position"])
        R = _frame_rotation(s)
        surface = Bool(get(s, "surface", true))
        nodes = _select_nodes(X, s["select"], surface ? surf : nothing)
        length(nodes) >= 3 || throw(ArgumentError("interface $name selects $(length(nodes)) nodes; it needs at least 3 (check `select`)"))
        isempty(intersect(seen, nodes)) || throw(ArgumentError("interface $name shares nodes with an earlier interface"))
        union!(seen, nodes)
        push!(out, Interface(name, p, R, nodes))
    end
    isempty(out) && throw(ArgumentError("a part needs at least one interface (the reference frame)"))
    length(out) <= 4 || throw(ArgumentError("at most 4 interfaces are supported, got $(length(out))"))
    return out
end

"""
    to_reference_frame!(grid, interfaces) -> (grid, interfaces in R, p1, R1)

Move the grid into the reference frame R of interface 1: x_R = R1' (x - p1)."""
function to_reference_frame(grid::Grid, ifs::Vector{Interface})
    p1 = ifs[1].position
    R1 = ifs[1].rotation
    nodes = [Node(Vec{3}(Tuple(R1' * (collect(n.x) .- p1)))) for n in getnodes(grid)]
    g = Grid(getcells(grid), nodes)
    out = [Interface(f.name, R1' * (f.position .- p1), R1' * f.rotation, f.nodes) for f in ifs]
    return g, out, p1, R1
end

"""
    rbe2_transform(fe, interfaces) -> (T, nfree)

The sparse map from the independent dofs to all dofs: the dofs of the nodes that no interface
ties (in dof order, `1:nfree`), then six per interface (translation, rotation in R
coordinates)."""
function rbe2_transform(fe::FEModel, ifs::Vector{Interface})
    n = ndofs_fe(fe)
    tied = falses(nnodes_fe(fe))
    for f in ifs, i in f.nodes
        tied[i] = true
    end
    freedofs = sort!([fe.nodedofs[a, i] for i in 1:nnodes_fe(fe) for a in 1:3 if !tied[i]])
    nfree = length(freedofs)
    I_ = Int[]
    J_ = Int[]
    V_ = Float64[]
    for (k, d) in enumerate(freedofs)
        push!(I_, d); push!(J_, k); push!(V_, 1.0)
    end
    for (j, f) in enumerate(ifs)
        c0 = nfree + 6(j - 1)
        for i in f.nodes
            r = fe.X[:, i] .- f.position
            # u = u_I + theta x r = u_I - [r]x theta
            rx = [0 -r[3] r[2]; r[3] 0 -r[1]; -r[2] r[1] 0]
            for a in 1:3
                d = fe.nodedofs[a, i]
                push!(I_, d); push!(J_, c0 + a); push!(V_, 1.0)
                for b in 1:3
                    v = -rx[a, b]
                    v == 0 && continue
                    push!(I_, d); push!(J_, c0 + 3 + b); push!(V_, v)
                end
            end
        end
    end
    T = sparse(I_, J_, V_, n, nfree + 6 * length(ifs))
    return T, nfree
end
