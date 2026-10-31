@block GrowthRate begin
    # Instantaneous exponential growth rate of the gap deviation from the trim gap p:
    #   lambda = d/dt ln|h - p| = v/(h - p).
    # For the linearised plant released from rest at h(0) = p + dh0 the deviation is
    # dh0*cosh(s*t) with s = sqrt(2*g/p), so lambda = s*tanh(s*t) tends to the unstable pole s
    # within a few 1/s; it stays there while the deviation is small against p.
    @inputs begin
        h::Real, [unit = "m", description = "Gap"]
        v::Real, [unit = "m/s", description = "Gap rate"]
    end
    @outputs lambda::Real, [unit = "1/s", description = "Growth rate v/(h - p)"]
    @parameters p::Real = 0.15, [unit = "m", description = "Trim gap the deviation is measured from"]
    @equations lambda ~ v / (h - p)
end
