@block LeadScrew begin
    # Lead screw (spindle and nut) with load-dependent thread friction: one revolution of the
    # spindle `a` advances the nut `b` by `lead`, so `b.f = lead/(2 pi) a.f`. The thread friction
    # is a torque on the spindle proportional to the axial load F = b.e (the screw-thread law, the
    # law of the stdlib `WormGear`):
    #
    #   driving     (the spindle pushes the load)  T_loss = (lead/2pi) |F| (1/eta - 1)
    #   back-driven (the load pushes the spindle)  T_loss = (lead/2pi) |F| (1 - eta_back)
    #
    # always against the spindle speed. The power out is then `eta` times the power in while the
    # spindle drives and `eta_back` times while the nut drives. For a thread with friction angle
    # rho and lead angle lambda, eta = tan(lambda)/tan(lambda + rho) and
    # eta_back = tan(lambda - rho)/tan(lambda) ~ 2 - 1/eta: the drive is SELF-LOCKING when
    # eta_back <= 0 (eta <= 1/2); the friction then holds any axial load at rest.
    #
    # Written without a switch (no ifelse, no abs, so no kink events while the load sits near
    # zero): with s = tanh(w/w_eps) and the smooth magnitude |F| ~ sqrt(F^2 + F_eps^2),
    #
    #   T_loss = (lead/2pi) [ |F| s (c_d + c_b)/2 - F s^2 (c_d - c_b)/2 ],  c_d = 1/eta - 1, c_b = 1 - eta_back,
    #
    # which is the two branches above wherever |s| = 1 (the driving branch has F s < 0 in the
    # power-into-the-port convention of `b`). At an exact standstill the friction vanishes
    # (regularised Coulomb), so a held load creeps at a spindle speed of the order of w_eps; a
    # small w_eps keeps that creep negligible over a run. F_eps leaves a no-load friction of
    # (lead/2pi) F_eps (c_d + c_b)/2.
    @ports begin
        a::Power{Rotation}
        b::Power{Translation}
    end
    @outputs begin
        T_loss::Real, [unit = "N*m", description = "Thread friction torque on the spindle (against its speed)"]
        P_loss::Real, [unit = "W", description = "Thread friction power, T_loss * a.f (>= 0)"]
    end
    @parameters begin
        lead::Real = 0.003, [unit = "m", min = 1.0e-9, description = "Lead: nut travel per spindle revolution"]
        eta::Real = 0.7, [unit = "1", min = 1.0e-6, max = 1, description = "Efficiency when the spindle drives the nut"]
        eta_back::Real = 0.57, [unit = "1", max = 1, description = "Efficiency when the nut drives the spindle; 0 or less makes the screw self-locking"]
        w_eps::Real = 1.0e-3, [unit = "rad/s", min = 1.0e-12, description = "Spindle-speed smoothing of the friction direction, tanh(w/w_eps)"]
        F_eps::Real = 0.01, [unit = "N", min = 0, description = "Load smoothing of |F| (no-load friction)"]
    end
    @variables begin
        s::Real = 0.0, [unit = "1", description = "Friction direction factor tanh(w/w_eps)"]
        Fa::Real = 0.01, [unit = "N", description = "Smooth load magnitude sqrt(F^2 + F_eps^2)"]
    end
    @equations begin
        b.f ~ lead * a.f / 6.283185307179586
        s ~ tanh(a.f / w_eps)
        Fa ~ sqrt(b.e * b.e + F_eps * F_eps)
        T_loss ~ lead / 6.283185307179586 * (0.5 * Fa * s * (1.0 / eta - eta_back) -
                                             0.5 * b.e * s * s * (1.0 / eta - 2.0 + eta_back))
        a.e ~ -b.e * lead / 6.283185307179586 + T_loss
        P_loss ~ T_loss * a.f
    end
    @causality (a, b) => :transformer
end
