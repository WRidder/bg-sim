# Modal stress recovery for the floating-frame modal body.
#
# The elastic field relative to the reference frame R is u = Phi q (interface 1 clamped, the
# Craig–Bampton basis diagonalised). Stress is linear in the strain, so with the per-mode stress
# fields S_k (the stress of mode k per unit modal coordinate) the stress anywhere is
#
#     sigma(x, t) = sum_k S_k(x) q_k(t)
#
# for every kind of mode alike: the fixed-interface modes and the static constraint modes are
# mixed by the diagonalisation, and each final mode is one displacement field with one stress
# field. The rigid motion of R carries no strain and adds nothing; the second-order field of
# the geometric stiffening is left out (it is second order in q). von Mises is not linear: the
# six components are superposed first and von Mises is taken of the sum.
#
# Accuracy ("mode displacement method"): loads at the interfaces are represented exactly by the
# constraint modes, so their static stress is exact. Distributed loads (the inertia of the part
# itself under the frame's acceleration, gravity) converge with the number of fixed-interface
# modes. `stress_validation!` measures both against the full FE model.
#
# Recovery (`nodal_stress`): element-wise at the cell nodes, averaged over the cells of a node.
# Nodes tied to an interface (RBE2) are not reported as hotspots or peaks: the rigid spider
# makes a local stress concentration at its edge that the real joint does not have.

"""
    StressPoint

A point where the block reports the stress: a user-named `hotspot` from the part spec, or a
`peak` candidate chosen by the tool. `node` is the FE node (on the surface, not tied to an
interface), `position` its coordinates in R, `requested` the asked position (hotspots) and
`sigma` the 6 x nm stress per unit modal coordinate (components xx yy zz xy xz yz)."""
struct StressPoint
    name::String
    kind::String
    node::Int
    position::Vector{Float64}
    requested::Union{Nothing,Vector{Float64}}
    sigma::Matrix{Float64}
end

_tied_nodes(ifs) = Set{Int}(i for f in ifs for i in f.nodes)

"""
The surface nodes of the FE grid that may carry a hotspot or a peak candidate.
`exclude_interfaces = true` drops the nodes tied to an interface, a number `d` (m) also drops
the surface nodes within `d` of a tied node, `false` keeps them all."""
function stress_surface_nodes(fe::FEModel, ifs; exclude_interfaces = true)
    surf = boundary_nodes(fe.grid)
    exclude_interfaces === false && return sort!(collect(surf))
    tied = _tied_nodes(ifs)
    d = exclude_interfaces === true ? 0.0 : Float64(exclude_interfaces)
    keep = Int[]
    T = fe.X[:, collect(tied)]
    for i in surf
        i in tied && continue
        if d > 0 && !isempty(tied)
            x = fe.X[:, i]
            any(j -> (T[1, j] - x[1])^2 + (T[2, j] - x[2])^2 + (T[3, j] - x[3])^2 < d^2, axes(T, 2)) && continue
        end
        push!(keep, i)
    end
    return sort!(keep)
end

_point_sigma(Sm, node) = reduce(hcat, [Sm[k][:, node] for k in eachindex(Sm)])

"""
    stress_load_cases(fe, r, aux; g = 9.81) -> Vector{(name, f)}

Static load cases (loads on the clamped-at-interface-1 model, in the reduced c-space of
`craig_bampton`): a unit force and a unit moment along each axis at every interface j >= 2
(R axes) and the self weight under `g` along each axis."""
function stress_load_cases(fe::FEModel, r::ReducedModel, aux; g::Real = 9.81)
    nc = length(aux.c)
    Tc = aux.T[:, aux.c]
    out = Tuple{String,Vector{Float64}}[]
    axes_ = ("x", "y", "z")
    for (j, f) in enumerate(r.interfaces)
        j == 1 && continue
        for a in 1:6
            v = zeros(nc)
            v[aux.nfree + 6(j - 2) + a] = 1.0
            push!(out, ((a <= 3 ? "force $(axes_[a]) 1 N at " : "moment $(axes_[a - 3]) 1 N*m at ") * f.name, v))
        end
    end
    for a in 1:3
        trv = _field(fe, x -> _e(a))
        push!(out, ("self weight, $(g) m/s^2 along $(axes_[a])", Vector{Float64}(Tc' * (fe.M * trv) .* g)))
    end
    return out
end

"""
    stress_fields!(r, fe, aux) -> r

The per-mode stress fields `r.stress_modes` (6 x nn each) of the reduced modes."""
function stress_fields!(r::ReducedModel, fe::FEModel)
    r.stress_modes = nodal_stress(fe, r.modes)
    return r
end

"""
    choose_stress_points!(r, fe; hotspots, peak_points = 24, exclude_interfaces = true,
        states = Vector[]) -> Vector{StressPoint}

The hotspots (`hotspots`: `(name, position in R)`; each snaps to the nearest surface node that
is not tied to an interface) and up to `peak_points` peak candidates, chosen greedily so that
the largest von Mises over the candidates comes as close as possible to the true surface peak
over the training `states` (modal coordinate vectors): each step adds the surface node that
raises the sum over the states of `min(1, max over the candidates / surface peak)` the most.
The block's `sigma_max` is the largest von Mises over all the points."""
function choose_stress_points!(r::ReducedModel, fe::FEModel; hotspots = Any[], peak_points::Integer = 24,
        exclude_interfaces = true, states = Vector{Vector{Float64}}())
    surf = stress_surface_nodes(fe, r.interfaces; exclude_interfaces)
    Xs = fe.X[:, surf]
    pts = StressPoint[]
    for (name, p) in hotspots
        d2 = vec(sum(abs2, Xs .- p; dims = 1))
        i = argmin(d2)
        n = surf[i]
        push!(pts, StressPoint(String(name), "hotspot", n, fe.X[:, n], collect(Float64, p), _point_sigma(r.stress_modes, n)))
    end
    Ssurf = [S[:, surf] for S in r.stress_modes]
    nz = length(states)
    V = zeros(nz, length(surf))       # von Mises of each state over the surface, / its peak
    for (z, q) in enumerate(states)
        v = von_mises_cols(superpose(Ssurf, q))
        m = maximum(v)
        m > 0 && (V[z, :] .= v ./ m)
    end
    cur = zeros(nz)
    chosen = Int[]
    for _ in 1:peak_points
        best, gain = 0, 0.0
        for n in axes(V, 2)
            g = 0.0
            @inbounds for z in 1:nz
                d = V[z, n] - cur[z]
                d > 0 && (g += d)
            end
            g > gain && ((best, gain) = (n, g))
        end
        best == 0 && break
        push!(chosen, best)
        @inbounds for z in 1:nz
            cur[z] = max(cur[z], V[z, best])
        end
    end
    for (k, i) in enumerate(chosen)
        n = surf[i]
        push!(pts, StressPoint("peak $k", "peak", n, fe.X[:, n], nothing, _point_sigma(r.stress_modes, n)))
    end
    r.stress_points = pts
    return pts
end

_vm_points(pts, q) = [von_mises(p.sigma * q) for p in pts]

# A small deterministic generator (no Random dependency): uniform and standard normal draws.
mutable struct _Rng
    s::UInt64
end
_unif!(g::_Rng) = (g.s = g.s * 6364136223846793005 + 1442695040888963407; ((g.s >> 11) / 2.0^53))
_gauss!(g::_Rng) = sqrt(-2 * log(max(_unif!(g), 1e-300))) * cos(2pi * _unif!(g))

# Representative load states of the reduced model: random combinations of the static load cases
# (each scaled to a unit surface peak first, so every load path weighs alike) and random static
# modal states (q_k = n_k / k_k, the response to a random modal force).
function _stress_states(g::_Rng, r::ReducedModel, case_q, n_mix::Integer, n_modal::Integer)
    out = Vector{Float64}[]
    for _ in 1:n_mix
        q = zeros(r.nm)
        for cq in case_q
            q .+= _gauss!(g) .* cq
        end
        push!(out, q)
    end
    for _ in 1:n_modal
        push!(out, [_gauss!(g) / r.kk[k] for k in 1:r.nm])
    end
    return out
end

"""
    modal_stress!(r, fe, aux; hotspots = [], peak_points = 24, exclude_interfaces = true,
        g = 9.81, samples = 200) -> Dict

The whole stress step: per-mode fields, the stress points and the validation against the full
FE model (`r.validation["stress"]`):

* `cases`: every static load case of `stress_load_cases` solved on the full FE model (interface
  1 clamped) and on the reduced model (q = Phi' f / k), von Mises at each hotspot and the peak
  over the surface (tied nodes excluded) of both, with the relative errors, and the block's
  estimate (the largest von Mises over its stress points) against the reduced model's true
  surface peak;
* `peak_coverage`: the same estimate for `2 samples` fresh random load states of the reduced
  model (random mixtures of the load cases, and q_k = n_k / k_k with n standard normal; the
  candidates were chosen on another sample): the smallest and mean ratio of the points' maximum
  to the surface maximum, and the share of states within 5 %."""
function modal_stress!(r::ReducedModel, fe::FEModel, aux; hotspots = Any[], peak_points::Integer = 24,
        exclude_interfaces = true, g::Real = 9.81, samples::Integer = 200)
    t0 = time()
    stress_fields!(r, fe)
    surf = stress_surface_nodes(fe, r.interfaces; exclude_interfaces)
    c = aux.c
    Kc = aux.Kt[c, c]
    Tc = aux.T[:, c]
    F = cholesky(Symmetric(Kc))
    cases = stress_load_cases(fe, r, aux; g)
    full_fields = Matrix{Float64}[]
    red_q = Vector{Float64}[]
    for (_, f) in cases
        u = Tc * (F \ f)
        push!(full_fields, nodal_stress(fe, u)[:, surf])
        push!(red_q, (aux.Y' * f) ./ r.kk)
    end
    Ssurf = [S[:, surf] for S in r.stress_modes]
    # training states for the peak candidates: the load cases, the single modes and random
    # mixtures of both kinds (`_stress_states`); a fresh sample of the mixtures checks them
    case_unit = map(red_q) do q
        m = maximum(von_mises_cols(superpose(Ssurf, q)))
        m > 0 ? q ./ m : q
    end
    rng = _Rng(0x2545F4914F6CDD1D)
    train = vcat(case_unit, [Float64.((1:r.nm) .== k) for k in 1:r.nm],
        _stress_states(rng, r, case_unit, samples, samples))
    pts = choose_stress_points!(r, fe; hotspots, peak_points, exclude_interfaces, states = train)
    hot = [p for p in pts if p.kind == "hotspot"]
    rel(a, b) = b == 0 ? (a == 0 ? 0.0 : Inf) : a / b - 1
    out_cases = Any[]
    for (i, (name, _)) in enumerate(cases)
        q = red_q[i]
        vf = von_mises_cols(full_fields[i])
        vr = von_mises_cols(superpose(Ssurf, q))
        jf = argmax(vf)
        jr = argmax(vr)
        est = maximum(_vm_points(pts, q))
        hs = Any[]
        for p in hot
            j = searchsortedfirst(surf, p.node)
            push!(hs, Dict{String,Any}("name" => p.name, "full" => vf[j], "reduced" => vr[j], "rel_error" => rel(vr[j], vf[j])))
        end
        push!(out_cases, Dict{String,Any}(
            "name" => name,
            "full_peak" => vf[jf], "full_peak_at" => fe.X[:, surf[jf]],
            "reduced_peak" => vr[jr], "reduced_peak_at" => fe.X[:, surf[jr]],
            "peak_rel_error" => rel(vr[jr], vf[jf]),
            "points_peak" => est, "points_vs_reduced_peak" => vr[jr] > 0 ? est / vr[jr] : 1.0,
            "hotspots" => hs))
    end
    # fresh random load states of the reduced model: how well the points find the surface peak
    ratios = Float64[]
    for q in _stress_states(rng, r, case_unit, samples, samples)
        vr = von_mises_cols(superpose(Ssurf, q))
        m = maximum(vr)
        m > 0 && push!(ratios, maximum(_vm_points(pts, q)) / m)
    end
    inb(x) = isfinite(x) ? x : NaN
    v = Dict{String,Any}(
        "cases" => out_cases,
        "max_peak_rel_error" => maximum(abs(inb(c["peak_rel_error"])) for c in out_cases),
        "max_peak_rel_error_interface_loads" => maximum((abs(inb(c["peak_rel_error"])) for c in out_cases
            if !startswith(c["name"], "self weight")); init = 0.0),
        "max_peak_rel_error_self_weight" => maximum((abs(inb(c["peak_rel_error"])) for c in out_cases
            if startswith(c["name"], "self weight")); init = 0.0),
        "peak_coverage" => Dict{String,Any}("samples" => length(ratios),
            "min_ratio" => isempty(ratios) ? NaN : minimum(ratios),
            "mean_ratio" => isempty(ratios) ? NaN : sum(ratios) / length(ratios),
            "within_5_percent" => isempty(ratios) ? NaN : count(>=(0.95), ratios) / length(ratios)),
        "surface_nodes" => length(surf),
        "seconds" => time() - t0,
    )
    r.validation["stress"] = v
    r.timings["stress"] = time() - t0
    return v
end

"""The `stress` entry of the reduced-model file: the stress points and how they were made."""
function stress_dict(r::ReducedModel; frame_position = r.frame_position, frame_rotation = r.frame_rotation)
    isempty(r.stress_points) && return nothing
    pts = Any[]
    for p in r.stress_points
        d = Dict{String,Any}("name" => p.name, "kind" => p.kind, "position" => p.position,
            "position_in_part" => frame_rotation * p.position .+ frame_position,
            "sigma" => _rows(p.sigma))
        if p.requested !== nothing
            d["requested"] = p.requested
            d["distance"] = norm(p.position .- p.requested)
        end
        push!(pts, d)
    end
    return Dict{String,Any}(
        "unit" => "Pa per unit modal coordinate (per m of eta_k)",
        "components" => collect(COMP6_NAMES),
        "recovery" => "C : sym(grad u) at the nodes of every cell, averaged over the cells of a node; the stress at a point is sum_k sigma_k eta_k (rigid motion gives none), von Mises of the summed components",
        "hotspots" => count(p -> p.kind == "hotspot", r.stress_points),
        "points" => pts,
        "excluded" => "surface nodes tied to an interface (RBE2 spider) are never hotspots or peak candidates",
    )
end
