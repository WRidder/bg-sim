@block FlexibleBeam3D begin
    # A slender flexible beam (rod, tube or rectangular bar) between two frames, by the
    # assumed-modes method: a floating reference frame plus up to three closed-form elastic
    # modes per family (bending along local y, bending along local z, torsion about the axis;
    # axial is rigid). It replaces a `RigidBody3D`: the beam's own mass and rotational inertia
    # are in it. The physics, the modal bond graph and the equations are in `ModalBeam3D`;
    # this composite gives each end its own 1-junction, so the ends bond like a body port
    # (a joint child, a transform or another body attach directly).
    #
    #   A (1-junction) ── ModalBeam3D.pa      ModalBeam3D.pb ── B (1-junction)
    #                            gA ──► gravity, pose, poseB
    #
    # Frames: end A at s = 0 with the beam axis along its +x, end B at s = L. `gA` is the world
    # pose of the end-A frame (from the joint chain, D-MB6 chart); `pose` is the world pose of
    # the reference frame (the frame the viewer deforms with the mode shapes of
    # `src/mech/modes.jl`; equal to the end-A frame for the clamped-free basis) and `poseB` the
    # world pose of end B (compose the next link from it). Modal coordinates `eta_y`, `eta_z`
    # (m) and `eta_t` (rad), free eigenfrequencies `f_y`, `f_z`, `f_t` (Hz) of all three modes of
    # each family in the chosen basis; an unused mode reads 0.
    @constants begin
        ny::Int = 2, [min = 0, max = 3, description = "Bending modes along local y"]
        nz::Int = 2, [min = 0, max = 3, description = "Bending modes along local z"]
        nt::Int = 1, [min = 0, max = 3, description = "Torsion modes about the beam axis"]
        basis::Int = 0, [options = ["clamped-free", "free-free"], description = "Mode basis: 0 clamped at A (cantilever), 1 free-free (mean axis)"]
        section::Int = 0, [options = ["rod", "tube", "rectangle"], description = "Cross-section: 0 solid rod (d), 1 tube (d, di), 2 rectangle (b along y, h along z)"]
    end
    @ports begin
        A::Power{Spatial}, [frame = "body"]
        B::Power{Spatial}, [frame = "body"]
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
    @components begin
        nodeA = Junction(1)
        nodeB = Junction(1)
        beam = ModalBeam3D(ny = ny, nz = nz, nt = nt, basis = basis, section = section,
            L = L, E = E, nu = nu, rho = rho, d = d, di = di, b = b, h = h,
            zeta_y = zeta_y, zeta_z = zeta_z, zeta_t = zeta_t, g0 = g0)
    end
    @observables begin
        pose = beam.pose
        poseB = beam.poseB
        V = beam.V
        eta_y = beam.eta_y
        eta_z = beam.eta_z
        eta_t = beam.eta_t
        f_y = beam.f_y
        f_z = beam.f_z
        f_t = beam.f_t
        twist = beam.twist
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
        connect(beam.eta_z, eta_z)
        connect(beam.eta_t, eta_t)
        connect(beam.f_y, f_y)
        connect(beam.f_z, f_z)
        connect(beam.f_t, f_t)
        connect(beam.twist, twist)
        connect(beam.dB, dB)
        connect(beam.Ek, Ek)
        connect(beam.Ee, Ee)
        connect(beam.Eg, Eg)
    end
end
