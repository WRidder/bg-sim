@block Notch begin
    # Second-order notch (band-stop) filter
    #   y/u = k * (s^2 + 2*depth*zeta*w0*s + w0^2) / (s^2 + 2*zeta*w0*s + w0^2),
    #   zeta = bandwidth / (2*w0).
    # The gain is k far from w0 and k*depth at w0 (depth = 0: an ideal notch); with depth = 0
    # the -3 dB band around w0 is exactly `bandwidth` wide. Frequencies are angular (rad/s).
    # Realised as a controllable canonical form with x1 = z, x2 = z'.
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "Gain away from the notch"]
        w0::Real = 10.0, [unit = "rad/s", min = 1.0e-9, description = "Centre frequency of the notch"]
        bandwidth::Real = 2.0, [unit = "rad/s", min = 1.0e-9, description = "Width of the notch: the -3 dB band for depth = 0"]
        depth::Real = 0.0, [min = 0, description = "Gain at w0 relative to k: 0 removes w0 completely, 1 is no notch"]
    end
    @variables begin
        x1::Real = 0.0, [description = "Canonical state z"]
        x2::Real = 0.0, [description = "Canonical state z'"]
    end
    @equations begin
        ddt(x1) ~ x2
        ddt(x2) ~ u - w0^2 * x1 - bandwidth * x2
        y ~ k * (u + (depth - 1.0) * bandwidth * x2)
    end
end
