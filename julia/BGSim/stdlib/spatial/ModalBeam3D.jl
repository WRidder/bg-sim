@block ModalBeam3D begin
    # Slender flexible beam, assumed-modes method (the modal core of `FlexibleBeam3D`).
    # A floating reference frame R (origin at end A, axis along +x to end B) carries the rigid
    # motion; up to three elastic modes per family ride on it: bending along local y
    # (`eta_y`), bending along local z (`eta_z`) and torsion about x (`eta_t`). The axial
    # direction is rigid. Mode shapes, normalisation and signs are the viewer contract of
    # `src/mech/modes.jl` ((1/L) int phi^2 ds = 1, so a bending mode has the modal mass
    # m = rho A L and a torsion mode rho I_p L).
    #
    # Ports `a` (frame at s = 0) and `b` (frame at s = L) are body-like (+twist, power in): a
    # flow is the twist of that end frame in its own coordinates, an effort the wrench applied
    # to the beam there. `FlexibleBeam3D` wraps each in a 1-junction so a joint, transform or
    # body bonds to it directly.
    #
    # Modal bond graph in the moving frame (Karnopp/Margolis/Rosenberg's distributed-system
    # graph, multibond form):
    #
    #   frame 1-junction (V) --- I_red(eta) [reduced rigid inertia] --- Euler gyrator ad(V)^T P
    #        |                     \
    #        | MTF Ad(H_P(eta))^-1   TF C(eta) (rigid->modal coupling: first moments of phi)
    #        v                       v
    #   port P 0-junction  <-- MTF J_P(eta) --- mode i 1-junction (eta_i') --- C 1/k_i, R d_i
    #   (A and B: twists add,                       |
    #    one wrench)                                0-junction --- I m_i (absolute modal momentum)
    #
    # Each mode is a 1-junction (modal velocity) with its C (k_i = lambda^4 E I / L^3, or
    # (k pi)^2 G J_t / L) and R (2 zeta omega_i m_i). Its I sits on a 0-junction that adds the
    # TF image C_i V of the frame twist, so the stored momentum is the absolute modal momentum
    # p_i = m_i eta_i' + C_i(eta) V. Each attachment point is a 0-junction whose twist is the
    # transported frame twist plus the modal contributions through a TF/MTF with modulus the
    # mode value phi_i(s_P) (translation) or slope phi_i'(s_P) / psi_i(s_P) (rotation).
    #
    # Equations (exactly that graph). The kinetic energy of the deformed beam, to second order
    # in the deflection (u_f(s) = -1/2 int_0^s |w'|^2 is the axial foreshortening):
    #
    #   T = 1/2 w.J(eta) w + w.(S(eta) x v) + 1/2 m |v|^2 + V.C(eta)^T eta' + 1/2 sum m_i eta_i'^2
    #   S = (m L/2 - Q1/2, m a.y, m a.z)            (first moment, a_i = (1/L) int phi_i)
    #   J = J0 + [m(|y|^2+|z|^2), -m L b.y, -m L b.z; ., -Q2 + m|z|^2, -m y.z; ., ., -Q2 + m|y|^2]
    #   Q1 = y.G1 y + z.G1 z, Q2 = y.G2 y + z.G2 z  (G1 = rho A int (L - s) phi' phi',
    #                                                G2 = rho A int (L^2 - s^2)/2 phi' phi')
    #   C rows: y_i' -> (-m z_i, 0, m L b_i, -(G1 y)_i, m a_i, 0)
    #           z_i' -> ( m y_i, -m L b_i, 0, -(G1 z)_i, 0, m a_i)
    #           t_j' -> ( rho I_p L at_j, 0, 0, 0, 0, 0)
    #
    # The states are the frame momentum P (6), the modal momenta p and the modal coordinates
    # eta. The flows come from M(eta) q' = p by a Schur complement: eta' = (p - C V)/m_i and
    # (M_VV - C^T M_e^-1 C) V = P - C^T M_e^-1 p, solved in closed form (3x3 linear block, then
    # 3x3 angular block). Then
    #
    #   P'  = ad(V)^T P + sum_P Ad(H_P)^-T e_P + W_gravity          (Euler-Poincare)
    #   p_i' = dT/d eta_i - k_i eta_i - d_i eta_i' + sum_P J_P^T e_P + Q_gravity
    #
    # so the beam is a port-Hamiltonian system with H = T + 1/2 sum k eta^2 + U_g: power
    # continuous at the ports and energy consistent by construction. dT/d eta carries the
    # centrifugal softening (w x u) and the **geometric stiffening**: the -Q2/2 (w_y^2 + w_z^2)
    # term of T is the centrifugal axial load acting on the foreshortening, i.e. the stored
    # energy 1/2 (k_i + k_g,i(w) - ...) eta_i^2 of a spinning arm. For a cantilever spinning at
    # W about an axis through A, the first flap mode gets w^2 = w0^2 + G2[1,1] W^2 =
    # w0^2 + 1.193 W^2 and the first lead-lag mode w0^2 + 0.193 W^2 (Southwell). The port B
    # position carries the foreshortening -1/2 eta.G0 eta along x, so an axial tip force
    # stiffens (tension) or softens (compression) the bending modes, and gravity acts on the
    # same field (G1 term), so a hanging beam stiffens.
    #
    # Port kinematics (exact, Gibbs chart as in Revolute3DCompliant): the end frame P sits at
    # r_P = (s_P + u_f(s_P), w_y(s_P), w_z(s_P)) with the rotation R(g), g = (tan(theta/2),
    # -w_z'/2, w_y'/2) at s_P (a pure twist turns the end by exactly theta, the slopes enter to
    # second order); a.f = Ad(H)^-1 V + [2/D (g' - g x g'); R^T r'], and the efforts map
    # through the transpose (the modal force is the Gibbs torque times dg/d eta, with
    # dg_x/d theta = (1 + g_x^2)/2), so e.f summed over the ports equals the power into V and eta'.
    #
    # Gravity: `gA` is the world pose of the end-A frame (the composed joint chain); the
    # reference pose is gA composed with H_A^-1 (identical for clamped-free), its z row turns
    # g0 into the frame, and the distributed weight gives the wrench [S x g; m g] and the modal
    # forces m a_i g_y - (G1 y)_i g_x. Outputs: `pose` (world pose of R, the frame the viewer
    # deforms), `poseB` (world pose of end B, for the downstream chain), `V` (frame twist),
    # `eta_*` (modal coordinates), `f_*` (free eigenfrequencies in Hz of all three modes of
    # each family in this basis), `twist` (theta(L) - theta(0)), `dB` (end-B displacement in
    # R), `Ek`, `Ee`, `Eg` (kinetic, strain, gravity energy).
    @constants begin
        ny::Int = 2, [min = 0, max = 3, description = "Bending modes along local y"]
        nz::Int = 2, [min = 0, max = 3, description = "Bending modes along local z"]
        nt::Int = 1, [min = 0, max = 3, description = "Torsion modes about the beam axis"]
        basis::Int = 0, [options = ["clamped-free", "free-free"], description = "Mode basis: 0 clamped at A (cantilever), 1 free-free (mean axis)"]
        section::Int = 0, [options = ["rod", "tube", "rectangle"], description = "Cross-section: 0 solid rod (d), 1 tube (d, di), 2 rectangle (b along y, h along z)"]
    end
    @ports begin
        pa::Power{Spatial}, [frame = "body"]
        pb::Power{Spatial}, [frame = "body"]
    end
    @inputs gA::Vec{7}
    @outputs begin
        pose::Vec{7}
        poseB::Vec{7}
        V::Vec{6}
        eta_y::Vec{3}, [unit = "m"]
        eta_z::Vec{3}, [unit = "m"]
        eta_t::Vec{3}, [unit = "rad"]
        f_y::Vec{3}, [unit = "Hz"]
        f_z::Vec{3}, [unit = "Hz"]
        f_t::Vec{3}, [unit = "Hz"]
        twist::Real, [unit = "rad"]
        dB::Vec{3}, [unit = "m"]
        Ek::Real, [unit = "J"]
        Ee::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
    end
    @parameters begin
        L::Real = 1.0, [unit = "m", min = 1.0e-9, description = "Length A to B"]
        E::Real = 2.1e11, [unit = "Pa", min = 0, description = "Young's modulus"]
        nu::Real = 0.3, [unit = "1", min = 0, max = 0.5, description = "Poisson ratio (G = E / (2 (1 + nu)))"]
        rho::Real = 7850.0, [unit = "kg/m^3", min = 1.0e-9, description = "Density"]
        d::Real = 0.01, [unit = "m", min = 0, description = "Rod or tube outer diameter"]
        di::Real = 0.008, [unit = "m", min = 0, description = "Tube inner diameter"]
        b::Real = 0.02, [unit = "m", min = 0, description = "Rectangle width along local y"]
        h::Real = 0.005, [unit = "m", min = 0, description = "Rectangle height along local z"]
        zeta_y::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio, bending along y"]
        zeta_z::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio, bending along z"]
        zeta_t::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio, torsion"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -z)"]
    end
    @variables begin
        # section and material
        A::Real = 1.0e-4, [unit = "m^2", description = "Cross-section area"]
        Iy::Real = 1.0e-9, [unit = "m^4", description = "Second moment int z^2 dA (bending along z)"]
        Iz::Real = 1.0e-9, [unit = "m^4", description = "Second moment int y^2 dA (bending along y)"]
        Ip::Real = 2.0e-9, [unit = "m^4", description = "Polar moment Iy + Iz (inertia)"]
        Jt::Real = 2.0e-9, [unit = "m^4", description = "Torsion constant (stiffness)"]
        rdiff::Real = 0.0, [unit = "m", description = "|b - h| (rectangle)"]
        rlong::Real = 0.0, [unit = "m", description = "Larger rectangle side"]
        rshort::Real = 0.0, [unit = "m", description = "Smaller rectangle side"]
        G::Real = 8.0e10, [unit = "Pa", description = "Shear modulus"]
        m::Real = 1.0, [unit = "kg", description = "Beam mass rho A L (bending modal mass)"]
        mt::Real = 1.0e-6, [unit = "kg*m^2", description = "Torsion modal mass rho I_p L"]
        J0::Vec{3} = [1.0, 1.0, 1.0], [unit = "kg*m^2", description = "Rigid inertia about end A"]
        # mode tables (dimensionless, from src/mech/modes.jl; selected by `basis`)
        lam::Vec{3} = [1.0, 1.0, 1.0], [unit = "1", description = "Bending eigenvalues lambda_n"]
        kk::Vec{3} = [1.0, 1.0, 1.0], [unit = "1", description = "Torsion wave numbers k_n"]
        ta::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L) int phi_n"]
        tb::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L^2) int s phi_n"]
        p0::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "phi_n(0)"]
        pL::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "phi_n(L)"]
        s0::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "L phi_n'(0)"]
        sL::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "L phi_n'(L)"]
        q0::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "psi_n(0)"]
        qL::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "psi_n(L)"]
        tat::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L) int psi_n"]
        G0::Mat{3,3}, [unit = "1", description = "L int phi_i' phi_j' ds"]
        G1::Mat{3,3}, [unit = "1", description = "int (1 - s/L) L phi_i' phi_j' ds"]
        G2::Mat{3,3}, [unit = "1", description = "int (1 - s^2/L^2)/2 L phi_i' phi_j' ds"]
        # modal stiffness and damping
        ky::Vec{3}, [unit = "N/m", description = "Bending-y modal stiffness"]
        kz::Vec{3}, [unit = "N/m", description = "Bending-z modal stiffness"]
        kt::Vec{3}, [unit = "N*m/rad", description = "Torsion modal stiffness"]
        cy::Vec{3}, [unit = "N*s/m", description = "Bending-y modal damping"]
        cz::Vec{3}, [unit = "N*s/m", description = "Bending-z modal damping"]
        ct::Vec{3}, [unit = "N*m*s/rad", description = "Torsion modal damping"]
        # states
        P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer, description = "Frame momentum [angular; linear] (conjugate to V)"]
        y::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Bending-y modal coordinates"]
        z::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Bending-z modal coordinates"]
        th::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad", state = :prefer, description = "Torsion modal coordinates"]
        py::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*s", state = :prefer, description = "Bending-y modal momenta"]
        pz::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*s", state = :prefer, description = "Bending-z modal momenta"]
        pth::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m*s", state = :prefer, description = "Torsion modal momenta"]
        # rates and generalized forces
        yd::Vec{3}, [unit = "m/s", description = "Bending-y modal velocities"]
        zd::Vec{3}, [unit = "m/s", description = "Bending-z modal velocities"]
        thd::Vec{3}, [unit = "rad/s", description = "Torsion modal velocities"]
        Fy::Vec{3}, [unit = "N", description = "Bending-y generalized force"]
        Fz::Vec{3}, [unit = "N", description = "Bending-z generalized force"]
        Fth::Vec{3}, [unit = "N*m", description = "Torsion generalized force"]
        # deflection-dependent inertia
        g0y::Vec{3}, [description = "G0 y / L"]
        g0z::Vec{3}, [description = "G0 z / L"]
        g1y::Vec{3}, [description = "rho A G1 y"]
        g1z::Vec{3}, [description = "rho A G1 z"]
        g2y::Vec{3}, [description = "m G2 y"]
        g2z::Vec{3}, [description = "m G2 z"]
        g1yd::Vec{3}, [description = "rho A G1 y'"]
        g1zd::Vec{3}, [description = "rho A G1 z'"]
        Q1::Real, [description = "y.G1 y + z.G1 z (rho A)"]
        Q2::Real, [description = "y.G2 y + z.G2 z (m)"]
        S::Vec{3}, [unit = "kg*m", description = "First moment of mass about A, frame R"]
        Jm::Mat{3,3}, [unit = "kg*m^2", description = "Inertia of the deformed beam about A"]
        Cy::Mat{3,6}, [description = "Coupling rows of the y modes"]
        Cz::Mat{3,6}, [description = "Coupling rows of the z modes"]
        Ct::Mat{3,6}, [description = "Coupling rows of the torsion modes"]
        MV::Mat{6,6}, [description = "Frame block of the mass matrix"]
        Mr::Mat{6,6}, [description = "Reduced frame mass matrix M_VV - C^T M_e^-1 C"]
        hr::Vec{6}, [description = "Reduced momentum P - C^T M_e^-1 p"]
        detD::Real, [description = "det of the linear block"]
        X::Mat{3,3}, [description = "Inverse of the linear block"]
        BX::Mat{3,3}, [description = "Coupling block times X"]
        Jr::Mat{3,3}, [description = "Angular Schur complement"]
        detJ::Real, [description = "det of Jr"]
        Y::Mat{3,3}, [description = "Inverse of Jr"]
        hw::Vec{3}, [description = "Angular right-hand side"]
        hv::Vec{3}, [description = "Linear right-hand side"]
        vw::Vec{3}, [description = "v x w"]
        dTy::Vec{3}, [unit = "N", description = "dT/dy"]
        dTz::Vec{3}, [unit = "N", description = "dT/dz"]
        # end frames: Gibbs vectors, rotations, positions, rates
        ga::Vec{3}, [unit = "1", description = "Gibbs vector of end A in R"]
        gb::Vec{3}, [unit = "1", description = "Gibbs vector of end B in R"]
        gad::Vec{3}, [description = "Rate of ga"]
        gbd::Vec{3}, [description = "Rate of gb"]
        Da::Real, [unit = "1", description = "1 + |ga|^2"]
        Db::Real, [unit = "1", description = "1 + |gb|^2"]
        Ra::Mat{3,3}, [unit = "1", description = "Rotation of end A in R"]
        Rb::Mat{3,3}, [unit = "1", description = "Rotation of end B in R"]
        ra::Vec{3}, [unit = "m", description = "Origin of end A in R"]
        rb::Vec{3}, [unit = "m", description = "Origin of end B in R"]
        rad::Vec{3}, [description = "Rate of ra"]
        rbd::Vec{3}, [description = "Rate of rb"]
        wa::Vec{3}, [description = "Relative angular rate of end A (its frame)"]
        wb::Vec{3}, [description = "Relative angular rate of end B (its frame)"]
        ua::Vec{3}, [description = "v + w x ra"]
        ub::Vec{3}, [description = "v + w x rb + rb'"]
        Fa::Vec{3}, [unit = "N", description = "End-A force in R"]
        Fb::Vec{3}, [unit = "N", description = "End-B force in R"]
        Ta::Vec{3}, [description = "End-A torque, Gibbs-conjugate"]
        Tb::Vec{3}, [description = "End-B torque, Gibbs-conjugate"]
        Wa::Vec{6}, [description = "End-A wrench on the frame"]
        Wb::Vec{6}, [description = "End-B wrench on the frame"]
        # gravity and poses
        sq::Real, [unit = "1", description = "|qA|^2"]
        c3::Vec{3}, [unit = "1", description = "World z in the end-A frame"]
        gv::Vec{3}, [unit = "m/s^2", description = "Gravity in the frame R"]
        qR::Vec{4}, [unit = "1", description = "Reference-frame quaternion"]
        sR::Real, [unit = "1", description = "|qR|^2"]
        RR::Mat{3,3}, [unit = "1", description = "Reference-frame rotation"]
    end
    @equations begin
        # ---- section (selected by the structural `section`) ----
        rdiff ~ sqrt((b - h) * (b - h))
        rlong ~ 0.5 * (b + h + rdiff)
        rshort ~ 0.5 * (b + h - rdiff)
        for k in 1:(1 - section)
            A ~ 0.7853981633974483 * d * d
            Iy ~ 0.04908738521234052 * d^4
        end
        for k in 1:(section * (2 - section))
            A ~ 0.7853981633974483 * (d * d - di * di)
            Iy ~ 0.04908738521234052 * (d^4 - di^4)
        end
        for k in 1:(1 - section)
            Iz ~ Iy
            Ip ~ 2.0 * Iy
            Jt ~ Ip
        end
        for k in 1:(section * (2 - section))
            Iz ~ Iy
            Ip ~ 2.0 * Iy
            Jt ~ Ip
        end
        for k in 1:(section - 1)
            A ~ b * h
            Iy ~ b * h^3 / 12.0
            Iz ~ h * b^3 / 12.0
            Ip ~ Iy + Iz
            # Roark: J = a c^3 (1/3 - 0.21 (c/a) (1 - c^4/(12 a^4))), a >= c the sides
            Jt ~ rlong * rshort^3 * (1.0 / 3.0 - 0.21 * rshort / rlong * (1.0 - rshort^4 / (12.0 * rlong^4)))
        end
        G ~ E / (2.0 * (1.0 + nu))
        m ~ rho * A * L
        mt ~ rho * Ip * L
        J0[1] ~ rho * Ip * L
        J0[2] ~ m * L * L / 3.0 + rho * Iy * L
        J0[3] ~ m * L * L / 3.0 + rho * Iz * L
        # ---- mode tables (src/mech/modes.jl, beam_mode_tables; checked by test_flex_modes.jl) ----
        lam[1] ~ (1 - basis) * 1.87510407 + basis * 4.73004074
        lam[2] ~ (1 - basis) * 4.69409113 + basis * 7.85320462
        lam[3] ~ (1 - basis) * 7.85475744 + basis * 10.99560784
        kk[1] ~ (1 - basis) * 0.5 + basis * 1.0
        kk[2] ~ (1 - basis) * 1.5 + basis * 2.0
        kk[3] ~ (1 - basis) * 2.5 + basis * 3.0
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
        q0[1] ~ basis * 1.4142135623730951
        q0[2] ~ basis * 1.4142135623730951
        q0[3] ~ basis * 1.4142135623730951
        qL[1] ~ (1 - basis) * 1.4142135623730951 - basis * 1.4142135623730951
        qL[2] ~ -(1 - basis) * 1.4142135623730951 + basis * 1.4142135623730951
        qL[3] ~ (1 - basis) * 1.4142135623730951 - basis * 1.4142135623730951
        tat[1] ~ (1 - basis) * 0.9003163161571
        tat[2] ~ (1 - basis) * 0.300105438719
        tat[3] ~ (1 - basis) * 0.1800632632314
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
        # ---- modal stiffness, damping and the free eigenfrequencies (Hz) ----
        for i in 1:3
            ky[i] ~ lam[i]^4 * E * Iz / (L * L * L)
            kz[i] ~ lam[i]^4 * E * Iy / (L * L * L)
            kt[i] ~ 9.869604401089358 * kk[i] * kk[i] * G * Jt / L
            cy[i] ~ 2.0 * zeta_y * sqrt(ky[i] * m)
            cz[i] ~ 2.0 * zeta_z * sqrt(kz[i] * m)
            ct[i] ~ 2.0 * zeta_t * sqrt(kt[i] * mt)
            f_y[i] ~ 0.15915494309189535 * sqrt(ky[i] / m)
            f_z[i] ~ 0.15915494309189535 * sqrt(kz[i] / m)
            f_t[i] ~ 0.15915494309189535 * sqrt(kt[i] / mt)
        end
        # ---- the deflection-dependent inertia ----
        for i in 1:3
            g0y[i] ~ (G0[i, 1] * y[1] + G0[i, 2] * y[2] + G0[i, 3] * y[3]) / L
            g0z[i] ~ (G0[i, 1] * z[1] + G0[i, 2] * z[2] + G0[i, 3] * z[3]) / L
            g1y[i] ~ m / L * (G1[i, 1] * y[1] + G1[i, 2] * y[2] + G1[i, 3] * y[3])
            g1z[i] ~ m / L * (G1[i, 1] * z[1] + G1[i, 2] * z[2] + G1[i, 3] * z[3])
            g2y[i] ~ m * (G2[i, 1] * y[1] + G2[i, 2] * y[2] + G2[i, 3] * y[3])
            g2z[i] ~ m * (G2[i, 1] * z[1] + G2[i, 2] * z[2] + G2[i, 3] * z[3])
            g1yd[i] ~ m / L * (G1[i, 1] * yd[1] + G1[i, 2] * yd[2] + G1[i, 3] * yd[3])
            g1zd[i] ~ m / L * (G1[i, 1] * zd[1] + G1[i, 2] * zd[2] + G1[i, 3] * zd[3])
        end
        Q1 ~ y[1] * g1y[1] + y[2] * g1y[2] + y[3] * g1y[3] + z[1] * g1z[1] + z[2] * g1z[2] + z[3] * g1z[3]
        Q2 ~ y[1] * g2y[1] + y[2] * g2y[2] + y[3] * g2y[3] + z[1] * g2z[1] + z[2] * g2z[2] + z[3] * g2z[3]
        S[1] ~ 0.5 * m * L - 0.5 * Q1
        S[2] ~ m * (ta[1] * y[1] + ta[2] * y[2] + ta[3] * y[3])
        S[3] ~ m * (ta[1] * z[1] + ta[2] * z[2] + ta[3] * z[3])
        Jm[1, 1] ~ J0[1] + m * (y[1] * y[1] + y[2] * y[2] + y[3] * y[3] + z[1] * z[1] + z[2] * z[2] + z[3] * z[3])
        Jm[2, 2] ~ J0[2] - Q2 + m * (z[1] * z[1] + z[2] * z[2] + z[3] * z[3])
        Jm[3, 3] ~ J0[3] - Q2 + m * (y[1] * y[1] + y[2] * y[2] + y[3] * y[3])
        Jm[1, 2] ~ -m * L * (tb[1] * y[1] + tb[2] * y[2] + tb[3] * y[3])
        Jm[1, 3] ~ -m * L * (tb[1] * z[1] + tb[2] * z[2] + tb[3] * z[3])
        Jm[2, 3] ~ -m * (y[1] * z[1] + y[2] * z[2] + y[3] * z[3])
        Jm[2, 1] ~ Jm[1, 2]
        Jm[3, 1] ~ Jm[1, 3]
        Jm[3, 2] ~ Jm[2, 3]
        for i in 1:3
            for j in 1:3
                MV[i, j] ~ Jm[i, j]
            end
        end
        MV[1, 4] ~ 0.0
        MV[1, 5] ~ -S[3]
        MV[1, 6] ~ S[2]
        MV[2, 4] ~ S[3]
        MV[2, 5] ~ 0.0
        MV[2, 6] ~ -S[1]
        MV[3, 4] ~ -S[2]
        MV[3, 5] ~ S[1]
        MV[3, 6] ~ 0.0
        for i in 1:3
            for j in 1:3
                MV[3 + j, i] ~ MV[i, 3 + j]
            end
        end
        MV[4, 4] ~ m
        MV[4, 5] ~ 0.0
        MV[4, 6] ~ 0.0
        MV[5, 4] ~ 0.0
        MV[5, 5] ~ m
        MV[5, 6] ~ 0.0
        MV[6, 4] ~ 0.0
        MV[6, 5] ~ 0.0
        MV[6, 6] ~ m
        # ---- modes: coupling rows C_i (zero for an inactive mode), rates, momenta ----
        for i in 1:ny
            Cy[i, 1] ~ -m * z[i]
            Cy[i, 2] ~ 0.0
            Cy[i, 3] ~ m * L * tb[i]
            Cy[i, 4] ~ -g1y[i]
            Cy[i, 5] ~ m * ta[i]
            Cy[i, 6] ~ 0.0
            ddt(y[i]) ~ yd[i]
            ddt(py[i]) ~ Fy[i]
        end
        for i in (ny + 1):3
            for k in 1:6
                Cy[i, k] ~ 0.0
            end
            y[i] ~ 0.0
            py[i] ~ 0.0
        end
        for i in 1:nz
            Cz[i, 1] ~ m * y[i]
            Cz[i, 2] ~ -m * L * tb[i]
            Cz[i, 3] ~ 0.0
            Cz[i, 4] ~ -g1z[i]
            Cz[i, 5] ~ 0.0
            Cz[i, 6] ~ m * ta[i]
            ddt(z[i]) ~ zd[i]
            ddt(pz[i]) ~ Fz[i]
        end
        for i in (nz + 1):3
            for k in 1:6
                Cz[i, k] ~ 0.0
            end
            z[i] ~ 0.0
            pz[i] ~ 0.0
        end
        for i in 1:nt
            Ct[i, 1] ~ mt * tat[i]
            for k in 2:6
                Ct[i, k] ~ 0.0
            end
            ddt(th[i]) ~ thd[i]
            ddt(pth[i]) ~ Fth[i]
        end
        for i in (nt + 1):3
            for k in 1:6
                Ct[i, k] ~ 0.0
            end
            th[i] ~ 0.0
            pth[i] ~ 0.0
        end
        # ---- frame twist from the momenta: (M_VV - C^T M_e^-1 C) V = P - C^T M_e^-1 p ----
        for k in 1:6
            for l in 1:6
                Mr[k, l] ~ MV[k, l] -
                           (Cy[1, k] * Cy[1, l] + Cy[2, k] * Cy[2, l] + Cy[3, k] * Cy[3, l] +
                            Cz[1, k] * Cz[1, l] + Cz[2, k] * Cz[2, l] + Cz[3, k] * Cz[3, l]) / m -
                           (Ct[1, k] * Ct[1, l] + Ct[2, k] * Ct[2, l] + Ct[3, k] * Ct[3, l]) / mt
            end
            hr[k] ~ P[k] -
                    (Cy[1, k] * py[1] + Cy[2, k] * py[2] + Cy[3, k] * py[3] +
                     Cz[1, k] * pz[1] + Cz[2, k] * pz[2] + Cz[3, k] * pz[3]) / m -
                    (Ct[1, k] * pth[1] + Ct[2, k] * pth[2] + Ct[3, k] * pth[3]) / mt
        end
        # linear block D = Mr[4:6, 4:6] (symmetric): X = D^-1 by cofactors
        detD ~ Mr[4, 4] * (Mr[5, 5] * Mr[6, 6] - Mr[5, 6] * Mr[6, 5]) -
               Mr[4, 5] * (Mr[5, 4] * Mr[6, 6] - Mr[5, 6] * Mr[6, 4]) +
               Mr[4, 6] * (Mr[5, 4] * Mr[6, 5] - Mr[5, 5] * Mr[6, 4])
        X[1, 1] ~ (Mr[5, 5] * Mr[6, 6] - Mr[5, 6] * Mr[6, 5]) / detD
        X[1, 2] ~ (Mr[4, 6] * Mr[6, 5] - Mr[4, 5] * Mr[6, 6]) / detD
        X[1, 3] ~ (Mr[4, 5] * Mr[5, 6] - Mr[4, 6] * Mr[5, 5]) / detD
        X[2, 1] ~ (Mr[5, 6] * Mr[6, 4] - Mr[5, 4] * Mr[6, 6]) / detD
        X[2, 2] ~ (Mr[4, 4] * Mr[6, 6] - Mr[4, 6] * Mr[6, 4]) / detD
        X[2, 3] ~ (Mr[4, 6] * Mr[5, 4] - Mr[4, 4] * Mr[5, 6]) / detD
        X[3, 1] ~ (Mr[5, 4] * Mr[6, 5] - Mr[5, 5] * Mr[6, 4]) / detD
        X[3, 2] ~ (Mr[4, 5] * Mr[6, 4] - Mr[4, 4] * Mr[6, 5]) / detD
        X[3, 3] ~ (Mr[4, 4] * Mr[5, 5] - Mr[4, 5] * Mr[5, 4]) / detD
        # angular Schur complement Jr = Mr_ww - B X B^T, B = Mr[1:3, 4:6]
        for i in 1:3
            for j in 1:3
                BX[i, j] ~ Mr[i, 4] * X[1, j] + Mr[i, 5] * X[2, j] + Mr[i, 6] * X[3, j]
            end
        end
        for i in 1:3
            for j in 1:3
                Jr[i, j] ~ Mr[i, j] - (BX[i, 1] * Mr[j, 4] + BX[i, 2] * Mr[j, 5] + BX[i, 3] * Mr[j, 6])
            end
        end
        detJ ~ Jr[1, 1] * (Jr[2, 2] * Jr[3, 3] - Jr[2, 3] * Jr[3, 2]) -
               Jr[1, 2] * (Jr[2, 1] * Jr[3, 3] - Jr[2, 3] * Jr[3, 1]) +
               Jr[1, 3] * (Jr[2, 1] * Jr[3, 2] - Jr[2, 2] * Jr[3, 1])
        Y[1, 1] ~ (Jr[2, 2] * Jr[3, 3] - Jr[2, 3] * Jr[3, 2]) / detJ
        Y[1, 2] ~ (Jr[1, 3] * Jr[3, 2] - Jr[1, 2] * Jr[3, 3]) / detJ
        Y[1, 3] ~ (Jr[1, 2] * Jr[2, 3] - Jr[1, 3] * Jr[2, 2]) / detJ
        Y[2, 1] ~ (Jr[2, 3] * Jr[3, 1] - Jr[2, 1] * Jr[3, 3]) / detJ
        Y[2, 2] ~ (Jr[1, 1] * Jr[3, 3] - Jr[1, 3] * Jr[3, 1]) / detJ
        Y[2, 3] ~ (Jr[1, 3] * Jr[2, 1] - Jr[1, 1] * Jr[2, 3]) / detJ
        Y[3, 1] ~ (Jr[2, 1] * Jr[3, 2] - Jr[2, 2] * Jr[3, 1]) / detJ
        Y[3, 2] ~ (Jr[1, 2] * Jr[3, 1] - Jr[1, 1] * Jr[3, 2]) / detJ
        Y[3, 3] ~ (Jr[1, 1] * Jr[2, 2] - Jr[1, 2] * Jr[2, 1]) / detJ
        for i in 1:3
            hw[i] ~ hr[i] - (BX[i, 1] * hr[4] + BX[i, 2] * hr[5] + BX[i, 3] * hr[6])
        end
        for i in 1:3
            V[i] ~ Y[i, 1] * hw[1] + Y[i, 2] * hw[2] + Y[i, 3] * hw[3]
        end
        for i in 1:3
            hv[i] ~ hr[3 + i] - (Mr[1, 3 + i] * V[1] + Mr[2, 3 + i] * V[2] + Mr[3, 3 + i] * V[3])
        end
        for i in 1:3
            V[3 + i] ~ X[i, 1] * hv[1] + X[i, 2] * hv[2] + X[i, 3] * hv[3]
        end
        # modal velocities: eta' = (p - C V) / m_i
        for i in 1:3
            yd[i] ~ (py[i] - (Cy[i, 1] * V[1] + Cy[i, 2] * V[2] + Cy[i, 3] * V[3] +
                               Cy[i, 4] * V[4] + Cy[i, 5] * V[5] + Cy[i, 6] * V[6])) / m
            zd[i] ~ (pz[i] - (Cz[i, 1] * V[1] + Cz[i, 2] * V[2] + Cz[i, 3] * V[3] +
                               Cz[i, 4] * V[4] + Cz[i, 5] * V[5] + Cz[i, 6] * V[6])) / m
            thd[i] ~ (pth[i] - Ct[i, 1] * V[1]) / mt
        end
        # ---- end frames (exact Gibbs chart) ----
        # torsion is exact (g_x = tan(theta/2), so a pure twist turns the end frame by exactly
        # theta, however large); the bending slopes enter as w'/2
        ga[1] ~ tan(0.5 * (q0[1] * th[1] + q0[2] * th[2] + q0[3] * th[3]))
        ga[2] ~ -0.5 * (s0[1] * z[1] + s0[2] * z[2] + s0[3] * z[3]) / L
        ga[3] ~ 0.5 * (s0[1] * y[1] + s0[2] * y[2] + s0[3] * y[3]) / L
        gb[1] ~ tan(0.5 * (qL[1] * th[1] + qL[2] * th[2] + qL[3] * th[3]))
        gb[2] ~ -0.5 * (sL[1] * z[1] + sL[2] * z[2] + sL[3] * z[3]) / L
        gb[3] ~ 0.5 * (sL[1] * y[1] + sL[2] * y[2] + sL[3] * y[3]) / L
        gad[1] ~ 0.5 * (1.0 + ga[1] * ga[1]) * (q0[1] * thd[1] + q0[2] * thd[2] + q0[3] * thd[3])
        gad[2] ~ -0.5 * (s0[1] * zd[1] + s0[2] * zd[2] + s0[3] * zd[3]) / L
        gad[3] ~ 0.5 * (s0[1] * yd[1] + s0[2] * yd[2] + s0[3] * yd[3]) / L
        gbd[1] ~ 0.5 * (1.0 + gb[1] * gb[1]) * (qL[1] * thd[1] + qL[2] * thd[2] + qL[3] * thd[3])
        gbd[2] ~ -0.5 * (sL[1] * zd[1] + sL[2] * zd[2] + sL[3] * zd[3]) / L
        gbd[3] ~ 0.5 * (sL[1] * yd[1] + sL[2] * yd[2] + sL[3] * yd[3]) / L
        Da ~ 1.0 + ga[1] * ga[1] + ga[2] * ga[2] + ga[3] * ga[3]
        Db ~ 1.0 + gb[1] * gb[1] + gb[2] * gb[2] + gb[3] * gb[3]
        Ra[1, 1] ~ (1.0 + ga[1] * ga[1] - ga[2] * ga[2] - ga[3] * ga[3]) / Da
        Ra[1, 2] ~ 2.0 * (ga[1] * ga[2] - ga[3]) / Da
        Ra[1, 3] ~ 2.0 * (ga[1] * ga[3] + ga[2]) / Da
        Ra[2, 1] ~ 2.0 * (ga[1] * ga[2] + ga[3]) / Da
        Ra[2, 2] ~ (1.0 - ga[1] * ga[1] + ga[2] * ga[2] - ga[3] * ga[3]) / Da
        Ra[2, 3] ~ 2.0 * (ga[2] * ga[3] - ga[1]) / Da
        Ra[3, 1] ~ 2.0 * (ga[1] * ga[3] - ga[2]) / Da
        Ra[3, 2] ~ 2.0 * (ga[2] * ga[3] + ga[1]) / Da
        Ra[3, 3] ~ (1.0 - ga[1] * ga[1] - ga[2] * ga[2] + ga[3] * ga[3]) / Da
        Rb[1, 1] ~ (1.0 + gb[1] * gb[1] - gb[2] * gb[2] - gb[3] * gb[3]) / Db
        Rb[1, 2] ~ 2.0 * (gb[1] * gb[2] - gb[3]) / Db
        Rb[1, 3] ~ 2.0 * (gb[1] * gb[3] + gb[2]) / Db
        Rb[2, 1] ~ 2.0 * (gb[1] * gb[2] + gb[3]) / Db
        Rb[2, 2] ~ (1.0 - gb[1] * gb[1] + gb[2] * gb[2] - gb[3] * gb[3]) / Db
        Rb[2, 3] ~ 2.0 * (gb[2] * gb[3] - gb[1]) / Db
        Rb[3, 1] ~ 2.0 * (gb[1] * gb[3] - gb[2]) / Db
        Rb[3, 2] ~ 2.0 * (gb[2] * gb[3] + gb[1]) / Db
        Rb[3, 3] ~ (1.0 - gb[1] * gb[1] - gb[2] * gb[2] + gb[3] * gb[3]) / Db
        ra[1] ~ 0.0
        ra[2] ~ p0[1] * y[1] + p0[2] * y[2] + p0[3] * y[3]
        ra[3] ~ p0[1] * z[1] + p0[2] * z[2] + p0[3] * z[3]
        rb[1] ~ L - 0.5 * (y[1] * g0y[1] + y[2] * g0y[2] + y[3] * g0y[3] + z[1] * g0z[1] + z[2] * g0z[2] + z[3] * g0z[3])
        rb[2] ~ pL[1] * y[1] + pL[2] * y[2] + pL[3] * y[3]
        rb[3] ~ pL[1] * z[1] + pL[2] * z[2] + pL[3] * z[3]
        rad[1] ~ 0.0
        rad[2] ~ p0[1] * yd[1] + p0[2] * yd[2] + p0[3] * yd[3]
        rad[3] ~ p0[1] * zd[1] + p0[2] * zd[2] + p0[3] * zd[3]
        rbd[1] ~ -(g0y[1] * yd[1] + g0y[2] * yd[2] + g0y[3] * yd[3] + g0z[1] * zd[1] + g0z[2] * zd[2] + g0z[3] * zd[3])
        rbd[2] ~ pL[1] * yd[1] + pL[2] * yd[2] + pL[3] * yd[3]
        rbd[3] ~ pL[1] * zd[1] + pL[2] * zd[2] + pL[3] * zd[3]
        # relative angular rates of the end frames, in their own coordinates: 2/D (g' - g x g')
        wa[1] ~ 2.0 / Da * (gad[1] - (ga[2] * gad[3] - ga[3] * gad[2]))
        wa[2] ~ 2.0 / Da * (gad[2] - (ga[3] * gad[1] - ga[1] * gad[3]))
        wa[3] ~ 2.0 / Da * (gad[3] - (ga[1] * gad[2] - ga[2] * gad[1]))
        wb[1] ~ 2.0 / Db * (gbd[1] - (gb[2] * gbd[3] - gb[3] * gbd[2]))
        wb[2] ~ 2.0 / Db * (gbd[2] - (gb[3] * gbd[1] - gb[1] * gbd[3]))
        wb[3] ~ 2.0 / Db * (gbd[3] - (gb[1] * gbd[2] - gb[2] * gbd[1]))
        # velocity of the end origins in R: v + w x r + r'
        ua[1] ~ V[4] + V[2] * ra[3] - V[3] * ra[2] + rad[1]
        ua[2] ~ V[5] + V[3] * ra[1] - V[1] * ra[3] + rad[2]
        ua[3] ~ V[6] + V[1] * ra[2] - V[2] * ra[1] + rad[3]
        ub[1] ~ V[4] + V[2] * rb[3] - V[3] * rb[2] + rbd[1]
        ub[2] ~ V[5] + V[3] * rb[1] - V[1] * rb[3] + rbd[2]
        ub[3] ~ V[6] + V[1] * rb[2] - V[2] * rb[1] + rbd[3]
        # port flows: [R^T w + w_rel; R^T (v + w x r + r')]
        for i in 1:3
            pa.f[i] ~ Ra[1, i] * V[1] + Ra[2, i] * V[2] + Ra[3, i] * V[3] + wa[i]
            pa.f[3 + i] ~ Ra[1, i] * ua[1] + Ra[2, i] * ua[2] + Ra[3, i] * ua[3]
            pb.f[i] ~ Rb[1, i] * V[1] + Rb[2, i] * V[2] + Rb[3, i] * V[3] + wb[i]
            pb.f[3 + i] ~ Rb[1, i] * ub[1] + Rb[2, i] * ub[2] + Rb[3, i] * ub[3]
        end
        # port efforts through the transpose: force in R, Gibbs-conjugate torque, frame wrench
        for i in 1:3
            Fa[i] ~ Ra[i, 1] * pa.e[4] + Ra[i, 2] * pa.e[5] + Ra[i, 3] * pa.e[6]
            Fb[i] ~ Rb[i, 1] * pb.e[4] + Rb[i, 2] * pb.e[5] + Rb[i, 3] * pb.e[6]
        end
        Ta[1] ~ 2.0 / Da * (pa.e[1] + ga[2] * pa.e[3] - ga[3] * pa.e[2])
        Ta[2] ~ 2.0 / Da * (pa.e[2] + ga[3] * pa.e[1] - ga[1] * pa.e[3])
        Ta[3] ~ 2.0 / Da * (pa.e[3] + ga[1] * pa.e[2] - ga[2] * pa.e[1])
        Tb[1] ~ 2.0 / Db * (pb.e[1] + gb[2] * pb.e[3] - gb[3] * pb.e[2])
        Tb[2] ~ 2.0 / Db * (pb.e[2] + gb[3] * pb.e[1] - gb[1] * pb.e[3])
        Tb[3] ~ 2.0 / Db * (pb.e[3] + gb[1] * pb.e[2] - gb[2] * pb.e[1])
        Wa[1] ~ Ra[1, 1] * pa.e[1] + Ra[1, 2] * pa.e[2] + Ra[1, 3] * pa.e[3] + ra[2] * Fa[3] - ra[3] * Fa[2]
        Wa[2] ~ Ra[2, 1] * pa.e[1] + Ra[2, 2] * pa.e[2] + Ra[2, 3] * pa.e[3] + ra[3] * Fa[1] - ra[1] * Fa[3]
        Wa[3] ~ Ra[3, 1] * pa.e[1] + Ra[3, 2] * pa.e[2] + Ra[3, 3] * pa.e[3] + ra[1] * Fa[2] - ra[2] * Fa[1]
        Wb[1] ~ Rb[1, 1] * pb.e[1] + Rb[1, 2] * pb.e[2] + Rb[1, 3] * pb.e[3] + rb[2] * Fb[3] - rb[3] * Fb[2]
        Wb[2] ~ Rb[2, 1] * pb.e[1] + Rb[2, 2] * pb.e[2] + Rb[2, 3] * pb.e[3] + rb[3] * Fb[1] - rb[1] * Fb[3]
        Wb[3] ~ Rb[3, 1] * pb.e[1] + Rb[3, 2] * pb.e[2] + Rb[3, 3] * pb.e[3] + rb[1] * Fb[2] - rb[2] * Fb[1]
        for i in 1:3
            Wa[3 + i] ~ Fa[i]
            Wb[3 + i] ~ Fb[i]
        end
        # ---- gravity: world z in the end-A frame, then in R (g_R = R_A^T-free: R_R^T e_z = Ra c3) ----
        sq ~ gA[1] * gA[1] + gA[2] * gA[2] + gA[3] * gA[3] + gA[4] * gA[4]
        c3[1] ~ 2.0 * (gA[2] * gA[4] - gA[1] * gA[3]) / sq
        c3[2] ~ 2.0 * (gA[3] * gA[4] + gA[1] * gA[2]) / sq
        c3[3] ~ (gA[1] * gA[1] - gA[2] * gA[2] - gA[3] * gA[3] + gA[4] * gA[4]) / sq
        for i in 1:3
            gv[i] ~ -g0 * (Ra[i, 1] * c3[1] + Ra[i, 2] * c3[2] + Ra[i, 3] * c3[3])
        end
        # ---- frame momentum: P' = ad(V)^T P + wrenches (Euler-Poincare) ----
        ddt(P[1]) ~ P[2] * V[3] - P[3] * V[2] + P[5] * V[6] - P[6] * V[5] + Wa[1] + Wb[1] + S[2] * gv[3] - S[3] * gv[2]
        ddt(P[2]) ~ P[3] * V[1] - P[1] * V[3] + P[6] * V[4] - P[4] * V[6] + Wa[2] + Wb[2] + S[3] * gv[1] - S[1] * gv[3]
        ddt(P[3]) ~ P[1] * V[2] - P[2] * V[1] + P[4] * V[5] - P[5] * V[4] + Wa[3] + Wb[3] + S[1] * gv[2] - S[2] * gv[1]
        ddt(P[4]) ~ P[5] * V[3] - P[6] * V[2] + Wa[4] + Wb[4] + m * gv[1]
        ddt(P[5]) ~ P[6] * V[1] - P[4] * V[3] + Wa[5] + Wb[5] + m * gv[2]
        ddt(P[6]) ~ P[4] * V[2] - P[5] * V[1] + Wa[6] + Wb[6] + m * gv[3]
        # ---- modal momenta: p' = dT/d eta - k eta - d eta' + J^T e + Q_gravity ----
        vw[1] ~ V[5] * V[3] - V[6] * V[2]
        vw[2] ~ V[6] * V[1] - V[4] * V[3]
        vw[3] ~ V[4] * V[2] - V[5] * V[1]
        for i in 1:3
            dTy[i] ~ m * y[i] * (V[1] * V[1] + V[3] * V[3]) - (V[2] * V[2] + V[3] * V[3]) * g2y[i] -
                     m * L * tb[i] * V[1] * V[2] - m * z[i] * V[2] * V[3] - g1y[i] * vw[1] +
                     m * ta[i] * vw[2] + m * V[1] * zd[i] - V[4] * g1yd[i]
            dTz[i] ~ m * z[i] * (V[1] * V[1] + V[2] * V[2]) - (V[2] * V[2] + V[3] * V[3]) * g2z[i] -
                     m * L * tb[i] * V[1] * V[3] - m * y[i] * V[2] * V[3] - g1z[i] * vw[1] +
                     m * ta[i] * vw[3] - m * V[1] * yd[i] - V[4] * g1zd[i]
            Fy[i] ~ dTy[i] - ky[i] * y[i] - cy[i] * yd[i] +
                    0.5 * Ta[3] * s0[i] / L + Fa[2] * p0[i] +
                    0.5 * Tb[3] * sL[i] / L + Fb[2] * pL[i] - Fb[1] * g0y[i] +
                    m * ta[i] * gv[2] - g1y[i] * gv[1]
            Fz[i] ~ dTz[i] - kz[i] * z[i] - cz[i] * zd[i] -
                    0.5 * Ta[2] * s0[i] / L + Fa[3] * p0[i] -
                    0.5 * Tb[2] * sL[i] / L + Fb[3] * pL[i] - Fb[1] * g0z[i] +
                    m * ta[i] * gv[3] - g1z[i] * gv[1]
            Fth[i] ~ -kt[i] * th[i] - ct[i] * thd[i] + 0.5 * (1.0 + ga[1] * ga[1]) * Ta[1] * q0[i] +
                     0.5 * (1.0 + gb[1] * gb[1]) * Tb[1] * qL[i]
        end
        # ---- poses: R = gA composed with H_A^-1, B = R composed with H_B ----
        qR[1] ~ (gA[1] + gA[2] * ga[1] + gA[3] * ga[2] + gA[4] * ga[3]) / sqrt(Da)
        qR[2] ~ (gA[2] - gA[1] * ga[1] - gA[3] * ga[3] + gA[4] * ga[2]) / sqrt(Da)
        qR[3] ~ (gA[3] - gA[1] * ga[2] + gA[2] * ga[3] - gA[4] * ga[1]) / sqrt(Da)
        qR[4] ~ (gA[4] - gA[1] * ga[3] - gA[2] * ga[2] + gA[3] * ga[1]) / sqrt(Da)
        sR ~ qR[1] * qR[1] + qR[2] * qR[2] + qR[3] * qR[3] + qR[4] * qR[4]
        RR[1, 1] ~ (qR[1] * qR[1] + qR[2] * qR[2] - qR[3] * qR[3] - qR[4] * qR[4]) / sR
        RR[1, 2] ~ 2.0 * (qR[2] * qR[3] - qR[1] * qR[4]) / sR
        RR[1, 3] ~ 2.0 * (qR[2] * qR[4] + qR[1] * qR[3]) / sR
        RR[2, 1] ~ 2.0 * (qR[2] * qR[3] + qR[1] * qR[4]) / sR
        RR[2, 2] ~ (qR[1] * qR[1] - qR[2] * qR[2] + qR[3] * qR[3] - qR[4] * qR[4]) / sR
        RR[2, 3] ~ 2.0 * (qR[3] * qR[4] - qR[1] * qR[2]) / sR
        RR[3, 1] ~ 2.0 * (qR[2] * qR[4] - qR[1] * qR[3]) / sR
        RR[3, 2] ~ 2.0 * (qR[3] * qR[4] + qR[1] * qR[2]) / sR
        RR[3, 3] ~ (qR[1] * qR[1] - qR[2] * qR[2] - qR[3] * qR[3] + qR[4] * qR[4]) / sR
        for i in 1:4
            pose[i] ~ qR[i]
        end
        for i in 1:3
            pose[4 + i] ~ gA[4 + i] - (RR[i, 1] * ra[1] + RR[i, 2] * ra[2] + RR[i, 3] * ra[3])
        end
        poseB[1] ~ (qR[1] - qR[2] * gb[1] - qR[3] * gb[2] - qR[4] * gb[3]) / sqrt(Db)
        poseB[2] ~ (qR[2] + qR[1] * gb[1] + qR[3] * gb[3] - qR[4] * gb[2]) / sqrt(Db)
        poseB[3] ~ (qR[3] + qR[1] * gb[2] - qR[2] * gb[3] + qR[4] * gb[1]) / sqrt(Db)
        poseB[4] ~ (qR[4] + qR[1] * gb[3] + qR[2] * gb[2] - qR[3] * gb[1]) / sqrt(Db)
        for i in 1:3
            poseB[4 + i] ~ pose[4 + i] + RR[i, 1] * rb[1] + RR[i, 2] * rb[2] + RR[i, 3] * rb[3]
        end
        # ---- taps ----
        for i in 1:3
            eta_y[i] ~ y[i]
            eta_z[i] ~ z[i]
            eta_t[i] ~ th[i]
        end
        twist ~ (qL[1] - q0[1]) * th[1] + (qL[2] - q0[2]) * th[2] + (qL[3] - q0[3]) * th[3]
        dB[1] ~ rb[1] - L
        dB[2] ~ rb[2]
        dB[3] ~ rb[3]
        Ek ~ 0.5 * (P[1] * V[1] + P[2] * V[2] + P[3] * V[3] + P[4] * V[4] + P[5] * V[5] + P[6] * V[6] +
                    py[1] * yd[1] + py[2] * yd[2] + py[3] * yd[3] + pz[1] * zd[1] + pz[2] * zd[2] +
                    pz[3] * zd[3] + pth[1] * thd[1] + pth[2] * thd[2] + pth[3] * thd[3])
        Ee ~ 0.5 * (ky[1] * y[1] * y[1] + ky[2] * y[2] * y[2] + ky[3] * y[3] * y[3] +
                    kz[1] * z[1] * z[1] + kz[2] * z[2] * z[2] + kz[3] * z[3] * z[3] +
                    kt[1] * th[1] * th[1] + kt[2] * th[2] * th[2] + kt[3] * th[3] * th[3])
        Eg ~ g0 * (m * pose[7] + RR[3, 1] * S[1] + RR[3, 2] * S[2] + RR[3, 3] * S[3])
    end
    @causality begin
        pa => :flow_out
        pb => :flow_out
    end
end
