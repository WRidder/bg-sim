@block BeaverRollAP begin
    # The asymmetric channel of the FDC 'Beaver' autopilot [FDC apilot/aplib.mdl, REP chapter 11]:
    # roll attitude hold (RAH) with the heading hold (HH) as its outer loop, and the turn
    # coordinator on the rudder. Gains in rad/rad (1 V = 1 deg), scheduled on V (m/s):
    #
    #   Kphi = 9.75e-4 V^2 - 0.108 V + 2.335625     Kpsi = 0.05 V - 1.1
    #   drr  = -7.5e-5 V^2 + 0.0095 V - 0.4606 (s)
    #
    #   dphi_ref = clamp(RAH: phi_ref, HH: Kpsi (psi_ref - psi);  +-30 deg)
    #   u1 = clamp(Kphi (dphi_ref - phi), +-3.75 deg),   d(I)/dt = 0.25 u1, I limited to +-1 deg
    #   da = u1 + I + 0.165 r
    #   dr = -4 (9.80665/V) sin(phi) + (drr + 4) r          (turn coordinator)
    #
    # Ours (see the README): mode 0 off, 1 RAH, 2 HH; absolute references with the heading error
    # wrapped to (-pi, pi]; the limited integrator as back-calculation (t_aw).
    @inputs begin
        mode::Real, [description = "0 off, 1 roll attitude hold, 2 heading hold"]
        phi::Real
        r::Real
        psi::Real
        V::Real
        phi_ref::Real, [description = "Bank reference (RAH)"]
        psi_ref::Real, [description = "Heading reference (HH)"]
    end
    @outputs begin
        da::Real, [description = "Aileron servo command (1 V = 1 deg)"]
        dr::Real, [description = "Rudder servo command (1 V = 1 deg)"]
        dphi_ref::Real, [description = "Limited bank reference"]
    end
    @parameters begin
        t_aw::Real = 0.05, [description = "Back-calculation time of the limited integrator"]
        t_off::Real = 0.5, [description = "Bleed time of the integrator while the loop is off"]
    end
    @variables begin
        I::Real = 0.0, [state = :prefer, description = "Integrator (rad)"]
        Kphi::Real = 0.0
        Kpsi::Real = 0.0
        drr::Real = 0.0
        on::Real = 0.0
        epsi::Real = 0.0
        u1::Real = 0.0
        Il::Real = 0.0
    end
    @equations begin
        on ~ ifelse(mode > 0.5, 1.0, 0.0)
        Kphi ~ 9.75e-4 * V * V - 0.108 * V + 2.335625
        Kpsi ~ 0.05 * V - 1.1
        drr ~ -7.5e-5 * V * V + 0.0095 * V - 0.4606
        epsi ~ atan(sin(psi_ref - psi), cos(psi_ref - psi))
        dphi_ref ~ clamp(ifelse(mode > 1.5, Kpsi * epsi, phi_ref), -0.5235987755982988, 0.5235987755982988)
        u1 ~ clamp(Kphi * (dphi_ref - phi), -0.06544984694978735, 0.06544984694978735)
        Il ~ clamp(I, -0.017453292519943295, 0.017453292519943295)
        da ~ on * (u1 + Il + 0.165 * r)
        dr ~ on * (-4.0 * (9.80665 / V) * sin(phi) + (drr + 4.0) * r)
        ddt(I) ~ ifelse(on > 0.5, 0.25 * u1 + (Il - I) / t_aw, -I / t_off)
    end
end
