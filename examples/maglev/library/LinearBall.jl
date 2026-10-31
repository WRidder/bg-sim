@block LinearBall begin
    # The maglev ball frozen at the operating gap p: the LPV model of the MathWorks example
    # evaluated at one value of the scheduling parameter,
    #   d/dt [dh; dv] = A(p) [dh; dv] + B(p) di,   A(p) = [0 1; 2g/p 0],
    #   B(p) = [0; -2*sqrt(g*alpha/m)/p],          h = p + dh,
    # with di = i - i_trim(p) and i_trim(p) = sqrt(m*g/alpha)*p. It takes and returns absolute
    # values (current in, gap out), so it drops into the same loop as MaglevBall.
    # (stdlib StateSpace with D = 0 is the textbook form, but its D*u term closes an
    # algebraic loop through the PID and the trim feedforward; this block has no feedthrough.)
    @inputs i::Real, [unit = "A", description = "Coil current"]
    @outputs h::Real, [unit = "m", description = "Gap p + dh"]
    @parameters begin
        p::Real = 0.15, [unit = "m", description = "Operating gap the model is frozen at"]
        m::Real = 0.02, [unit = "kg", description = "Ball mass"]
        g::Real = 9.81, [unit = "m/s^2", description = "Gravity"]
        alpha::Real = 2.4832e-5, [unit = "H*m", description = "Force constant"]
    end
    @variables begin
        dh::Real = 0.0, [unit = "m", state = :prefer, description = "Gap deviation from p"]
        dv::Real = 0.0, [unit = "m/s", state = :prefer, description = "Velocity deviation"]
        i_trim::Real = 0.0, [unit = "A", description = "Trim current at p"]
    end
    @equations begin
        i_trim ~ sqrt(m * g / alpha) * p
        ddt(dh) ~ dv
        ddt(dv) ~ 2.0 * g / p * dh - 2.0 * sqrt(g * alpha / m) / p * (i - i_trim)
        h ~ p + dh
    end
end
