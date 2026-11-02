@block WheelSide begin
    # The cornering force of one tyre (an R on the contact's lateral bond): FGLGear's
    # magic-formula side force over the slip angle in degrees,
    #   slip = atan(vy / sqrt(vx^2 + vs^2)),   Bs = B slip
    #   F = fn mu_s sin(C atan(Bs - E (Bs - atan(Bs))))
    # (B 0.06/deg, C 2.8, E 1.03: FGLGear's defaults; D = mu_s fn). vs keeps the slip angle
    # defined at a standstill. Power in F vy >= 0 below the peak slip.
    @ports j::Power{Translation}
    @inputs begin
        fn::Real, [unit = "N", description = "Normal force of the leg"]
        vx::Real, [unit = "m/s", description = "Rolling speed of the leg"]
    end
    @outputs F::Real, [unit = "N"]
    @parameters begin
        mu_s::Real = 0.8
        B::Real = 0.06, [description = "Stiffness factor per degree of slip"]
        C::Real = 2.8
        E::Real = 1.03
        vs::Real = 2.0, [unit = "m/s", min = 1.0e-9, description = "Regularisation speed of the slip angle"]
    end
    @variables begin
        slip::Real = 0.0, [description = "Slip angle (deg)"]
        bs::Real = 0.0
    end
    @equations begin
        slip ~ atan(j.f / sqrt(vx * vx + vs * vs)) * 57.29577951308232
        bs ~ B * slip
        F ~ fn * mu_s * sin(C * atan(bs - E * (bs - atan(bs))))
        j.e ~ F
    end
    @causality j => :effort_out
end
