@block StrutDamper begin
    # The damper of a landing-gear leg (FGLGear's linear damping, an R on the contact's normal
    # 1-junction), active only while the wheel is down (sig from StrutSpring) and clamped so the
    # leg never pulls the aircraft down: with Fb = b sig dq/dt,
    #   F = Fb + sig sp(-Fk - Fb),   sp the smooth positive part over `feps`
    # (Fk + F >= 0 up to the smoothing). Power in j.e j.f = F dq/dt.
    @ports j::Power{Translation}
    @inputs begin
        Fk::Real, [unit = "N", description = "Spring force of the leg"]
        sig::Real, [description = "Wheel-down factor of the leg (StrutSpring.sig)"]
    end
    @outputs F::Real, [unit = "N", description = "Damper force"]
    @parameters begin
        b::Real = 23350.0, [unit = "N*s/m", min = 0, description = "Damping (JSBSim damping_coeff)"]
        feps::Real = 1.0, [unit = "N", min = 1.0e-12, description = "Smoothing force of the no-pull clamp"]
    end
    @variables begin
        Fb::Real = 0.0, [unit = "N"]
        z::Real = 0.0, [unit = "N"]
        rz::Real = 1.0, [unit = "N"]
        zp::Real = 0.0, [unit = "N"]
    end
    @equations begin
        Fb ~ b * j.f * sig
        z ~ -Fk - Fb
        rz ~ sqrt(z * z + feps * feps)
        zp ~ ifelse(z < 0.0, 0.5 * feps * feps / (rz - z), 0.5 * (z + rz))
        F ~ Fb + sig * zp
        j.e ~ F
    end
    @causality j => :effort_out
end
