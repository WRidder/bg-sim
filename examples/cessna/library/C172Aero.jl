@block C172Aero begin
    # The aerodynamic build-up of JSBSim's c172p (c172p.xml; Roskam's Cessna 182 derivatives, see
    # the example README for the provenance), as the six inputs of
    # `stdlib:multibond/ExternalWrenchSpatial` at the centre of gravity in the body frame
    # (x forward, y left, z up): a modulated source on the airframe's multibond.
    #
    # The tables come in from stdlib Lookup1D blocks; their second axis (flaps, the stall flag) is
    # interpolated here, piecewise linearly and clamped, which is exactly JSBSim's bilinear table:
    #   cdwbh0..3   CDWBH(alpha) at flaps 0, 10, 20, 30 deg
    #   clwbh0/1    CLWBH(alpha) unstalled / stalled (the stall-hysteresis flag `hyst`, 0 or 1)
    #   cyb0/30, cyp0/30, cyr0/30, clr0/30   at flaps 0 and 30 deg
    #   kcd, kcl    ground-effect factors over h/b; cddf, cldf, cmdf over flaps; clb, cnb over beta
    #
    # Coefficients (JSBSim axes: drag, side force, lift; roll, pitch, yaw):
    #   CD = CD0 + kcd (cddf + CDWBH) + CDDE |de| + CDBETA |beta|        (|x| as sqrt(x^2 + eps^2))
    #   CY = CYB + CYDR dr + b/2V (CYP p + CYR r)
    #   CL = kcl (CLWBH + cldf) + CLDE de + c/2V (CLADOT alphadot + CLQ q)
    #   Cl = clb + b/2V (CLP p + CLR r) + CLDA da + CLDR dr
    #   Cm = CMO + CMALPHA alpha + c/2V (CMQ q + CMADOT alphadot) + cmdf
    #   Cn = cnb + b/2V (CNP p + CNR r) + CNDA da
    # Forces qbar S C, moments qbar S b Cl, qbar S cbar Cm, qbar S b Cn about the aerodynamic
    # reference point, plus the elevator and rudder moments on the propwash dynamic pressure
    # qbar_ind = rho (u + 2 vi)^2 / 2 (vi the propeller's induced velocity):
    #   M += qbar_ind S cbar CMDE de,   N += qbar_ind S b CNDR dr.
    # The wind-axis forces turn into body axes with alpha and beta; the moment about the centre
    # of gravity adds r_aero x F.
    @inputs begin
        u::Real, [unit = "m/s"]
        alpha::Real, [unit = "rad"]
        beta::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        r::Real, [unit = "rad/s"]
        qbar::Real, [unit = "Pa"]
        rho::Real, [unit = "kg/m^3"]
        bi2v::Real, [unit = "s"]
        ci2v::Real, [unit = "s"]
        alphadot::Real, [unit = "rad/s"]
        vi::Real, [unit = "m/s", description = "Propeller induced velocity"]
        de::Real, [unit = "rad"]
        da::Real, [unit = "rad"]
        dr::Real, [unit = "rad"]
        flap::Real, [description = "Flap angle (deg)"]
        hyst::Real, [description = "Stall-hysteresis flag (0 or 1)"]
        kcd::Real
        kcl::Real
        cddf::Real
        cldf::Real
        cmdf::Real
        clb::Real
        cnb::Real
        clwbh0::Real
        clwbh1::Real
        cdwbh0::Real
        cdwbh1::Real
        cdwbh2::Real
        cdwbh3::Real
        cyb0::Real
        cyb30::Real
        cyp0::Real
        cyp30::Real
        cyr0::Real
        cyr30::Real
        clr0::Real
        clr30::Real
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        CD::Real
        CY::Real
        CL::Real
        Cl::Real
        Cm::Real
        Cn::Real
        qbar_ind::Real, [unit = "Pa"]
    end
    @parameters begin
        S::Real = 16.16516, [unit = "m^2", description = "Wing area (174 ft^2)"]
        b::Real = 10.91184, [unit = "m", description = "Span (35.8 ft)"]
        cbar::Real = 1.49352, [unit = "m", description = "Mean chord (4.9 ft)"]
        rax::Real = 0.0, [unit = "m", description = "Aerodynamic reference point from the CG, body x"]
        ray::Real = 0.0, [unit = "m", description = "Aerodynamic reference point, body y"]
        raz::Real = 0.0, [unit = "m", description = "Aerodynamic reference point, body z"]
        eps::Real = 1.0e-3, [description = "Smoothing of |de| and |beta| (rad)"]
        CD0::Real = 0.027
        CDDE::Real = 0.06
        CDBETA::Real = 0.17
        CYDR::Real = 0.187
        CLDE::Real = 0.43
        CLADOT::Real = 1.7
        CLQ::Real = 3.9
        CLP::Real = -0.484
        CLDA::Real = 0.229
        CLDR::Real = 0.0147
        CMO::Real = 0.1
        CMALPHA::Real = -1.8
        CMQ::Real = -12.4
        CMADOT::Real = -7.27
        CMDE::Real = -1.122
        CNP::Real = -0.0278
        CNR::Real = -0.0937
        CNDA::Real = -0.0053
        CNDR::Real = -0.043
    end
    @variables begin
        fc::Real = 0.0, [description = "Flap angle clamped to 0 .. 30 deg"]
        f30::Real = 0.0, [description = "Flap fraction of the 0/30 deg tables"]
        hc::Real = 0.0
        w0::Real = 1.0
        w1::Real = 0.0
        w2::Real = 0.0
        w3::Real = 0.0
        cdwbh::Real = 0.0
        clwbh::Real = 0.0
        cyb::Real = 0.0
        cyp::Real = 0.0
        cyr::Real = 0.0
        clr::Real = 0.0
        qs::Real = 0.0, [unit = "N"]
        qis::Real = 0.0, [unit = "N"]
        Xw::Real = 0.0, [unit = "N", description = "Wind-axis force x (-drag)"]
        Yw::Real = 0.0, [unit = "N", description = "Wind-axis side force"]
        Zw::Real = 0.0, [unit = "N", description = "Wind-axis force z (-lift)"]
        ca::Real = 1.0
        sa::Real = 0.0
        cb::Real = 1.0
        sb::Real = 0.0
        Xb::Real = 0.0, [unit = "N", description = "Body force x, FRD"]
        Yb::Real = 0.0, [unit = "N", description = "Body force y, FRD"]
        Zb::Real = 0.0, [unit = "N", description = "Body force z, FRD"]
        L::Real = 0.0, [unit = "N*m"]
        M::Real = 0.0, [unit = "N*m"]
        N::Real = 0.0, [unit = "N*m"]
    end
    @equations begin
        fc ~ clamp(flap, 0.0, 30.0)
        f30 ~ fc / 30.0
        hc ~ clamp(hyst, 0.0, 1.0)
        w0 ~ clamp(1.0 - abs(fc) / 10.0, 0.0, 1.0)
        w1 ~ clamp(1.0 - abs(fc - 10.0) / 10.0, 0.0, 1.0)
        w2 ~ clamp(1.0 - abs(fc - 20.0) / 10.0, 0.0, 1.0)
        w3 ~ clamp(1.0 - abs(fc - 30.0) / 10.0, 0.0, 1.0)
        cdwbh ~ w0 * cdwbh0 + w1 * cdwbh1 + w2 * cdwbh2 + w3 * cdwbh3
        clwbh ~ clwbh0 + hc * (clwbh1 - clwbh0)
        cyb ~ cyb0 + f30 * (cyb30 - cyb0)
        cyp ~ cyp0 + f30 * (cyp30 - cyp0)
        cyr ~ cyr0 + f30 * (cyr30 - cyr0)
        clr ~ clr0 + f30 * (clr30 - clr0)
        CD ~ CD0 + kcd * (cddf + cdwbh) + CDDE * sqrt(de * de + eps * eps) + CDBETA * sqrt(beta * beta + eps * eps)
        CY ~ cyb + CYDR * dr + bi2v * (cyp * p + cyr * r)
        CL ~ kcl * (clwbh + cldf) + CLDE * de + ci2v * (CLADOT * alphadot + CLQ * q)
        Cl ~ clb + bi2v * (CLP * p + clr * r) + CLDA * da + CLDR * dr
        Cm ~ CMO + CMALPHA * alpha + ci2v * (CMQ * q + CMADOT * alphadot) + cmdf
        Cn ~ cnb + bi2v * (CNP * p + CNR * r) + CNDA * da
        qbar_ind ~ 0.5 * rho * (u + 2.0 * vi) * (u + 2.0 * vi)
        qs ~ qbar * S
        qis ~ qbar_ind * S
        Xw ~ -CD * qs
        Yw ~ CY * qs
        Zw ~ -CL * qs
        ca ~ cos(alpha)
        sa ~ sin(alpha)
        cb ~ cos(beta)
        sb ~ sin(beta)
        Xb ~ ca * cb * Xw - ca * sb * Yw - sa * Zw
        Yb ~ sb * Xw + cb * Yw
        Zb ~ sa * cb * Xw - sa * sb * Yw + ca * Zw
        L ~ qs * b * Cl
        M ~ qs * cbar * Cm + qis * cbar * CMDE * de
        N ~ qs * b * Cn + qis * b * CNDR * dr
        # FRD -> FLU, and the moment of the force at the reference point about the CG.
        fx ~ Xb
        fy ~ -Yb
        fz ~ -Zb
        tx ~ L + (ray * fz - raz * fy)
        ty ~ -M + (raz * fx - rax * fz)
        tz ~ -N + (rax * fy - ray * fx)
    end
end
