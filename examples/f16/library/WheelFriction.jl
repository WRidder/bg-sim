@block WheelFriction begin
    # Rolling resistance and the wheel brake of one leg (an R on the contact's rolling-direction
    # bond): F = mu fn tanh(v / vs), mu = mu_r + brake (mu_s - mu_r) (FGLGear: the rolling
    # coefficient, rising to the static one at full brake). Power in F v >= 0.
    @ports j::Power{Translation}
    @inputs begin
        fn::Real, [unit = "N", description = "Normal force of the leg"]
        brake::Real, [description = "Brake 0 .. 1"]
    end
    @outputs F::Real, [unit = "N"]
    @parameters begin
        mu_r::Real = 0.02, [description = "Rolling friction coefficient"]
        mu_s::Real = 0.8, [description = "Static friction coefficient (full brake)"]
        vs::Real = 0.2, [unit = "m/s", min = 1.0e-9, description = "Regularisation speed"]
    end
    @equations begin
        F ~ (mu_r + clamp(brake, 0.0, 1.0) * (mu_s - mu_r)) * fn * tanh(j.f / vs)
        j.e ~ F
    end
    @causality j => :effort_out
end
