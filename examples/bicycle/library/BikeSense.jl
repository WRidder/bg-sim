@block BikeSense begin
    # The benchmark bicycle's coordinates (Meijaard et al. 2007), read from the 3D bond graph.
    #
    # Inputs: the rear frame's reference pose `gr` (a frame that is world-aligned when the bicycle
    # stands upright and straight, here at the rear hub), the rear frame body pose `gB` and body
    # twist `VB` (RigidBody3D outputs), the steer joint and the rear hub joint.
    #
    # With `Rr` the rotation of `gr`, the rear frame orientation is Rz(yaw) Rx(lean) Ry(pitch)
    # (world z up, y to the left). The paper's frame has z down and y to the right, so the lean
    # angle has the paper's sign (positive = leaning to the right) and the paper's yaw is minus
    # the world yaw:
    #
    #     phi = asin(Rr[3,2]),    yaw = atan(-Rr[1,2], Rr[2,2]),
    #     a = (cos yaw, sin yaw, 0) the heading, c = (-sin yaw, cos yaw, 0),
    #     phid = w . a,   pitch rate = (w . c)/cos(phi),   yaw rate = w_z - pitch rate sin(phi),
    #
    # with `w = R_B VB[1:3]` the world angular velocity of the rear frame. The steer angle is the
    # steer joint angle (its axis points down the steer axis, the paper's delta). The forward speed
    # is the paper's `v = -qR' rR`: the rear wheel rate relative to the frame times the rolling
    # radius. `psi` integrates the paper's heading rate (no wrap).
    @parameters begin
        rR::Real = 0.3, [unit = "m", min = 0, description = "Rear wheel radius (forward speed from the wheel rate)"]
    end
    @inputs begin
        gr::Vec{7}
        gB::Vec{7}
        VB::Vec{6}
        q_steer::Real
        qd_steer::Real
        qd_rear::Real
    end
    @variables begin
        psi_i::Real = 0.0, [unit = "rad", state = :prefer, description = "Integrated heading (paper sign)"]
        sr::Real = 1.0, [unit = "1", description = "Squared norm of the reference quaternion"]
        sb::Real = 1.0, [unit = "1", description = "Squared norm of the body quaternion"]
        Rr::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Reference rotation of the rear frame"]
        RB::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rear frame body rotation"]
        w::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Rear frame angular velocity in the world"]
        yaw::Real = 0.0, [unit = "rad", description = "World yaw of the rear frame"]
        thd::Real = 0.0, [unit = "rad/s", description = "Pitch rate of the rear frame"]
    end
    @outputs begin
        phi::Real, [unit = "rad", description = "Lean of the rear frame (paper sign: to the right)"]
        phid::Real, [unit = "rad/s", description = "Lean rate"]
        delta::Real, [unit = "rad", description = "Steer angle (paper sign: to the right)"]
        deltad::Real, [unit = "rad/s", description = "Steer rate"]
        psi::Real, [unit = "rad", description = "Heading (paper sign: to the right), integrated"]
        psid::Real, [unit = "rad/s", description = "Heading rate (paper sign)"]
        pitch::Real, [unit = "rad", description = "Pitch of the rear frame (positive nose down in the world)"]
        v::Real, [unit = "m/s", description = "Forward speed rR times the rear wheel rate"]
        x::Real, [unit = "m", description = "Rear hub, world x"]
        y::Real, [unit = "m", description = "Rear hub, world y (to the left)"]
    end
    @equations begin
        sr ~ gr[1] * gr[1] + gr[2] * gr[2] + gr[3] * gr[3] + gr[4] * gr[4]
        Rr[1, 1] ~ (gr[1] * gr[1] + gr[2] * gr[2] - gr[3] * gr[3] - gr[4] * gr[4]) / sr
        Rr[1, 2] ~ 2 * (gr[2] * gr[3] - gr[1] * gr[4]) / sr
        Rr[1, 3] ~ 2 * (gr[2] * gr[4] + gr[1] * gr[3]) / sr
        Rr[2, 1] ~ 2 * (gr[2] * gr[3] + gr[1] * gr[4]) / sr
        Rr[2, 2] ~ (gr[1] * gr[1] - gr[2] * gr[2] + gr[3] * gr[3] - gr[4] * gr[4]) / sr
        Rr[2, 3] ~ 2 * (gr[3] * gr[4] - gr[1] * gr[2]) / sr
        Rr[3, 1] ~ 2 * (gr[2] * gr[4] - gr[1] * gr[3]) / sr
        Rr[3, 2] ~ 2 * (gr[3] * gr[4] + gr[1] * gr[2]) / sr
        Rr[3, 3] ~ (gr[1] * gr[1] - gr[2] * gr[2] - gr[3] * gr[3] + gr[4] * gr[4]) / sr
        sb ~ gB[1] * gB[1] + gB[2] * gB[2] + gB[3] * gB[3] + gB[4] * gB[4]
        RB[1, 1] ~ (gB[1] * gB[1] + gB[2] * gB[2] - gB[3] * gB[3] - gB[4] * gB[4]) / sb
        RB[1, 2] ~ 2 * (gB[2] * gB[3] - gB[1] * gB[4]) / sb
        RB[1, 3] ~ 2 * (gB[2] * gB[4] + gB[1] * gB[3]) / sb
        RB[2, 1] ~ 2 * (gB[2] * gB[3] + gB[1] * gB[4]) / sb
        RB[2, 2] ~ (gB[1] * gB[1] - gB[2] * gB[2] + gB[3] * gB[3] - gB[4] * gB[4]) / sb
        RB[2, 3] ~ 2 * (gB[3] * gB[4] - gB[1] * gB[2]) / sb
        RB[3, 1] ~ 2 * (gB[2] * gB[4] - gB[1] * gB[3]) / sb
        RB[3, 2] ~ 2 * (gB[3] * gB[4] + gB[1] * gB[2]) / sb
        RB[3, 3] ~ (gB[1] * gB[1] - gB[2] * gB[2] - gB[3] * gB[3] + gB[4] * gB[4]) / sb
        for i in 1:3
            w[i] ~ RB[i, 1] * VB[1] + RB[i, 2] * VB[2] + RB[i, 3] * VB[3]
        end
        phi ~ asin(Rr[3, 2])
        yaw ~ atan(-Rr[1, 2], Rr[2, 2])
        pitch ~ atan(-Rr[3, 1], Rr[3, 3])
        phid ~ w[1] * cos(yaw) + w[2] * sin(yaw)
        thd ~ (-w[1] * sin(yaw) + w[2] * cos(yaw)) / cos(phi)
        psid ~ -(w[3] - thd * sin(phi))
        ddt(psi_i) ~ psid
        psi ~ psi_i
        delta ~ q_steer
        deltad ~ qd_steer
        v ~ rR * qd_rear
        x ~ gr[5]
        y ~ gr[6]
    end
end
