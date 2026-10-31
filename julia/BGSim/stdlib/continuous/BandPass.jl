@block BandPass begin
    # Second-order band-pass filter
    #   y/u = k * bandwidth*s / (s^2 + bandwidth*s + w0^2):
    # the gain is k at the centre frequency w0, falls to k/sqrt(2) at the edges of a band
    # exactly `bandwidth` wide (the edges are at geometric mean w0), and has no DC gain.
    # Frequencies are angular (rad/s). Q = w0 / bandwidth. Realised as a controllable
    # canonical form with x1 = z, x2 = z'.
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        k::Real = 1.0, [description = "Gain at the centre frequency"]
        w0::Real = 10.0, [unit = "rad/s", min = 1.0e-9, description = "Centre frequency"]
        bandwidth::Real = 2.0, [unit = "rad/s", min = 1.0e-9, description = "Width of the -3 dB pass band"]
    end
    @variables begin
        x1::Real = 0.0, [description = "Canonical state z"]
        x2::Real = 0.0, [description = "Canonical state z'"]
    end
    @equations begin
        ddt(x1) ~ x2
        ddt(x2) ~ u - w0^2 * x1 - bandwidth * x2
        y ~ k * bandwidth * x2
    end
end
