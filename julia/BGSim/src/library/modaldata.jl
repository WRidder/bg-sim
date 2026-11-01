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
    out = Pair{String,Any}[
        "nm" => Int(nm), "stiffening" => stiff,
        "mass" => mass, "S0" => S0, "J0" => J0, "mk" => mk, "kk" => kk,
        "St" => St, "Sr" => Sr, "J1" => J1,
    ]
    for (c, name) in enumerate(MODAL_COMP6)
        push!(out, "E" * name => E[:, ((c - 1) * nm + 1):(c * nm)])
    end
    append!(out, Pair{String,Any}["XP" => XP, "QP" => QP, "RP" => RP, "PT" => PT, "PR" => PR])
    for (b, name) in enumerate(MODAL_G_NAMES)
        push!(out, name => G[:, ((b - 1) * nm + 1):(b * nm)])
    end
    return out
end
