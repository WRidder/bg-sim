@block Fin begin
    # The vertical tail of the Heffley & Mnich model (lines 7895 .. 8010), a modulated source
    # applied at the fin. Local side velocity VA = v + vi_TR - D.VT r (the tail-rotor wake blows
    # on the fin), side force rho/2 (YUU |u| u + YUV |u| VA), or the stalled rho/2 YMAX |V| VA
    # when |VA| > 0.3 |u|. The force fy is FLU. With smooth = 1 (ours) the stall switch is a tanh
    # blend over (VA/u)^2 = 0.09 +- 0.01, so a closed loop cannot chatter on it.
    @inputs begin
        u::Real
        v::Real
        r::Real
        vi_tr::Real, [description = "Tail-rotor induced velocity (m/s)"]
        rho::Real
    end
    @outputs begin
        fy::Real
        stall::Real
    end
    @parameters begin
        YUU::Real = 0.0, [description = "Camber side-force area (m^2)"]
        YUV::Real = -1.0, [description = "Side-force slope area (m^2)"]
        YMAX::Real = -1.0, [description = "Stalled area (m^2)"]
        d_vt::Real = 0.0, [description = "Fin aft of the CG (m)"]
        smooth::Real = 0.0, [description = "0: the report's hard switch; 1: a tanh blend over a narrow band (ours, a109-sim)"]
    end
    @variables begin
        va::Real = 0.0
        vta::Real = 0.0
        Y::Real = 0.0
        sig::Real = 0.0
    end
    @equations begin
        va ~ v + vi_tr - d_vt * r
        vta ~ sqrt(u * u + va * va)
        sig ~ smooth * 0.5 * (1.0 + tanh((va * va - 0.09 * u * u) / (0.01 * (u * u + 1.0)))) +
              (1.0 - smooth) * ifelse(va * va > 0.09 * u * u, 1.0, 0.0)
        stall ~ sig
        Y ~ sig * 0.5 * rho * YMAX * vta * va +
            (1.0 - sig) * 0.5 * rho * (YUU * sqrt(u * u + 1.0e-6) * u + YUV * sqrt(u * u + 1.0e-6) * va)
        fy ~ -Y
    end
end
