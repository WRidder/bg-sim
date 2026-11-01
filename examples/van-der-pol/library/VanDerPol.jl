@block VanDerPol begin
    # The textbook Van der Pol oscillator as an equation model,
    #   x'' - mu (1 - x^2) x' + x = 0,   ' = d/dtau,  tau = w0 t,
    # written as two first-order equations in the state (x, y = x'). With w0 = 1 the run time is
    # tau itself; with the w0 of a physical oscillator the block runs in that system's seconds
    # and is its scaled reference.
    @parameters begin
        mu::Real = 1.0, [min = 0, description = "Nonlinearity (damping) parameter"]
        w0::Real = 1.0, [min = 0, description = "Time scale: tau = w0 t (rad/s)"]
    end
    @outputs begin
        x::Real, [description = "Scaled state x"]
        y::Real, [description = "Scaled rate y = dx/dtau"]
    end
    @variables begin
        xs::Real = 0.5, [state = :prefer, description = "State x"]
        ys::Real = 0.0, [state = :prefer, description = "State y = dx/dtau"]
    end
    @equations begin
        ddt(xs) ~ w0 * ys
        ddt(ys) ~ w0 * (mu * (1.0 - xs * xs) * ys - xs)
        x ~ xs
        y ~ ys
    end
end
