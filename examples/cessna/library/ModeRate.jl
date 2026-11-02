@block ModeRate begin
    # The rate of a real lateral mode (sensor tap, no physics): released on a real eigenvector,
    # the bank evolves as phi0 e^(lambda t), so lambda = (d phi/dt) / phi with the exact Euler
    # rate d phi/dt = p + tan(theta) (q sin(phi) + r cos(phi)). It reads the roll mode
    # (lambda about -5.6 1/s) and the spiral (about -0.01 1/s) in the first seconds.
    @inputs begin
        phi::Real, [unit = "rad"]
        theta::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
    end
    @outputs begin
        lambda::Real, [unit = "1/s"]
        phidot::Real, [unit = "rad/s"]
    end
    @equations begin
        phidot ~ p + tan(theta) * (q * sin(phi) + r * cos(phi))
        lambda ~ phidot / phi
    end
end
