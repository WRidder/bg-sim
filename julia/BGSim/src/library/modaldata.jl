# Reduced-model files of FEM flexible bodies (`stdlib:spatial/ModalBody3D`).
#
# The offline tool `julia/BGSimFEM` meshes a part, reduces it with Craig–Bampton and writes a
# JSON file of format `bgsim.modal-body` (version 1; documented in
# `docs/modal-body-format.md`). A `ModalBody3D` node names that file in its `constants`
# (`file`, project-relative, e.g. `data/bracket.modal.json`), exactly like a CsvSource names
# its CSV file. The compiler reads the file while it instantiates the node and turns its
# content into the block's structural constants: the mode count `nm`
# and the reduced matrices (mass properties, modal mass and stiffness, the inertia invariants,
# the interface mode values and the geometric-stiffening matrices). They are constants, not
# parameters, so they fold into literals: a zero entry drops out of the equations, the exported
# C code holds them as numbers, and editing the file changes the compile key (recompiles).
#
# The heavy FEM dependencies never enter BGSim: only this JSON reader does.

"""
    ModalDataError(message, hint)

A problem with a reduced-model file or its settings; the instantiation pass reports it as
`E108` at the node."""
struct ModalDataError <: Exception
    message::String
    hint::String
end

Base.showerror(io::IO, e::ModalDataError) = print(io, "reduced-model file: ", e.message)

const MODAL_BODY_FORMAT = "bgsim.modal-body"
const MODAL_MAX_INTERFACES = 4
const MODAL_MAX_MODES = 48
const MODAL_COMP6 = ("xx", "yy", "zz", "xy", "xz", "yz")
# Stiffening blocks in the order of the block's constant `G`.
const MODAL_STIFF_BLOCKS = ("translation" => 3, "inertia" => 6, "rotation" => 3)
# The block constants of the 21 stiffening matrices: translation x y z, inertia xx yy zz xy xz
# yz, rotation x y z, the force x y z at interface B, C and D.
const MODAL_G_NAMES = ("Gt1", "Gt2", "Gt3", "Gj1", "Gj2", "Gj3", "Gj4", "Gj5", "Gj6",
    "Gr1", "Gr2", "Gr3", "Gb1", "Gb2", "Gb3", "Gc1", "Gc2", "Gc3", "Gd1", "Gd2", "Gd3")

const MODAL_CACHE = Dict{String,Any}()
const MODAL_CACHE_ORDER = String[]
const MODAL_LOCK = ReentrantLock()

function modal_resolve_path(project_dir, file::AbstractString)
    try
        return csv_resolve_path(project_dir, file)
    catch err
        err isa CsvError || rethrow()
        msg = replace(err.message, "CSV file" => "reduced-model file")
        throw(ModalDataError(msg,
            "put the reduced-model file (written by julia/BGSimFEM) in the project, e.g. `data/<part>.modal.json`, and set the node's `file` to that path"))
    end
end

_mf(x) = x isa Real ? Float64(x) : throw(ModalDataError("expected a number, got $(repr(x))", ""))

function _mvec(d, key, n; file)
    haskey(d, key) || throw(ModalDataError("`$file` has no `$key`", "write the file with julia/BGSimFEM"))
    v = d[key]
    (v isa AbstractVector && length(v) == n) ||
        throw(ModalDataError("`$key` of `$file` must have $n entries", ""))
    return Float64[_mf(x) for x in v]
end

function _mmat(v, n, m, what; file)
    (v isa AbstractVector && length(v) == n && all(r -> r isa AbstractVector && length(r) == m, v)) ||
        throw(ModalDataError("`$what` of `$file` must be a $n x $m matrix (a list of $n rows)", ""))
    A = zeros(n, m)
    for i in 1:n, j in 1:m
        A[i, j] = _mf(v[i][j])
    end
    return A
end

function _quat_rot(q)
    w, x, y, z = q ./ sqrt(sum(abs2, q))
    return [1 - 2(y^2 + z^2) 2(x * y - w * z) 2(x * z + w * y);
            2(x * y + w * z) 1 - 2(x^2 + z^2) 2(y * z - w * x);
            2(x * z - w * y) 2(y * z + w * x) 1 - 2(x^2 + y^2)]
end

# Entries this far below the largest of their matrix are noise of the FE solution; dropping
# them keeps exact symmetries (zero couplings) exact, so they fold out of the equations.
function _clean!(A::AbstractArray; rtol = 1e-10)
    s = maximum(abs, A; init = 0.0)
    s == 0 && return A
    for i in eachindex(A)
        abs(A[i]) < rtol * s && (A[i] = 0.0)
    end
    return A
end

"""
    load_modal_body(project_dir, settings) -> Vector{Pair{String,Any}}

Read the reduced-model file named by `settings["file"]` and return the block constants of
`ModalBody3D` in declaration order (sizes first). `settings["stiffening"]` (0 or 1, default 1)
keeps or drops the geometric-stiffening terms; a file without them always gives 0."""
function load_modal_body(project_dir, settings::AbstractDict)
    file = String(get(settings, "file", ""))
    isempty(strip(file)) && throw(ModalDataError("no reduced-model file is selected",
        "set the node's `file` to the project's reduced-model file, e.g. `data/bracket.modal.json` (written by julia/BGSimFEM)"))
    path = modal_resolve_path(project_dir, file)
    isfile(path) || throw(ModalDataError("the reduced-model file `$file` does not exist in the project",
        "run julia/BGSimFEM on the part spec, or fix the path"))
    bytes = read(path)
    key = bytes2hex(sha256(bytes))
    d = lock(MODAL_LOCK) do
        get(MODAL_CACHE, key, nothing)
    end
    if d === nothing
        d = try
            JSON3.read(String(copy(bytes)), Dict{String,Any})
        catch err
            throw(ModalDataError("`$file` is not valid JSON ($(sprint(showerror, err)))", ""))
        end
        lock(MODAL_LOCK) do
            MODAL_CACHE[key] = d
            push!(MODAL_CACHE_ORDER, key)
            while length(MODAL_CACHE_ORDER) > 8
                delete!(MODAL_CACHE, popfirst!(MODAL_CACHE_ORDER))
            end
        end
    end
    get(d, "format", "") == MODAL_BODY_FORMAT || throw(ModalDataError(
        "`$file` is not a reduced-model file (format `$(get(d, "format", "?"))`, expected `$MODAL_BODY_FORMAT`)", ""))
    get(d, "version", 0) == 1 || throw(ModalDataError("`$file` has version $(get(d, "version", "?")); this simulator reads version 1", ""))
    nm = get(d, "nm", 0)
    (nm isa Integer && 1 <= nm <= MODAL_MAX_MODES) ||
        throw(ModalDataError("`$file` must have 1 to $MODAL_MAX_MODES modes, has $(repr(nm))",
            "reduce with fewer fixed-interface modes or interfaces"))
    ifs = get(d, "interfaces", Any[])
    ni = length(ifs)
    1 <= ni <= MODAL_MAX_INTERFACES ||
        throw(ModalDataError("`$file` must have 1 to $MODAL_MAX_INTERFACES interfaces, has $ni", ""))
    stiff_want = get(settings, "stiffening", 1)
    stiff_want = stiff_want isa AbstractString ? (strip(stiff_want) in ("0", "off", "false") ? 0 : 1) :
                 (stiff_want in (0, false) ? 0 : 1)
    stiff = (stiff_want == 1 && get(d, "stiffening", nothing) isa AbstractDict) ? 1 : 0

    mass = _mf(d["mass"])
    mass > 0 || throw(ModalDataError("`$file` has a mass of $mass kg", ""))
    S0 = _mvec(d, "first_moment", 3; file)
    J0 = _mmat(d["inertia"], 3, 3, "inertia"; file)
    mk = _mvec(d, "modal_mass", nm; file)
    kk = _mvec(d, "modal_stiffness", nm; file)
    all(>(0), mk) || throw(ModalDataError("`$file` has a modal mass that is not positive", ""))
    all(>=(0), kk) || throw(ModalDataError("`$file` has a negative modal stiffness", ""))
    St = _clean!(_mmat(d["St"], 3, nm, "St"; file))
    Sr = _clean!(_mmat(d["Sr"], 3, nm, "Sr"; file))
    J1 = _clean!(_mmat(d["J1"], 6, nm, "J1"; file))
    Ed = d["E"]
    E = zeros(nm, 6nm)
    for (c, name) in enumerate(MODAL_COMP6)
        E[:, ((c - 1) * nm + 1):(c * nm)] = _mmat(Ed[name], nm, nm, "E.$name"; file)
    end
    _clean!(E)
    XP = zeros(3, MODAL_MAX_INTERFACES)
    QP = zeros(4, MODAL_MAX_INTERFACES)
    RP = zeros(3, 3 * MODAL_MAX_INTERFACES)
    PT = zeros(3 * MODAL_MAX_INTERFACES, nm)
    PR = zeros(3 * MODAL_MAX_INTERFACES, nm)
    for j in 1:MODAL_MAX_INTERFACES
        QP[1, j] = 1.0
        RP[:, (3j - 2):(3j)] = [1.0 0 0; 0 1 0; 0 0 1]
    end
    for (j, f) in enumerate(ifs)
        XP[:, j] = _mvec(f, "position", 3; file)
        q = _mvec(f, "quaternion", 4; file)
        q ./= sqrt(sum(abs2, q))
        QP[:, j] = q
        RP[:, (3j - 2):(3j)] = _quat_rot(q)
        PT[(3j - 2):(3j), :] = _mmat(f["translation"], 3, nm, "interfaces[$j].translation"; file)
        PR[(3j - 2):(3j), :] = _mmat(f["rotation"], 3, nm, "interfaces[$j].rotation"; file)
    end
    _clean!(PT)
    _clean!(PR)
    # Geometric stiffening: 21 nm x nm blocks, side by side: translation (3), inertia (6),
    # rotation (3), interface force at interfaces 2, 3, 4 (3 each; zero for a missing one).
    G = zeros(nm, 21nm)
    if stiff == 1
        s = d["stiffening"]
        blk = 0
        for (name, n) in MODAL_STIFF_BLOCKS
            mats = s[name]
            length(mats) == n || throw(ModalDataError("`stiffening.$name` of `$file` must have $n matrices", ""))
            for c in 1:n
                blk += 1
                G[:, ((blk - 1) * nm + 1):(blk * nm)] = _mmat(mats[c], nm, nm, "stiffening.$name[$c]"; file)
            end
        end
        fi = get(s, "interface_force", Any[])
        length(fi) == 3 * (ni - 1) || throw(ModalDataError("`stiffening.interface_force` of `$file` must have $(3 * (ni - 1)) matrices", ""))
        for c in eachindex(fi)
            b = 12 + c
            G[:, ((b - 1) * nm + 1):(b * nm)] = _mmat(fi[c], nm, nm, "stiffening.interface_force[$c]"; file)
        end
        _clean!(G)
    end
    ns, nh, SP = _modal_stress(d, nm; file)
    rail = _modal_rail(d, nm; file)
    out = Pair{String,Any}[
        "nm" => Int(nm), "stiffening" => stiff, "ns" => ns, "nh" => nh,
        "nr" => rail.nr, "nc" => rail.nc,
        "mass" => mass, "S0" => S0, "J0" => J0, "mk" => mk, "kk" => kk,
        "St" => St, "Sr" => Sr, "J1" => J1,
    ]
    for (c, name) in enumerate(MODAL_COMP6)
        push!(out, "E" * name => E[:, ((c - 1) * nm + 1):(c * nm)])
    end
    append!(out, Pair{String,Any}["XP" => XP, "QP" => QP, "RP" => RP, "PT" => PT, "PR" => PR])
    for (b, name) in enumerate(MODAL_G_NAMES)
        # the rotational-acceleration cases stay in the file but the block does not use them
        # (ModalBodyCore3D, header: they would enter the coupling rows of the mass matrix)
        startswith(name, "Gr") && continue
        push!(out, name => G[:, ((b - 1) * nm + 1):(b * nm)])
    end
    for (c, name) in enumerate(MODAL_COMP6)
        push!(out, "S" * name => SP[c])
    end
    append!(out, Pair{String,Any}["RL" => rail.RL, "XR" => rail.XR, "RR" => rail.RR, "QR" => rail.QR])
    for a in 1:3
        push!(out, "CT$a" => rail.CT[a])
    end
    for a in 1:3
        push!(out, "CR$a" => rail.CR[a])
    end
    return out
end

const MODAL_MAX_CHEBYSHEV = 32

"""
    _modal_rail(d, nm; file) -> NamedTuple

The file's `rail` (julia/BGSimFEM, rail.jl): a straight rail with Chebyshev tables of the rail
frame's translation (R) and rotation (rail frame) per mode. Without one, `nr = 0` and zero
tables (ports E and S of the block carry no flow)."""
function _modal_rail(d, nm; file)
    r = get(d, "rail", nothing)
    if !(r isa AbstractDict)
        z = zeros(nm, 2)
        return (nr = 0, nc = 2, RL = 1.0, XR = zeros(3), RR = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0],
            QR = [1.0, 0.0, 0.0, 0.0], CT = [copy(z) for _ in 1:3], CR = [copy(z) for _ in 1:3])
    end
    nc = get(r, "chebyshev", 0)
    (nc isa Integer && 2 <= nc <= MODAL_MAX_CHEBYSHEV) || throw(ModalDataError(
        "`rail.chebyshev` of `$file` must be 2 to $MODAL_MAX_CHEBYSHEV, is $(repr(nc))", ""))
    RL = _mf(get(r, "length", 0.0))
    RL > 0 || throw(ModalDataError("`rail.length` of `$file` must be positive", ""))
    q = _mvec(r, "quaternion", 4; file)
    q ./= sqrt(sum(abs2, q))
    tr, rt = get(r, "translation", nothing), get(r, "rotation", nothing)
    (tr isa AbstractVector && length(tr) == 3 && rt isa AbstractVector && length(rt) == 3) ||
        throw(ModalDataError("`rail.translation` and `rail.rotation` of `$file` must hold 3 tables each", ""))
    CT = [_clean!(_mmat(tr[a], nm, nc, "rail.translation[$a]"; file); rtol = 1e-12) for a in 1:3]
    CR = [_clean!(_mmat(rt[a], nm, nc, "rail.rotation[$a]"; file); rtol = 1e-12) for a in 1:3]
    return (nr = 1, nc = Int(nc), RL = RL, XR = _mvec(r, "start", 3; file), RR = _quat_rot(q),
        QR = q, CT = CT, CR = CR)
end

const MODAL_MAX_STRESS_POINTS = 64

"""
    _modal_stress(d, nm; file) -> (ns, nh, [Sxx, Syy, Szz, Sxy, Sxz, Syz])

The stress points of the file's `stress` entry (written by julia/BGSimFEM): `ns` points, the
first `nh` of them the named hotspots, the others the peak candidates, and per stress
component an `ns x nm` matrix (Pa per unit modal coordinate). A file without stress points
gives one zero point (`ns = nh = 1`), so the block's stress outputs read 0. Without named
hotspots `nh` is 1 and the hotspot output repeats the peak estimate's first candidate."""
function _modal_stress(d, nm; file)
    s = get(d, "stress", nothing)
    pts = s isa AbstractDict ? get(s, "points", Any[]) : Any[]
    if isempty(pts)
        return 1, 1, [zeros(1, nm) for _ in 1:6]
    end
    ns = length(pts)
    ns <= MODAL_MAX_STRESS_POINTS || throw(ModalDataError(
        "`$file` has $ns stress points; the simulator reads at most $MODAL_MAX_STRESS_POINTS",
        "reduce with fewer `stress.peak_points` or hotspots"))
    nhot = count(p -> get(p, "kind", "") == "hotspot", pts)
    all(get(pts[i], "kind", "") == "hotspot" for i in 1:nhot) || throw(ModalDataError(
        "the hotspots of `$file` must come before the peak candidates in `stress.points`", ""))
    SP = [zeros(ns, nm) for _ in 1:6]
    for (i, p) in enumerate(pts)
        A = _mmat(get(p, "sigma", nothing), 6, nm, "stress.points[$i].sigma"; file)
        for c in 1:6
            SP[c][i, :] = A[c, :]
        end
    end
    for c in 1:6
        _clean!(SP[c]; rtol = 1e-12)
    end
    return ns, max(nhot, 1), SP
end

"""The names of the stress points of a reduced-model file (hotspots first), for the docs and the inspector."""
function modal_stress_names(d)
    s = get(d, "stress", nothing)
    s isa AbstractDict || return String[]
    return String[String(get(p, "name", "")) for p in get(s, "points", Any[])]
end
