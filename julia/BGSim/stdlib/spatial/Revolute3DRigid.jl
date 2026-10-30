@block Revolute3DRigid begin
    # **Rigid** spatial revolute joint (D-MB7 experiment): exact rotation `q` about the local z
    # axis of the joint frame, and the five other relative twist directions held by **hard
    # constraints** instead of the stiff springs of `Revolute3D`. It is the `kr, kt -> Inf`
    # limit of `Revolute3D`: the chart is `H(q) = (Rz(q), 0)` and
    #
    #     V_rel = child.f - Ad(H)^-1 parent.f,      V_rel[1, 2, 4, 5, 6] = 0,   qdot = V_rel[3]
    #     child.e = [F[1], F[2], tau, Fl[1], Fl[2], Fl[3]]
    #     parent.e = -Ad(H)^-T child.e = -[R (F, tau); R Fl]
    #
    # `F` (N*m) and `Fl` (N) are the **constraint reactions** (Lagrange multipliers): no equation
    # defines them, the five velocity constraints take their place, so the block stays balanced
    # and, with `Ja = 0`, the port power closes identically (`parent.e.parent.f +
    # child.e.child.f + drive.e*qdot = 0`: the reactions do no work on an admissible twist).
    # The axial rows below carry `tau + Ja*qdd`, the drive effort plus the armature.
    #
    # The constraints are written at the **velocity** level on the body twists. The link poses are
    # composed from `q` (D-MB6), never integrated, so there is no position-level constraint to
    # drift: a body on this joint is index-2 in its momenta, and `mtkcompile`'s index reduction
    # (Pantelides + dummy derivatives) differentiates the five constraints once and keeps one
    # rate per joint as a state. A fixed-base serial chain of `n` such joints compiles to exactly
    # `2n` differential states (`q` and `qdot` per joint): minimal coordinates. The body momenta,
    # twists, reactions and accelerations are algebraic, solved by the implicit integrator
    # (mass-matrix DAE, `Rodas5P`/`FBDF`). The SCAP marks the child body's inertia
    # derivative-causal (W201): the physical signature of the hard constraint, not a fault
    # (DEC-MB-2).
    #
    # Making the index reduction pick `qdot`. The dummy-derivative selection is structural: left
    # alone it may keep a body twist component that is identically zero for the geometry (a
    # singular initialization). Two things make `qdot` the state: `qdot` carries `state =
    # :prefer` (a state priority, honoured for W201 models), and its derivative appears in an
    # original equation through the **armature** term `Ja * qdd` (without it MTK eliminates
    # `qdot` as an alias of a twist before the priorities are read). `Ja` is a real joint-space
    # inertia (MuJoCo's `armature`), applied between parent and child, so the block stores
    # `Ja qdot^2 / 2`. The default `Ja = 0` keeps the term structurally but not numerically: a
    # W201 model is compiled with `allow_parameter = false`, so the tearing never divides by
    # `Ja` (or by any other parameter that may be zero).
    #
    # Joint frame = parent port frame (frame-neutral, like `Revolute3D`): place and orient the
    # axis with `FixedTransform3DNeutral` on either side. D-MB8: the drive is a **Rotation** port
    # (N*m, rad/s). `pose` is `H` on the D-MB6 chart `(q_w, q_x, q_y, q_z, p)`.
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
        drive::Power{Rotation}
    end
    @parameters begin
        q0::Real = 0.0, [unit = "rad", description = "Initial joint angle"]
        Ja::Real = 0.0, [unit = "kg*m^2", min = 0, description = "Armature (reflected rotor) inertia on the joint axis"]
    end
    @variables begin
        cq::Real = 1.0, [unit = "1", description = "cos(q)"]
        sq::Real = 0.0, [unit = "1", description = "sin(q)"]
        q::Real = 0.0, [unit = "rad", description = "Joint angle"]
        qdot::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Joint rate (the state kept by the index reduction)"]
        qdd::Real = 0.0, [unit = "rad/s^2", description = "Joint acceleration"]
        wn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent angular rate in the child frame"]
        vn::Vec{3} = [0.0, 0.0, 0.0], [description = "Parent linear rate in the child frame"]
        F::Vec{2} = [0.0, 0.0], [unit = "N*m", description = "Constraint reaction torques about x and y (child frame)"]
        Fl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Constraint reaction force (child frame)"]
        tau::Real = 0.0, [unit = "N*m", description = "Axial effort carried by the drive"]
    end
    @outputs begin
        qout::Real, [unit = "rad"]
        qdout::Real, [unit = "rad/s"]
        pose::Vec{7}
        mout::Vec{2}, [unit = "N*m"]
        fout::Vec{3}, [unit = "N"]
    end
    @equations begin
        cq ~ cos(q)
        sq ~ sin(q)
        # Ad(H)^-1 [w; v] = [R^T w; R^T v] with R = Rz(q), H = (R, 0).
        wn[1] ~ cq * parent.f[1] + sq * parent.f[2]
        wn[2] ~ -sq * parent.f[1] + cq * parent.f[2]
        wn[3] ~ parent.f[3]
        vn[1] ~ cq * parent.f[4] + sq * parent.f[5]
        vn[2] ~ -sq * parent.f[4] + cq * parent.f[5]
        vn[3] ~ parent.f[6]
        # The five hard constraints: zero relative twist off the axis.
        child.f[1] ~ wn[1]
        child.f[2] ~ wn[2]
        child.f[4] ~ vn[1]
        child.f[5] ~ vn[2]
        child.f[6] ~ vn[3]
        child.f[3] ~ wn[3] + qdot
        ddt(qdot) ~ qdd
        q ~ q0 + int(qdot, 0.0)
        # child.e = [F; tau; Fl]: the reactions are the multipliers of the constraints above.
        child.e[1] ~ F[1]
        child.e[2] ~ F[2]
        child.e[3] ~ tau + Ja * qdd
        child.e[4] ~ Fl[1]
        child.e[5] ~ Fl[2]
        child.e[6] ~ Fl[3]
        # parent.e = -Ad(H)^-T child.e = -[R (F, tau); R Fl]
        parent.e[1] ~ -(cq * F[1] - sq * F[2])
        parent.e[2] ~ -(sq * F[1] + cq * F[2])
        parent.e[3] ~ -(tau + Ja * qdd)
        parent.e[4] ~ -(cq * Fl[1] - sq * Fl[2])
        parent.e[5] ~ -(sq * Fl[1] + cq * Fl[2])
        parent.e[6] ~ -Fl[3]
        drive.e ~ -tau
        drive.f ~ qdot
        qout ~ q
        qdout ~ qdot
        pose[1] ~ cos(0.5 * q)
        pose[2] ~ 0.0
        pose[3] ~ 0.0
        pose[4] ~ sin(0.5 * q)
        pose[5] ~ 0.0
        pose[6] ~ 0.0
        pose[7] ~ 0.0
        mout[1] ~ F[1]
        mout[2] ~ F[2]
        fout[1] ~ Fl[1]
        fout[2] ~ Fl[2]
        fout[3] ~ Fl[3]
    end
    @causality begin
        (parent, child) => :transformer
        drive => :flow_out
    end
end
