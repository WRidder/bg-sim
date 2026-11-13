@block FinSet begin
    # The four fins in the rotor slipstream: the surfaces that let a single-propeller vehicle
    # carry the motor reaction without a yaw actuator. They are lifting surfaces in the
    # slipstream, and the slipstream comes from momentum theory (`design.py` has a Python twin
    # of this law and solves the trim with it):
    #
    #   v_i  = -V_c/2 + sqrt(V_c^2/4 + T / (2 rho A))   induced velocity at the disc (momentum
    #                                       theory in axial flight; V_c is the climb speed of the
    #                                       disc through the air along the body axis)
    #   w_a  = k_w v_i                      induced axial wake speed at the fin station (k_w from
    #                                       the distance below the disc, 1 + d/sqrt(d^2 + R^2))
    #   u_t  = Q / (mdot r_f),  mdot = rho A (V_c + v_i)    swirl at the fin radius: the wake's
    #                                       angular momentum flux equals the rotor torque Q
    #
    # The fins sit inside the contracted wake (tip radius < R/sqrt(k_w)). Fin k at azimuth
    # phi_k = k pi/2, mid-span radius r_f, height z_f: a flat plate whose chord runs along the
    # body axis, turned by the incidence `delta` about its span. The air velocity relative to
    # the fin is
    #
    #   U = -w_a e_z + u_t e_t + R^T wind - (v_b + w_b x r_k)
    #
    # split into chordwise `U_c`, normal `U_n` (angle of attack atan(U_n, U_c)) and spanwise
    # `U_r`. Low-aspect-ratio plate:
    #
    #   F_n = q (a U_n U_c + b U_n |U_n|)   normal force (lift slope a, cross-flow drag b),
    #                                       i.e. q |U|^2 (a sin(al) cos(al) + b sin(al) |sin(al)|)
    #   F_c = q c_f U_c |U_c|               chordwise friction,  F_r = q c_r U_r |U_r|
    #
    # with q = rho S / 2. The tangential part of the fin forces is
    # the yaw torque `Qz` that opposes the motor reaction; the axial part is a download on the
    # vehicle. Both scale with the rotor speed squared, like Q, so the incidence that balances
    # the motor reaction at hover balances it at every speed. A body yaw rate changes U_t and
    # gives the yaw damping. Four identical fins at 90 deg have no preferred heading: a steady
    # crossflow changes the yaw torque only at second order. The slipstream is not skewed by a
    # crossflow (a hover/low-speed model).
    @inputs begin
        V::Vec{6}
        pose::Vec{7}
        T::Real, [unit = "N", description = "Rotor thrust"]
        Q::Real, [unit = "N*m", description = "Rotor drag torque (the wake's angular momentum flux)"]
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        fs_fin::Vec{3}
        Qz::Real, [unit = "N*m", description = "Total fin yaw torque (opposes the rotor reaction)"]
        wa::Real, [unit = "m/s", description = "Axial slipstream speed at the fins"]
        ut::Real, [unit = "m/s", description = "Swirl speed at the fin radius"]
        alpha1::Real, [unit = "rad", description = "Angle of attack of fin 1"]
    end
    @parameters begin
        m::Real = 1.2, [unit = "kg", min = 0.01, description = "Total mass (for the specific force)"]
        rho::Real = 1.225, [unit = "kg/m^3", min = 0, description = "Air density"]
        A::Real = 0.073, [unit = "m^2", min = 1.0e-6, description = "Rotor disc area"]
        kw::Real = 1.85, [min = 1.0, max = 2.0, description = "Axial wake speed at the fins over the induced velocity"]
        wind::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Steady wind, world frame"]
        S::Real = 0.009, [unit = "m^2", min = 0, description = "Area of one fin"]
        rf::Real = 0.08, [unit = "m", min = 1.0e-3, description = "Fin mid-span radius"]
        zf::Real = -0.07, [unit = "m", description = "Fin centre height relative to the CoM"]
        delta::Real = 0.2, [unit = "rad", description = "Fin incidence (positive: more angle of attack in the swirl)"]
        cla::Real = 0.86, [min = 0, description = "Lift slope of the low-aspect-ratio plate (per rad)"]
        cdn::Real = 1.2, [min = 0, description = "Cross-flow drag coefficient of the plate"]
        cf::Real = 0.02, [min = 0, description = "Chordwise friction coefficient"]
        cr::Real = 0.05, [min = 0, description = "Spanwise drag coefficient"]
        epsv::Real = 1.0e-3, [unit = "m/s", min = 1.0e-9, description = "Smoothing speed of |u| u"]
    end
    @variables begin
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        s2::Real = 1.0, [description = "Squared quaternion norm"]
        wdx::Real = 0.0, [unit = "m/s", description = "Wind in body x"]
        wdy::Real = 0.0, [unit = "m/s", description = "Wind in body y"]
        wdz::Real = 0.0, [unit = "m/s", description = "Wind in body z"]
        Tp::Real = 0.0, [unit = "N", description = "Smooth positive part of the thrust"]
        Vc::Real = 0.0, [unit = "m/s", description = "Climb speed through the air along the body axis"]
        vi::Real = 0.0, [unit = "m/s", description = "Induced velocity at the disc"]
        q::Real = 0.0, [unit = "kg/m", description = "rho S / 2"]
        sd::Real = 0.0
        cd::Real = 1.0
        Ur1::Real = 0.0, [unit = "m/s"]
        Ut1::Real = 0.0, [unit = "m/s"]
        Uz1::Real = 0.0, [unit = "m/s"]
        Ur2::Real = 0.0, [unit = "m/s"]
        Ut2::Real = 0.0, [unit = "m/s"]
        Uz2::Real = 0.0, [unit = "m/s"]
        Ur3::Real = 0.0, [unit = "m/s"]
        Ut3::Real = 0.0, [unit = "m/s"]
        Uz3::Real = 0.0, [unit = "m/s"]
        Ur4::Real = 0.0, [unit = "m/s"]
        Ut4::Real = 0.0, [unit = "m/s"]
        Uz4::Real = 0.0, [unit = "m/s"]
        Uc1::Real = 0.0, [unit = "m/s"]
        Un1::Real = 0.0, [unit = "m/s"]
        Uc2::Real = 0.0, [unit = "m/s"]
        Un2::Real = 0.0, [unit = "m/s"]
        Uc3::Real = 0.0, [unit = "m/s"]
        Un3::Real = 0.0, [unit = "m/s"]
        Uc4::Real = 0.0, [unit = "m/s"]
        Un4::Real = 0.0, [unit = "m/s"]
        Fn1::Real = 0.0, [unit = "N"]
        Fn2::Real = 0.0, [unit = "N"]
        Fn3::Real = 0.0, [unit = "N"]
        Fn4::Real = 0.0, [unit = "N"]
        Fc1::Real = 0.0, [unit = "N"]
        Fc2::Real = 0.0, [unit = "N"]
        Fc3::Real = 0.0, [unit = "N"]
        Fc4::Real = 0.0, [unit = "N"]
        Fr1::Real = 0.0, [unit = "N"]
        Fr2::Real = 0.0, [unit = "N"]
        Fr3::Real = 0.0, [unit = "N"]
        Fr4::Real = 0.0, [unit = "N"]
        Ft1::Real = 0.0, [unit = "N"]
        Ft2::Real = 0.0, [unit = "N"]
        Ft3::Real = 0.0, [unit = "N"]
        Ft4::Real = 0.0, [unit = "N"]
        Fz1::Real = 0.0, [unit = "N"]
        Fz2::Real = 0.0, [unit = "N"]
        Fz3::Real = 0.0, [unit = "N"]
        Fz4::Real = 0.0, [unit = "N"]
    end
    @equations begin
        s2 ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        R[1, 1] ~ (pose[1] * pose[1] + pose[2] * pose[2] - pose[3] * pose[3] - pose[4] * pose[4]) / s2
        R[1, 2] ~ 2 * (pose[2] * pose[3] - pose[1] * pose[4]) / s2
        R[1, 3] ~ 2 * (pose[2] * pose[4] + pose[1] * pose[3]) / s2
        R[2, 1] ~ 2 * (pose[2] * pose[3] + pose[1] * pose[4]) / s2
        R[2, 2] ~ (pose[1] * pose[1] - pose[2] * pose[2] + pose[3] * pose[3] - pose[4] * pose[4]) / s2
        R[2, 3] ~ 2 * (pose[3] * pose[4] - pose[1] * pose[2]) / s2
        R[3, 1] ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s2
        R[3, 2] ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s2
        R[3, 3] ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s2
        wdx ~ R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3]
        wdy ~ R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3]
        wdz ~ R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3]
        # slipstream from momentum theory
        Tp ~ 0.5 * (T + sqrt(T * T + 1.0e-6))
        Vc ~ V[6] - wdz
        vi ~ -0.5 * Vc + sqrt(0.25 * Vc * Vc + Tp / (2.0 * rho * A) + 0.01)
        wa ~ kw * vi
        ut ~ Q / (rho * A * (Vc + vi) * rf)
        q ~ 0.5 * rho * S
        sd ~ sin(delta)
        cd ~ cos(delta)
        # fin 1: phi = 0, r = (rf, 0, zf), e_r = +x, e_t = +y
        Ur1 ~ wdx - (V[4] + V[2] * zf)
        Ut1 ~ wdy + ut - (V[5] + V[3] * rf - V[1] * zf)
        Uz1 ~ wdz - wa - (V[6] - V[2] * rf)
        # fin 2: phi = pi/2, r = (0, rf, zf), e_r = +y, e_t = -x
        Ur2 ~ wdy - (V[5] - V[1] * zf)
        Ut2 ~ -wdx + ut + (V[4] + V[2] * zf - V[3] * rf)
        Uz2 ~ wdz - wa - (V[6] + V[1] * rf)
        # fin 3: phi = pi, r = (-rf, 0, zf), e_r = -x, e_t = -y
        Ur3 ~ -wdx + (V[4] + V[2] * zf)
        Ut3 ~ -wdy + ut + (V[5] - V[3] * rf - V[1] * zf)
        Uz3 ~ wdz - wa - (V[6] + V[2] * rf)
        # fin 4: phi = 3 pi/2, r = (0, -rf, zf), e_r = -y, e_t = +x
        Ur4 ~ -wdy + (V[5] - V[1] * zf)
        Ut4 ~ wdx + ut - (V[4] + V[2] * zf + V[3] * rf)
        Uz4 ~ wdz - wa - (V[6] - V[1] * rf)
        # chordwise and normal components (chord turned by the incidence)
        Uc1 ~ -cd * Uz1 - sd * Ut1
        Un1 ~ -sd * Uz1 + cd * Ut1
        Uc2 ~ -cd * Uz2 - sd * Ut2
        Un2 ~ -sd * Uz2 + cd * Ut2
        Uc3 ~ -cd * Uz3 - sd * Ut3
        Un3 ~ -sd * Uz3 + cd * Ut3
        Uc4 ~ -cd * Uz4 - sd * Ut4
        Un4 ~ -sd * Uz4 + cd * Ut4
        # plate forces
        Fn1 ~ q * (cla * Un1 * Uc1 + cdn * Un1 * sqrt(Un1 * Un1 + epsv * epsv))
        Fn2 ~ q * (cla * Un2 * Uc2 + cdn * Un2 * sqrt(Un2 * Un2 + epsv * epsv))
        Fn3 ~ q * (cla * Un3 * Uc3 + cdn * Un3 * sqrt(Un3 * Un3 + epsv * epsv))
        Fn4 ~ q * (cla * Un4 * Uc4 + cdn * Un4 * sqrt(Un4 * Un4 + epsv * epsv))
        Fc1 ~ q * cf * Uc1 * sqrt(Uc1 * Uc1 + epsv * epsv)
        Fc2 ~ q * cf * Uc2 * sqrt(Uc2 * Uc2 + epsv * epsv)
        Fc3 ~ q * cf * Uc3 * sqrt(Uc3 * Uc3 + epsv * epsv)
        Fc4 ~ q * cf * Uc4 * sqrt(Uc4 * Uc4 + epsv * epsv)
        Fr1 ~ q * cr * Ur1 * sqrt(Ur1 * Ur1 + epsv * epsv)
        Fr2 ~ q * cr * Ur2 * sqrt(Ur2 * Ur2 + epsv * epsv)
        Fr3 ~ q * cr * Ur3 * sqrt(Ur3 * Ur3 + epsv * epsv)
        Fr4 ~ q * cr * Ur4 * sqrt(Ur4 * Ur4 + epsv * epsv)
        # tangential and axial components in the body frame
        Ft1 ~ Fn1 * cd - Fc1 * sd
        Ft2 ~ Fn2 * cd - Fc2 * sd
        Ft3 ~ Fn3 * cd - Fc3 * sd
        Ft4 ~ Fn4 * cd - Fc4 * sd
        Fz1 ~ -Fn1 * sd - Fc1 * cd
        Fz2 ~ -Fn2 * sd - Fc2 * cd
        Fz3 ~ -Fn3 * sd - Fc3 * cd
        Fz4 ~ -Fn4 * sd - Fc4 * cd
        # body forces: fin 1 (Fr, Ft, Fz), fin 2 (-Ft, Fr, Fz), fin 3 (-Fr, -Ft, Fz), fin 4 (Ft, -Fr, Fz)
        fx ~ Fr1 - Ft2 - Fr3 + Ft4
        fy ~ Ft1 + Fr2 - Ft3 - Fr4
        fz ~ Fz1 + Fz2 + Fz3 + Fz4
        # moments r_k x F_k about the CoM, summed
        tx ~ -zf * Ft1 + rf * Fz2 - zf * Fr2 + zf * Ft3 - rf * Fz4 + zf * Fr4
        ty ~ zf * Fr1 - rf * Fz1 - zf * Ft2 - zf * Fr3 + rf * Fz3 + zf * Ft4
        tz ~ rf * (Ft1 + Ft2 + Ft3 + Ft4)
        Qz ~ tz
        alpha1 ~ atan(Un1 / sqrt(Un1 * Un1 + Uc1 * Uc1 + epsv * epsv), Uc1 / sqrt(Un1 * Un1 + Uc1 * Uc1 + epsv * epsv))
        fs_fin[1] ~ fx / m
        fs_fin[2] ~ fy / m
        fs_fin[3] ~ fz / m
    end
end
