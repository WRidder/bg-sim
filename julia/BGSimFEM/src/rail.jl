# A rail on the part: a straight line along which a carriage slides (a linear guide on a
# gantry beam). The carriage is not a fixed interface: it moves, and the modal body block
# (`ModalBody3D`, port E) needs the motion of the rail frame at the carriage's position s for
# every mode, and its derivative along s:
#
#   r_E(s, q) = X0 + s t + PT(s) q        (rail frame origin in R)
#   g_E(s, q) = 1/2 PR(s) q               (its elastic rotation, Gibbs vector in the rail frame)
#
# PT(s), PR(s) (3 x nm each) are the rigid fit of each mode over the rail's footprint: the
# surface nodes of the rail's mounting face (the `footprint.select` region) within
# `half_length` of the station along the rail. A least-squares rigid motion u + theta x (x - c)
# of those nodes gives the translation u and the rotation theta of the guide block there, the
# way the block's four bearing pads would follow the face. The fit is sampled at `stations`
# stations from start to end and fitted by a Chebyshev series in x = 2 s / L - 1,
#
#   PT(s) = sum_n CT_n T_n(x),   PR(s) = sum_n CR_n T_n(x)
#
# (`chebyshev` terms, default 20), so the block gets smooth tables with exact derivatives and
# no switching. The tool reports the fit error.
#
# Accuracy. The Craig–Bampton basis has constraint modes at the interfaces, not along the
# rail: the static deflection under a carriage load between the interfaces comes from the
# fixed-interface modes alone and converges with their number (a point load at mid-span of a
# beam: about 97 % with the first bending mode). `load_modes` adds the static response to unit
# loads at a few rail stations (the two directions across the rail and the torsion about it)
# to the basis (modal truncation augmentation, M-orthogonal to the rest): a load at such a
# station is then exact, and in between it is interpolated far better than by the vibration
# modes. `validation.rail` compares the static deflection of the rail frame under unit loads
# at several stations against the full FE model.

struct Rail
    name::String
    start::Vector{Float64}          # R coordinates
    length::Float64
    rotation::Matrix{Float64}       # rail frame in R: columns x (normal), y, z = t
    s::Vector{Float64}              # stations (m from start)
    nodes::Vector{Vector{Int}}      # footprint nodes per station
    half_length::Float64
    nc::Int                         # Chebyshev terms
end

_cheb(x::Real, nc::Integer) = begin
    T = zeros(nc)
    T[1] = 1.0
    nc >= 2 && (T[2] = x)
    for n in 3:nc
        T[n] = 2x * T[n - 1] - T[n - 2]
    end
    T
end

"""d T_n / dx of the Chebyshev polynomials (the same recurrence differentiated)."""
_dcheb(x::Real, nc::Integer) = begin
    T = _cheb(x, nc)
    D = zeros(nc)
    nc >= 2 && (D[2] = 1.0)
    for n in 3:nc
        D[n] = 2T[n - 1] + 2x * D[n - 1] - D[n - 2]
    end
    D
end

"""
    make_rail(grid, spec, p1, R1) -> Rail

The rail of the part spec (part coordinates; the grid is the part grid, the rail is returned in
R, x_R = R1' (x - p1)). Spec keys: `name`, `start`, `end`, `normal` (the rail frame's x axis,
out of the mounting face; made perpendicular to the rail), `stations` (default 41),
`chebyshev` (default 20), `footprint`: `{half_length, select, surface (default true)}`."""
function make_rail(grid::Grid, spec::AbstractDict, p1::AbstractVector, R1::AbstractMatrix)
    name = String(get(spec, "name", "rail"))
    a, b = _vec3(spec["start"]), _vec3(spec["end"])
    L = norm(b .- a)
    L > 0 || throw(ArgumentError("rail $name: start and end coincide"))
    t = (b .- a) ./ L
    nrm = _vec3(get(spec, "normal", abs(t[3]) < 0.9 ? [0.0, 0.0, 1.0] : [1.0, 0.0, 0.0]))
    x = nrm .- dot(nrm, t) .* t
    norm(x) > 1e-9 || throw(ArgumentError("rail $name: `normal` is parallel to the rail"))
    x ./= norm(x)
    y = cross(t, x)
    Rp = hcat(x, y, t)
    fp = spec["footprint"]
    hl = Float64(fp["half_length"])
    X = node_coordinates(grid)
    surf = Bool(get(fp, "surface", true)) ? boundary_nodes(grid) : nothing
    cand = _select_nodes(X, fp["select"], surf)
    ns = Int(get(spec, "stations", 41))
    nc = Int(get(spec, "chebyshev", 20))
    ns >= 2 && nc >= 2 || throw(ArgumentError("rail $name: needs at least 2 stations and 2 Chebyshev terms"))
    s = collect(range(0.0, L; length = ns))
    nodes = Vector{Int}[]
    for si in s
        c = a .+ si .* t
        N = [i for i in cand if abs(dot(X[:, i] .- c, t)) <= hl]
        length(N) >= 3 || throw(ArgumentError("rail $name: the footprint at s = $(round(si; sigdigits = 4)) m has $(length(N)) nodes; widen `half_length` or `select`"))
        push!(nodes, N)
    end
    return Rail(name, R1' * (a .- p1), L, R1' * Rp, s, nodes, hl, nc)
end

"""The least-squares rigid fit of nodes `N` about `c` (R): a 6 x 3|N| matrix P with
[u; theta] = P * (stacked nodal displacements)."""
function _rigid_fit_operator(X::AbstractMatrix, N::AbstractVector{<:Integer}, c::AbstractVector)
    A = zeros(3length(N), 6)
    for (j, i) in enumerate(N)
        r = X[:, i] .- c
        rows = 3(j - 1) .+ (1:3)
        A[rows, 1:3] = Matrix{Float64}(I, 3, 3)
        # theta x r = -[r]x theta
        A[rows, 4:6] = -[0 -r[3] r[2]; r[3] 0 -r[1]; -r[2] r[1] 0]
    end
    return (A' * A) \ A'
end

_station_centre(rail::Rail, s) = rail.start .+ s .* rail.rotation[:, 3]

"""[u; theta] (6 x ncols, R coordinates) of displacement fields `U` (dofs x ncols) at station i."""
function rail_station_motion(fe::FEModel, rail::Rail, i::Integer, U::AbstractMatrix)
    N = rail.nodes[i]
    P = _rigid_fit_operator(fe.X, N, _station_centre(rail, rail.s[i]))
    rows = reduce(vcat, [fe.nodedofs[:, n] for n in N])
    return P * U[rows, :]
end

"""
    rail_tables!(r, fe, rail) -> Dict

Fit the modes at every station, then the Chebyshev coefficients (least squares over the
stations). Stores `r.rail` (the file's `rail` entry) and returns it."""
function rail_tables!(r::ReducedModel, fe::FEModel, rail::Rail)
    nm, ns, nc = r.nm, length(rail.s), rail.nc
    PT = zeros(ns, 3, nm)
    PR = zeros(ns, 3, nm)
    Rt = rail.rotation'
    for i in 1:ns
        m = rail_station_motion(fe, rail, i, r.modes)
        PT[i, :, :] = m[1:3, :]
        PR[i, :, :] = Rt * m[4:6, :]
    end
    xs = 2 .* rail.s ./ rail.length .- 1
    V = reduce(vcat, [_cheb(x, nc)' for x in xs])          # ns x nc
    nc <= ns || throw(ArgumentError("rail $(rail.name): more Chebyshev terms ($nc) than stations ($ns)"))
    fit(Y) = V \ Y                                          # nc x nm
    CT = [Matrix(fit(PT[:, a, :])') for a in 1:3]           # each nm x nc
    CR = [Matrix(fit(PR[:, a, :])') for a in 1:3]
    # fit error relative to each table's largest value, over a finer grid than the stations
    err_t = 0.0
    err_r = 0.0
    for a in 1:3
        st = maximum(abs, PT[:, a, :]; init = 0.0)
        sr = maximum(abs, PR[:, a, :]; init = 0.0)
        st > 0 && (err_t = max(err_t, maximum(abs, V * CT[a]' .- PT[:, a, :]) / st))
        sr > 0 && (err_r = max(err_r, maximum(abs, V * CR[a]' .- PR[:, a, :]) / sr))
    end
    d = Dict{String,Any}(
        "name" => rail.name,
        "start" => rail.start,
        "length" => rail.length,
        "quaternion" => rot_to_quat(rail.rotation),
        "rotation_matrix" => _rows(rail.rotation),
        "chebyshev" => nc,
        "basis" => "x = 2 s / length - 1; PT(s) = sum_n CT[:, n] T_n(x) (3 x nm, R), PR(s) the same (rail frame), T_1 = 1, T_2 = x, T_n = 2 x T_(n-1) - T_(n-2)",
        "translation" => [_rows(CT[a]) for a in 1:3],
        "rotation" => [_rows(CR[a]) for a in 1:3],
        "stations" => ns,
        "footprint_half_length" => rail.half_length,
        "footprint_nodes" => [length(N) for N in rail.nodes],
        "fit_error" => Dict("translation" => err_t, "rotation" => err_r),
    )
    r.rail = d
    return d
end

"""PT(s), PR(s) (3 x nm each) and their s-derivatives from the Chebyshev tables of `r.rail`."""
function rail_eval(d::AbstractDict, s::Real)
    L, nc = Float64(d["length"]), Int(d["chebyshev"])
    x = 2s / L - 1
    T, D = _cheb(x, nc), _dcheb(x, nc) .* (2 / L)
    m(rows) = reduce(vcat, [collect(row)' for row in rows])
    PT = reduce(vcat, [(m(d["translation"][a]) * T)' for a in 1:3])
    PR = reduce(vcat, [(m(d["rotation"][a]) * T)' for a in 1:3])
    dPT = reduce(vcat, [(m(d["translation"][a]) * D)' for a in 1:3])
    dPR = reduce(vcat, [(m(d["rotation"][a]) * D)' for a in 1:3])
    return PT, PR, dPT, dPR
end

"""
Unit loads on the rail footprint at station fraction `f` (dofs x 3): a force along the rail
frame's x and y axes (spread evenly over the footprint nodes) and a moment about the rail
(nodal forces t x r / sum |r_perp|^2)."""
function rail_unit_loads(fe::FEModel, rail::Rail, f::Real)
    s = clamp(f, 0.0, 1.0) * rail.length
    i = argmin(abs.(rail.s .- s))
    N = rail.nodes[i]
    c = _station_centre(rail, rail.s[i])
    t = rail.rotation[:, 3]
    F = zeros(ndofs_fe(fe), 3)
    for (col, e) in ((1, rail.rotation[:, 1]), (2, rail.rotation[:, 2]))
        for n in N
            F[fe.nodedofs[:, n], col] .+= e ./ length(N)
        end
    end
    rp = [(r = fe.X[:, n] .- c; r .- dot(r, t) .* t) for n in N]
    den = sum(sum(abs2, r) for r in rp)
    for (n, r) in zip(N, rp)
        F[fe.nodedofs[:, n], 3] .+= cross(t, r) ./ den
    end
    return F, rail.s[i]
end

"""
    validate_rail!(r, fe, aux, rail; fractions) -> Dict

Static deflection of the rail frame under unit loads at the stations `fractions` (of the
length) on the full FE model (interface 1 clamped) against the reduced model through the
rail tables. Stores `r.validation["rail"]`."""
function validate_rail!(r::ReducedModel, fe::FEModel, aux, rail::Rail;
        fractions = (0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9))
    t0 = time()
    c = aux.c
    Tc = aux.T[:, c]
    Fc = cholesky(Symmetric(aux.Kt[c, c]))
    cases = Any[]
    names = ("force x", "force y", "moment z")
    for f in fractions
        F, s = rail_unit_loads(fe, rail, f)
        i = argmin(abs.(rail.s .- s))
        PT, PR, _, _ = rail_eval(r.rail, s)
        P = vcat(PT, PR)
        for k in 1:3
            fc = Tc' * F[:, k]
            u = Tc * (Fc \ fc)
            m = rail_station_motion(fe, rail, i, reshape(u, :, 1))[:, 1]
            full = vcat(m[1:3], rail.rotation' * m[4:6])
            # translations in the rail frame for the report
            full_rf = vcat(rail.rotation' * m[1:3], full[4:6])
            q = (aux.Y' * fc) ./ r.kk
            red = P * q
            red_rf = vcat(rail.rotation' * red[1:3], red[4:6])
            # the loaded direction: rail x, rail y or the rotation about the rail
            j = k == 3 ? 6 : k
            push!(cases, Dict{String,Any}("station" => s, "fraction" => f, "load" => names[k],
                "full" => full_rf, "reduced" => red_rf,
                "full_compliance" => full_rf[j], "reduced_compliance" => red_rf[j],
                "rel_error" => (red_rf[j] - full_rf[j]) / full_rf[j]))
        end
    end
    # the error against the largest deflection of the same load along the rail: a load near a
    # clamped end deflects the rail very little (and mostly locally), where a relative error
    # says little
    for name in names
        sel = [c for c in cases if c["load"] == name]
        top = maximum(abs(c["full_compliance"]) for c in sel)
        for c in sel
            c["error_of_largest"] = (c["reduced_compliance"] - c["full_compliance"]) / top
        end
    end
    v = Dict{String,Any}("cases" => cases,
        "max_error_of_largest" => maximum(abs(c["error_of_largest"]) for c in cases),
        "max_rel_error" => maximum(abs(c["rel_error"]) for c in cases),
        "max_rel_error_force" => maximum(abs(c["rel_error"]) for c in cases if c["load"] != "moment z"),
        "max_rel_error_torsion" => maximum(abs(c["rel_error"]) for c in cases if c["load"] == "moment z"),
        "seconds" => time() - t0)
    r.validation["rail"] = v
    return v
end
