@block GripMonitor begin
    # Watches the grip: the parcel's sway relative to the gripper, its distance from the TCP,
    # the number of cups whose seal latch has tripped, and the `holds` latch for the dashboard.
    #
    #   q_rel = conj(q_G) (x) q_parcel,  sway = 2 sign(q_rel,w) q_rel,v      (rad, gripper frame)
    #   sep   = |p_parcel - (p_G + R_G r_TCP)|                              (the CoM is the TCP at rest)
    #   holds: 1, set to 0 by an event when sep exceeds d_drop before t_rel (the release at the
    #          place position; after it the gripper leaves the parcel). A single lost cup does
    #          not count as a drop: `n_lost` reports the cups whose seal latch has tripped.
    @inputs begin
        gp::Vec{7}, [description = "Parcel pose (centre of mass)"]
        gg::Vec{7}, [description = "Gripper pose G"]
        s1::Real, [unit = "1", description = "Cup 1 sealed (1) or lost (0)"]
        s2::Real, [unit = "1", description = "Cup 2 sealed (1) or lost (0)"]
        s3::Real, [unit = "1", description = "Cup 3 sealed (1) or lost (0)"]
        s4::Real, [unit = "1", description = "Cup 4 sealed (1) or lost (0)"]
        s5::Real, [unit = "1", description = "Cup 5 sealed (1) or lost (0)"]
        s6::Real, [unit = "1", description = "Cup 6 sealed (1) or lost (0)"]
    end
    @parameters begin
        tx::Real = 0.0, [unit = "m", description = "TCP x in G"]
        ty::Real = 0.0, [unit = "m", description = "TCP y in G"]
        tz::Real = -0.19, [unit = "m", description = "TCP z in G"]
        t_rel::Real = 3.0, [unit = "s", description = "Release time: the monitor stops judging"]
        d_drop::Real = 0.05, [unit = "m", description = "Separation that counts as a dropped parcel"]
    end
    @variables begin
        holds::Real = 1.0, [unit = "1", description = "1 while the parcel is held (latched to 0 when it separates before t_rel)"]
        rw::Real = 1.0, [unit = "1", description = "Relative quaternion w"]
        rx::Real = 0.0, [unit = "1", description = "Relative quaternion x"]
        ry::Real = 0.0, [unit = "1", description = "Relative quaternion y"]
        rz::Real = 0.0, [unit = "1", description = "Relative quaternion z"]
        sg::Real = 1.0, [unit = "1", description = "Sign of rw"]
        s::Real = 1.0, [unit = "1", description = "Squared norm of the gripper quaternion"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Gripper rotation"]
        zd::Real = -1.0, [unit = "m", description = "Gated separation margin"]
    end
    @outputs begin
        sway_x::Real, [unit = "rad", description = "Parcel rotation relative to the gripper about the gripper x axis"]
        sway_y::Real, [unit = "rad", description = "Parcel rotation relative to the gripper about the gripper y axis"]
        sway::Real, [unit = "rad", description = "Parcel tilt relative to the gripper (magnitude)"]
        sep::Real, [unit = "m", description = "Distance of the parcel centre of mass from the TCP"]
        n_lost::Real, [unit = "1", description = "Number of cups whose seal latch has tripped"]
        held::Real, [unit = "1", description = "1 while the parcel is held, 0 after a loss"]
    end
    @equations begin
        rw ~ gg[1] * gp[1] + gg[2] * gp[2] + gg[3] * gp[3] + gg[4] * gp[4]
        rx ~ gg[1] * gp[2] - gp[1] * gg[2] - (gg[3] * gp[4] - gg[4] * gp[3])
        ry ~ gg[1] * gp[3] - gp[1] * gg[3] - (gg[4] * gp[2] - gg[2] * gp[4])
        rz ~ gg[1] * gp[4] - gp[1] * gg[4] - (gg[2] * gp[3] - gg[3] * gp[2])
        sg ~ ifelse(rw < 0.0, -1.0, 1.0)
        sway_x ~ 2 * sg * rx
        sway_y ~ 2 * sg * ry
        sway ~ 2 * atan(sqrt(rx * rx + ry * ry), sqrt(rw * rw + rz * rz))
        s ~ gg[1] * gg[1] + gg[2] * gg[2] + gg[3] * gg[3] + gg[4] * gg[4]
        R[1, 1] ~ (gg[1] * gg[1] + gg[2] * gg[2] - gg[3] * gg[3] - gg[4] * gg[4]) / s
        R[1, 2] ~ 2 * (gg[2] * gg[3] - gg[1] * gg[4]) / s
        R[1, 3] ~ 2 * (gg[2] * gg[4] + gg[1] * gg[3]) / s
        R[2, 1] ~ 2 * (gg[2] * gg[3] + gg[1] * gg[4]) / s
        R[2, 2] ~ (gg[1] * gg[1] - gg[2] * gg[2] + gg[3] * gg[3] - gg[4] * gg[4]) / s
        R[2, 3] ~ 2 * (gg[3] * gg[4] - gg[1] * gg[2]) / s
        R[3, 1] ~ 2 * (gg[2] * gg[4] - gg[1] * gg[3]) / s
        R[3, 2] ~ 2 * (gg[3] * gg[4] + gg[1] * gg[2]) / s
        R[3, 3] ~ (gg[1] * gg[1] - gg[2] * gg[2] - gg[3] * gg[3] + gg[4] * gg[4]) / s
        sep ~ sqrt((gp[5] - gg[5] - (R[1, 1] * tx + R[1, 2] * ty + R[1, 3] * tz))^2 +
                   (gp[6] - gg[6] - (R[2, 1] * tx + R[2, 2] * ty + R[2, 3] * tz))^2 +
                   (gp[7] - gg[7] - (R[3, 1] * tx + R[3, 2] * ty + R[3, 3] * tz))^2)
        n_lost ~ 6 - (s1 + s2 + s3 + s4 + s5 + s6)
        zd ~ ifelse(t < t_rel, sep - d_drop, -1.0)
        ddt(holds) ~ 0.0
        held ~ holds
    end
    @events begin
        zd > 0 => begin
            reinit(holds, 0.0)
        end
    end
end
