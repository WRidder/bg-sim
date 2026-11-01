@block F16Forces begin
    # Force and moment build-up of the Stevens & Lewis F-16 (NASA TP-1538 data), as the six
    # inputs of `stdlib:multibond/ExternalWrenchSpatial` in the geometric body frame
    # (x forward, y left, z up, about the centre of gravity).
    #
    # The table values come in from stdlib Lookup1D/Lookup2D blocks (alpha, beta, el in deg):
    #   cx0 = CX(alpha, el), cz0 = CZ(alpha), cm0 = CM(alpha, el), cl0 = CL(alpha, beta),
    #   cn0 = CN(alpha, beta) (the book tabulates them over |beta| and applies sgn(beta); the tables here are
    #   extended to negative beta as odd functions, so no sign switch is needed), dlda .. dndr (alpha, beta) and the nine damping derivatives.
    # The build-up is the book's F16 subroutine (Section 3.6), in FRD axes:
    #   CX = cx0 + cbar q/(2 Vt) CXq
    #   CY = -0.02 beta + 0.021 ail/20 + 0.086 rdr/30 + b/(2 Vt) (CYr r + CYp p)
    #   CZ = cz0 (1 - (beta/57.3)^2) - 0.19 el/25 + cbar q/(2 Vt) CZq
    #   Cl = cl0 + dlda ail/20 + dldr rdr/30 + b/(2 Vt) (Clr r + Clp p)
    #   Cm = cm0 + cbar q/(2 Vt) Cmq + CZ (xcgr - xcg)
    #   Cn = cn0 + dnda ail/20 + dndr rdr/30 + b/(2 Vt) (Cnr r + Cnp p) - CY (xcgr - xcg) cbar/b
    # Forces qbar S C, moments qbar S b Cl, qbar S cbar Cm, qbar S b Cn. The thrust acts along
    # body x through the centre of gravity; the engine's angular momentum `he` along body x adds
    # the gyroscopic torque -w x he. The book's model has no Mach (compressibility) effects in
    # the aerodynamics: Mach only enters the thrust tables.
    #
    # nz is the load factor at the centre of gravity, -Z_aero/(m g0) (1 g in level flight), as
    # in the book; ny is the lateral load factor Y_aero/(m g0) (positive to the right). P_ext is
    # the power of the aero force, thrust and moments, F.v + M.w.
    @inputs begin
        vt::Real, [unit = "m/s"]
        alpha_deg::Real
        beta_deg::Real
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        qbar::Real, [unit = "Pa"]
        el::Real, [description = "Elevator (stabilator), deg, positive trailing edge down"]
        ail::Real, [description = "Aileron, deg"]
        rdr::Real, [description = "Rudder, deg"]
        thrust::Real, [unit = "N"]
        cx0::Real
        cz0::Real
        cm0::Real
        cl0::Real
        cn0::Real
        dlda::Real
        dldr::Real
        dnda::Real
        dndr::Real
        cxq::Real
        cyr::Real
        cyp::Real
        czq::Real
        clr::Real
        clp::Real
        cmq::Real
        cnr::Real
        cnp::Real
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        nz::Real
        ny::Real
        CXT::Real
        CYT::Real
        CZT::Real
        CLT::Real
        CMT::Real
        CNT::Real
        P_ext::Real, [unit = "W"]
    end
    @parameters begin
        S::Real = 27.870912, [unit = "m^2", description = "Wing area (300 ft^2)"]
        b::Real = 9.144, [unit = "m", description = "Span (30 ft)"]
        cbar::Real = 3.450336, [unit = "m", description = "Mean aerodynamic chord (11.32 ft)"]
        xcg::Real = 0.35, [description = "Centre of gravity, fraction of cbar"]
        xcgr::Real = 0.35, [description = "Reference CG of the moment data, fraction of cbar"]
        he::Real = 216.930872, [description = "Engine angular momentum along body x (160 slug ft^2/s), kg m^2/s"]
        m::Real = 9295.44, [unit = "kg", description = "Mass (for nz)"]
        g0::Real = 9.805416, [unit = "m/s^2", description = "Gravity (32.17 ft/s^2)"]
    end
    @variables begin
        tvt::Real = 0.0
        X::Real = 0.0, [description = "Aero force x, FRD (N)"]
        Y::Real = 0.0, [description = "Aero force y, FRD (N)"]
        Z::Real = 0.0, [description = "Aero force z, FRD (N)"]
        L::Real = 0.0, [description = "Rolling moment, FRD (N m)"]
        M::Real = 0.0, [description = "Pitching moment, FRD (N m)"]
        N::Real = 0.0, [description = "Yawing moment, FRD (N m)"]
        u::Real = 0.0
        v::Real = 0.0
        w::Real = 0.0
    end
    @equations begin
        tvt ~ 0.5 / vt
        CXT ~ cx0 + cbar * q * tvt * cxq
        CYT ~ -0.02 * beta_deg + 0.021 * (ail / 20.0) + 0.086 * (rdr / 30.0) + b * tvt * (cyr * r + cyp * p)
        CZT ~ cz0 * (1.0 - (beta_deg / 57.3)^2) - 0.19 * (el / 25.0) + cbar * q * tvt * czq
        CLT ~ cl0 + dlda * (ail / 20.0) + dldr * (rdr / 30.0) + b * tvt * (clr * r + clp * p)
        CMT ~ cm0 + cbar * q * tvt * cmq + CZT * (xcgr - xcg)
        CNT ~ cn0 + dnda * (ail / 20.0) + dndr * (rdr / 30.0) + b * tvt * (cnr * r + cnp * p) - CYT * (xcgr - xcg) * cbar / b
        X ~ qbar * S * CXT + thrust
        Y ~ qbar * S * CYT
        Z ~ qbar * S * CZT
        L ~ qbar * S * b * CLT
        M ~ qbar * S * cbar * CMT
        N ~ qbar * S * b * CNT
        nz ~ -qbar * S * CZT / (m * g0)
        ny ~ qbar * S * CYT / (m * g0)
        # FRD -> FLU (y and z change sign); gyroscopic torque -w x (he, 0, 0) = (0, -r he, q he) in FRD.
        fx ~ X
        fy ~ -Y
        fz ~ -Z
        tx ~ L
        ty ~ -(M - r * he)
        tz ~ -(N + q * he)
        # Power of the external (non-gravity) wrench: in FRD, F.v + M.w; the gyroscopic part does no work.
        u ~ vt * cos(alpha_deg / 57.29577951308232) * cos(beta_deg / 57.29577951308232)
        v ~ vt * sin(beta_deg / 57.29577951308232)
        w ~ vt * sin(alpha_deg / 57.29577951308232) * cos(beta_deg / 57.29577951308232)
        P_ext ~ X * u + Y * v + Z * w + L * p + M * q + N * r
    end
end
