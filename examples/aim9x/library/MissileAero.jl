@block MissileAero begin
    # Aerodynamic force and moment build-up of a slender cruciform missile, as the six scalar
    # inputs of `stdlib:multibond/ExternalWrenchSpatial`, in the FLU body frame (x forward,
    # y left, z up) about the centre of mass.
    #
    # The block is the constitutive law of the airframe; the coefficient *tables* live in
    # stdlib `Lookup1D` blocks and arrive as `cna` (normal-force slope against Mach) and
    # `cd0` (zero-lift drag). The body force is
    #
    #   CN(alpha) = cna alpha + CN2 alpha |alpha|            (slender body + vortex lift)
    #   CN(beta)  = cna beta  + CN2 beta  |beta|
    #   CD        = cd0 + K_INDUCED (CN_alpha^2 + CN_beta^2)
    #
    # and the canards add the control force, resolved from the four fin deflections: a fin at
    # azimuth phi (from +y towards +z) has its normal along (-sin phi, cos phi) in the (y, z)
    # plane. The resultant force and the moment about the centre of mass are
    #
    #   F_c = qbar S_fin CN_DELTA sum(delta_i [0, -sin phi_i, cos phi_i])
    #   M_c = r x F_c,  with r = (x_canard, R_fin cos phi, R_fin sin phi)
    #
    # so the pitch, yaw and roll moments come out of the same geometry. The fins are 45 deg
    # apart, as on the Sidewinder's cruciform canards.
    #
    # Signs: alpha, beta in rad; positive delta_i is a normal force along +(-sin phi, cos phi);
    # positive n_z is up, positive n_y is left; the aero moment is FRD-like internally and
    # converted to FLU at the output (y and z change sign).
    @inputs begin
        va::Vec{3}, [unit = "m/s", description = "Air-relative velocity in body axes"]
        alpha::Real, [unit = "rad", description = "Angle of attack, positive nose up"]
        beta::Real, [unit = "rad", description = "Sideslip, positive nose left"]
        q_up::Real, [unit = "rad/s", description = "Pitch rate, positive nose up"]
        r_right::Real, [unit = "rad/s", description = "Yaw rate, positive nose right"]
        p::Real, [unit = "rad/s", description = "Roll rate, positive right wing down"]
        qbar::Real, [unit = "Pa", description = "Dynamic pressure"]
        vt::Real, [unit = "m/s", description = "Airspeed"]
        m::Real, [unit = "kg", description = "Current mass (for the load factors)"]
        d1::Real, [unit = "deg", description = "Canard 1 deflection"]
        d2::Real, [unit = "deg", description = "Canard 2 deflection"]
        d3::Real, [unit = "deg", description = "Canard 3 deflection"]
        d4::Real, [unit = "deg", description = "Canard 4 deflection"]
        cna::Real, [description = "Normal-force slope against Mach (Lookup1D)"]
        cd0::Real, [description = "Zero-lift drag against Mach (Lookup1D)"]
    end
    @parameters begin
        S::Real = 0.0126678, [unit = "m^2", min = 1.0e-9, description = "Body reference area, pi d^2/4"]
        d_ref::Real = 0.127, [unit = "m", min = 1.0e-9, description = "Pitch and yaw reference length"]
        b_ref::Real = 0.2794, [unit = "m", min = 1.0e-9, description = "Roll reference length (span)"]
        S_fin::Real = 0.020, [unit = "m^2", min = 0, description = "Total canard area (four fins)"]
        CN_DELTA::Real = 2.0, [min = 0, description = "Canard normal-force slope per rad"]
        x_canard::Real = 1.10, [unit = "m", description = "Centre of mass to the canard centre (positive forward)"]
        R_fin::Real = 0.0635, [unit = "m", description = "Canard root radius from the body axis"]
        CN3::Real = 80.0, [min = 0, description = "Cubic (vortex) lift coefficient per rad^3"]
        CN_MAX::Real = 12.0, [min = 0, description = "Clamp of the normal-force coefficient"]
        K_INDUCED::Real = 0.10, [min = 0, description = "Induced drag factor"]
        CM_RATIO::Real = -0.80, [description = "Cm/CN: negative is statically stable"]
        CN_RATIO::Real = 0.80, [description = "Cn/CN_beta: negative is weathercock stable"]
        CM_Q::Real = -1500.0, [description = "Pitch damping derivative Cm_q"]
        CN_R::Real = -1200.0, [description = "Yaw damping derivative Cn_r"]
        CL_P::Real = -0.50, [description = "Roll damping derivative Cl_p"]
        alpha_max::Real = 40.0, [unit = "deg", description = "Alpha at which the normal-force table is held"]
        g0::Real = 9.80665, [unit = "m/s^2", description = "Gravitational acceleration (load factors)"]
    end
    @variables begin
        cn_a::Real = 0.0, [description = "Body normal-force coefficient, alpha"]
        cn_b::Real = 0.0, [description = "Body side-force coefficient, beta"]
        cd::Real = 0.0
        fx_c::Real = 0.0, [unit = "N", description = "Canard force, body y (FRD)"]
        fz_c::Real = 0.0, [unit = "N", description = "Canard force, body z (FRD)"]
        mx_c::Real = 0.0, [unit = "N*m", description = "Canard roll moment (FRD)"]
        my_c::Real = 0.0, [unit = "N*m", description = "Canard pitch moment (FRD)"]
        mz_c::Real = 0.0, [unit = "N*m", description = "Canard yaw moment (FRD)"]
        FY::Real = 0.0, [unit = "N", description = "Side force, FRD (positive right)"]
        FZ::Real = 0.0, [unit = "N", description = "Normal force, FRD (positive down)"]
        FX::Real = 0.0, [unit = "N", description = "Axial force, FRD"]
        CL_m::Real = 0.0, [unit = "N*m", description = "Rolling moment, FRD"]
        CM_m::Real = 0.0, [unit = "N*m", description = "Pitching moment, FRD"]
        CN_m::Real = 0.0, [unit = "N*m", description = "Yawing moment, FRD"]
        tv::Real = 1.0, [description = "d_ref / (2 Vt)"]
        tb::Real = 1.0, [description = "b_ref / (2 Vt)"]
        fsum_y::Real = 0.0, [description = "Fin deflection sum in the y direction (rad)"]
        fsum_z::Real = 0.0, [description = "Fin deflection sum in the z direction (rad)"]
        fsum_r::Real = 0.0, [description = "Fin deflection sum for roll (rad)"]
        fc::Real = 0.0, [unit = "N", description = "qbar S_fin CN_DELTA"]
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        CN::Real
        CY::Real
        CD::Real
        Cm::Real
        Cn::Real
        Cl::Real
        n_z::Real, [description = "Load factor at the centre of mass, up positive"]
        n_y::Real, [description = "Lateral load factor, left positive"]
        a_z::Real, [unit = "m/s^2", description = "Specific normal acceleration, up positive"]
        a_y::Real, [unit = "m/s^2", description = "Specific lateral acceleration, left positive"]
        alpha_deg::Real
        beta_deg::Real
        stall::Real, [description = "1 when |alpha| is past the table"]
        P_ext::Real, [unit = "W", description = "Power of the aerodynamic wrench"]
    end
    @equations begin
        cn_a ~ clamp(cna * alpha + CN3 * alpha * alpha * alpha, -CN_MAX, CN_MAX)
        cn_b ~ clamp(cna * beta + CN3 * beta * beta * beta, -CN_MAX, CN_MAX)
        cd ~ cd0 + K_INDUCED * (cn_a * cn_a + cn_b * cn_b)
        # canard forces: a fin at azimuth phi (45, 135, 225, 315 deg) pushes along
        # (-sin phi, cos phi) in the (y, z) plane for positive delta
        fsum_y ~ -0.017453292519943295 * (d1 + d2 - d3 - d4) * 0.70710678
        fsum_z ~ 0.017453292519943295 * (d1 - d2 - d3 + d4) * 0.70710678
        fsum_r ~ 0.017453292519943295 * (d1 + d2 + d3 + d4)
        fc ~ qbar * S_fin * CN_DELTA
        fx_c ~ fc * fsum_y
        fz_c ~ fc * fsum_z
        mx_c ~ R_fin * fc * fsum_r
        my_c ~ -x_canard * fz_c
        mz_c ~ x_canard * fx_c
        FX ~ -qbar * S * cd
        FY ~ -qbar * S * cn_b + fx_c
        FZ ~ -qbar * S * cn_a + fz_c
        tv ~ d_ref / (2.0 * max(vt, 1.0))
        tb ~ b_ref / (2.0 * max(vt, 1.0))
        CL_m ~ qbar * S * b_ref * (CL_P * p * tb) + mx_c
        CM_m ~ qbar * S * d_ref * (CM_RATIO * cn_a + CM_Q * q_up * tv) + my_c
        CN_m ~ qbar * S * b_ref * (CN_RATIO * cn_b + CN_R * r_right * tb) + mz_c
        # FRD -> FLU and load factors
        fx ~ FX
        fy ~ -FY
        fz ~ -FZ
        tx ~ CL_m
        ty ~ -CM_m
        tz ~ -CN_m
        CN ~ cn_a
        CY ~ cn_b
        CD ~ cd
        Cm ~ CM_m / max(qbar * S * d_ref, 1.0e-9)
        Cn ~ CN_m / max(qbar * S * b_ref, 1.0e-9)
        Cl ~ CL_m / max(qbar * S * b_ref, 1.0e-9)
        n_z ~ fz / max(m * g0, 1.0e-9)
        n_y ~ fy / max(m * g0, 1.0e-9)
        a_z ~ fz / max(m, 1.0e-9)
        a_y ~ fy / max(m, 1.0e-9)
        alpha_deg ~ alpha * 57.29577951308232
        beta_deg ~ beta * 57.29577951308232
        stall ~ ifelse(alpha_deg * alpha_deg > alpha_max * alpha_max, 1.0, 0.0)
        P_ext ~ FX * va[1] + FY * va[2] + FZ * va[3] + CL_m * p + CM_m * q_up + CN_m * r_right
    end
end
