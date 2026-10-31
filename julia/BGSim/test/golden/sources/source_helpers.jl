# Shared references of the periodic signal-source goldens (Sawtooth, Triangle, Trapezoid,
# RepeatingTable, the smooth sources). Included by those test files, not by the golden walk
# (the file name does not start with `test_`).
module SourceGolden

using ..BondGraphGolden

export period_phase, snap, gl_area, edges, run_sources, source_errors

"""    run_sources(block, cases; t_end, points) -> (columns, result)

One model with an instance `S<i>` of `stdlib:sources/<block>` per entry of `cases` (its
parameter Dict, values as strings), each driving an Integrator `I<i>`, run through the real
pipeline with the golden settings."""
function run_sources(block, cases; t_end, points)
    nodes, conns = Any[], Any[]
    for (i, params) in enumerate(cases)
        push!(nodes, bg_node("s$i", "S$i", bg_ref("stdlib:sources/" * block);
            params = Dict{String,Any}(params)))
        push!(nodes, bg_node("i$i", "I$i", bg_ref("stdlib:continuous/Integrator")))
        push!(conns, bg_conn("c$i", "signal", "s$i", "y", "i$i", "u"))
    end
    columns, result, _ = bg_run(bg_model(block * "DrivesIntegrators", nodes, conns;
        t_end = t_end, points = points))
    return columns, result
end

"""    source_errors(columns, i, ref, breaks; t_end, points) -> (output error, area error)

The largest error of `S<i>/y` against `ref(t)` over the output grid, and of the integral
`I<i>/y` against the exact area of `ref` over every recorded row (event pairs included)."""
function source_errors(columns, i, ref, breaks; t_end, points)
    ey = maximum(abs(bg_value(columns, "S$i/y", t) - ref(t))
                 for t in range(0.0, t_end; length = points))
    times = columns["time"]
    ea = maximum(abs.(bg_all(columns, "I$i/y") .- [gl_area(ref, 0.0, t, breaks) for t in times]))
    return ey, ea
end

"""    period_phase(t, origin, period) -> (n, f)

The period index `n` and the fraction `f` in [0, 1) of `t` in a periodic signal whose
periods start at `origin`. A time within 1e-9 periods of an edge is taken **at** the edge
(f = 0), which is the right limit the recorder's event pairs end with: decimal edges such
as 0.3 = 3 * 0.1 are not exact in floating point, so a plain `floor` would put them a
period early."""
function period_phase(t, origin, period)
    p = (t - origin) / period
    n = round(p)
    abs(p - n) < 1.0e-9 && return Int(n), 0.0
    fl = floor(p)
    return Int(fl), p - fl
end

"""    snap(s, points) -> s

`s` moved onto the first of `points` within 1e-12 of it (the right limit at a breakpoint)."""
function snap(s, points)
    for b in points
        abs(s - b) < 1.0e-12 && return b
    end
    return s
end

"""    edges(origin, period, t_end) -> Vector{Float64}

Every `origin + k*period` in (-period, t_end + period), for the integration breakpoints."""
edges(origin, period, t_end) =
    [origin + k * period for k in floor(Int, -origin / period) - 1:ceil(Int, (t_end - origin) / period) + 1]

const GL_X = (-0.906179845938664, -0.5384693101056831, 0.0, 0.5384693101056831, 0.906179845938664)
const GL_W = (0.23692688505618908, 0.47862867049936647, 0.5688888888888889, 0.47862867049936647, 0.23692688505618908)

"""    gl_area(f, a, b, breaks; h = 0.005) -> Float64

The integral of the piecewise-smooth `f` over [a, b]: 5-point Gauss-Legendre on pieces of at
most `h` between the `breaks`, so `f` is never evaluated at a breakpoint and every piecewise
polynomial of degree up to 9 is integrated exactly."""
function gl_area(f, a, b, breaks; h = 0.005)
    b <= a && return 0.0
    pts = sort!(unique!(vcat([a, b], [x for x in breaks if a < x < b])))
    total = 0.0
    for i in 1:length(pts) - 1
        lo, hi = pts[i], pts[i + 1]
        n = max(1, ceil(Int, (hi - lo) / h))
        for j in 0:n - 1
            l = lo + (hi - lo) * j / n
            r = lo + (hi - lo) * (j + 1) / n
            m, w = (l + r) / 2, (r - l) / 2
            total += w * sum(GL_W[q] * f(m + w * GL_X[q]) for q in 1:5)
        end
    end
    return total
end

end # module
