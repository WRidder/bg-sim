@block FlexibleBeam2D begin
    # A slender flexible beam in the plane (rod, tube or rectangular bar) by the assumed-modes
    # method: a floating reference frame plus up to three closed-form in-plane bending modes
    # (axial rigid). It replaces a `RigidBody2D`: the beam's own mass and yaw inertia are in
    # it. The physics, the modal bond graph and the equations are in `ModalBeam2D`; this
    # composite gives each end its own 1-junction, so the ends bond like a body port.
    #
    #   A (1-junction) ── ModalBeam2D.pa      ModalBeam2D.pb ── B (1-junction)
    #                            gA ──► gravity, pose, poseB
    #
    # Frames: end A at s = 0 with the beam axis along its +x, end B at s = L. `gA` is the world
    # pose (theta, x, y) of the end-A frame; `pose` is the world pose of the reference frame
    # (the frame the viewer deforms with the mode shapes of `src/mech/modes.jl`) and `poseB`
    # the world pose of end B. Modal coordinates `eta_y` (m) and the free eigenfrequencies
    # `f_y` (Hz) of the three modes in the chosen basis; an unused mode reads 0.
    @constants begin
        ny::Int = 2, [min = 0, max = 3, description = "In-plane bending modes"]
        basis::Int = 0, [options = ["clamped-free", "free-free"], description = "Mode basis: 0 clamped at A (cantilever), 1 free-free (mean axis)"]
        section::Int = 0, [options = ["rod", "tube", "rectangle"], description = "Cross-section: 0 solid rod (d), 1 tube (d, di), 2 rectangle (b in the plane, h out of it)"]
    end
    @ports begin
        A::Power{Planar}, [frame = "body"]
        B::Power{Planar}, [frame = "body"]
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
    @components begin
        nodeA = Junction(1)
        nodeB = Junction(1)
        beam = ModalBeam2D(ny = ny, basis = basis, section = section, L = L, E = E, rho = rho,
            d = d, di = di, b = b, h = h, zeta_y = zeta_y, g0 = g0)
    end
    @observables begin
        pose = beam.pose
        poseB = beam.poseB
        V = beam.V
        eta_y = beam.eta_y
        f_y = beam.f_y
        dB = beam.dB
        Ek = beam.Ek
        Ee = beam.Ee
        Eg = beam.Eg
    end
    @connections begin
        connect(A, nodeA)
        connect(nodeA, beam.pa)
        connect(B, nodeB)
        connect(nodeB, beam.pb)
        connect(gA, beam.gA)
        connect(beam.pose, pose)
        connect(beam.poseB, poseB)
        connect(beam.V, V)
        connect(beam.eta_y, eta_y)
        connect(beam.f_y, f_y)
        connect(beam.dB, dB)
        connect(beam.Ek, Ek)
        connect(beam.Ee, Ee)
        connect(beam.Eg, Eg)
    end
end
