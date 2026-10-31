@block MaglevBall begin
    # Current-driven magnetic levitation plant of the MathWorks maglev example: a steel ball
    # of mass m hangs below an electromagnet, h is the gap from the magnet face down to the
    # ball and the coil current i is the input (the coil is ideal, so the current is imposed):
    #   m*dv/dt = m*g - alpha*i^2/h^2 - F_c,   dh/dt = v.
    # The magnet pulls the ball up, toward smaller h. Two stiff contacts keep a run that loses
    # the ball physical: the cover plate under the coil at h_min and the landing pedestal at
    # h_max (F_c is their force on the ball, positive pushing toward smaller h).
    @inputs i::Real, [unit = "A", description = "Coil current"]
    @outputs begin
        h::Real, [unit = "m", description = "Gap from the magnet face down to the ball"]
        v::Real, [unit = "m/s", description = "Ball velocity, positive downward (gap opening)"]
    end
    @parameters begin
        m::Real = 0.02, [unit = "kg", min = 0, description = "Ball mass"]
        g::Real = 9.81, [unit = "m/s^2", description = "Gravitational acceleration"]
        alpha::Real = 2.4832e-5, [unit = "H*m", min = 0, description = "Force constant, F = alpha*i^2/h^2 (N*m^2/A^2)"]
        h_min::Real = 0.01, [unit = "m", min = 0, description = "Gap at which the ball touches the cover plate under the coil"]
        h_max::Real = 0.3, [unit = "m", description = "Gap at which the ball lands on the pedestal"]
        k_c::Real = 1.0e4, [unit = "N/m", min = 0, description = "Contact stiffness of the plate and the pedestal"]
        d_c::Real = 10.0, [unit = "N*s/m", min = 0, description = "Contact damping"]
    end
    @variables begin
        x::Real = 0.15, [unit = "m", state = :prefer, description = "Gap state"]
        w::Real = 0.0, [unit = "m/s", state = :prefer, description = "Velocity state"]
        F_mag::Real = 0.0, [unit = "N", description = "Magnetic attraction alpha*i^2/h^2, upward"]
        F_c::Real = 0.0, [unit = "N", description = "Contact force of the plate (negative) or the pedestal (positive)"]
    end
    @equations begin
        ddt(x) ~ w
        F_mag ~ alpha * i * i / (x * x)
        F_c ~ ifelse(x > h_max, max(k_c * (x - h_max) + d_c * w, 0.0),
            ifelse(x < h_min, min(k_c * (x - h_min) + d_c * w, 0.0), 0.0))
        m * ddt(w) ~ m * g - F_mag - F_c
        h ~ x
        v ~ w
    end
end
