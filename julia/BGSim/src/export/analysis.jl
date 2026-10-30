# Step-size analysis (plan/EXPORT_PLAN.md D-EX7).
#
# Fixed-step explicit methods are limited by stability and by accuracy. Both follow from the
# eigenvalues λ of the Jacobian, sampled at the initial point and, when a reference run is
# given, along its trajectory:
#
#   stability  |R(hλ)| <= 1 for every λ with Re λ < 0, R the method's amplification
#              function (Euler 1 + z, RK4 the degree-4 Taylor polynomial);
#   accuracy   h·|λ| <= accuracy (default 0.3) for every λ: the step resolves the fastest
#              mode. This is a heuristic; the example harness measures the real error.
#
# The internal step is the communication step (and every discrete period) divided by the
# smallest whole number of substeps that satisfies both, with a whole number of nanoseconds.

import LinearAlgebra

amplification(method::Symbol, z) =
    method === :euler ? abs(1 + z) : abs(1 + z + z^2 / 2 + z^3 / 6 + z^4 / 24)

"""    stable_step(method, lams) -> Float64

The largest `h` with `|R(hλ)| <= 1` for every eigenvalue in `lams` with a negative real part
(bisection per eigenvalue). `Inf` when no eigenvalue limits the step."""
function stable_step(method::Symbol, lams)
    h = Inf
    for λ in lams
        real(λ) < -1e-12 * max(1.0, abs(λ)) || continue
        lo, hi = 0.0, 10.0 / abs(λ)
        for _ in 1:80
            mid = (lo + hi) / 2
            amplification(method, mid * λ) <= 1 ? (lo = mid) : (hi = mid)
        end
        h = min(h, lo)
    end
    return h
end

function _reference_rows(ref_dir::AbstractString)
    manifest = JSON3.read(read(joinpath(ref_dir, "manifest.json"), String))
    ids = String[String(s.id) for s in manifest.signals]
    raw = reinterpret(Float64, read(joinpath(ref_dir, "stream.f64")))
    ncol = 1 + length(ids)
    nrow = length(raw) ÷ ncol
    return ids, [raw[(r - 1) * ncol + 1:r * ncol] for r in 1:nrow]
end

"""    spectrum_scan(jac_fn, x0, p0, names_x, names_p, iv_start; reference_dir, samples)

The eigenvalues of the numeric Jacobian at the initial point and at `samples` rows of the
reference run (states and held values read from the recorded signals when present). Returns
`(points, worst_abs, worst_t)` where `points` is a vector of `(t, eigenvalues)`."""
function spectrum_scan(jac_fn, x0::Vector{Float64}, p0::Vector{Float64},
    names_x::Vector{String}, names_p::Vector{String}, t0::Float64;
    reference_dir = nothing, samples::Int = 25, ranges = Tuple{Int,Float64,Float64}[])
    points = Tuple{Float64,Vector{ComplexF64}}[]
    eig(J) = ComplexF64.(LinearAlgebra.eigvals(J))
    isempty(x0) && return points
    push!(points, (t0, eig(jac_fn(x0, p0, t0))))
    # Declared ranges of runtime-settable values `(index into p, lo, hi)`: each end on its
    # own, and every corner of the box when there are at most 6 of them.
    for (k, lo, hi) in ranges, v in (lo, hi)
        p = copy(p0); p[k] = v
        push!(points, (t0, eig(jac_fn(x0, p, t0))))
    end
    if 2 <= length(ranges) <= 6
        for bits in 0:(2^length(ranges) - 1)
            p = copy(p0)
            for (j, (k, lo, hi)) in enumerate(ranges)
                p[k] = (bits >> (j - 1)) & 1 == 1 ? hi : lo
            end
            push!(points, (t0, eig(jac_fn(x0, p, t0))))
        end
    end
    if reference_dir !== nothing && isfile(joinpath(reference_dir, "stream.f64"))
        ids, rows = _reference_rows(reference_dir)
        col = Dict(id => i + 1 for (i, id) in enumerate(ids))
        picks = unique(round.(Int, range(1, length(rows); length = min(samples, length(rows)))))
        for r in picks
            row = rows[r]
            x = Float64[haskey(col, n) ? row[col[n]] : x0[i] for (i, n) in enumerate(names_x)]
            p = Float64[haskey(col, n) ? row[col[n]] : p0[i] for (i, n) in enumerate(names_p)]
            all(isfinite, x) || continue
            J = jac_fn(x, p, row[1])
            all(isfinite, J) || continue
            push!(points, (row[1], eig(J)))
        end
    end
    return points
end

"""    choose_step(method, points, base_ns; margin, accuracy, max_substeps) -> NamedTuple

The internal step for `method` (`:euler` or `:rk4`): `base_ns` (the communication step and
every discrete period are multiples of it) divided by the smallest admissible substep count
that keeps `h <= margin * stable_step` and `h * |λ| <= accuracy` at every scanned point."""
function choose_step(method::Symbol, points, base_ns::Int64; margin = 0.5, accuracy = 0.3,
    max_substeps = 1000)
    h_stable = Inf
    h_accurate = Inf
    worst_abs = 0.0
    worst_t = isempty(points) ? 0.0 : points[1][1]
    for (t, lams) in points
        isempty(lams) && continue
        h_stable = min(h_stable, stable_step(method, lams))
        a = maximum(abs, lams)
        if a > worst_abs
            worst_abs, worst_t = a, t
        end
        a > 0 && (h_accurate = min(h_accurate, accuracy / a))
    end
    h_target = min(margin * h_stable, h_accurate)
    base = base_ns / 1e9
    k = h_target >= base ? 1 : ceil(Int, base / h_target)
    # The step must be a whole number of nanoseconds: take the next divisor of base_ns.
    while base_ns % k != 0
        k += 1
    end
    return (
        method = method, dt_ns = base_ns ÷ k, substeps = k, base_ns = base_ns,
        stable_step = h_stable, accurate_step = h_accurate, max_abs_lambda = worst_abs,
        at_t = worst_t, over_budget = k > max_substeps,
    )
end
