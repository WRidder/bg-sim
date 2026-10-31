@block ModalBeam2D begin
    # Slender flexible beam in the plane, assumed-modes method (the modal core of
    # `FlexibleBeam2D`): a floating reference frame R (origin at end A, axis along +x to end B)
    # plus up to three in-plane bending modes along local y (`eta_y`); the axial direction is
    # rigid. Same shapes, normalisation and signs as the spatial `ModalBeam3D` and the viewer
    # contract (`src/mech/modes.jl`): w(s) = sum phi_n(s) eta_n, (1/L) int phi^2 ds = 1, so a mode
    # has the modal mass m = rho A L.
    #
    # Ports `pa` (s = 0) and `pb` (s = L) are body-like (+twist, power in); `FlexibleBeam2D`
    # puts each in a 1-junction. Planar twists are `[w; vx; vy]` (angular first).
    #
    # Modal bond graph (the planar slice of ModalBeam3D's):
    #
    #   frame 1-junction (V) -- I_red(eta) -- Euler gyrator (w x P)
    #        |  MTF Ad(H_P(eta))^-1        \ TF C(eta)
    #   port 0-junction <-- MTF J_P -- mode 1-junction (eta') -- C 1/k, R d
    #                                         |
    #                                   0-junction -- I m (absolute modal momentum)
    #
    # Kinetic energy (second order in the deflection, u_f the axial foreshortening):
    #
    #   T = 1/2 J(eta) w^2 + w (S_x v_y - S_y v_x) + 1/2 m |v|^2 + V.C(eta)^T eta' + 1/2 m |eta'|^2
    #   S = (m L/2 - Q1/2, m a.y), J = J0 - Q2 + m |y|^2, C_i = (m L b_i, -(G1 y)_i, m a_i)
    #
    # with the tables of `ModalBeam3D` (a, b first moments; G1, G2 the uniform and centrifugal
    # axial-load integrals). States: frame momentum P (3), modal momenta p and coordinates y.
    # Flows: y' = (p - C V)/m and (M_VV - C^T C/m) V = P - C^T p/m (3x3, by cofactors). Then
    # P' = ad(V)^T P + sum Ad^-T e_P + W_g and p' = dT/dy - k y - d y' + J_P^T e_P + Q_g, so the
    # block is energy consistent (H = T + 1/2 k y^2 + U_g) and power continuous at the ports. A
    # spinning cantilever gets the in-plane (lead-lag) Southwell shift w^2 = w0^2 + 0.193 W^2:
    # centrifugal stiffening G2[1,1] = 1.193 minus the softening of the rotating frame.
    #
    # Ports: the end frame P sits at r_P = (s_P + u_f(s_P), w(s_P)), rotated by the slope
    # theta_P = w'(s_P) (exact planar rotation); the port twist is Ad(H_P)^-1 V + [theta_P';
    # R^T r_P'] and the efforts map through the transpose. Gravity (world -y): `gA` is the
    # world pose (theta, x, y) of end A; the reference angle is gA[1] - theta_A.
    @constants begin
        ny::Int = 2, [min = 0, max = 3, description = "In-plane bending modes"]
        basis::Int = 0, [options = ["clamped-free", "free-free"], description = "Mode basis: 0 clamped at A (cantilever), 1 free-free (mean axis)"]
        section::Int = 0, [options = ["rod", "tube", "rectangle"], description = "Cross-section: 0 solid rod (d), 1 tube (d, di), 2 rectangle (b in the plane, h out of it)"]
    end
    @ports begin
        pa::Power{Planar}, [frame = "body"]
        pb::Power{Planar}, [frame = "body"]
    end
    @inputs gA::Vec{3}
    @outputs begin
        pose::Vec{3}
        poseB::Vec{3}
        V::Vec{3}
        eta_y::Vec{3}, [unit = "m"]
        f_y::Vec{3}, [unit = "Hz"]
        dB::Vec{2}, [unit = "m"]
        Ek::Real, [unit = "J"]
        Ee::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
    end
    @parameters begin
        L::Real = 1.0, [unit = "m", min = 1.0e-9, description = "Length A to B"]
        E::Real = 2.1e11, [unit = "Pa", min = 0, description = "Young's modulus"]
        rho::Real = 7850.0, [unit = "kg/m^3", min = 1.0e-9, description = "Density"]
        d::Real = 0.01, [unit = "m", min = 0, description = "Rod or tube outer diameter"]
        di::Real = 0.008, [unit = "m", min = 0, description = "Tube inner diameter"]
        b::Real = 0.02, [unit = "m", min = 0, description = "Rectangle width in the plane (local y)"]
        h::Real = 0.005, [unit = "m", min = 0, description = "Rectangle height out of the plane"]
        zeta_y::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -y)"]
    end
    @variables begin
        A::Real = 1.0e-4, [unit = "m^2", description = "Cross-section area"]
        Iz::Real = 1.0e-9, [unit = "m^4", description = "Second moment int y^2 dA (in-plane bending)"]
        m::Real = 1.0, [unit = "kg", description = "Beam mass rho A L (modal mass)"]
        J0::Real = 1.0, [unit = "kg*m^2", description = "Rigid yaw inertia about end A"]
        lam::Vec{3} = [1.0, 1.0, 1.0], [unit = "1", description = "Bending eigenvalues lambda_n"]
        ta::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L) int phi_n"]
        tb::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L^2) int s phi_n"]
        p0::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "phi_n(0)"]
        pL::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "phi_n(L)"]
        s0::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "L phi_n'(0)"]
        sL::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "L phi_n'(L)"]
        G0::Mat{3,3}, [unit = "1", description = "L int phi_i' phi_j' ds"]
        G1::Mat{3,3}, [unit = "1", description = "int (1 - s/L) L phi_i' phi_j' ds"]
        G2::Mat{3,3}, [unit = "1", description = "int (1 - s^2/L^2)/2 L phi_i' phi_j' ds"]
        ky::Vec{3}, [unit = "N/m", description = "Modal stiffness"]
        cy::Vec{3}, [unit = "N*s/m", description = "Modal damping"]
        P::Vec{3} = [0.0, 0.0, 0.0], [state = :prefer, description = "Frame momentum [angular; linear] (conjugate to V)"]
        y::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Modal coordinates"]
        py::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*s", state = :prefer, description = "Modal momenta"]
        yd::Vec{3}, [unit = "m/s", description = "Modal velocities"]
        Fy::Vec{3}, [unit = "N", description = "Generalized modal force"]
        dTy::Vec{3}, [unit = "N", description = "dT/dy"]
        g0y::Vec{3}, [description = "G0 y / L"]
        g1y::Vec{3}, [description = "rho A G1 y"]
        g2y::Vec{3}, [description = "m G2 y"]
        g1yd::Vec{3}, [description = "rho A G1 y'"]
        Q1::Real, [description = "y.G1 y (rho A)"]
        Q2::Real, [description = "y.G2 y (m)"]
        S::Vec{2}, [unit = "kg*m", description = "First moment of mass about A, frame R"]
        Jz::Real, [unit = "kg*m^2", description = "Yaw inertia of the deformed beam about A"]
        Cy::Mat{3,3}, [description = "Coupling rows of the modes"]
        MV::Mat{3,3}, [description = "Frame block of the mass matrix"]
        Mr::Mat{3,3}, [description = "Reduced frame mass matrix"]
        hr::Vec{3}, [description = "Reduced momentum"]
        detM::Real, [description = "det Mr"]
        Xi::Mat{3,3}, [description = "Mr^-1"]
        tha::Real, [unit = "rad", description = "Slope angle of end A in R"]
        thb::Real, [unit = "rad", description = "Slope angle of end B in R"]
        ra::Vec{2}, [unit = "m", description = "Origin of end A in R"]
        rb::Vec{2}, [unit = "m", description = "Origin of end B in R"]
        rad::Vec{2}, [description = "Rate of ra"]
        rbd::Vec{2}, [description = "Rate of rb"]
        ua::Vec{2}, [description = "Velocity of the end-A origin in R"]
        ub::Vec{2}, [description = "Velocity of the end-B origin in R"]
        Fa::Vec{2}, [unit = "N", description = "End-A force in R"]
        Fb::Vec{2}, [unit = "N", description = "End-B force in R"]
        thR::Real, [unit = "rad", description = "World angle of the reference frame"]
        gv::Vec{2}, [unit = "m/s^2", description = "Gravity in R"]
    end
    @equations begin
        for k in 1:(1 - section)
            A ~ 0.7853981633974483 * d * d
            Iz ~ 0.04908738521234052 * d^4
        end
        for k in 1:(section * (2 - section))
            A ~ 0.7853981633974483 * (d * d - di * di)
            Iz ~ 0.04908738521234052 * (d^4 - di^4)
        end
        for k in 1:(section - 1)
            A ~ b * h
            Iz ~ h * b^3 / 12.0
        end
        m ~ rho * A * L
        J0 ~ m * L * L / 3.0 + rho * Iz * L
        # mode tables (src/mech/modes.jl, beam_mode_tables; checked by test_flex_modes.jl)
        lam[1] ~ (1 - basis) * 1.87510407 + basis * 4.73004074
        lam[2] ~ (1 - basis) * 4.69409113 + basis * 7.85320462
        lam[3] ~ (1 - basis) * 7.85475744 + basis * 10.99560784
        ta[1] ~ (1 - basis) * 0.7829917564063
        ta[2] ~ (1 - basis) * 0.433935895432
        ta[3] ~ (1 - basis) * 0.2544252968097
        tb[1] ~ (1 - basis) * 0.5688257439265
        tb[2] ~ (1 - basis) * 0.09076678726647
        tb[3] ~ (1 - basis) * 0.03241637441233
        p0[1] ~ basis * 2.0
        p0[2] ~ basis * 2.0
        p0[3] ~ basis * 2.0
        pL[1] ~ 2.0
        pL[2] ~ -2.0
        pL[3] ~ 2.0
        s0[1] ~ basis * -9.294551004172
        s0[2] ~ basis * -15.71861801892
        s0[3] ~ basis * -21.99047787747
        sL[1] ~ (1 - basis) * 2.753010965453 + basis * 9.294551004172
        sL[2] ~ (1 - basis) * -9.561556842306 + basis * -15.71861801892
        sL[3] ~ (1 - basis) * 15.69733206881 + basis * 21.99047787754
        G0[1, 1] ~ (1 - basis) * 4.647778317285 + basis * 49.48082253819
        G0[1, 2] ~ (1 - basis) * -7.379875261489
        G0[1, 3] ~ (1 - basis) * 3.941515478111 + basis * 35.37751189136
        G0[2, 1] ~ (1 - basis) * -7.379875261489
        G0[2, 2] ~ (1 - basis) * 32.41739903923 + basis * 108.9245920663
        G0[2, 3] ~ (1 - basis) * -22.35244450007
        G0[3, 1] ~ (1 - basis) * 3.941515478111 + basis * 35.37751189136
        G0[3, 2] ~ (1 - basis) * -22.35244450007
        G0[3, 3] ~ (1 - basis) * 77.29889079224 + basis * 186.8667130182
        G1[1, 1] ~ (1 - basis) * 1.570878190949 + basis * 24.74041128807
        G1[1, 2] ~ (1 - basis) * -0.4223203854097 + basis * 22.22650947162
        G1[1, 3] ~ (1 - basis) * -1.072084834975 + basis * 17.68875592331
        G1[2, 1] ~ (1 - basis) * -0.4223203854097 + basis * 22.22650947162
        G1[2, 2] ~ (1 - basis) * 8.647142684041 + basis * 54.46229606919
        G1[2, 3] ~ (1 - basis) * 1.890054687087 + basis * 42.23903813385
        G1[3, 1] ~ (1 - basis) * -1.072084834975 + basis * 17.68875592331
        G1[3, 2] ~ (1 - basis) * 1.890054687087 + basis * 42.23903813385
        G1[3, 3] ~ (1 - basis) * 24.95211332038 + basis * 93.43335648215
        G2[1, 1] ~ (1 - basis) * 1.193336374652 + basis * 15.41996977084
        G2[1, 2] ~ (1 - basis) * -0.6858552806076 + basis * 11.11325473969
        G2[1, 3] ~ (1 - basis) * -0.7923792210011 + basis * 8.256932475883
        G2[2, 1] ~ (1 - basis) * -0.6858552806076 + basis * 11.11325473969
        G2[2, 2] ~ (1 - basis) * 6.478224857785 + basis * 33.62854287128
        G2[2, 3] ~ (1 - basis) * 0.1694078691625 + basis * 21.11951905048
        G2[3, 1] ~ (1 - basis) * -0.7923792210011 + basis * 8.256932475883
        G2[3, 2] ~ (1 - basis) * 0.1694078691625 + basis * 21.11951905048
        G2[3, 3] ~ (1 - basis) * 17.85951988813 + basis * 58.04128485384
        for i in 1:3
            ky[i] ~ lam[i]^4 * E * Iz / (L * L * L)
            cy[i] ~ 2.0 * zeta_y * sqrt(ky[i] * m)
            f_y[i] ~ 0.15915494309189535 * sqrt(ky[i] / m)
        end
        # deflection-dependent inertia
        for i in 1:3
            g0y[i] ~ (G0[i, 1] * y[1] + G0[i, 2] * y[2] + G0[i, 3] * y[3]) / L
            g1y[i] ~ m / L * (G1[i, 1] * y[1] + G1[i, 2] * y[2] + G1[i, 3] * y[3])
            g2y[i] ~ m * (G2[i, 1] * y[1] + G2[i, 2] * y[2] + G2[i, 3] * y[3])
            g1yd[i] ~ m / L * (G1[i, 1] * yd[1] + G1[i, 2] * yd[2] + G1[i, 3] * yd[3])
        end
        Q1 ~ y[1] * g1y[1] + y[2] * g1y[2] + y[3] * g1y[3]
        Q2 ~ y[1] * g2y[1] + y[2] * g2y[2] + y[3] * g2y[3]
        S[1] ~ 0.5 * m * L - 0.5 * Q1
        S[2] ~ m * (ta[1] * y[1] + ta[2] * y[2] + ta[3] * y[3])
        Jz ~ J0 - Q2 + m * (y[1] * y[1] + y[2] * y[2] + y[3] * y[3])
        MV[1, 1] ~ Jz
        MV[1, 2] ~ -S[2]
        MV[1, 3] ~ S[1]
        MV[2, 1] ~ -S[2]
        MV[2, 2] ~ m
        MV[2, 3] ~ 0.0
        MV[3, 1] ~ S[1]
        MV[3, 2] ~ 0.0
        MV[3, 3] ~ m
        for i in 1:ny
            Cy[i, 1] ~ m * L * tb[i]
            Cy[i, 2] ~ -g1y[i]
            Cy[i, 3] ~ m * ta[i]
            ddt(y[i]) ~ yd[i]
            ddt(py[i]) ~ Fy[i]
        end
        for i in (ny + 1):3
            for k in 1:3
                Cy[i, k] ~ 0.0
            end
            y[i] ~ 0.0
            py[i] ~ 0.0
        end
        for k in 1:3
            for l in 1:3
                Mr[k, l] ~ MV[k, l] - (Cy[1, k] * Cy[1, l] + Cy[2, k] * Cy[2, l] + Cy[3, k] * Cy[3, l]) / m
            end
            hr[k] ~ P[k] - (Cy[1, k] * py[1] + Cy[2, k] * py[2] + Cy[3, k] * py[3]) / m
        end
        detM ~ Mr[1, 1] * (Mr[2, 2] * Mr[3, 3] - Mr[2, 3] * Mr[3, 2]) -
               Mr[1, 2] * (Mr[2, 1] * Mr[3, 3] - Mr[2, 3] * Mr[3, 1]) +
               Mr[1, 3] * (Mr[2, 1] * Mr[3, 2] - Mr[2, 2] * Mr[3, 1])
        Xi[1, 1] ~ (Mr[2, 2] * Mr[3, 3] - Mr[2, 3] * Mr[3, 2]) / detM
        Xi[1, 2] ~ (Mr[1, 3] * Mr[3, 2] - Mr[1, 2] * Mr[3, 3]) / detM
        Xi[1, 3] ~ (Mr[1, 2] * Mr[2, 3] - Mr[1, 3] * Mr[2, 2]) / detM
        Xi[2, 1] ~ (Mr[2, 3] * Mr[3, 1] - Mr[2, 1] * Mr[3, 3]) / detM
        Xi[2, 2] ~ (Mr[1, 1] * Mr[3, 3] - Mr[1, 3] * Mr[3, 1]) / detM
        Xi[2, 3] ~ (Mr[1, 3] * Mr[2, 1] - Mr[1, 1] * Mr[2, 3]) / detM
        Xi[3, 1] ~ (Mr[2, 1] * Mr[3, 2] - Mr[2, 2] * Mr[3, 1]) / detM
        Xi[3, 2] ~ (Mr[1, 2] * Mr[3, 1] - Mr[1, 1] * Mr[3, 2]) / detM
        Xi[3, 3] ~ (Mr[1, 1] * Mr[2, 2] - Mr[1, 2] * Mr[2, 1]) / detM
        for i in 1:3
            V[i] ~ Xi[i, 1] * hr[1] + Xi[i, 2] * hr[2] + Xi[i, 3] * hr[3]
        end
        for i in 1:3
            yd[i] ~ (py[i] - (Cy[i, 1] * V[1] + Cy[i, 2] * V[2] + Cy[i, 3] * V[3])) / m
        end
        # end frames
        tha ~ (s0[1] * y[1] + s0[2] * y[2] + s0[3] * y[3]) / L
        thb ~ (sL[1] * y[1] + sL[2] * y[2] + sL[3] * y[3]) / L
        ra[1] ~ 0.0
        ra[2] ~ p0[1] * y[1] + p0[2] * y[2] + p0[3] * y[3]
        rb[1] ~ L - 0.5 * (y[1] * g0y[1] + y[2] * g0y[2] + y[3] * g0y[3])
        rb[2] ~ pL[1] * y[1] + pL[2] * y[2] + pL[3] * y[3]
        rad[1] ~ 0.0
        rad[2] ~ p0[1] * yd[1] + p0[2] * yd[2] + p0[3] * yd[3]
        rbd[1] ~ -(g0y[1] * yd[1] + g0y[2] * yd[2] + g0y[3] * yd[3])
        rbd[2] ~ pL[1] * yd[1] + pL[2] * yd[2] + pL[3] * yd[3]
        ua[1] ~ V[2] - V[1] * ra[2] + rad[1]
        ua[2] ~ V[3] + V[1] * ra[1] + rad[2]
        ub[1] ~ V[2] - V[1] * rb[2] + rbd[1]
        ub[2] ~ V[3] + V[1] * rb[1] + rbd[2]
        pa.f[1] ~ V[1] + (s0[1] * yd[1] + s0[2] * yd[2] + s0[3] * yd[3]) / L
        pa.f[2] ~ cos(tha) * ua[1] + sin(tha) * ua[2]
        pa.f[3] ~ -sin(tha) * ua[1] + cos(tha) * ua[2]
        pb.f[1] ~ V[1] + (sL[1] * yd[1] + sL[2] * yd[2] + sL[3] * yd[3]) / L
        pb.f[2] ~ cos(thb) * ub[1] + sin(thb) * ub[2]
        pb.f[3] ~ -sin(thb) * ub[1] + cos(thb) * ub[2]
        Fa[1] ~ cos(tha) * pa.e[2] - sin(tha) * pa.e[3]
        Fa[2] ~ sin(tha) * pa.e[2] + cos(tha) * pa.e[3]
        Fb[1] ~ cos(thb) * pb.e[2] - sin(thb) * pb.e[3]
        Fb[2] ~ sin(thb) * pb.e[2] + cos(thb) * pb.e[3]
        # gravity (world -y) in R
        thR ~ gA[1] - tha
        gv[1] ~ -g0 * sin(thR)
        gv[2] ~ -g0 * cos(thR)
        # frame momentum: P' = ad(V)^T P + wrenches
        ddt(P[1]) ~ V[3] * P[2] - V[2] * P[3] + pa.e[1] + ra[1] * Fa[2] - ra[2] * Fa[1] +
                    pb.e[1] + rb[1] * Fb[2] - rb[2] * Fb[1] + S[1] * gv[2] - S[2] * gv[1]
        ddt(P[2]) ~ V[1] * P[3] + Fa[1] + Fb[1] + m * gv[1]
        ddt(P[3]) ~ -V[1] * P[2] + Fa[2] + Fb[2] + m * gv[2]
        # modal momenta: p' = dT/dy - k y - d y' + J^T e + Q_gravity
        for i in 1:3
            dTy[i] ~ V[1] * V[1] * (m * y[i] - g2y[i]) - V[1] * (V[3] * g1y[i] + V[2] * m * ta[i]) -
                     V[2] * g1yd[i]
            Fy[i] ~ dTy[i] - ky[i] * y[i] - cy[i] * yd[i] +
                    pa.e[1] * s0[i] / L + Fa[2] * p0[i] +
                    pb.e[1] * sL[i] / L + Fb[2] * pL[i] - Fb[1] * g0y[i] +
                    m * ta[i] * gv[2] - g1y[i] * gv[1]
        end
        # poses: R = gA composed with H_A^-1, B = R composed with H_B
        pose[1] ~ thR
        pose[2] ~ gA[2] - (cos(thR) * ra[1] - sin(thR) * ra[2])
        pose[3] ~ gA[3] - (sin(thR) * ra[1] + cos(thR) * ra[2])
        poseB[1] ~ thR + thb
        poseB[2] ~ pose[2] + cos(thR) * rb[1] - sin(thR) * rb[2]
        poseB[3] ~ pose[3] + sin(thR) * rb[1] + cos(thR) * rb[2]
        for i in 1:3
            eta_y[i] ~ y[i]
        end
        dB[1] ~ rb[1] - L
        dB[2] ~ rb[2]
        Ek ~ 0.5 * (P[1] * V[1] + P[2] * V[2] + P[3] * V[3] + py[1] * yd[1] + py[2] * yd[2] + py[3] * yd[3])
        Ee ~ 0.5 * (ky[1] * y[1] * y[1] + ky[2] * y[2] * y[2] + ky[3] * y[3] * y[3])
        Eg ~ g0 * (m * pose[3] + sin(thR) * S[1] + cos(thR) * S[2])
    end
    @causality begin
        pa => :flow_out
        pb => :flow_out
    end
end
