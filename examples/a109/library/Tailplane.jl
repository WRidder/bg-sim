@block Tailplane begin
    # The horizontal tail of the Heffley & Mnich model (lines 7410 .. 7560), a modulated source
    # applied at the tailplane. The rotor wake reaches the tail when the edge of the skewed wake,
    # D.DW = u/(vi - w) (H.HUB - H.HT) - (D.HT - D.HUB - R) (+ 1 ft for the A109), lies within the
    # rotor radius; the downwash factor is then 2 (1 - D.DW/R), else 0. The local vertical
    # velocity WA = w - eps vi + D.HT q gives the lift rho/2 (ZUU |u| u + ZUW |u| WA), or the
    # stalled rho/2 ZMAX |V| WA when |WA| > 0.3 |u| (always so in hover). The force fz is FLU.
    # With smooth = 1 (ours) the wake edge (over D.DW = 0 +- 0.3 m) and the stall (over
    # (WA/u)^2 = 0.09 +- 0.01) are tanh blends, so a closed loop cannot chatter on them, and the
    # downwash factor's cut at D.DW = R is the smooth max(x, 0) = (x + sqrt(x^2 + 0.01^2)) / 2 of
    # x = 1 - D.DW/R. That cut must not be a condition: where w passes vi (a descent at about
    # 40 kt) D.DW swings through +-10^4 m within one integrator step, and a fixed-step solver
    # that holds the condition over the step would use 2 (1 - D.DW/R) ~ -3600 there.
    @inputs begin
        u::Real
        v::Real
        w::Real
        q::Real
        vi::Real, [description = "Main-rotor induced velocity (m/s)"]
        rho::Real
    end
    @outputs begin
        fz::Real
        eps::Real, [description = "Downwash factor"]
        stall::Real, [description = "1: surface stalled"]
    end
    @parameters begin
        ZUU::Real = 0.0, [description = "Incidence lift area (m^2)"]
        ZUW::Real = -1.0, [description = "Lift-slope area (m^2)"]
        ZMAX::Real = -1.0, [description = "Stalled area (m^2)"]
        R::Real = 5.4864, [description = "Main-rotor radius (m)"]
        h_hub::Real = 0.0
        h_ht::Real = 0.0
        d_ht::Real = 0.0
        d_hub::Real = 0.0
        dw_shift::Real = 0.3048, [description = "Shift of the wake edge (A109: 1 ft)"]
        smooth::Real = 0.0, [description = "0: the report's hard switch; 1: a tanh blend over a narrow band (ours, a109-sim)"]
    end
    @variables begin
        den::Real = 1.0
        ddw::Real = 0.0
        wa::Real = 0.0
        vta::Real = 0.0
        Z::Real = 0.0
        edge::Real = 0.0
        sig::Real = 0.0
    end
    @equations begin
        den ~ vi - w
        ddw ~ u * den / (den * den + 1.0e-6) * (h_hub - h_ht) - (d_ht - d_hub - R) + dw_shift
        edge ~ smooth * 0.5 * (1.0 + tanh(ddw / 0.3)) + (1.0 - smooth) * ifelse(ddw > 0.0, 1.0, 0.0)
        eps ~ edge * (smooth * ((1.0 - ddw / R) + sqrt((1.0 - ddw / R)^2 + 1.0e-4)) +
                      (1.0 - smooth) * ifelse(ddw < R, 2.0 * (1.0 - ddw / R), 0.0))
        wa ~ w - eps * vi + d_ht * q
        vta ~ sqrt(u * u + v * v + wa * wa)
        sig ~ smooth * 0.5 * (1.0 + tanh((wa * wa - 0.09 * u * u) / (0.01 * (u * u + 1.0)))) +
              (1.0 - smooth) * ifelse(wa * wa > 0.09 * u * u, 1.0, 0.0)
        stall ~ sig
        Z ~ sig * 0.5 * rho * ZMAX * vta * wa +
            (1.0 - sig) * 0.5 * rho * (ZUU * sqrt(u * u + 1.0e-6) * u + ZUW * sqrt(u * u + 1.0e-6) * wa)
        fz ~ -Z
    end
end
