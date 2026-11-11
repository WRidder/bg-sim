@block ModalBody3D begin
    # A flexible body reduced from a finite element model of an arbitrary part (Craig–Bampton,
    # julia/BGSimFEM). It replaces a `RigidBody3D`: the part's own mass and inertia are in it.
    # The node names the reduced-model file in its settings (`file`, project-relative, e.g.
    # `data/bracket.modal.json`); the compiler reads the file and sets every constant below
    # from it (the defaults are a two-mode placeholder). The physics and the equations are in
    # `ModalBodyCore3D`; this composite gives each interface its own 1-junction, so the
    # interfaces bond like body ports and an interface the part does not use may stay open.
    #
    #   A (1-junction) ── core.pa   core.pb ── B   core.pc ── C   core.pd ── D
    #                       gA ──► gravity, pose, poseB, poseC, poseD
    #
    # Frames: A is the reference frame R (the frame of the first interface of the reduced
    # model, clamped in the Craig–Bampton basis); B, C, D are the further interfaces in the
    # order of the file. `gA` is the world pose of A (from the joint chain); `pose` is the world
    # pose of R (the frame the viewer deforms the part's mesh in, with the mode shapes of the
    # GLB that the reduction wrote); `poseB`..`poseD` are the world poses of the deformed
    # interfaces (compose the next link from them). `eta` are the modal coordinates (m, the
    # signals of a `mode-shapes` binding), `f` the modal frequencies with A clamped (Hz).
    #
    # Stress (`ModalStress3D`, from the file's `stress` points): `sigma_vm[1..nh]` is the von
    # Mises stress at the hotspots named in the part spec and `sigma_max` the largest von Mises
    # over the hotspots and the peak candidates, an estimate of the peak over the part (Pa).
    # The six components superpose linearly over the modes; rigid motion gives no stress. A
    # file without stress points reads 0 there.
    #
    # Rail (the file's `rail`, a moving interface along a straight line on the part, e.g. the
    # linear guide of a gantry beam): port E is the frame of the guide block at the position
    # `s` on the deformed rail (z along the rail; `poseE` its world pose), port S the slide
    # (Translation: the drive force in, s' out) of a slider of mass `ms` that starts at `s0`.
    # Mount the carriage on E through a joint that slides along z (Prismatic3D whose drive is
    # held by a stiff spring: the drive stiffness), and drive S. Without a rail, E and S carry
    # no flow; leave them open.
    @constants begin
        nm::Int = 2, [min = 1, max = 48, description = "Number of modal coordinates (from the reduced-model file)"]
        stiffening::Int = 1, [options = ["off", "on"], description = "Geometric stiffening terms: 0 off, 1 on (when the file has them)"]
        ns::Int = 1, [min = 1, max = 64, description = "Number of stress points (from the reduced-model file)"]
        nh::Int = 1, [min = 1, max = 64, description = "Number of hotspots among them"]
        nr::Int = 0, [options = ["none", "rail"], description = "1 when the file has a rail (ports E and S)"]
        nc::Int = 2, [min = 2, max = 32, description = "Chebyshev terms of the rail tables"]
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
        Sxx::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xx per unit modal coordinate at the stress points"]
        Syy::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress yy per unit modal coordinate"]
        Szz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress zz per unit modal coordinate"]
        Sxy::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xy per unit modal coordinate"]
        Sxz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xz per unit modal coordinate"]
        Syz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress yz per unit modal coordinate"]
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
        A::Power{Spatial}, [frame = "body"]
        B::Power{Spatial}, [frame = "body"]
        C::Power{Spatial}, [frame = "body"]
        D::Power{Spatial}, [frame = "body"]
        E::Power{Spatial}, [frame = "body"]
        S::Power{Translation}
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
        sigma_vm::Vec{nh}, [unit = "Pa"]
        sigma_max::Real, [unit = "Pa"]
    end
    @parameters begin
        zeta::Real = 0.01, [unit = "1", min = 0, description = "Modal damping ratio (every mode)"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration (world -z)"]
        ms::Real = 0.5, [unit = "kg", min = 1.0e-6, description = "Rail slider mass (the drive's moving part along the rail)"]
        s0::Real = 0.0, [unit = "m", description = "Initial rail position (from the rail start)"]
    end
    @components begin
        nodeA = Junction(1)
        nodeB = Junction(1)
        nodeC = Junction(1)
        nodeD = Junction(1)
        nodeE = Junction(1)
        nodeS = Junction(1)
        core = ModalBodyCore3D(nm = nm, stiffening = stiffening, mass = mass, S0 = S0,
            J0 = J0, mk = mk, kk = kk, St = St, Sr = Sr, J1 = J1, Exx = Exx, Eyy = Eyy, Ezz = Ezz,
            Exy = Exy, Exz = Exz, Eyz = Eyz, XP = XP, QP = QP, RP = RP, PT = PT, PR = PR, Gt1 = Gt1,
            Gt2 = Gt2, Gt3 = Gt3, Gj1 = Gj1, Gj2 = Gj2, Gj3 = Gj3, Gj4 = Gj4, Gj5 = Gj5, Gj6 = Gj6,
            Gb1 = Gb1, Gb2 = Gb2, Gb3 = Gb3, Gc1 = Gc1, Gc2 = Gc2,
            Gc3 = Gc3, Gd1 = Gd1, Gd2 = Gd2, Gd3 = Gd3,
            nr = nr, nc = nc, RL = RL, XR = XR, RR = RR, QR = QR, CT1 = CT1, CT2 = CT2, CT3 = CT3,
            CR1 = CR1, CR2 = CR2, CR3 = CR3,
            zeta = zeta, g0 = g0, ms = ms, s0 = s0)
        stress = ModalStress3D(nm = nm, ns = ns, nh = nh, Sxx = Sxx, Syy = Syy, Szz = Szz,
            Sxy = Sxy, Sxz = Sxz, Syz = Syz)
    end
    @observables begin
        pose = core.pose
        poseB = core.poseB
        poseC = core.poseC
        poseD = core.poseD
        poseE = core.poseE
        s = core.s
        sd = core.sd
        V = core.V
        eta = core.eta
        f = core.f
        Ek = core.Ek
        Ee = core.Ee
        Eg = core.Eg
        sigma_vm = stress.sigma_vm
        sigma_max = stress.sigma_max
    end
    @connections begin
connect(A, nodeA)
connect(nodeA, core.pa)
connect(B, nodeB)
connect(nodeB, core.pb)
connect(C, nodeC)
connect(nodeC, core.pc)
connect(D, nodeD)
connect(nodeD, core.pd)
connect(E, nodeE)
connect(nodeE, core.pe)
connect(S, nodeS)
connect(nodeS, core.ps)
connect(gA, core.gA)
        connect(core.pose, pose)
        connect(core.poseB, poseB)
        connect(core.poseC, poseC)
        connect(core.poseD, poseD)
        connect(core.poseE, poseE)
        connect(core.s, s)
        connect(core.sd, sd)
        connect(core.V, V)
        connect(core.eta, eta)
        connect(core.f, f)
        connect(core.Ek, Ek)
        connect(core.Ee, Ee)
        connect(core.Eg, Eg)
        connect(core.eta, stress.q)
        connect(stress.sigma_vm, sigma_vm)
        connect(stress.sigma_max, sigma_max)
    end
end
