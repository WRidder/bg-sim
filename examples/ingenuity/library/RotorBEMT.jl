@block RotorBEMT begin
    # Aerodynamics of one Ingenuity rotor (two hingeless blades) by blade-element/momentum theory
    # (BEMT), as a nonlinear R on the rotor's rotation bond plus the hub wrench it puts on the
    # airframe. The same law as `design/rotor_ref.py`, which fits and checks it.
    #
    # Port `shaft`: flow = rotor speed relative to the airframe (rad/s, sign `spin`), effort = the
    # aerodynamic drag torque spin*Q the rotor's 1-junction loses (power Q*Omega >= 0).
    #
    # Blade elements at NS stations y[i] (chord c, twist tw relative to the 0.75 R pitch, lift
    # fraction lf: 0 outboard of the tip-loss radius, trapezoid width wd). With Omega = spin*shaft.f,
    # vc the axial inflow (climb speed plus the other rotor's wake, `vext`) and the pitch above the
    # zero-lift angle th_e = theta + tw - alpha0, every annulus balances blade-element lift against
    # annulus momentum scaled by the induced-velocity factor kappa:
    #
    #     rho b y (th_e Omega y - vc - vi) = 4 pi rho y vi (vi + kappa vc) / kappa^2,   b = nb c a lf Omega / 2
    #
    # whose positive root vi is closed-form (no algebraic loop, no division by Omega, smooth through a
    # standstill). Then, with u = th_e Omega y - vc - vi (= Omega y times the angle of attack):
    #
    #     T = sum rho b y u wd
    #     Q = sum [rho (b/Omega) y u (vc + vi) wd + 1/2 rho nb c (Omega y)^2 cd y wd],
    #         cd (Omega y)^2 = d0 (Omega y)^2 + d2 (a u - clm Omega y)^2
    #
    # Hub wrench (hub frame, body axes; inputs of an ExternalWrenchSpatial mounted at the hub):
    #     fz = T                          thrust along the shaft
    #     fx, fy = -h_c va                profile-drag H-force against the edgewise airspeed
    #     tz = -spin Q                    the drag torque acts between rotor and air, but the rotor's
    #                                     1-junction loses it relative to the airframe (Rotor3D hands
    #                                     every drive torque back to the carrier), so the airframe
    #                                     gets it back here: in hover the airframe then feels exactly
    #                                     the motor reaction
    #     tx = k_c cx + k_e va[2] + k_q wb[1],  ty = k_c cy - k_e va[1] + k_q wb[2]
    #   k_c   moment per radian of cyclic of a stiff hingeless rotor (quasi-steady 1/rev lift)
    #   k_e   edgewise-flow moment: Pitt-Peters inflow gradient dv = 15 pi/64 V (y/R) cos psi,
    #         times the gain `edge` (Grip et al. 2017 needed about 2.5 to match the swinging-arm test)
    #   k_q   identified on-axis rate moment (Grip et al. 2017: Lp = Mq of about +0.4 1/s, i.e. the
    #         inflow-gradient effect removes the blade-element damping and slightly overcompensates)
    @constants NS::Int = 16
    @ports shaft::Power{Rotation}
    @inputs begin
        theta::Real, [unit = "rad", description = "Collective pitch at 0.75 R"]
        cx::Real, [unit = "rad", description = "Cyclic pitch amplitude that rolls the airframe (+ about body x)"]
        cy::Real, [unit = "rad", description = "Cyclic pitch amplitude that pitches the airframe (+ about body y)"]
        va::Vec{3}, [unit = "m/s", description = "Airframe velocity relative to the air, body frame"]
        wb::Vec{3}, [unit = "rad/s", description = "Body angular rate"]
        vext::Real, [unit = "m/s", description = "Extra axial inflow (the upper rotor's wake at the lower rotor)"]
    end
    @outputs begin
        T::Real, [unit = "N", description = "Thrust"]
        Q::Real, [unit = "N*m", description = "Aerodynamic torque (opposing the rotation)"]
        P::Real, [unit = "W", description = "Aerodynamic (shaft) power Q Omega"]
        v0::Real, [unit = "m/s", description = "Area-mean induced velocity (the uniform inflow)"]
        speed_rpm::Real, [unit = "1", description = "Rotor speed in rpm (`rpm` itself is the built-in constant 2 pi/60)"]
        CT::Real, [description = "Thrust coefficient T / (rho A (Omega R)^2)"]
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @parameters begin
        rho::Real = 0.0165, [unit = "kg/m^3", min = 0.005, max = 0.03, description = "Air density"]
        spin::Real = 1.0, [description = "+1: spins counter-clockwise seen from above (about +z); -1: clockwise"]
        nb::Real = 2.0, [description = "Number of blades"]
        R::Real = 0.605, [unit = "m", min = 0, description = "Rotor radius"]
        a::Real = 5.5, [unit = "1/rad", min = 0, description = "Lift-curve slope"]
        alpha0::Real = -0.06806784082777885, [unit = "rad", description = "Zero-lift angle of attack"]
        kappa::Real = 1.2, [min = 1.0, description = "Induced-velocity factor on annulus momentum"]
        d0::Real = 0.0428, [description = "Profile drag polar: cd = d0 + d2 (cl - clm)^2"]
        d2::Real = 0.051, [description = "Profile drag polar, quadratic term"]
        clm::Real = 0.25, [description = "Profile drag polar, lift coefficient of minimum drag"]
        edge::Real = 2.5, [min = 0, description = "Gain on the Pitt-Peters edgewise inflow gradient"]
        k_q::Real = 0.0, [unit = "N*m*s/rad", description = "Rate moment per body rate (positive = destabilising)"]
        y::Vec{NS} = [0.0549, 0.0890, 0.1231, 0.1572, 0.1913, 0.2254, 0.2595, 0.2936, 0.3277, 0.3618, 0.3959, 0.4300, 0.4641, 0.4982, 0.5323, 0.6050], [unit = "m", description = "Station radius"]
        c::Vec{NS} = [0.0306, 0.0400, 0.0500, 0.0600, 0.0700, 0.0800, 0.0900, 0.1000, 0.1100, 0.1150, 0.1150, 0.1100, 0.1000, 0.0900, 0.0700, 0.0165], [unit = "m", description = "Chord"]
        tw::Vec{NS} = [0.21, 0.22, 0.23, 0.22, 0.2, 0.18, 0.15, 0.12, 0.09, 0.06, 0.03, 0.0, -0.02, -0.04, -0.06, -0.07], [unit = "rad", description = "Twist relative to the 0.75 R pitch"]
        lf::Vec{NS} = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0], [description = "Lift fraction of the station (tip loss)"]
        wd::Vec{NS} = [0.017, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.017], [unit = "m", description = "Station width (trapezoid weight)"]
        Deps::Real = 1.0, [unit = "m^2/s^2", min = 0, description = "Smoothing of the discriminant's positive part"]
        k_rpm::Real = 9.549296585513721, [unit = "s", description = "rpm per rad/s"]
    end
    @variables begin
        Om::Real = 0.0, [unit = "rad/s", description = "Rotor speed (positive in the spin direction)"]
        vc::Real = 0.0, [unit = "m/s", description = "Axial inflow through the disc (climb plus wake)"]
        a2::Real = 1.0, [description = "4 pi / kappa^2"]
        bb::Vec{NS}, [unit = "m/s", description = "nb c a lf Omega / 2"]
        dd::Vec{NS}, [unit = "m^2/s^2", description = "Discriminant of the annulus quadratic"]
        vi::Vec{NS}, [unit = "m/s", description = "Induced velocity at the station"]
        u::Vec{NS}, [unit = "m/s", description = "Omega y times the angle of attack"]
        dT::Vec{NS}, [unit = "N/m", description = "Thrust per unit span at the station"]
        dQ::Vec{NS}, [unit = "N", description = "Torque per unit span at the station"]
        yvi::Vec{NS}, [unit = "m^2/s", description = "y vi"]
        s3::Vec{NS}, [unit = "m^4", description = "c lf y^3"]
        s1::Vec{NS}, [unit = "m^2", description = "c y"]
        kc::Real = 0.0, [unit = "N*m/rad", description = "Cyclic moment gain"]
        ke::Real = 0.0, [unit = "N*s", description = "Edgewise-flow moment gain"]
        hc::Real = 0.0, [unit = "N*s/m", description = "H-force coefficient"]
    end
    @equations begin
        Om ~ spin * shaft.f
        vc ~ va[3] + vext
        a2 ~ 12.566370614359172 / (kappa * kappa)
        for i in 1:NS
            bb[i] ~ 0.5 * nb * c[i] * a * lf[i] * Om
            dd[i] ~ (12.566370614359172 * vc / kappa + bb[i])^2 + 4.0 * a2 * bb[i] * ((theta + tw[i] - alpha0) * Om * y[i] - vc)
            vi[i] ~ (-(12.566370614359172 * vc / kappa + bb[i]) + sqrt(0.5 * (dd[i] + sqrt(dd[i] * dd[i] + Deps * Deps)))) / (2.0 * a2)
            u[i] ~ (theta + tw[i] - alpha0) * Om * y[i] - vc - vi[i]
            dT[i] ~ rho * bb[i] * y[i] * u[i]
            dQ[i] ~ rho * 0.5 * nb * c[i] * a * lf[i] * y[i] * u[i] * (vc + vi[i]) +
                    0.5 * rho * nb * c[i] * (d0 * (Om * y[i])^2 + d2 * (a * u[i] - clm * Om * y[i])^2) * y[i]
            yvi[i] ~ y[i] * vi[i]
            s3[i] ~ c[i] * lf[i] * y[i] * y[i] * y[i]
            s1[i] ~ c[i] * y[i]
        end
        T ~ dot(dT, wd)
        Q ~ dot(dQ, wd)
        P ~ Q * Om
        v0 ~ 2.0 * dot(yvi, wd) / (R * R)
        speed_rpm ~ k_rpm * Om
        CT ~ T / (rho * 3.141592653589793 * R * R * (Om * R)^2 + 1.0e-9)
        kc ~ 0.25 * nb * rho * a * Om * Om * dot(s3, wd)
        ke ~ edge * 0.25 * nb * rho * a * Om * 0.7363107781851078 / R * dot(s3, wd)
        hc ~ 0.5 * rho * nb * d0 * Om * dot(s1, wd)
        shaft.e ~ spin * Q
        fz ~ T
        fx ~ -hc * va[1]
        fy ~ -hc * va[2]
        tz ~ -spin * Q
        tx ~ kc * cx + ke * va[2] + k_q * wb[1]
        ty ~ kc * cy - ke * va[1] + k_q * wb[2]
    end
    @causality shaft => (:effort_out, :fixed)
end
