# Step-size and integrator analysis (plan/EXPORT_PLAN.md D-EX7).
#
# Fixed-step methods are limited by stability and by accuracy. Both follow from the
# eigenvalues λ of the Jacobian, sampled at the initial point and, when a reference run is
# given, along its trajectory. For a DAE (a singular mass matrix) these are the finite
# eigenvalues of the pencil (J, M): the eigenvalues of the Schur complement on the
# differential rows, which is the ODE the algebraic equations leave.
#
# Explicit methods (Euler, RK4):
#   stability  |R(hλ)| <= 1 for every λ with Re λ < 0, R the method's stability function
#              (Euler 1 + z, RK4 the degree-4 Taylor polynomial);
#   accuracy   h·|λ| <= accuracy (default 0.3) for every λ: the step resolves the fastest
#              mode.
# Rosenbrock methods (ROS2, ROS34PW2, Rodas4P; all L-stable, so stability never limits h):
#   every mode is either resolved, |R(hλ) - e^(hλ)| <= tol·max(1, |e^(hλ)|) with tol the RK4
#   error at h·|λ| = accuracy (so both families resolve a mode equally well), or damped,
#   |R(hλ)| <= damping and |e^(hλ)| <= damping: a parasitic fast mode the method kills in a
#   step, as the exact flow does, or damped numerically, |R(hλ)| <= damping and
#   h·|λ| >= stiff_ratio (default 10): a stiff mode far above the step's bandwidth that the
#   exact flow does not damp (an undamped joint stiffness), which the method kills although
#   the model would keep it ringing. W213 reports how many and from which frequency; forcing
#   rk4 resolves them. A mode in between (a lightly damped oscillation near the bandwidth,
#   or a decay of a few steps) must be resolved, so an LC circuit or a pendulum in the
#   bandwidth is still followed.
# Both are heuristics; the example harness measures the real error.
#
# The internal step is the communication step (and every discrete period) divided by the
# smallest whole number of substeps that satisfies the rule, with a whole number of
# nanoseconds. `choose_method` compares the candidates by estimated cost per communication
# step (D-EX7c): derivative calls, the Jacobian, the LU (n³/3) and the solves.

import LinearAlgebra

const EXPLICIT_METHODS = (:euler, :rk4)
const ROSENBROCK_METHODS = (:ros2, :ros34pw2, :rodas4p)
const EXPORT_METHODS = (EXPLICIT_METHODS..., ROSENBROCK_METHODS...)

"""Rosenbrock tableaus in the transformed form (`bg_solver.c` has the same numbers):
`W = M - γhJ`, `u_i = x + Σ a_ij k_j`, `W k_i = γh (f(t + c_i h, u_i) + d_i h f_t + M Σ (c_ij/h) k_j)`,
`x⁺ = x + Σ b_i k_i`. `order` is the order for ODEs and for index-1 DAEs."""
const ROSENBROCK_TABLEAUS = Dict{Symbol,NamedTuple}(
    :ros2 => (gamma = 1.7071067811865475, order = 2,
        a = [0 0; 0.585786437626905 0],
        c_ = [0 0; -1.17157287525381 0],
        c = [0.0, 1.0], d = [1.7071067811865475, -1.7071067811865475],
        b = [0.8786796564403574, 0.2928932188134525]),
    :ros34pw2 => (gamma = 0.435866521508459, order = 3,
        a = [0 0 0 0
             2.0 0 0 0
             1.4192173174557647 -0.2592322116729697 0 0
             4.18476048231916 -0.28519201735549593 2.294280360279042 0],
        c_ = [0 0 0 0
              -4.588560720558084 0 0 0
              -4.18476048231916 0.28519201735549593 0 0
              -6.368179200128359 -6.795620944466837 2.8700986043310563 0],
        c = [0.0, 0.871733043016918, 0.7315799577888524, 1.0],
        d = [0.435866521508459, -0.435866521508459, -0.4133333762338865, -5.551115123125783e-17],
        b = [4.1847604823191595, -0.28519201735549565, 2.2942803602790414, 1.0]),
    :rodas4p => (gamma = 0.25, order = 4,
        a = [0 0 0 0 0 0
             3 0 0 0 0 0
             1.831036793486759 0.4955183967433795 0 0 0 0
             2.304376582692669 -0.05249275245743001 -1.176798761832782 0 0 0
             -7.170454962423024 -4.741636671481785 -16.31002631330971 -1.062004044111401 0 0
             -7.170454962423024 -4.741636671481785 -16.31002631330971 -1.062004044111401 1 0],
        c_ = [0 0 0 0 0 0
              -12 0 0 0 0 0
              -8.791795173947035 -2.207865586973518 0 0 0 0
              10.81793056857153 6.780270611428266 19.5348594464241 0 0 0
              34.19095006749676 15.49671153725963 54.7476087596413 14.16005392148534 0 0
              34.62605830930532 15.30084976114473 56.99955578662667 18.40807009793095 -5.714285714285717 0],
        c = [0.0, 0.75, 0.21, 0.63, 1.0, 1.0],
        d = [0.25, -0.5, -0.023504, -0.0362, 0.0, 0.0],
        b = [-7.170454962423024, -4.741636671481785, -16.31002631330971, -1.062004044111401, 1.0, 1.0]),
)

is_rosenbrock(method::Symbol) = method in ROSENBROCK_METHODS

"""Stages of a method: derivative calls per step (Rosenbrock: also the solves)."""
method_stages(method::Symbol) =
    method === :euler ? 1 : method === :rk4 ? 4 : length(ROSENBROCK_TABLEAUS[method].b)

"""    stability_function(method, z) -> ComplexF64

`R(z)`: one step of `method` on `x' = λx` from `x = 1`, with `z = hλ`. For a Rosenbrock
method the stage equations reduce to `(1/γ - z) k_i = z (1 + Σ a_ij k_j) + Σ c_ij k_j`."""
function stability_function(method::Symbol, z)
    z = ComplexF64(z)
    method === :euler && return 1 + z
    method === :rk4 && return 1 + z + z^2 / 2 + z^3 / 6 + z^4 / 24
    tab = ROSENBROCK_TABLEAUS[method]
    s = length(tab.b)
    k = zeros(ComplexF64, s)
    for i in 1:s
        r = z
        for j in 1:i-1
            r += z * tab.a[i, j] * k[j] + tab.c_[i, j] * k[j]
        end
        k[i] = r / (1 / tab.gamma - z)
    end
    return 1 + sum(tab.b[i] * k[i] for i in 1:s)
end

amplification(method::Symbol, z) = abs(stability_function(method, z))

"""    stable_step(method, lams) -> Float64

The largest `h` with `|R(hλ)| <= 1` for every eigenvalue in `lams` with a negative real part
(bisection per eigenvalue). `Inf` when no eigenvalue limits the step, which is always the
case for the (L-stable) Rosenbrock methods."""
function stable_step(method::Symbol, lams)
    h = Inf
    for λ in lams
        real(λ) < -1e-12 * max(1.0, abs(λ)) || continue
        if is_rosenbrock(method)
            # A-stable: check a log grid of steps; the first unstable one would bound h.
            for e in range(-3, 9; length = 97)
                hh = 10.0^e / abs(λ)
                if amplification(method, hh * λ) > 1 + 1e-12
                    h = min(h, hh)
                    break
                end
            end
            continue
        end
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

"""    pencil_eigvals(J, mass) -> Vector{ComplexF64}

The finite eigenvalues of `M x' = J x` for a diagonal `mass`: with `d` the rows where the
mass is non-zero and `a` the algebraic rows, the eigenvalues of
`M_dd⁻¹ (J_dd - J_da J_aa⁻¹ J_ad)`. Throws `LinearAlgebra.SingularException` when `J_aa` is
singular (the DAE is not index 1 at that point)."""
function pencil_eigvals(J::AbstractMatrix, mass::AbstractVector)
    a = findall(iszero, mass)
    isempty(a) && return ComplexF64.(LinearAlgebra.eigvals(J ./ mass))
    d = findall(!iszero, mass)
    isempty(d) && return ComplexF64[]
    Jaa = J[a, a]
    F = LinearAlgebra.lu(Jaa; check = false)
    LinearAlgebra.issuccess(F) && LinearAlgebra.cond(Jaa, 1) < 1e14 ||
        throw(LinearAlgebra.SingularException(0))
    S = J[d, d] - J[d, a] * (F \ J[a, d])
    return ComplexF64.(LinearAlgebra.eigvals(S ./ mass[d]))
end

"""    spectrum_scan(jac_fn, x0, p0, names_x, names_p, iv_start; reference_dir, samples,
                  ranges, mass)

The eigenvalues of the numeric Jacobian at the initial point and at `samples` rows of the
reference run (states and held values read from the recorded signals when present). With a
`mass` diagonal they are the finite eigenvalues of the pencil (`pencil_eigvals`); a sample
where the algebraic block is singular is skipped. Returns a vector of `(t, eigenvalues)`."""
function spectrum_scan(jac_fn, x0::Vector{Float64}, p0::Vector{Float64},
    names_x::Vector{String}, names_p::Vector{String}, t0::Float64;
    reference_dir = nothing, samples::Int = 25, ranges = Tuple{Int,Float64,Float64}[],
    mass = nothing)
    points = Tuple{Float64,Vector{ComplexF64}}[]
    eig(J) = mass === nothing ? ComplexF64.(LinearAlgebra.eigvals(J)) : pencil_eigvals(J, mass)
    function add!(t, J)
        all(isfinite, J) || return
        lams = try
            eig(J)
        catch err
            err isa LinearAlgebra.SingularException || rethrow()
            return
        end
        push!(points, (t, lams))
    end
    isempty(x0) && return points
    add!(t0, jac_fn(x0, p0, t0))
    # Declared ranges of runtime-settable values `(index into p, lo, hi)`: each end on its
    # own, and every corner of the box when there are at most 6 of them.
    for (k, lo, hi) in ranges, v in (lo, hi)
        p = copy(p0); p[k] = v
        add!(t0, jac_fn(x0, p, t0))
    end
    if 2 <= length(ranges) <= 6
        for bits in 0:(2^length(ranges) - 1)
            p = copy(p0)
            for (j, (k, lo, hi)) in enumerate(ranges)
                p[k] = (bits >> (j - 1)) & 1 == 1 ? hi : lo
            end
            add!(t0, jac_fn(x0, p, t0))
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
            add!(row[1], jac_fn(x, p, row[1]))
        end
    end
    return points
end

function _spectrum_summary(points)
    worst_abs = 0.0
    worst_t = isempty(points) ? 0.0 : points[1][1]
    for (t, lams) in points
        isempty(lams) && continue
        a = maximum(abs, lams)
        if a > worst_abs
            worst_abs, worst_t = a, t
        end
    end
    return worst_abs, worst_t
end

"""    choose_step(method, points, base_ns; margin, accuracy, max_substeps, damping,
                stiff_ratio) -> NamedTuple

The internal step for `method`: `base_ns` (the communication step and every discrete period
are multiples of it) divided by the smallest admissible substep count. For Euler and RK4 that
keeps `h <= margin * stable_step` and `h * |λ| <= accuracy` at every scanned point; for a
Rosenbrock method every mode must be resolved or damped (file header)."""
function choose_step(method::Symbol, points, base_ns::Int64; margin = 0.5, accuracy = 0.3,
    max_substeps = 1000, damping = 0.05, stiff_ratio = 10.0)
    is_rosenbrock(method) && return _choose_step_rosenbrock(method, points, base_ns;
        accuracy, max_substeps, damping, stiff_ratio)
    h_stable = Inf
    h_accurate = Inf
    worst_abs, worst_t = _spectrum_summary(points)
    for (t, lams) in points
        isempty(lams) && continue
        h_stable = min(h_stable, stable_step(method, lams))
        a = maximum(abs, lams)
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

"""The per-step error tolerance on one mode: what RK4 makes at `h·|λ| = accuracy`."""
mode_tolerance(accuracy) = abs(stability_function(:rk4, -accuracy) - exp(-accuracy))

"""    mode_class(method, z, tol, damping, stiff_ratio) -> Symbol

How a Rosenbrock step `z = hλ` treats one mode (file header): `:resolved`; `:damped` (the
method and the exact flow both shrink it below `damping` in one step); `:numerical` (only the
method does, and the mode is stiff, `|z| >= stiff_ratio`; W213); or `:fail`."""
function mode_class(method, z, tol, damping, stiff_ratio)
    ez = exp(ComplexF64(z))
    r = stability_function(method, z)
    abs(r - ez) <= tol * max(1.0, abs(ez)) && return :resolved
    abs(r) <= damping || return :fail
    abs(ez) <= damping && return :damped
    return abs(z) >= stiff_ratio ? :numerical : :fail
end

_mode_ok(method, z, tol, damping, stiff_ratio) =
    mode_class(method, z, tol, damping, stiff_ratio) !== :fail

"""The distinct modes of the scanned points: one per conjugate pair, none at zero (the
samples repeat most eigenvalues)."""
function distinct_modes(points)
    # (`+ 0.0` maps -0.0 to 0.0, so a conjugate pair on the imaginary axis is one mode)
    lams = unique(λ -> (round(real(λ); sigdigits = 6) + 0.0, round(abs(imag(λ)); sigdigits = 6)),
        ComplexF64[λ for (_, ls) in points for λ in ls])
    return filter!(λ -> abs(λ) > 1e-12, lams)
end

"""    numerically_damped(method, points, h; accuracy, damping, stiff_ratio) -> (count, min_hz)

The modes a Rosenbrock step `h` accepts only because the method damps them (`:numerical`):
how many, and the lowest of their natural frequencies `|λ|/2π` in Hz (`Inf` when none)."""
function numerically_damped(method::Symbol, points, h::Real; accuracy = 0.3, damping = 0.05,
    stiff_ratio = 10.0, kwargs...)
    is_rosenbrock(method) || return (0, Inf)
    tol = mode_tolerance(accuracy)
    lams = filter(λ -> mode_class(method, h * λ, tol, damping, stiff_ratio) === :numerical,
        distinct_modes(points))
    return (length(lams), isempty(lams) ? Inf : minimum(abs, lams) / 2π)
end

function _choose_step_rosenbrock(method, points, base_ns; accuracy, max_substeps, damping,
    stiff_ratio)
    tol = mode_tolerance(accuracy)
    worst_abs, worst_t = _spectrum_summary(points)
    lams = distinct_modes(points)
    h_stable = isempty(points) ? Inf : minimum(stable_step(method, ls) for (_, ls) in points)
    kmax = 10 * max_substeps
    divisors = [k for k in 1:min(kmax, base_ns) if base_ns % k == 0]
    k = 0
    for kk in divisors
        h = base_ns / kk / 1e9
        if all(λ -> _mode_ok(method, h * λ, tol, damping, stiff_ratio), lams)
            k = kk
            break
        end
    end
    found = k > 0
    found || (k = last(divisors))
    return (
        method = method, dt_ns = base_ns ÷ k, substeps = k, base_ns = base_ns,
        stable_step = h_stable, accurate_step = found ? base_ns / k / 1e9 : 0.0,
        max_abs_lambda = worst_abs, at_t = worst_t, over_budget = !found || k > max_substeps,
    )
end

"""    step_rule_met(method, points, h; margin, accuracy, damping, stiff_ratio) -> Bool

Whether the internal step `h` meets `method`'s rule at every scanned point."""
function step_rule_met(method::Symbol, points, h::Real; margin = 0.5, accuracy = 0.3,
    damping = 0.05, stiff_ratio = 10.0, max_substeps = 0)
    lams = ComplexF64[λ for (_, ls) in points for λ in ls]
    if is_rosenbrock(method)
        tol = mode_tolerance(accuracy)
        return all(λ -> _mode_ok(method, h * λ, tol, damping, stiff_ratio), lams)
    end
    return all(λ -> h * abs(λ) <= accuracy, lams) && h <= margin * stable_step(method, lams)
end

"""    derivative_call_cost(f_ops, n) -> Float64

The cost model's price of one derivative call: the right-hand side's operations plus the
loads, stores and call overhead."""
derivative_call_cost(f_ops::Real, n::Integer) = f_ops + 2n + 10

"""    step_cost(method, n; f_ops, jac_ops, has_t, lu_ops, solve_ops) -> Float64

Estimated floating-point work of one internal step on `n` states: `f_ops` per derivative
call, `jac_ops` per Jacobian. A Rosenbrock step forms and factors `W` (`lu_ops`, dense
n² + n³/3 by default), solves once per stage (`solve_ops`, dense 2n²) and combines the
stages; with `has_t` it spends one more derivative call on `df/dt`. The sparse LU passes its
own counts (`lu_flops`, `lu_solve_flops`)."""
function step_cost(method::Symbol, n::Integer; f_ops::Real, jac_ops::Real = 0.0,
    has_t::Bool = false, lu_ops::Real = n^2 + n^3 / 3, solve_ops::Real = 2n^2)
    call = derivative_call_cost(f_ops, n)
    method === :euler && return call + 2n
    method === :rk4 && return 4call + 12n
    s = method_stages(method)
    return jac_ops + lu_ops + s * (call + solve_ops + 2s * n) + (has_t ? call + 2n : 0)
end

"""    choose_method(candidates, points, base_ns, n; f_ops, jac_ops, has_t, lu_ops,
                  solve_ops, kwargs...) -> (choice, table)

Of `candidates`, the method with the lowest estimated cost per `base_ns` (substeps × step
cost) whose step rule is met within the substep budget; when none is, the cheapest.
`jac_ops` is a function of the method (the Jacobian is only built when a Rosenbrock method
can win). `table` lists every candidate for the report."""
function choose_method(candidates, points, base_ns::Int64, n::Integer; f_ops, jac_ops,
    has_t = false, lu_ops::Real = n^2 + n^3 / 3, solve_ops::Real = 2n^2, kwargs...)
    table = NamedTuple[]
    for m in candidates
        c = choose_step(m, points, base_ns; kwargs...)
        cost = c.substeps * step_cost(m, n; f_ops, jac_ops = jac_ops(m), has_t, lu_ops,
            solve_ops)
        push!(table, (method = m, choice = c, cost = cost))
    end
    ok = filter(r -> !r.choice.over_budget, table)
    pool = isempty(ok) ? table : ok
    best = pool[argmin([r.cost for r in pool])]
    return best.choice, table
end
