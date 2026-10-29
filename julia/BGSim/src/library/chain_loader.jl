# Work package J-MB15: the joint-chain record loader, `lumpInto`, inverse dynamics and gravity
# compensation. (The file is `chain_loader.jl`, not `loader.jl`: `loader.jl` is the J1.3 block
# loader of this module.)
#
# A chain is described by plain records that map 1:1 onto SDF `<link>` / `<joint>`. The loader turns
# them into a model fragment (nodes + connections of the model document) built from the J-MB9
# composites; the numeric functions work on the same records with the screw core of `src/mech/`.

using LinearAlgebra: Diagonal, cross, dot, eigen, norm, det, I, Symmetric
using StaticArrays: SVector, SMatrix

const _Mech = BGSim.Mech

# ---------------------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------------------

"""
    LinkRecord(name; mass, com = [0,0,0], inertia = [..3 principal moments..], axes = I)
    LinkRecord(name; mass, com, tensor = [3x3 inertia about the CoM in the link frame])

A rigid link. SDF mapping: `<link name>` with `<inertial>`; the **link frame** is the frame of the
SDF link, which here is the frame of the joint that moves it (the child side of `JointRecord`, at
joint position zero).

| field | SDF | meaning |
| --- | --- | --- |
| `name` | `<link name>` | unique link name; `"world"` is reserved for the fixed base |
| `mass` | `<inertial><mass>` | kg, positive |
| `com` | `<inertial><pose>` position | centre of mass in the link frame, m |
| `inertia` | `<inertial><inertia>` after diagonalisation | principal moments about the CoM, kg m^2 |
| `axes` | `<inertial><pose>` rotation | rotation whose columns are the principal axes in the link frame |

The `tensor` form diagonalises a full inertia tensor (`ixx, ixy, ...`) into `inertia`/`axes`
(`RigidBody3D` carries a diagonal principal inertia, so the body frame is the principal frame).
"""
struct LinkRecord
    name::String
    mass::Float64
    com::Vector{Float64}
    inertia::Vector{Float64}
    axes::Matrix{Float64}
end

function LinkRecord(name; mass, com = zeros(3), inertia = nothing, axes = Matrix(1.0I, 3, 3), tensor = nothing)
    mass > 0 || throw(ArgumentError("link `$name`: the mass must be positive, got $mass"))
    if tensor !== nothing
        inertia === nothing || throw(ArgumentError("link `$name`: give `inertia` or `tensor`, not both"))
        J, R = _principal(Matrix{Float64}(tensor))
        return LinkRecord(String(name), Float64(mass), Float64.(collect(com)), J, R)
    end
    inertia === nothing && throw(ArgumentError("link `$name`: `inertia` (principal moments) or `tensor` is required"))
    J = Float64.(collect(inertia))
    length(J) == 3 && all(>(0), J) || throw(ArgumentError("link `$name`: the principal moments must be 3 positive numbers, got $J"))
    A = Matrix{Float64}(axes)
    maximum(abs.(A * A' - I)) < 1e-9 && det(A) > 0 || throw(ArgumentError("link `$name`: `axes` must be a proper rotation matrix"))
    return LinkRecord(String(name), Float64(mass), Float64.(collect(com)), J, A)
end

"""Principal moments and a proper principal-axes rotation of a symmetric inertia tensor."""
function _principal(T)
    maximum(abs.(T - T')) <= 1e-12 * max(1.0, maximum(abs.(T))) || throw(ArgumentError("the inertia tensor is not symmetric"))
    E = eigen(Symmetric(T))
    all(>(0), E.values) || throw(ArgumentError("the inertia tensor is not positive definite"))
    R = Matrix(E.vectors)
    det(R) < 0 && (R[:, 3] .*= -1)
    return Vector(E.values), R
end

"""
    joint_pose(; xyz = [0,0,0], rpy = nothing, quat = nothing) -> (R, p)

A pose `(rotation matrix, position)` from SDF-style `xyz` and `rpy` (roll about x, pitch about y,
yaw about z, `R = Rz(yaw) Ry(pitch) Rx(roll)`) or from a quaternion `(w, x, y, z)`.
"""
function joint_pose(; xyz = zeros(3), rpy = nothing, quat = nothing)
    p = Float64.(collect(xyz))
    length(p) == 3 || throw(ArgumentError("pose: `xyz` needs 3 components"))
    rpy !== nothing && quat !== nothing && throw(ArgumentError("pose: give `rpy` or `quat`, not both"))
    if quat !== nothing
        w, x, y, z = Float64.(collect(quat))
        s = w * w + x * x + y * y + z * z
        R = [(w * w + x * x - y * y - z * z) 2*(x * y - w * z) 2*(x * z + w * y)
            2*(x * y + w * z) (w * w - x * x + y * y - z * z) 2*(y * z - w * x)
            2*(x * z - w * y) 2*(y * z + w * x) (w * w - x * x - y * y + z * z)] ./ s
        return R, p
    end
    r, pi_, y = rpy === nothing ? (0.0, 0.0, 0.0) : Float64.(collect(rpy))
    Rx = [1.0 0 0; 0 cos(r) -sin(r); 0 sin(r) cos(r)]
    Ry = [cos(pi_) 0 sin(pi_); 0 1.0 0; -sin(pi_) 0 cos(pi_)]
    Rz = [cos(y) -sin(y) 0; sin(y) cos(y) 0; 0 0 1.0]
    return Rz * Ry * Rx, p
end

"""
    JointRecord(name; parent, child, type = :revolute, axis = [0,0,1], origin = joint_pose(), ...)

A joint. SDF mapping: `<joint name type>` with `<parent>`, `<child>`, `<pose relative_to=parent>`
(`origin`: the joint frame in the **parent link frame**, at joint position zero) and
`<axis><xyz>` (`axis`, a vector **in the joint frame**). The child link frame equals the joint
frame at position zero and is the joint frame rotated by `q` about `axis` (or translated by `q`
along it) afterwards.

* `type`: `:revolute`, `:prismatic` or `:fixed` (a fixed joint has no coordinate; it is merged with
  [`lumpInto`](@ref) before a model is loaded).
* `parent = "world"` attaches to the fixed base.
* `limits = (lower, upper)` (SDF `<limit>`): the loader uses the `*Limit` joint variant.
* `kr, kt, br, bt` (optional): stiffness/damping of the held directions of this joint; they default
  to the `stiffness`/`damping_ratio` options of [`load_chain`](@ref).
"""
struct JointRecord
    name::String
    parent::String
    child::String
    type::Symbol
    axis::Vector{Float64}
    R::Matrix{Float64}
    p::Vector{Float64}
    limits::Union{Nothing,Tuple{Float64,Float64}}
    kr::Union{Nothing,Float64}
    kt::Union{Nothing,Float64}
    br::Union{Nothing,Float64}
    bt::Union{Nothing,Float64}
end

function JointRecord(name; parent, child, type = :revolute, axis = [0.0, 0.0, 1.0], origin = joint_pose(),
    limits = nothing, kr = nothing, kt = nothing, br = nothing, bt = nothing)
    type in (:revolute, :prismatic, :fixed) || throw(ArgumentError("joint `$name`: unknown type `$type` (revolute, prismatic, fixed)"))
    a = Float64.(collect(axis))
    length(a) == 3 && norm(a) > 0 || throw(ArgumentError("joint `$name`: `axis` must be a non-zero 3-vector"))
    R, p = origin
    lim = limits === nothing ? nothing : (Float64(limits[1]), Float64(limits[2]))
    f(x) = x === nothing ? nothing : Float64(x)
    return JointRecord(String(name), String(parent), String(child), type, a ./ norm(a),
        Matrix{Float64}(R), Float64.(collect(p)), lim, f(kr), f(kt), f(br), f(bt))
end

"""
    JointChain(links, joints)

The records of a kinematic tree with a fixed base: `joints` are in tree order (a joint's parent link
is the child of an earlier joint or `"world"`), the **joint coordinates** `q`, `qd`, `qdd` and
`tau` of every numeric function are indexed over the non-fixed joints in that order.
Exactly one joint has `parent = "world"` (the base). Validation errors name the record.
"""
struct JointChain
    links::Vector{LinkRecord}
    joints::Vector{JointRecord}
    function JointChain(links, joints)
        ln = Dict(l.name => l for l in links)
        length(ln) == length(links) || throw(ArgumentError("duplicate link names in the chain records"))
        haskey(ln, "world") && throw(ArgumentError("`world` is reserved for the base; it cannot be a link name"))
        seen = Set{String}(["world"])
        names = Set{String}()
        nroot = 0
        for j in joints
            j.name in names && throw(ArgumentError("duplicate joint name `$(j.name)`"))
            push!(names, j.name)
            haskey(ln, j.child) || throw(ArgumentError("joint `$(j.name)`: unknown child link `$(j.child)`"))
            j.parent in seen || throw(ArgumentError("joint `$(j.name)`: parent `$(j.parent)` is not `world` or the child of an earlier joint"))
            j.child in seen && throw(ArgumentError("joint `$(j.name)`: child `$(j.child)` already has a parent joint (a closed loop is not a chain)"))
            push!(seen, j.child)
            j.parent == "world" && (nroot += 1)
        end
        for l in links
            l.name in seen || throw(ArgumentError("link `$(l.name)` is not attached by any joint"))
        end
        nroot == 1 || throw(ArgumentError("exactly one joint must have parent `world`, got $nroot"))
        return new(collect(links), collect(joints))
    end
end

_ndof(c::JointChain) = count(j -> j.type != :fixed, c.joints)

# ---------------------------------------------------------------------------------------
# Effective frames. The joint axis is the local z of the joint frame (J-MB9), so a joint with a
# general axis a is placed with a rotation `Rp` that takes z onto a. Per joint:
#   RN, pN   joint-side frame F = joint frame o Rp, in the parent's *post-joint* frame
#   bpose    body (CoM + principal axes) pose in the post-joint frame F o Rz(q)
# and the post-joint frame of a link is F rotated by q about z.
# ---------------------------------------------------------------------------------------

function _align_z(a)
    ez = [0.0, 0.0, 1.0]
    v = cross(ez, a)
    c = dot(ez, a)
    if c < -1 + 1e-12
        return [1.0 0 0; 0 -1.0 0; 0 0 -1.0]
    end
    V = [0.0 -v[3] v[2]; v[3] 0.0 -v[1]; -v[2] v[1] 0.0]
    return Matrix(1.0I, 3, 3) + V + V * V / (1 + c)
end

struct _Eff
    joint::JointRecord
    link::LinkRecord
    parent::Int            # index of the parent joint in `joints`, 0 = world
    Rp::Matrix{Float64}    # placement rotation (z -> axis)
    RN::Matrix{Float64}    # F frame in the parent's post-joint frame
    pN::Vector{Float64}
    Rb::Matrix{Float64}    # body frame in the post-joint frame
    pb::Vector{Float64}    # = CoM in the post-joint frame
end

function _effective(chain::JointChain)
    idx = Dict(j.child => i for (i, j) in enumerate(chain.joints))
    ln = Dict(l.name => l for l in chain.links)
    eff = _Eff[]
    for j in chain.joints
        link = ln[j.child]
        Rp = j.type == :fixed ? Matrix(1.0I, 3, 3) : _align_z(j.axis)
        par = j.parent == "world" ? 0 : idx[j.parent]
        Rpar = par == 0 ? Matrix(1.0I, 3, 3) : eff[par].Rp
        # joint frame in the parent link frame (R, p) -> in the parent post-joint frame
        RN = Rpar' * j.R * Rp
        pN = Rpar' * j.p
        push!(eff, _Eff(j, link, par, Rp, RN, pN, Rp' * link.axes, Rp' * link.com))
    end
    return eff
end

# ---------------------------------------------------------------------------------------
# Recursive Newton-Euler in spatial (6-vector, angular first) form with the screw core.
# ---------------------------------------------------------------------------------------


function _ad6(V)
    return Matrix(_Mech.ad(_Mech.Twist{6}(SVector{6}(V...))))
end

function _full_inertia(l::LinkRecord, Rp)
    Rb = Rp' * l.axes
    return Rb * Diagonal(l.inertia) * Rb'
end

"""Joint torques/forces and the wrench each joint transmits (frame: the post-joint link frame)."""
function _rne(chain::JointChain, q, qd, qdd, g)
    eff = _effective(chain)
    n = length(eff)
    nd = _ndof(chain)
    for (nm, v) in (("q", q), ("qd", qd), ("qdd", qdd))
        length(v) == nd || throw(ArgumentError("`$nm` has $(length(v)) entries, the chain has $nd joint coordinates"))
    end
    k = 0
    X = Vector{Matrix{Float64}}(undef, n)     # Ad(g_i^-1): parent post-joint twist -> own
    V = Vector{Vector{Float64}}(undef, n)
    A = Vector{Vector{Float64}}(undef, n)
    S = Vector{Union{Nothing,Vector{Float64}}}(undef, n)
    gs = Vector{Any}(undef, n)
    for i in 1:n
        e = eff[i]
        t = e.joint.type
        qi = qdi = qddi = 0.0
        if t != :fixed
            k += 1
            qi, qdi, qddi = q[k], qd[k], qdd[k]
        end
        R, p = if t == :revolute
            Rz = [cos(qi) -sin(qi) 0.0; sin(qi) cos(qi) 0.0; 0.0 0.0 1.0]
            e.RN * Rz, e.pN
        elseif t == :prismatic
            e.RN, e.pN + e.RN * [0.0, 0.0, qi]
        else
            e.RN, e.pN
        end
        gi = _Mech.SE3(R, p)
        gs[i] = gi
        X[i] = Matrix(_Mech.Ad(inv(gi)))
        s = t == :revolute ? [0.0, 0.0, 1.0, 0, 0, 0] : t == :prismatic ? [0.0, 0, 0, 0, 0, 1.0] : nothing
        S[i] = s
        Vp = e.parent == 0 ? zeros(6) : V[e.parent]
        Ap = e.parent == 0 ? [0.0, 0, 0, 0, 0, g] : A[e.parent]
        Vi = X[i] * Vp
        Ai = X[i] * Ap
        if s !== nothing
            Vi = Vi + s * qdi
            Ai = Ai + _ad6(Vi) * (s * qdi) + s * qddi
        end
        V[i], A[i] = Vi, Ai
    end
    F = Vector{Vector{Float64}}(undef, n)
    for i in 1:n
        e = eff[i]
        Ic = _full_inertia(e.link, e.Rp)
        M = Matrix(_Mech.spatial_inertia(e.link.mass, Ic, SVector{3}(e.Rp' * e.link.com)))
        F[i] = M * A[i] - _ad6(V[i])' * (M * V[i])
    end
    f = [copy(x) for x in F]
    for i in n:-1:1
        par = eff[i].parent
        par == 0 && continue
        # wrench of frame i expressed in the parent post-joint frame: Ad(g_i^-1)' f_i
        f[par] += X[i]' * f[i]
    end
    tau = Float64[]
    for i in 1:n
        S[i] === nothing || push!(tau, dot(S[i], f[i]))
    end
    return tau, f, eff
end

"""
    inverse_dynamics(chain, q, qd, qdd; g = 9.81) -> tau

Recursive Newton-Euler over the records: the joint torques (revolute) or forces (prismatic) that
produce `qdd` at `(q, qd)` with gravity `g` along the world -z, for the joints in record order
(fixed joints carry no coordinate). Spatial 6-vector formulation with the screw core
(`Ad`, `ad`, `spatial_inertia`), angular first.
"""
inverse_dynamics(chain::JointChain, q, qd, qdd; g = 9.81) = _rne(chain, q, qd, qdd, g)[1]

"""
    gravity_compensation(chain, q; g = 9.81) -> tau

The joint torques/forces that hold the pose `q` at rest: `inverse_dynamics` with zero rates and
accelerations, equal to the gradient of the potential energy.
"""
gravity_compensation(chain::JointChain, q; g = 9.81) =
    inverse_dynamics(chain, q, zeros(length(q)), zeros(length(q)); g = g)

# ---------------------------------------------------------------------------------------
# lumpInto
# ---------------------------------------------------------------------------------------

"""
    lumpInto(chain, parent) -> JointChain

Merge every rigidly attached child of the link `parent` into it: each `:fixed` joint whose parent
is `parent` (recursively through fixed joints) removes its child link and adds the child's mass,
centre of mass and inertia to `parent` (parallel axis theorem, `I = sum(I_i + m_i (|d|^2 1 - d d')`
about the new centre of mass). Joints that hung on a lumped child are re-attached to `parent` with
their origin composed with the fixed joint's pose.

The merged inertia tensor is generally not diagonal in the link frame. `RigidBody3D` carries a
diagonal principal inertia, so the tensor is re-diagonalised: `LinkRecord.axes` holds the principal
axes rotation, and the loader mounts the body on the post-joint frame with exactly that rotation
and the new centre of mass (the link-side transformer of the joint), so the joint frames of
the children keep their meaning. Throws when `parent` is unknown.
"""
function lumpInto(chain::JointChain, parent::AbstractString)
    parent = String(parent)
    any(l -> l.name == parent, chain.links) || throw(ArgumentError("lumpInto: unknown link `$parent`"))
    ln = Dict(l.name => l for l in chain.links)
    # poses (R, p) of every link merged into `parent`, in the parent link frame
    merged = Dict{String,Tuple{Matrix{Float64},Vector{Float64}}}(parent => (Matrix(1.0I, 3, 3), zeros(3)))
    removed = Set{String}()
    gone = Set{String}()
    changed = true
    while changed
        changed = false
        for j in chain.joints
            if j.type == :fixed && haskey(merged, j.parent) && !(j.child in gone)
                Rp, pp = merged[j.parent]
                merged[j.child] = (Rp * j.R, pp + Rp * j.p)
                push!(gone, j.child)
                push!(removed, j.name)
                changed = true
            end
        end
    end
    m = 0.0
    csum = zeros(3)
    for (nm, (R, p)) in merged
        l = ln[nm]
        m += l.mass
        csum += l.mass * (p + R * l.com)
    end
    c = csum / m
    T = zeros(3, 3)
    for (nm, (R, p)) in merged
        l = ln[nm]
        Ra = R * l.axes
        d = p + R * l.com - c
        T += Ra * Diagonal(l.inertia) * Ra' + l.mass * (dot(d, d) * Matrix(1.0I, 3, 3) - d * d')
    end
    J, Ax = _principal(T)
    newlink = LinkRecord(parent, m, c, J, Ax)
    links = [l.name == parent ? newlink : l for l in chain.links if !(l.name in gone)]
    joints = JointRecord[]
    for j in chain.joints
        j.name in removed && continue
        if haskey(merged, j.parent) && j.parent != parent
            Rp, pp = merged[j.parent]
            j = JointRecord(j.name, parent, j.child, j.type, j.axis, Rp * j.R, pp + Rp * j.p, j.limits, j.kr, j.kt, j.br, j.bt)
        end
        push!(joints, j)
    end
    return JointChain(links, joints)
end

# ---------------------------------------------------------------------------------------
# The model fragment
# ---------------------------------------------------------------------------------------

_num(x) = string(Float64(x))
_vecs(v) = "[" * join((_num(x) for x in v), ", ") * "]"

function _posepar(R, p)
    q = _Mech.quat_from_rotation(SMatrix{3,3}(R))
    return Dict{String,Any}("qw" => _num(q.w), "qx" => _num(q.x), "qy" => _num(q.y), "qz" => _num(q.z),
        "x" => _num(p[1]), "y" => _num(p[2]), "z" => _num(p[3]))
end

function _inv_pose(R, p)
    return R', -(R' * p)
end

function _node(id, name, block; params = Dict{String,Any}(), starts = Dict{String,Any}())
    return Dict{String,Any}("id" => id, "name" => id, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0), "params" => params,
        "constants" => Dict{String,Any}(), "starts" => starts)
end
_ref(r) = Dict{String,Any}("ref" => r)

"""
    load_chain(chain; stiffness = 1e7, damping_ratio = 0.7, g0 = 9.81, q0 = zeros, qdd0 = zeros,
               deflect = true, drives = nothing, prefix = "") -> Dict

Emit the chain as a model fragment `Dict("nodes" => ..., "connections" => ..., "drive_ports" => ...,
"pose_signals" => ..., "bodies" => ...)`, ready to merge into a model's `diagram` (use
[`chain_model`](@ref) to wrap it into a runnable document).

Per joint `J` (child link `C`, parent link `P`) the nodes are, with `prefix` prepended to every id:

| id | block | role |
| --- | --- | --- |
| `world`, `world_pose` | `GroundSpatial`, `LocalPose3D` | the fixed base (identity pose) |
| `J_t` | `FixedTransform3DNeutral` | joint frame (rotated so its local z is the joint axis) in the frame of body `P` (`N - c_P` bookkeeping: the CoM and principal-axes frame of `P`) |
| `J` | `Revolute3D` / `Prismatic3D` (`...Limit` with limits) | compliant joint, stiffness `stiffness` (or the record's `kr`, `kt`), damping at `damping_ratio` of critical for the distal mass (translations) and a 0.3 kg m^2 reference inertia (rotations) |
| `J_l` | `FixedTransform3DNeutral` | post-joint frame to the body frame of `C` (CoM, principal axes, back-rotation of the placement) |
| `C_bj`, `C` | 1-junction, `RigidBody3D` | the body junction and the body (mass, principal inertia, `g0`) |
| `J_ln`, `J_ca`, `J_cb`, `J_lc`, `J_cc` | `LocalPose3D`/`ComposePose3D` | algebraic poses: `J_cb/g` is the post-joint frame of `J` in the world, `J_cc/g` the pose of body `C` (fixed base) |

Every element bonds element -> junction. **Drive ports are exposed**: `fragment["drive_ports"][J]`
is `(node = J, port = "drive")` (a `Power{Rotation}` / `Power{Translation}` port taking the joint
effort). When `drives` is a `Dict(joint name => constant torque)` the loader attaches
`J_drive` (`MSe`) fed by `J_tau` (`Constant`) to each listed joint; otherwise the port is left open
for the user to attach drives or servos.

`q0` is the initial joint coordinates (record order over the non-fixed joints) and `qdd0` the joint
acceleration the start is built for: with `qdd0` given the revolute joints start at the consistent
deflections `-(joint wrench)/k` of the Newton-Euler model (so the stiff modes are not excited);
prismatic joints start undeflected. `deflect = false` starts every joint undeflected, so the composed poses at t = 0 are the exact rigid forward kinematics.
"""
function load_chain(chain::JointChain; stiffness = 1.0e7, damping_ratio = 0.7, g0 = 9.81,
    q0 = zeros(_ndof(chain)), qdd0 = zeros(_ndof(chain)), deflect = true, drives = nothing, prefix = "")
    any(j -> j.type == :fixed, chain.joints) &&
        throw(ArgumentError("load_chain: the chain has fixed joints (" *
                            join([j.name for j in chain.joints if j.type == :fixed], ", ") *
                            "); merge them first with lumpInto(chain, parent)"))
    eff = _effective(chain)
    n = length(eff)
    pf(s) = prefix * s
    nodes = Dict{String,Any}[]
    conns = Dict{String,Any}[]
    cid = Ref(0)
    bond!(a, ap, b, bp) = push!(conns, _conn(pf("c$(cid[] += 1)"), "bond", a, ap, b, bp))
    sig!(a, ap, b, bp) = push!(conns, _conn(pf("c$(cid[] += 1)"), "signal", a, ap, b, bp))
    # distal mass for the damping of the translations
    distal = [eff[i].link.mass for i in 1:n]
    for i in n:-1:1
        eff[i].parent == 0 || (distal[eff[i].parent] += distal[i])
    end
    # consistent starts
    _, wr, _ = _rne(chain, q0, zeros(length(q0)), qdd0, g0)
    push!(nodes, _node(pf("world"), "World", _ref("stdlib:multibond/GroundSpatial")))
    push!(nodes, _node(pf("world_pose"), "WorldPose", _ref("stdlib:spatial/LocalPose3D");
        params = _posepar(Matrix(1.0I, 3, 3), zeros(3))))
    drive_ports = Dict{String,Any}()
    bodies = Dict{String,String}()
    wprev(i) = eff[i].parent == 0 ? pf("world_pose") : pf(eff[eff[i].parent].joint.name * "_cb")
    for i in 1:n
        e = eff[i]
        j = e.joint
        jn = pf(j.name)
        bj, bn = pf(e.link.name * "_bj"), pf(e.link.name)
        # joint frame in the parent body frame: inv(F) o B_parent, B_parent = (axes, com) in the parent post-joint frame
        Rb_par, pb_par = e.parent == 0 ? (Matrix(1.0I, 3, 3), zeros(3)) : (eff[e.parent].Rb, eff[e.parent].pb)
        Rf, pf_ = _inv_pose(e.RN, e.pN)
        gR, gp = Rf * Rb_par, pf_ + Rf * pb_par
        push!(nodes, _node(jn * "_t", j.name * " in", _ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _posepar(gR, gp)))
        bond!(jn * "_t", "a", jn, "parent")
        if e.parent == 0
            bond!(pf("world"), "p", jn * "_t", "b")
        else
            bond!(jn * "_t", "b", pf(eff[e.parent].link.name * "_bj"), nothing)
        end
        kk = stiffness
        kr = something(j.kr, kk)
        kt = something(j.kt, kk)
        br = something(j.br, 2 * damping_ratio * sqrt(kr * 0.3))
        bt = something(j.bt, 2 * damping_ratio * sqrt(kt * distal[i]))
        k = count(x -> x.joint.type != :fixed, eff[1:i])
        params = Dict{String,Any}("kt" => _num(kt), "kr" => _num(kr), "bt" => _num(bt), "br" => _num(br),
            "q0" => _num(q0[k]))
        starts = Dict{String,Any}()
        if j.type == :revolute && deflect
            n3 = -(wr[i][1:3])
            f3 = -(wr[i][4:6])
            starts["dth"] = _vecs(n3[1:2] ./ kr)
            starts["dl"] = _vecs(f3 ./ kt)
        end
        block = "stdlib:spatial/" * (j.type == :revolute ? "Revolute3D" : "Prismatic3D")
        if j.limits !== nothing
            block *= "Limit"
            params["lower"] = _num(j.limits[1])
            params["upper"] = _num(j.limits[2])
        end
        push!(nodes, _node(jn, j.name, _ref(block); params = params, starts = starts))
        push!(nodes, _node(jn * "_l", j.name * " out", _ref("stdlib:multibond/FixedTransform3DNeutral");
            params = _posepar(e.Rb, e.pb)))
        push!(nodes, _node(bj, e.link.name * " junction", Dict{String,Any}("junction" => "1")))
        push!(nodes, _node(bn, e.link.name, _ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => _num(e.link.mass), "J" => _vecs(e.link.inertia), "g0" => _num(g0))))
        bodies[e.link.name] = bn
        bond!(jn, "child", jn * "_l", "a")
        bond!(jn * "_l", "b", bj, nothing)
        bond!(bn, "p", bj, nothing)
        drive_ports[j.name] = (node = jn, port = "drive")
        if drives !== nothing && haskey(drives, j.name)
            push!(nodes, _node(jn * "_drive", j.name * " drive", _ref("stdlib:bondgraph/MSe")))
            push!(nodes, _node(jn * "_tau", j.name * " torque", _ref("stdlib:sources/Constant");
                params = Dict{String,Any}("value" => _num(drives[j.name]))))
            sig!(jn * "_tau", "y", jn * "_drive", "u")
            bond!(jn * "_drive", "p", jn, "drive")
        end
        # algebraic poses: W_i = W_{i-1} o (Rp_par' R_j Rp_i, Rp_par' p_j) o Rz(q); body = W_i o (Rb, pb)
        push!(nodes, _node(jn * "_ln", j.name * " N", _ref("stdlib:spatial/LocalPose3D");
            params = _posepar(e.RN, e.pN)))
        push!(nodes, _node(jn * "_lc", j.name * " body", _ref("stdlib:spatial/LocalPose3D");
            params = _posepar(e.Rb, e.pb)))
        push!(nodes, _node(jn * "_ca", j.name * " A", _ref("stdlib:multibond/ComposePose3D")))
        push!(nodes, _node(jn * "_cb", j.name * " W", _ref("stdlib:multibond/ComposePose3D")))
        push!(nodes, _node(jn * "_cc", e.link.name * " pose", _ref("stdlib:multibond/ComposePose3D")))
        sig!(wprev(i), "g", jn * "_ca", "gp")
        sig!(jn * "_ln", "g", jn * "_ca", "gl")
        sig!(jn * "_ca", "g", jn * "_cb", "gp")
        sig!(jn, "pose", jn * "_cb", "gl")
        sig!(jn * "_cb", "g", jn * "_cc", "gp")
        sig!(jn * "_lc", "g", jn * "_cc", "gl")
        sig!(jn * "_cc", "g", bn, "g")
    end
    return Dict{String,Any}("nodes" => nodes, "connections" => conns, "drive_ports" => drive_ports,
        "bodies" => bodies,
        "pose_signals" => Dict(e.link.name => (node = pf(e.joint.name * "_cc"), port = "g") for e in eff))
end

function _conn(id, kind, a, ap, b, bp)
    from = Dict{String,Any}("node" => a)
    ap === nothing || (from["port"] = ap)
    to = Dict{String,Any}("node" => b)
    bp === nothing || (to["port"] = bp)
    return Dict{String,Any}("id" => id, "kind" => kind, "from" => from, "to" => to)
end

"""
    chain_model(fragment; name = "Chain", t_end = 1.0, points = 101, reltol = 1e-9, abstol = 1e-11) -> Dict

Wrap a [`load_chain`](@ref) fragment into a complete model document (plan 3.3) that
`IR.parse_model` accepts.
"""
function chain_model(fragment; name = "Chain", t_end = 1.0, points = 101, reltol = 1.0e-9, abstol = 1.0e-11,
    solver = "Rodas5P")
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => String(name),
        "diagram" => Dict{String,Any}("nodes" => Any[fragment["nodes"]...],
            "connections" => Any[fragment["connections"]...], "subsystemPorts" => Any[], "annotations" => Any[]),
        "settings" => Dict{String,Any}("t_start" => 0.0, "t_end" => t_end, "solver" => solver,
            "reltol" => reltol, "abstol" => abstol, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points), "event_limit" => 10000),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[])
end
