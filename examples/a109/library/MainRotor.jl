@block MainRotor begin
    # The main rotor of the Heffley & Mnich minimum-complexity model (NASA CR-177476, Appendix A
    # and the A109 revisions of Appendix D), converted to SI. A modulated source: it computes the
    # rotor force and hub moment from the air data and the controls, and a FixedTransform3DNeutral
    # applies them at the hub (the bond graph forms r x F). The rotor torque goes to the
    # drivetrain bond graph (RotorPower), not to this wrench.
    #
    #   flapping     first-order tip-path-plane dynamics, states a1 (longitudinal, + aft) and b1
    #                (lateral, + right): a1' = -ITB B.SUM - ITB2 A.SUM - q,
    #                b1' = -ITB A.SUM + ITB2 B.SUM - p, with the dihedral derivatives DB1DV and
    #                DA1DU magnified below VTRANS (A109: WAKE.FN), and coupled = 0 the A109's
    #                decoupled flapping (ITB2 = 0, ITB = GAM.OM.16)
    #   thrust       blade element T = (WB - kg vi) Omega R rho a b c R / 4 and momentum
    #                vi sqrt(U^2 + (WR - vi)^2) = T/(2 rho A), solved by 8 unrolled Newton steps
    #                from the root of a quadratic (the report iterates 5 times per frame from
    #                the last frame's value; the converged values are the same)
    #   force        X = -T (a1 - IS), Y = T b1, Z = -T (FRD); hub moment L = DL.DB1 b1,
    #                M = DL.DB1 a1 (the offset-hinge spring); the outputs are in FLU, the frame of
    #                the bond graph
    #   ground eff.  ours (not in the report; `ge` = 0 switches it off): the Cheeseman-Bennett
    #                factor 1 - (R/4z)^2 / (1 + V^2/vh^2) on the induced velocity in the blade
    #                equation (an induced-velocity efficiency factor, as section V.C recommends)
    #   rpm_mode     0: the aerodynamics see the nominal speed om0 (the report's constant-RPM
    #                model); 1: the actual rotor speed `om` from the drivetrain bond graph
    #
    # Inputs are the air-relative body velocities and rates in the report's axes (FRD, m/s,
    # rad/s), the controls (rad), the air density and the hub height above the ground.
    @inputs begin
        u::Real
        v::Real
        w::Real
        p::Real
        q::Real
        om::Real, [description = "Rotor speed from the drivetrain (rad/s)"]
        th0::Real, [description = "Collective pitch theta0 (rad)"]
        B1::Real, [description = "Longitudinal cyclic B1 (rad, + forward stick)"]
        A1::Real, [description = "Lateral cyclic A1 (rad, + right stick)"]
        rho::Real
        hgt::Real, [description = "Hub height above the ground (m)"]
    end
    @outputs begin
        tx::Real
        ty::Real
        tz::Real
        fx::Real
        fy::Real
        fz::Real
        T::Real, [description = "Thrust (N)"]
        vi::Real, [description = "Induced velocity (m/s)"]
        vi_eff::Real, [description = "Induced velocity in the blade equation, kg vi (m/s)"]
        om_a::Real, [description = "Rotor speed the aerodynamics see (rad/s)"]
        a1_deg::Real
        b1_deg::Real
        a1r::Real, [description = "Longitudinal flapping (rad)"]
        b1r::Real, [description = "Lateral flapping (rad)"]
    end
    @parameters begin
        R::Real = 5.4864, [description = "Rotor radius (m)"]
        e::Real = 0.1524, [description = "Hinge offset (m)"]
        I_B::Real = 287.4, [description = "Blade flap inertia (kg m^2)"]
        a::Real = 6.0, [description = "Blade lift-curve slope (1/rad)"]
        nb::Real = 4.0, [description = "Number of blades"]
        c::Real = 0.3353, [description = "Blade chord (m)"]
        twist::Real = -0.105, [description = "Blade twist (rad)"]
        IS::Real = 0.11, [description = "Shaft tilt, forward (rad)"]
        K1::Real = 0.0, [description = "Delta-3 coupling"]
        db1dv::Real = 0.0, [description = "Dihedral derivative DB1DV (rad per m/s)"]
        vtrans::Real = 15.24, [description = "End of the low-speed dihedral magnification (m/s)"]
        wake_on::Real = 1.0, [description = "1: the A109 low-speed magnification of the dihedral effect"]
        smooth::Real = 0.0, [description = "0: the report's switch at VTRANS; 1: a tanh blend over VTRANS +- ~1 m/s (ours, a109-sim)"]
        coupled::Real = 0.0, [description = "1: coupled flapping of the base listing; 0: the A109's decoupled flapping"]
        rpm_mode::Real = 0.0, [description = "0: aerodynamics at om0 (constant RPM, the report); 1: at the drivetrain speed"]
        om0::Real = 40.317, [description = "Nominal rotor speed (rad/s)"]
        ge::Real = 0.0, [description = "Ground effect (ours, Cheeseman-Bennett): 1 on, 0 off"]
        vh::Real = 10.35, [description = "Hover induced velocity sqrt(W/(2 rho0 A)) (m/s), for the ground effect"]
        d_hub::Real = 0.0, [description = "Hub position aft of the CG (m): N.MR has no -D.HUB Y.MR"]
    end
    @variables begin
        a1::Real = 0.0, [state = :prefer, description = "Longitudinal flapping, + aft (rad)"]
        b1::Real = 0.0, [state = :prefer, description = "Lateral flapping, + right (rad)"]
        gam16::Real = 1.0
        kc::Real = 0.0
        itb2::Real = 0.0
        itb::Real = 1.0
        dldb1::Real = 0.0
        wake::Real = 0.0
        asum::Real = 0.0
        bsum::Real = 0.0
        wr::Real = 0.0
        wb::Real = 0.0
        kt::Real = 1.0
        kg::Real = 1.0
        zr::Real = 1.0
        u2::Real = 0.0
        cq::Real = 1.0
        bq::Real = 1.0
        dq::Real = 0.0
        vn::Vec{9} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        sn::Vec{8} = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        X::Real = 0.0
        Y::Real = 0.0
        Z::Real = 0.0
    end
    @equations begin
        om_a ~ rpm_mode * om + (1.0 - rpm_mode) * om0
        # ---- flapping (lines 1690 .. 1699, 6341 .. 6360)
        gam16 ~ rho * a * c * R^4 / I_B * om_a / 16.0 * (1.0 + 8.0 / 3.0 * e / R)
        kc ~ 0.75 * om_a * e / R / gam16 + K1
        itb2 ~ coupled * om_a / (1.0 + (om_a / gam16)^2)
        itb ~ coupled * itb2 * om_a / gam16 + (1.0 - coupled) * gam16
        dldb1 ~ nb / 2.0 * (1.5 * I_B * e / R * om_a * om_a)
        wake ~ wake_on * (smooth * 0.5 * (1.0 - tanh(u - vtrans)) + (1.0 - smooth) * ifelse(u < vtrans, 1.0, 0.0))
        asum ~ b1 - A1 + kc * a1 + db1dv * v * (1.0 + wake)
        bsum ~ a1 + B1 - kc * b1 - db1dv * u * (1.0 + 2.0 * wake)
        ddt(a1) ~ -itb * bsum - itb2 * asum - q
        ddt(b1) ~ -itb * asum + itb2 * bsum - p
        # ---- thrust and induced velocity (lines 6490 .. 6610)
        wr ~ w + (a1 - IS) * u - b1 * v
        wb ~ wr + 2.0 / 3.0 * om_a * R * (th0 + 0.75 * twist)
        kt ~ om_a * R * rho * a * nb * c * R / 4.0
        zr ~ sqrt(hgt * hgt + 0.25 * R * R)
        u2 ~ u * u + v * v
        kg ~ 1.0 - ge * (R / (4.0 * zr))^2 / (1.0 + u2 / (vh * vh))
        cq ~ kt / (2.0 * rho * pi * R * R)
        bq ~ sqrt(u2 + wr * wr) + cq * kg
        dq ~ bq * bq + 4.0 * cq * wb
        vn[1] ~ 2.0 * cq * wb / (bq + sqrt(sqrt(dq * dq + 1.0)))
        for k in 1:8
            sn[k] ~ sqrt(u2 + (wr - vn[k])^2 + 1.0e-4)
            vn[k + 1] ~ vn[k] - (vn[k] * sn[k] - cq * (wb - kg * vn[k])) / (sn[k] - vn[k] * (wr - vn[k]) / sn[k] + cq * kg)
        end
        vi ~ vn[9]
        vi_eff ~ kg * vn[9]
        T ~ kt * (wb - kg * vn[9])
        # ---- forces and moments (lines 6890 .. 6980), FRD -> FLU
        X ~ -T * (a1 - IS)
        Y ~ T * b1
        Z ~ -T
        fx ~ X
        fy ~ -Y
        fz ~ -Z
        tx ~ dldb1 * b1
        ty ~ -(dldb1 * a1)
        tz ~ -(d_hub * Y)
        a1_deg ~ a1 * 57.29577951308232
        b1_deg ~ b1 * 57.29577951308232
        a1r ~ a1
        b1r ~ b1
    end
end
