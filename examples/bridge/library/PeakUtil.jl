@block PeakUtil begin
    # The largest utilisation of a truss so far: a peak hold of max_k |util[k]| for a dashboard
    # gauge (the end value of a run is its worst moment; during playback, the worst so far).
    #
    # Smooth, so it adds no events: with |u| ~ a_k = sqrt(util[k]^2 + e^2) and the soft ramp
    # r(x) = (x + sqrt(x^2 + e^2)) / 2,
    #
    #     d(peak)/dt = sum_k r(a_k - peak) / tau
    #
    # follows any bar above the held value within about tau |d util/dt| and creeps by less than
    # nb e^2 / (4 tau |a_k - peak|) per second below it (e = 1e-4, tau = 1 ms: 1e-3 over a run).
    # A failed bar's util drops to zero, but the peak keeps the 1 it reached when it failed.
    @constants nb::Int = 2, [min = 1, description = "Number of bars"]
    @inputs util::Vec{nb}, [unit = "1", description = "Bar utilisations (truss output util)"]
    @outputs peak::Real, [unit = "1"]
    @parameters begin
        tau::Real = 1.0e-3, [unit = "s", min = 1.0e-6, description = "Tracking time constant"]
        e::Real = 1.0e-4, [unit = "1", min = 1.0e-12, description = "Smoothing width"]
    end
    @variables begin
        p::Real = 0.0, [unit = "1", state = :prefer, description = "Held peak"]
        a::Vec{nb}, [unit = "1", description = "Smooth |util|"]
        r::Vec{nb}, [unit = "1", description = "Soft ramp of a - p"]
        s::Vec{nb}, [unit = "1", description = "Running sum of r"]
    end
    @equations begin
        for k in 1:nb
            a[k] ~ sqrt(util[k] * util[k] + e * e)
            r[k] ~ 0.5 * (a[k] - p + sqrt((a[k] - p) * (a[k] - p) + e * e))
        end
        s[1] ~ r[1]
        for k in 2:nb
            s[k] ~ s[k - 1] + r[k]
        end
        ddt(p) ~ s[nb] / tau
        peak ~ p
    end
end
