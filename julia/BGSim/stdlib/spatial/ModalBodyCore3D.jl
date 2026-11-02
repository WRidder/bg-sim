@block ModalBodyCore3D begin
    # FEM flexible body, floating-frame formulation with general modal invariants (the modal
    # core of `ModalBody3D`). The reduced matrices come from a Craig–Bampton reduction of a
    # finite element model (julia/BGSimFEM): the compiler reads the reduced-model file of the
    # `ModalBody3D` node and passes its content down as the constants below (they fold into
    # literals: the simulation and the exported C code hold them as numbers).
    #
    # The reference frame R is the frame of interface A; the elastic field is measured relative
    # to it (Craig–Bampton with interface A clamped, the general form of the beam blocks'
    # clamped-free basis): a material point at x (in R) moves to r = x + Phi(x) q, q the nm
    # modal coordinates (m; diagonal modal mass mk and stiffness kk). The kinetic energy is
    # exact for this linear field; the second-order field u2(q) enters through the
    # geometric-stiffening matrices (int f . u2 = -1/2 q' G(f) q, see julia/BGSimFEM) in the
    # first moment S(q) and the inertia J(q) only:
    #
    #   T = 1/2 m |v|^2 + v.(w x S(q)) + 1/2 w.J(q) w + V.C(q)' q' + 1/2 sum mk q'^2
    #   S(q) = S0 + St q - 1/2 (q' Gt_a q)_a
    #   J(q) = J0 + sum_k q_k J1_k + (tr U I - U) - 1/2 (q' Gj_ab q)_ab,  U_ab = q' E_ab q
    #   C rows: rotation   Sr[:,k] - (W_a q)_k,  W_x = Eyz - Eyz', W_y = Exz' - Exz, W_z = Exy - Exy'
    #           translation St[:,k]
    #
    # So the body stiffens by its rotation (centrifugal, through J(q) and S(q)), by gravity
    # (through S(q) in U_g) and by the interface forces (below). The u2 terms of the coupling
    # rows C (stiffening by the frame's translational and angular acceleration) are left out on
    # purpose: they are first order in q, and without the matching third-order terms of the
    # modal mass block they make the mass matrix indefinite already at moderate deflections of a
    # light part (the rotational Schur complement of a free body is small). The file's
    # rotational-acceleration matrices (`stiffening.rotation`) are therefore not used.
    #
    # This is the multibond bond graph of `ModalBeam3D` with arbitrary invariants: the frame
    # 1-junction with the reduced rigid inertia and the Euler gyrator, the modal 1-junctions
    # with their C (kk) and R (2 zeta sqrt(kk mk)), the modal momenta p = mk q' + C V on
    # 0-junctions, and an MTF from the frame and the modes to every interface. States: the frame
    # momentum P (6), the modal momenta p and the modal coordinates q. The flows follow from the
    # momenta by a Schur complement (closed-form 3x3 blocks, so the body is an explicit ODE and
    # exports without a linear solve):
    #
    #   q' = (p - C V) / mk,   (M_VV - C' diag(1/mk) C) V = P - C' (p / mk)
    #   P' = ad(V)' P + sum_P Ad(H_P)^-T e_P + W_gravity                    (Euler-Poincare)
    #   p' = dT/dq - kk q - ck q' + sum_P J_P' e_P + Q_gravity
    #
    # H = T + 1/2 sum kk q^2 + U_g is conserved without damping (power-continuous ports).
    #
    # Interfaces: A (port pa) is the frame R itself. Interface j = B, C, D (ports pb, pc, pd)
    # sits at r_j = XP_j + PT_j q - 1/2 (q' G_j,a q)_a (the interface-force stiffening) with
    # the rotation RP_j R(g_j), g_j = 1/2 PR_j q (Gibbs vector in the interface frame, exact
    # chart as in ModalBeam3D): flow [R_j' w + w_rel; R_j' (v + w x r_j + r_j')], effort
    # through the transpose. An interface the file does not have has zero mode
    # values: it is a rigid point at the origin of R; leave it unconnected.
    #
    # Rail (nr = 1, the file's `rail`): a moving interface, the frame of a carriage's guide
    # block at the position sr along a straight rail on the part. Its origin and elastic
    # rotation follow Chebyshev tables in x = 2 sr / RL - 1 (smooth, exact d/ds, no switching):
    #
    #   r_E = XR + sr t + PT(sr) q,   g_E = 1/2 PR(sr) q,   PT = sum_n CT_n T_n(x), PR likewise
    #
    # and its rate includes the sliding along the deformed rail, r_E' = PT q' + (t + PT' q) sr'
    # and g_E' = 1/2 (PR q' + PR' q sr'), so a carriage on pe rides the deformed rail. The slide
    # sr belongs to a slider of mass ms (the drive's moving part along the rail; its own motion
    # with the body frame is left out, keep it small and put the carriage's mass on the body at
    # pe): ms sr'' = ps.e + Fs, with the rail's generalized force Fs = (t + PT' q) . F_E +
    # g_E,s . TG_E, which makes pe, ps and the body power-continuous. Without a rail both ports
    # carry zero flow; leave them unconnected.
    @constants begin
        nm::Int = 2, [min = 1, max = 48, description = "Number of modal coordinates (from the reduced-model file)"]
        stiffening::Int = 1, [options = ["off", "on"], description = "Geometric stiffening terms: 0 off, 1 on (when the file has them)"]
        mass::Real = 1.0, [unit = "kg", description = "Mass"]
        S0::Vec{3} = [0.5, 0.0, 0.0], [unit = "kg*m", description = "First moment of mass in R"]
        J0::Mat{3,3} = [0.01 0.0 0.0; 0.0 0.34 0.0; 0.0 0.0 0.34], [unit = "kg*m^2", description = "Inertia tensor about the origin of R"]
        mk::Vec{nm} = [0.25, 0.25], [unit = "kg", description = "Modal masses"]
        kk::Vec{nm} = [1.0e4, 1.0e4], [unit = "N/m", description = "Modal stiffnesses"]
        St::Mat{3,nm} = [0.0 0.0; 0.2 0.0; 0.0 0.2], [description = "int rho Phi (translational coupling)"]
        Sr::Mat{3,nm} = [0.0 0.0; 0.0 -0.15; 0.15 0.0], [description = "int rho x x Phi (rotational coupling)"]
        J1::Mat{6,nm} = [0.0 0.0; 0.0 0.0; 0.0 0.0; -0.2 0.0; 0.0 -0.2; 0.0 0.0], [description = "First-order inertia per mode (xx yy zz xy xz yz)"]
        Exx::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "int rho Phi_x' Phi_x"]
        Eyy::Mat{nm,nm} = [0.25 0.0; 0.0 0.0], [description = "int rho Phi_y' Phi_y"]
        Ezz::Mat{nm,nm} = [0.0 0.0; 0.0 0.25], [description = "int rho Phi_z' Phi_z"]
        Exy::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "int rho Phi_x' Phi_y"]
        Exz::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "int rho Phi_x' Phi_z"]
        Eyz::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "int rho Phi_y' Phi_z"]
        XP::Mat{3,4} = [0.0 1.0 0.0 0.0; 0.0 0.0 0.0 0.0; 0.0 0.0 0.0 0.0], [unit = "m", description = "Interface origins in R (columns A, B, C, D)"]
        QP::Mat{4,4} = [1.0 1.0 1.0 1.0; 0.0 0.0 0.0 0.0; 0.0 0.0 0.0 0.0; 0.0 0.0 0.0 0.0], [description = "Interface orientations in R, quaternions (w, x, y, z) as columns"]
        RP::Mat{3,12} = [1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0 0.0; 0.0 1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0; 0.0 0.0 1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0 0.0 1.0], [description = "Interface rotations in R (3x3 blocks A, B, C, D)"]
        PT::Mat{12,nm} = [0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 1.0 0.0; 0.0 1.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0], [description = "Interface translations per mode (rows 3j-2..3j: interface j, in R)"]
        PR::Mat{12,nm} = [0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 -1.5; 1.5 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0; 0.0 0.0], [description = "Interface rotations per mode (rows 3j-2..3j: interface j, in its own frame)"]
        Gt1::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit translational inertia load x"]
        Gt2::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: translational inertia load y"]
        Gt3::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: translational inertia load z"]
        Gj1::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component xx"]
        Gj2::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component yy"]
        Gj3::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component zz"]
        Gj4::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component xy"]
        Gj5::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component xz"]
        Gj6::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: inertia component yz"]
        Gb1::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force x at interface B"]
        Gb2::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force y at interface B"]
        Gb3::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force z at interface B"]
        Gc1::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force x at interface C"]
        Gc2::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force y at interface C"]
        Gc3::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force z at interface C"]
        Gd1::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force x at interface D"]
        Gd2::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force y at interface D"]
        Gd3::Mat{nm,nm} = [0.0 0.0; 0.0 0.0], [description = "Stiffening: unit force z at interface D"]
        # rail (a moving interface, see the header): Chebyshev tables of the rail frame motion
        nr::Int = 0, [options = ["none", "rail"], description = "1 when the file has a rail (port pe, slide ps)"]
        nc::Int = 2, [min = 2, max = 32, description = "Chebyshev terms of the rail tables"]
        RL::Real = 1.0, [unit = "m", description = "Rail length"]
        XR::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Rail start in R"]
        RR::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Rail frame in R (columns x, y, z = along the rail)"]
        QR::Vec{4} = [1.0, 0.0, 0.0, 0.0], [description = "Rail frame in R, quaternion (w, x, y, z)"]
        CT1::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail translation x per mode (R), Chebyshev coefficients"]
        CT2::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail translation y per mode (R)"]
        CT3::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail translation z per mode (R)"]
        CR1::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail rotation x per mode (rail frame)"]
        CR2::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail rotation y per mode (rail frame)"]
        CR3::Mat{nm,nc} = [0.0 0.0; 0.0 0.0], [description = "Rail rotation z per mode (rail frame)"]
    end
    @ports begin
        pa::Power{Spatial}, [frame = "body"]
        pb::Power{Spatial}, [frame = "body"]
        pc::Power{Spatial}, [frame = "body"]
        pd::Power{Spatial}, [frame = "body"]
        pe::Power{Spatial}, [frame = "body"]
        ps::Power{Translation}
    end
    @inputs gA::Vec{7}
    @outputs begin
        pose::Vec{7}
        poseB::Vec{7}
        poseC::Vec{7}
        poseD::Vec{7}
        poseE::Vec{7}
        s::Real, [unit = "m"]
        sd::Real, [unit = "m/s"]
        V::Vec{6}
        eta::Vec{nm}, [unit = "m"]
        f::Vec{nm}, [unit = "Hz"]
        Ek::Real, [unit = "J"]
        Ee::Real, [unit = "J"]
        Eg::Real, [unit = "J"]
    end
    @parameters begin
        zeta::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio (every mode)"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -z)"]
        ms::Real = 0.5, [unit = "kg", min = 1.0e-6, description = "Rail slider mass (the drive's moving part along the rail)"]
        s0::Real = 0.0, [unit = "m", description = "Initial rail position (from the rail start)"]
    end
    @variables begin
        # rail (port pe at the rail position sr, slider momentum psl)
        sr::Real = 0.0, [unit = "m", description = "Rail position"]
        psl::Real = 0.0, [unit = "N*s", state = :prefer, description = "Slider momentum"]
        sdr::Real, [unit = "m/s", description = "Rail speed"]
        xr::Real, [unit = "1", description = "2 sr / RL - 1"]
        Tr::Vec{nc}, [description = "Chebyshev polynomials at xr"]
        dTr::Vec{nc}, [description = "d Tr / d sr"]
        pt1::Vec{nm}
        pt2::Vec{nm}
        pt3::Vec{nm}
        pr1::Vec{nm}
        pr2::Vec{nm}
        pr3::Vec{nm}
        dpt1::Vec{nm}
        dpt2::Vec{nm}
        dpt3::Vec{nm}
        dpr1::Vec{nm}
        dpr2::Vec{nm}
        dpr3::Vec{nm}
        uE::Vec{3}, [unit = "m", description = "Rail frame displacement PT(s) q (R)"]
        usE::Vec{3}, [unit = "1", description = "d uE / d s"]
        rE::Vec{3}, [unit = "m", description = "Rail frame origin in R"]
        rdE::Vec{3}, [unit = "m/s", description = "Rate of rE"]
        gE::Vec{3}, [unit = "1", description = "Rail frame Gibbs vector 1/2 PR(s) q"]
        gsE::Vec{3}, [unit = "1/m", description = "d gE / d s"]
        gdE::Vec{3}, [description = "Rate of gE"]
        DE::Real, [unit = "1", description = "1 + |gE|^2"]
        RgE::Mat{3,3}, [unit = "1", description = "R(gE)"]
        RE::Mat{3,3}, [unit = "1", description = "Rail frame in R, RR R(gE)"]
        wE::Vec{3}, [description = "Relative angular rate of the rail frame (its frame)"]
        vE::Vec{3}, [description = "v + w x rE + rE'"]
        FE::Vec{3}, [unit = "N", description = "Rail force in R"]
        TGE::Vec{3}, [description = "Gibbs-conjugate rail torque"]
        WE::Vec{6}, [description = "Rail wrench on the frame"]
        QE::Vec{nm}, [unit = "N", description = "Rail generalized modal forces"]
        FsE::Real, [unit = "N", description = "Rail generalized force on the slide"]
        QAE::Vec{4}, [unit = "1", description = "gA quaternion times QR"]
        # states
        P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer, description = "Frame momentum [angular; linear] (conjugate to V)"]
        q::Vec{nm} = [0.0, 0.0], [unit = "m", state = :prefer, description = "Modal coordinates"]
        p::Vec{nm} = [0.0, 0.0], [unit = "N*s", state = :prefer, description = "Modal momenta"]
        qd::Vec{nm}, [unit = "m/s", description = "Modal velocities"]
        Fq::Vec{nm}, [unit = "N", description = "Modal generalized forces"]
        ck::Vec{nm}, [unit = "N*s/m", description = "Modal damping"]
        # products of the inertia invariants with q and q'
        stq::Vec{3}, [description = "St q"]
        j1q::Vec{6}, [description = "J1 q"]
        exq::Vec{nm}, [description = "Exx q"]
        eyq::Vec{nm}, [description = "Eyy q"]
        ezq::Vec{nm}, [description = "Ezz q"]
        exyq::Vec{nm}, [description = "Exy q"]
        exyt::Vec{nm}, [description = "Exy' q"]
        exzq::Vec{nm}, [description = "Exz q"]
        exzt::Vec{nm}, [description = "Exz' q"]
        eyzq::Vec{nm}, [description = "Eyz q"]
        eyzt::Vec{nm}, [description = "Eyz' q"]
        exyd::Vec{nm}, [description = "Exy q'"]
        exytd::Vec{nm}, [description = "Exy' q'"]
        exzd::Vec{nm}, [description = "Exz q'"]
        exztd::Vec{nm}, [description = "Exz' q'"]
        eyzd::Vec{nm}, [description = "Eyz q'"]
        eyztd::Vec{nm}, [description = "Eyz' q'"]
        U::Vec{6}, [description = "q' E_ab q (xx yy zz xy xz yz)"]
        # stiffening products G q, G q' and quadratic forms q' G q
        gq1::Vec{nm}
        gq2::Vec{nm}
        gq3::Vec{nm}
        gq4::Vec{nm}
        gq5::Vec{nm}
        gq6::Vec{nm}
        gq7::Vec{nm}
        gq8::Vec{nm}
        gq9::Vec{nm}
        gq13::Vec{nm}
        gq14::Vec{nm}
        gq15::Vec{nm}
        gq16::Vec{nm}
        gq17::Vec{nm}
        gq18::Vec{nm}
        gq19::Vec{nm}
        gq20::Vec{nm}
        gq21::Vec{nm}
        sg::Vec{21}, [description = "q' G_c q"]
        spd::Vec{9}, [description = "qd' G_c q of the interface-force cases (minus the rate of the second-order interface position)"]
        kq::Vec{nm}, [unit = "N", description = "kk q"]
        # deflection-dependent inertia
        S::Vec{3}, [unit = "kg*m", description = "First moment of the deformed body in R"]
        Jc::Vec{6}, [unit = "kg*m^2", description = "Inertia of the deformed body (xx yy zz xy xz yz)"]
        C::Mat{nm,6}, [description = "Coupling rows (twist -> modal momenta)"]
        Cm::Mat{nm,6}, [description = "C rows divided by the modal masses"]
        MV::Mat{6,6}, [description = "Frame block of the mass matrix"]
        Mr::Mat{6,6}, [description = "Reduced frame mass matrix M_VV - C' diag(1/mk) C"]
        hr::Vec{6}, [description = "Reduced momentum P - C' (p / mk)"]
        cv::Vec{nm}, [description = "C V"]
        detD::Real, [description = "det of the linear block"]
        X::Mat{3,3}, [description = "Inverse of the linear block"]
        BX::Mat{3,3}, [description = "Coupling block times X"]
        Jr::Mat{3,3}, [description = "Angular Schur complement"]
        detJ::Real, [description = "det of Jr"]
        Y::Mat{3,3}, [description = "Inverse of Jr"]
        hw::Vec{3}, [description = "Angular right-hand side"]
        hv::Vec{3}, [description = "Linear right-hand side"]
        # dT/dq
        ww::Vec{6}, [description = "w_x^2, w_y^2, w_z^2, 2 w_x w_y, 2 w_x w_z, 2 w_y w_z"]
        vw::Vec{3}, [description = "v x w"]
        j1w::Vec{nm}, [description = "J1' ww"]
        stv::Vec{nm}, [description = "St' (v x w)"]
        dT::Vec{nm}, [unit = "N", description = "dT/dq"]
        # interfaces B, C, D (columns / blocks j = 1, 2, 3)
        uP::Vec{12}, [unit = "m", description = "PT q: interface displacements (first order)"]
        udP::Vec{12}, [description = "PT q'"]
        gP::Vec{12}, [unit = "1", description = "1/2 PR q: interface Gibbs vectors"]
        gdP::Vec{12}, [description = "1/2 PR q'"]
        rj::Mat{3,3}, [unit = "m", description = "Interface origins in R (column j)"]
        rdj::Mat{3,3}, [description = "Rate of rj"]
        Dj::Vec{3}, [unit = "1", description = "1 + |g_j|^2"]
        Rg::Mat{3,9}, [unit = "1", description = "Elastic rotation R(g_j) (3x3 blocks)"]
        Rj::Mat{3,9}, [unit = "1", description = "Interface rotation in R, RP_j R(g_j) (3x3 blocks)"]
        wrel::Mat{3,3}, [description = "Relative angular rate of interface j (its frame)"]
        uj::Mat{3,3}, [description = "v + w x r_j + r_j'"]
        eP::Mat{6,3}, [description = "Efforts at the interfaces B, C, D"]
        fP::Mat{6,3}, [description = "Flows at the interfaces B, C, D"]
        FR::Vec{12}, [unit = "N", description = "Interface forces in R (rows 3j+1..3j+3; A rows zero)"]
        TG::Vec{12}, [description = "Gibbs-conjugate interface torques (rows 3j+1..3j+3; A rows zero)"]
        Wj::Mat{6,3}, [description = "Interface wrenches on the frame"]
        ptf::Vec{nm}, [unit = "N", description = "PT' FR"]
        prt::Vec{nm}, [description = "PR' TG"]
        # gravity and poses
        sq::Real, [unit = "1", description = "|gA quaternion|^2"]
        c3::Vec{3}, [unit = "1", description = "World z in R"]
        gv::Vec{3}, [unit = "m/s^2", description = "Gravity in R"]
        stg::Vec{nm}, [description = "St' gv"]
        RA::Mat{3,3}, [unit = "1", description = "World rotation of R"]
        QA::Mat{4,3}, [unit = "1", description = "gA quaternion times the interface's rest orientation"]
    end
    @equations begin
        # ---- damping ----
        for k in 1:nm
            ck[k] ~ 2.0 * zeta * sqrt(kk[k] * mk[k])
            f[k] ~ 0.15915494309189535 * sqrt(kk[k] / mk[k])
        end
        # ---- invariants times q ----
        stq ~ St * q
        j1q ~ J1 * q
        exq ~ Exx * q
        eyq ~ Eyy * q
        ezq ~ Ezz * q
        exyq ~ Exy * q
        exyt ~ transpose(Exy) * q
        exzq ~ Exz * q
        exzt ~ transpose(Exz) * q
        eyzq ~ Eyz * q
        eyzt ~ transpose(Eyz) * q
        exyd ~ Exy * qd
        exytd ~ transpose(Exy) * qd
        exzd ~ Exz * qd
        exztd ~ transpose(Exz) * qd
        eyzd ~ Eyz * qd
        eyztd ~ transpose(Eyz) * qd
        U[1] ~ dot(q, exq)
        U[2] ~ dot(q, eyq)
        U[3] ~ dot(q, ezq)
        U[4] ~ dot(q, exyq)
        U[5] ~ dot(q, exzq)
        U[6] ~ dot(q, eyzq)
        # ---- geometric stiffening (the second-order field), or zero ----
        for s in 1:stiffening
            gq1 ~ Gt1 * q
            gq2 ~ Gt2 * q
            gq3 ~ Gt3 * q
            gq4 ~ Gj1 * q
            gq5 ~ Gj2 * q
            gq6 ~ Gj3 * q
            gq7 ~ Gj4 * q
            gq8 ~ Gj5 * q
            gq9 ~ Gj6 * q
            gq13 ~ Gb1 * q
            gq14 ~ Gb2 * q
            gq15 ~ Gb3 * q
            gq16 ~ Gc1 * q
            gq17 ~ Gc2 * q
            gq18 ~ Gc3 * q
            gq19 ~ Gd1 * q
            gq20 ~ Gd2 * q
            gq21 ~ Gd3 * q
            sg[1] ~ dot(q, gq1)
            sg[2] ~ dot(q, gq2)
            sg[3] ~ dot(q, gq3)
            sg[4] ~ dot(q, gq4)
            sg[5] ~ dot(q, gq5)
            sg[6] ~ dot(q, gq6)
            sg[7] ~ dot(q, gq7)
            sg[8] ~ dot(q, gq8)
            sg[9] ~ dot(q, gq9)
            sg[10] ~ 0.0               # the rotational-acceleration cases are not used (see the header)
            sg[11] ~ 0.0
            sg[12] ~ 0.0
            sg[13] ~ dot(q, gq13)
            sg[14] ~ dot(q, gq14)
            sg[15] ~ dot(q, gq15)
            sg[16] ~ dot(q, gq16)
            sg[17] ~ dot(q, gq17)
            sg[18] ~ dot(q, gq18)
            sg[19] ~ dot(q, gq19)
            sg[20] ~ dot(q, gq20)
            sg[21] ~ dot(q, gq21)
            spd[1] ~ dot(qd, gq13)
            spd[2] ~ dot(qd, gq14)
            spd[3] ~ dot(qd, gq15)
            spd[4] ~ dot(qd, gq16)
            spd[5] ~ dot(qd, gq17)
            spd[6] ~ dot(qd, gq18)
            spd[7] ~ dot(qd, gq19)
            spd[8] ~ dot(qd, gq20)
            spd[9] ~ dot(qd, gq21)
        end
        for s in 1:(1 - stiffening)
            for k in 1:nm
                gq1[k] ~ 0.0
                gq2[k] ~ 0.0
                gq3[k] ~ 0.0
                gq4[k] ~ 0.0
                gq5[k] ~ 0.0
                gq6[k] ~ 0.0
                gq7[k] ~ 0.0
                gq8[k] ~ 0.0
                gq9[k] ~ 0.0
                gq13[k] ~ 0.0
                gq14[k] ~ 0.0
                gq15[k] ~ 0.0
                gq16[k] ~ 0.0
                gq17[k] ~ 0.0
                gq18[k] ~ 0.0
                gq19[k] ~ 0.0
                gq20[k] ~ 0.0
                gq21[k] ~ 0.0
            end
            for c in 1:21
                sg[c] ~ 0.0
            end
            for c in 1:9
                spd[c] ~ 0.0
            end
        end
        # ---- first moment and inertia of the deformed body ----
        for a in 1:3
            S[a] ~ S0[a] + stq[a] - 0.5 * sg[a]
        end
        Jc[1] ~ J0[1, 1] + j1q[1] + U[2] + U[3] - 0.5 * sg[4]
        Jc[2] ~ J0[2, 2] + j1q[2] + U[1] + U[3] - 0.5 * sg[5]
        Jc[3] ~ J0[3, 3] + j1q[3] + U[1] + U[2] - 0.5 * sg[6]
        Jc[4] ~ J0[1, 2] + j1q[4] - U[4] - 0.5 * sg[7]
        Jc[5] ~ J0[1, 3] + j1q[5] - U[5] - 0.5 * sg[8]
        Jc[6] ~ J0[2, 3] + j1q[6] - U[6] - 0.5 * sg[9]
        # ---- coupling rows C_k = [rotation; translation] (first-order field only, see the header) ----
        for k in 1:nm
            C[k, 1] ~ Sr[1, k] - (eyzq[k] - eyzt[k])
            C[k, 2] ~ Sr[2, k] - (exzt[k] - exzq[k])
            C[k, 3] ~ Sr[3, k] - (exyq[k] - exyt[k])
            C[k, 4] ~ St[1, k]
            C[k, 5] ~ St[2, k]
            C[k, 6] ~ St[3, k]
            for i in 1:6
                Cm[k, i] ~ C[k, i] / mk[k]
            end
        end
        # ---- frame block of the mass matrix [J, [S x]; [S x]', m I] ----
        MV[1, 1] ~ Jc[1]
        MV[2, 2] ~ Jc[2]
        MV[3, 3] ~ Jc[3]
        MV[1, 2] ~ Jc[4]
        MV[2, 1] ~ Jc[4]
        MV[1, 3] ~ Jc[5]
        MV[3, 1] ~ Jc[5]
        MV[2, 3] ~ Jc[6]
        MV[3, 2] ~ Jc[6]
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
        MV[4, 4] ~ mass
        MV[4, 5] ~ 0.0
        MV[4, 6] ~ 0.0
        MV[5, 4] ~ 0.0
        MV[5, 5] ~ mass
        MV[5, 6] ~ 0.0
        MV[6, 4] ~ 0.0
        MV[6, 5] ~ 0.0
        MV[6, 6] ~ mass
        # ---- frame twist from the momenta: (M_VV - C' M_e^-1 C) V = P - C' M_e^-1 p ----
        Mr ~ MV - transpose(C) * Cm
        hr ~ P - transpose(Cm) * p
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
        # angular Schur complement Jr = Mr_ww - B X B', B = Mr[1:3, 4:6]
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
        # modal velocities q' = (p - C V) / mk
        cv ~ C * V
        for k in 1:nm
            qd[k] ~ (p[k] - cv[k]) / mk[k]
        end
        # ---- dT/dq ----
        ww[1] ~ V[1] * V[1]
        ww[2] ~ V[2] * V[2]
        ww[3] ~ V[3] * V[3]
        ww[4] ~ 2.0 * V[1] * V[2]
        ww[5] ~ 2.0 * V[1] * V[3]
        ww[6] ~ 2.0 * V[2] * V[3]
        vw[1] ~ V[5] * V[3] - V[6] * V[2]
        vw[2] ~ V[6] * V[1] - V[4] * V[3]
        vw[3] ~ V[4] * V[2] - V[5] * V[1]
        j1w ~ transpose(J1) * ww
        stv ~ transpose(St) * vw
        for k in 1:nm
            dT[k] ~ 0.5 * j1w[k] +
                    (eyq[k] + ezq[k]) * ww[1] + (exq[k] + ezq[k]) * ww[2] + (exq[k] + eyq[k]) * ww[3] -
                    0.5 * ((exyq[k] + exyt[k]) * ww[4] + (exzq[k] + exzt[k]) * ww[5] + (eyzq[k] + eyzt[k]) * ww[6]) -
                    0.5 * (gq4[k] * ww[1] + gq5[k] * ww[2] + gq6[k] * ww[3] + gq7[k] * ww[4] + gq8[k] * ww[5] + gq9[k] * ww[6]) +
                    stv[k] - (gq1[k] * vw[1] + gq2[k] * vw[2] + gq3[k] * vw[3]) +
                    V[1] * (eyzd[k] - eyztd[k]) + V[2] * (exztd[k] - exzd[k]) + V[3] * (exyd[k] - exytd[k])
        end
        # ---- interfaces B, C, D (j = 1, 2, 3): position, rotation, flows, efforts ----
        uP ~ PT * q
        udP ~ PT * qd
        gP ~ 0.5 * (PR * q)
        gdP ~ 0.5 * (PR * qd)
        for j in 1:3
            for a in 1:3
                rj[a, j] ~ XP[a, j + 1] + uP[3 * j + a] - 0.5 * sg[12 + 3 * (j - 1) + a]
                rdj[a, j] ~ udP[3 * j + a] - spd[3 * (j - 1) + a]
            end
            Dj[j] ~ 1.0 + gP[3 * j + 1] * gP[3 * j + 1] + gP[3 * j + 2] * gP[3 * j + 2] + gP[3 * j + 3] * gP[3 * j + 3]
            Rg[1, 3 * j - 2] ~ (1.0 + gP[3 * j + 1] * gP[3 * j + 1] - gP[3 * j + 2] * gP[3 * j + 2] - gP[3 * j + 3] * gP[3 * j + 3]) / Dj[j]
            Rg[1, 3 * j - 1] ~ 2.0 * (gP[3 * j + 1] * gP[3 * j + 2] - gP[3 * j + 3]) / Dj[j]
            Rg[1, 3 * j] ~ 2.0 * (gP[3 * j + 1] * gP[3 * j + 3] + gP[3 * j + 2]) / Dj[j]
            Rg[2, 3 * j - 2] ~ 2.0 * (gP[3 * j + 1] * gP[3 * j + 2] + gP[3 * j + 3]) / Dj[j]
            Rg[2, 3 * j - 1] ~ (1.0 - gP[3 * j + 1] * gP[3 * j + 1] + gP[3 * j + 2] * gP[3 * j + 2] - gP[3 * j + 3] * gP[3 * j + 3]) / Dj[j]
            Rg[2, 3 * j] ~ 2.0 * (gP[3 * j + 2] * gP[3 * j + 3] - gP[3 * j + 1]) / Dj[j]
            Rg[3, 3 * j - 2] ~ 2.0 * (gP[3 * j + 1] * gP[3 * j + 3] - gP[3 * j + 2]) / Dj[j]
            Rg[3, 3 * j - 1] ~ 2.0 * (gP[3 * j + 2] * gP[3 * j + 3] + gP[3 * j + 1]) / Dj[j]
            Rg[3, 3 * j] ~ (1.0 - gP[3 * j + 1] * gP[3 * j + 1] - gP[3 * j + 2] * gP[3 * j + 2] + gP[3 * j + 3] * gP[3 * j + 3]) / Dj[j]
            for a in 1:3
                for b in 1:3
                    Rj[a, 3 * (j - 1) + b] ~ RP[a, 3 * j + 1] * Rg[1, 3 * (j - 1) + b] +
                                             RP[a, 3 * j + 2] * Rg[2, 3 * (j - 1) + b] +
                                             RP[a, 3 * j + 3] * Rg[3, 3 * (j - 1) + b]
                end
            end
            # relative angular rate of the interface frame, in its own coordinates: 2/D (g' - g x g')
            wrel[1, j] ~ 2.0 / Dj[j] * (gdP[3 * j + 1] - (gP[3 * j + 2] * gdP[3 * j + 3] - gP[3 * j + 3] * gdP[3 * j + 2]))
            wrel[2, j] ~ 2.0 / Dj[j] * (gdP[3 * j + 2] - (gP[3 * j + 3] * gdP[3 * j + 1] - gP[3 * j + 1] * gdP[3 * j + 3]))
            wrel[3, j] ~ 2.0 / Dj[j] * (gdP[3 * j + 3] - (gP[3 * j + 1] * gdP[3 * j + 2] - gP[3 * j + 2] * gdP[3 * j + 1]))
            # velocity of the interface origin in R: v + w x r + r'
            uj[1, j] ~ V[4] + V[2] * rj[3, j] - V[3] * rj[2, j] + rdj[1, j]
            uj[2, j] ~ V[5] + V[3] * rj[1, j] - V[1] * rj[3, j] + rdj[2, j]
            uj[3, j] ~ V[6] + V[1] * rj[2, j] - V[2] * rj[1, j] + rdj[3, j]
            # flows [R' w + w_rel; R' u], efforts through the transpose
            for i in 1:3
                fP[i, j] ~ Rj[1, 3 * (j - 1) + i] * V[1] + Rj[2, 3 * (j - 1) + i] * V[2] + Rj[3, 3 * (j - 1) + i] * V[3] + wrel[i, j]
                fP[3 + i, j] ~ Rj[1, 3 * (j - 1) + i] * uj[1, j] + Rj[2, 3 * (j - 1) + i] * uj[2, j] + Rj[3, 3 * (j - 1) + i] * uj[3, j]
                FR[3 * j + i] ~ Rj[i, 3 * (j - 1) + 1] * eP[4, j] + Rj[i, 3 * (j - 1) + 2] * eP[5, j] + Rj[i, 3 * (j - 1) + 3] * eP[6, j]
            end
            TG[3 * j + 1] ~ 2.0 / Dj[j] * (eP[1, j] + gP[3 * j + 2] * eP[3, j] - gP[3 * j + 3] * eP[2, j])
            TG[3 * j + 2] ~ 2.0 / Dj[j] * (eP[2, j] + gP[3 * j + 3] * eP[1, j] - gP[3 * j + 1] * eP[3, j])
            TG[3 * j + 3] ~ 2.0 / Dj[j] * (eP[3, j] + gP[3 * j + 1] * eP[2, j] - gP[3 * j + 2] * eP[1, j])
            Wj[1, j] ~ Rj[1, 3 * j - 2] * eP[1, j] + Rj[1, 3 * j - 1] * eP[2, j] + Rj[1, 3 * j] * eP[3, j] +
                       rj[2, j] * FR[3 * j + 3] - rj[3, j] * FR[3 * j + 2]
            Wj[2, j] ~ Rj[2, 3 * j - 2] * eP[1, j] + Rj[2, 3 * j - 1] * eP[2, j] + Rj[2, 3 * j] * eP[3, j] +
                       rj[3, j] * FR[3 * j + 1] - rj[1, j] * FR[3 * j + 3]
            Wj[3, j] ~ Rj[3, 3 * j - 2] * eP[1, j] + Rj[3, 3 * j - 1] * eP[2, j] + Rj[3, 3 * j] * eP[3, j] +
                       rj[1, j] * FR[3 * j + 2] - rj[2, j] * FR[3 * j + 1]
            for a in 1:3
                Wj[3 + a, j] ~ FR[3 * j + a]
            end
        end
        for a in 1:3
            FR[a] ~ 0.0
            TG[a] ~ 0.0
        end
        ptf ~ transpose(PT) * FR
        prt ~ transpose(PR) * TG
        for i in 1:6
            pa.f[i] ~ V[i]
            eP[i, 1] ~ pb.e[i]
            eP[i, 2] ~ pc.e[i]
            eP[i, 3] ~ pd.e[i]
            pb.f[i] ~ fP[i, 1]
            pc.f[i] ~ fP[i, 2]
            pd.f[i] ~ fP[i, 3]
        end
        # ---- rail (port pe at sr, slide ps), or zero ----
        for rr in 1:nr
            sr ~ s0 + int(sdr, 0.0)
            sdr ~ psl / ms
            ddt(psl) ~ ps.e + FsE
            ps.f ~ sdr
            xr ~ 2.0 * sr / RL - 1.0
            Tr[1] ~ 1.0
            Tr[2] ~ xr
            dTr[1] ~ 0.0
            dTr[2] ~ 2.0 / RL
            for n in 3:nc
                Tr[n] ~ 2.0 * xr * Tr[n - 1] - Tr[n - 2]
                dTr[n] ~ 4.0 / RL * Tr[n - 1] + 2.0 * xr * dTr[n - 1] - dTr[n - 2]
            end
            pt1 ~ CT1 * Tr
            pt2 ~ CT2 * Tr
            pt3 ~ CT3 * Tr
            pr1 ~ CR1 * Tr
            pr2 ~ CR2 * Tr
            pr3 ~ CR3 * Tr
            dpt1 ~ CT1 * dTr
            dpt2 ~ CT2 * dTr
            dpt3 ~ CT3 * dTr
            dpr1 ~ CR1 * dTr
            dpr2 ~ CR2 * dTr
            dpr3 ~ CR3 * dTr
            uE[1] ~ dot(pt1, q)
            uE[2] ~ dot(pt2, q)
            uE[3] ~ dot(pt3, q)
            usE[1] ~ dot(dpt1, q)
            usE[2] ~ dot(dpt2, q)
            usE[3] ~ dot(dpt3, q)
            gE[1] ~ 0.5 * dot(pr1, q)
            gE[2] ~ 0.5 * dot(pr2, q)
            gE[3] ~ 0.5 * dot(pr3, q)
            gsE[1] ~ 0.5 * dot(dpr1, q)
            gsE[2] ~ 0.5 * dot(dpr2, q)
            gsE[3] ~ 0.5 * dot(dpr3, q)
            gdE[1] ~ 0.5 * dot(pr1, qd) + gsE[1] * sdr
            gdE[2] ~ 0.5 * dot(pr2, qd) + gsE[2] * sdr
            gdE[3] ~ 0.5 * dot(pr3, qd) + gsE[3] * sdr
            for a in 1:3
                rE[a] ~ XR[a] + sr * RR[a, 3] + uE[a]
            end
            # the frame rides the deformed rail: r' = PT q' + (t + dPT/ds q) s'
            rdE[1] ~ dot(pt1, qd) + (RR[1, 3] + usE[1]) * sdr
            rdE[2] ~ dot(pt2, qd) + (RR[2, 3] + usE[2]) * sdr
            rdE[3] ~ dot(pt3, qd) + (RR[3, 3] + usE[3]) * sdr
            DE ~ 1.0 + gE[1] * gE[1] + gE[2] * gE[2] + gE[3] * gE[3]
            RgE[1, 1] ~ (1.0 + gE[1] * gE[1] - gE[2] * gE[2] - gE[3] * gE[3]) / DE
            RgE[1, 2] ~ 2.0 * (gE[1] * gE[2] - gE[3]) / DE
            RgE[1, 3] ~ 2.0 * (gE[1] * gE[3] + gE[2]) / DE
            RgE[2, 1] ~ 2.0 * (gE[1] * gE[2] + gE[3]) / DE
            RgE[2, 2] ~ (1.0 - gE[1] * gE[1] + gE[2] * gE[2] - gE[3] * gE[3]) / DE
            RgE[2, 3] ~ 2.0 * (gE[2] * gE[3] - gE[1]) / DE
            RgE[3, 1] ~ 2.0 * (gE[1] * gE[3] - gE[2]) / DE
            RgE[3, 2] ~ 2.0 * (gE[2] * gE[3] + gE[1]) / DE
            RgE[3, 3] ~ (1.0 - gE[1] * gE[1] - gE[2] * gE[2] + gE[3] * gE[3]) / DE
            RE ~ RR * RgE
            wE[1] ~ 2.0 / DE * (gdE[1] - (gE[2] * gdE[3] - gE[3] * gdE[2]))
            wE[2] ~ 2.0 / DE * (gdE[2] - (gE[3] * gdE[1] - gE[1] * gdE[3]))
            wE[3] ~ 2.0 / DE * (gdE[3] - (gE[1] * gdE[2] - gE[2] * gdE[1]))
            vE[1] ~ V[4] + V[2] * rE[3] - V[3] * rE[2] + rdE[1]
            vE[2] ~ V[5] + V[3] * rE[1] - V[1] * rE[3] + rdE[2]
            vE[3] ~ V[6] + V[1] * rE[2] - V[2] * rE[1] + rdE[3]
            for i in 1:3
                pe.f[i] ~ RE[1, i] * V[1] + RE[2, i] * V[2] + RE[3, i] * V[3] + wE[i]
                pe.f[3 + i] ~ RE[1, i] * vE[1] + RE[2, i] * vE[2] + RE[3, i] * vE[3]
                FE[i] ~ RE[i, 1] * pe.e[4] + RE[i, 2] * pe.e[5] + RE[i, 3] * pe.e[6]
            end
            TGE[1] ~ 2.0 / DE * (pe.e[1] + gE[2] * pe.e[3] - gE[3] * pe.e[2])
            TGE[2] ~ 2.0 / DE * (pe.e[2] + gE[3] * pe.e[1] - gE[1] * pe.e[3])
            TGE[3] ~ 2.0 / DE * (pe.e[3] + gE[1] * pe.e[2] - gE[2] * pe.e[1])
            WE[1] ~ RE[1, 1] * pe.e[1] + RE[1, 2] * pe.e[2] + RE[1, 3] * pe.e[3] + rE[2] * FE[3] - rE[3] * FE[2]
            WE[2] ~ RE[2, 1] * pe.e[1] + RE[2, 2] * pe.e[2] + RE[2, 3] * pe.e[3] + rE[3] * FE[1] - rE[1] * FE[3]
            WE[3] ~ RE[3, 1] * pe.e[1] + RE[3, 2] * pe.e[2] + RE[3, 3] * pe.e[3] + rE[1] * FE[2] - rE[2] * FE[1]
            for a in 1:3
                WE[3 + a] ~ FE[a]
            end
            for k in 1:nm
                QE[k] ~ pt1[k] * FE[1] + pt2[k] * FE[2] + pt3[k] * FE[3] +
                        0.5 * (pr1[k] * TGE[1] + pr2[k] * TGE[2] + pr3[k] * TGE[3])
            end
            FsE ~ (RR[1, 3] + usE[1]) * FE[1] + (RR[2, 3] + usE[2]) * FE[2] + (RR[3, 3] + usE[3]) * FE[3] +
                  gsE[1] * TGE[1] + gsE[2] * TGE[2] + gsE[3] * TGE[3]
            QAE[1] ~ gA[1] * QR[1] - gA[2] * QR[2] - gA[3] * QR[3] - gA[4] * QR[4]
            QAE[2] ~ gA[1] * QR[2] + gA[2] * QR[1] + gA[3] * QR[4] - gA[4] * QR[3]
            QAE[3] ~ gA[1] * QR[3] - gA[2] * QR[4] + gA[3] * QR[1] + gA[4] * QR[2]
            QAE[4] ~ gA[1] * QR[4] + gA[2] * QR[3] - gA[3] * QR[2] + gA[4] * QR[1]
            poseE[1] ~ (QAE[1] - QAE[2] * gE[1] - QAE[3] * gE[2] - QAE[4] * gE[3]) / sqrt(DE)
            poseE[2] ~ (QAE[2] + QAE[1] * gE[1] + QAE[3] * gE[3] - QAE[4] * gE[2]) / sqrt(DE)
            poseE[3] ~ (QAE[3] + QAE[1] * gE[2] - QAE[2] * gE[3] + QAE[4] * gE[1]) / sqrt(DE)
            poseE[4] ~ (QAE[4] + QAE[1] * gE[3] + QAE[2] * gE[2] - QAE[3] * gE[1]) / sqrt(DE)
            for i in 1:3
                poseE[4 + i] ~ gA[4 + i] + RA[i, 1] * rE[1] + RA[i, 2] * rE[2] + RA[i, 3] * rE[3]
            end
        end
        for rr in 1:(1 - nr)
            sr ~ 0.0
            psl ~ 0.0
            sdr ~ 0.0
            ps.f ~ 0.0
            xr ~ 0.0
            for n in 1:nc
                Tr[n] ~ 0.0
                dTr[n] ~ 0.0
            end
            for k in 1:nm
                pt1[k] ~ 0.0
                pt2[k] ~ 0.0
                pt3[k] ~ 0.0
                pr1[k] ~ 0.0
                pr2[k] ~ 0.0
                pr3[k] ~ 0.0
                dpt1[k] ~ 0.0
                dpt2[k] ~ 0.0
                dpt3[k] ~ 0.0
                dpr1[k] ~ 0.0
                dpr2[k] ~ 0.0
                dpr3[k] ~ 0.0
                QE[k] ~ 0.0
            end
            for a in 1:3
                uE[a] ~ 0.0
                usE[a] ~ 0.0
                rE[a] ~ 0.0
                rdE[a] ~ 0.0
                gE[a] ~ 0.0
                gsE[a] ~ 0.0
                gdE[a] ~ 0.0
                wE[a] ~ 0.0
                vE[a] ~ 0.0
                FE[a] ~ 0.0
                TGE[a] ~ 0.0
                for b in 1:3
                    RgE[a, b] ~ 0.0
                    RE[a, b] ~ 0.0
                end
            end
            DE ~ 1.0
            FsE ~ 0.0
            for i in 1:6
                pe.f[i] ~ 0.0
                WE[i] ~ 0.0
            end
            for i in 1:4
                QAE[i] ~ 0.0
            end
            for i in 1:7
                poseE[i] ~ gA[i]
            end
        end
        # ---- gravity: world z in R (gA is the world pose of R) ----
        sq ~ gA[1] * gA[1] + gA[2] * gA[2] + gA[3] * gA[3] + gA[4] * gA[4]
        c3[1] ~ 2.0 * (gA[2] * gA[4] - gA[1] * gA[3]) / sq
        c3[2] ~ 2.0 * (gA[3] * gA[4] + gA[1] * gA[2]) / sq
        c3[3] ~ (gA[1] * gA[1] - gA[2] * gA[2] - gA[3] * gA[3] + gA[4] * gA[4]) / sq
        for i in 1:3
            gv[i] ~ -g0 * c3[i]
        end
        stg ~ transpose(St) * gv
        # ---- frame momentum: P' = ad(V)' P + wrenches (Euler-Poincare) ----
        ddt(P[1]) ~ P[2] * V[3] - P[3] * V[2] + P[5] * V[6] - P[6] * V[5] + pa.e[1] + Wj[1, 1] + Wj[1, 2] + Wj[1, 3] + WE[1] + S[2] * gv[3] - S[3] * gv[2]
        ddt(P[2]) ~ P[3] * V[1] - P[1] * V[3] + P[6] * V[4] - P[4] * V[6] + pa.e[2] + Wj[2, 1] + Wj[2, 2] + Wj[2, 3] + WE[2] + S[3] * gv[1] - S[1] * gv[3]
        ddt(P[3]) ~ P[1] * V[2] - P[2] * V[1] + P[4] * V[5] - P[5] * V[4] + pa.e[3] + Wj[3, 1] + Wj[3, 2] + Wj[3, 3] + WE[3] + S[1] * gv[2] - S[2] * gv[1]
        ddt(P[4]) ~ P[5] * V[3] - P[6] * V[2] + pa.e[4] + Wj[4, 1] + Wj[4, 2] + Wj[4, 3] + WE[4] + mass * gv[1]
        ddt(P[5]) ~ P[6] * V[1] - P[4] * V[3] + pa.e[5] + Wj[5, 1] + Wj[5, 2] + Wj[5, 3] + WE[5] + mass * gv[2]
        ddt(P[6]) ~ P[4] * V[2] - P[5] * V[1] + pa.e[6] + Wj[6, 1] + Wj[6, 2] + Wj[6, 3] + WE[6] + mass * gv[3]
        # ---- modal momenta: p' = dT/dq - kk q - ck q' + interface and gravity forces ----
        for k in 1:nm
            kq[k] ~ kk[k] * q[k]
            Fq[k] ~ dT[k] - kq[k] - ck[k] * qd[k] + ptf[k] + 0.5 * prt[k] + QE[k] -
                    (gq13[k] * FR[4] + gq14[k] * FR[5] + gq15[k] * FR[6] +
                     gq16[k] * FR[7] + gq17[k] * FR[8] + gq18[k] * FR[9] +
                     gq19[k] * FR[10] + gq20[k] * FR[11] + gq21[k] * FR[12]) +
                    stg[k] - (gq1[k] * gv[1] + gq2[k] * gv[2] + gq3[k] * gv[3])
            ddt(q[k]) ~ qd[k]
            ddt(p[k]) ~ Fq[k]
        end
        # ---- poses: R is the world pose gA; interface j = gA (x) QP_j (x) (1, g_j)/sqrt(D) ----
        RA[1, 1] ~ (gA[1] * gA[1] + gA[2] * gA[2] - gA[3] * gA[3] - gA[4] * gA[4]) / sq
        RA[1, 2] ~ 2.0 * (gA[2] * gA[3] - gA[1] * gA[4]) / sq
        RA[1, 3] ~ 2.0 * (gA[2] * gA[4] + gA[1] * gA[3]) / sq
        RA[2, 1] ~ 2.0 * (gA[2] * gA[3] + gA[1] * gA[4]) / sq
        RA[2, 2] ~ (gA[1] * gA[1] - gA[2] * gA[2] + gA[3] * gA[3] - gA[4] * gA[4]) / sq
        RA[2, 3] ~ 2.0 * (gA[3] * gA[4] - gA[1] * gA[2]) / sq
        RA[3, 1] ~ 2.0 * (gA[2] * gA[4] - gA[1] * gA[3]) / sq
        RA[3, 2] ~ 2.0 * (gA[3] * gA[4] + gA[1] * gA[2]) / sq
        RA[3, 3] ~ (gA[1] * gA[1] - gA[2] * gA[2] - gA[3] * gA[3] + gA[4] * gA[4]) / sq
        for j in 1:3
            QA[1, j] ~ gA[1] * QP[1, j + 1] - gA[2] * QP[2, j + 1] - gA[3] * QP[3, j + 1] - gA[4] * QP[4, j + 1]
            QA[2, j] ~ gA[1] * QP[2, j + 1] + gA[2] * QP[1, j + 1] + gA[3] * QP[4, j + 1] - gA[4] * QP[3, j + 1]
            QA[3, j] ~ gA[1] * QP[3, j + 1] - gA[2] * QP[4, j + 1] + gA[3] * QP[1, j + 1] + gA[4] * QP[2, j + 1]
            QA[4, j] ~ gA[1] * QP[4, j + 1] + gA[2] * QP[3, j + 1] - gA[3] * QP[2, j + 1] + gA[4] * QP[1, j + 1]
        end
        for i in 1:7
            pose[i] ~ gA[i]
        end
        poseB[1] ~ (QA[1, 1] - QA[2, 1] * gP[4] - QA[3, 1] * gP[5] - QA[4, 1] * gP[6]) / sqrt(Dj[1])
        poseB[2] ~ (QA[2, 1] + QA[1, 1] * gP[4] + QA[3, 1] * gP[6] - QA[4, 1] * gP[5]) / sqrt(Dj[1])
        poseB[3] ~ (QA[3, 1] + QA[1, 1] * gP[5] - QA[2, 1] * gP[6] + QA[4, 1] * gP[4]) / sqrt(Dj[1])
        poseB[4] ~ (QA[4, 1] + QA[1, 1] * gP[6] + QA[2, 1] * gP[5] - QA[3, 1] * gP[4]) / sqrt(Dj[1])
        poseC[1] ~ (QA[1, 2] - QA[2, 2] * gP[7] - QA[3, 2] * gP[8] - QA[4, 2] * gP[9]) / sqrt(Dj[2])
        poseC[2] ~ (QA[2, 2] + QA[1, 2] * gP[7] + QA[3, 2] * gP[9] - QA[4, 2] * gP[8]) / sqrt(Dj[2])
        poseC[3] ~ (QA[3, 2] + QA[1, 2] * gP[8] - QA[2, 2] * gP[9] + QA[4, 2] * gP[7]) / sqrt(Dj[2])
        poseC[4] ~ (QA[4, 2] + QA[1, 2] * gP[9] + QA[2, 2] * gP[8] - QA[3, 2] * gP[7]) / sqrt(Dj[2])
        poseD[1] ~ (QA[1, 3] - QA[2, 3] * gP[10] - QA[3, 3] * gP[11] - QA[4, 3] * gP[12]) / sqrt(Dj[3])
        poseD[2] ~ (QA[2, 3] + QA[1, 3] * gP[10] + QA[3, 3] * gP[12] - QA[4, 3] * gP[11]) / sqrt(Dj[3])
        poseD[3] ~ (QA[3, 3] + QA[1, 3] * gP[11] - QA[2, 3] * gP[12] + QA[4, 3] * gP[10]) / sqrt(Dj[3])
        poseD[4] ~ (QA[4, 3] + QA[1, 3] * gP[12] + QA[2, 3] * gP[11] - QA[3, 3] * gP[10]) / sqrt(Dj[3])
        for i in 1:3
            poseB[4 + i] ~ gA[4 + i] + RA[i, 1] * rj[1, 1] + RA[i, 2] * rj[2, 1] + RA[i, 3] * rj[3, 1]
            poseC[4 + i] ~ gA[4 + i] + RA[i, 1] * rj[1, 2] + RA[i, 2] * rj[2, 2] + RA[i, 3] * rj[3, 2]
            poseD[4 + i] ~ gA[4 + i] + RA[i, 1] * rj[1, 3] + RA[i, 2] * rj[2, 3] + RA[i, 3] * rj[3, 3]
        end
        # ---- taps and energies ----
        for k in 1:nm
            eta[k] ~ q[k]
        end
        Ek ~ 0.5 * (dot(P, V) + dot(p, qd) + psl * sdr)
        s ~ sr
        sd ~ sdr
        Ee ~ 0.5 * dot(q, kq)
        Eg ~ g0 * (mass * gA[7] + RA[3, 1] * S[1] + RA[3, 2] * S[2] + RA[3, 3] * S[3])
    end
    @causality begin
        pa => :flow_out
        pb => :flow_out
        pc => :flow_out
        pd => :flow_out
        pe => :flow_out
        ps => :flow_out
    end
end
