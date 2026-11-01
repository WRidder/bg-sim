@block CupMonitor begin
    # Watches one cup and draws it. From the tool pose `gt` (the cup mount frame T) and the
    # payload pose `gp` (its centre of mass):
    #
    #   A = p_T + R_T (mx, my, 0)          the cup mount (world)
    #   C = p_T + R_T (mx, my, -L0)        where the lip sits on an unloaded cup
    #   B = p_P + R_P (bx, by, bz)         the attach point on the payload (where the lip is)
    #
    # The 3D scene draws the bellows as segments from A to the lip: the see-through bellows body,
    # two fold rings at s_r1 and s_r2 of the length, and the lip disc (coloured by U). The lip
    # follows B while the cup is sealed and returns to C once the seal latch has dropped (the
    # payload falls away from it). `sway` is the payload tilt relative to the tool, `dlip` the
    # lip's distance from its unloaded place, and `held` a latch that drops when `dlip` exceeds
    # d_drop before the release time t_rel. The cup's extension and transmitted force come out
    # again multiplied by the seal latch (ext_c, T_c), so a force-stroke plot ends at the origin
    # when the lip leaves the payload instead of tracing the free tool.
    @inputs begin
        gt::Vec{7}, [description = "Tool (cup mount frame) pose"]
        gp::Vec{7}, [description = "Payload pose (centre of mass)"]
        sealed::Real, [unit = "1", description = "Cup seal latch (1 sealed, 0 lost)"]
        ext::Real, [unit = "m", description = "Cup axial extension"]
        T::Real, [unit = "N", description = "Cup transmitted pull"]
    end
    @parameters begin
        mx::Real = 0.0, [unit = "m", description = "Cup mount x in the tool frame"]
        my::Real = 0.0, [unit = "m", description = "Cup mount y in the tool frame"]
        bx::Real = 0.0, [unit = "m", description = "Attach point x in the payload body frame"]
        by::Real = 0.0, [unit = "m", description = "Attach point y in the payload body frame"]
        bz::Real = 0.02, [unit = "m", description = "Attach point z in the payload body frame"]
        L0::Real = 0.03, [unit = "m", description = "Cup rest length"]
        t_rel::Real = 100.0, [unit = "s", description = "Release time: the monitor stops judging"]
        d_drop::Real = 0.02, [unit = "m", description = "Lip displacement that counts as a drop"]
        s_r1::Real = 0.36, [unit = "1", description = "Position of fold ring 1 (share of the length)"]
        s_r2::Real = 0.68, [unit = "1", description = "Position of fold ring 2 (share of the length)"]
        t_r::Real = 0.004, [unit = "m", description = "Fold ring thickness (display)"]
        t_l::Real = 0.003, [unit = "m", description = "Lip thickness (display)"]
    end
    @variables begin
        nt::Real = 1.0, [unit = "1", description = "Tool quaternion norm squared"]
        Rt::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Tool rotation"]
        np_::Real = 1.0, [unit = "1", description = "Payload quaternion norm squared"]
        Rp::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Payload rotation"]
        Ax::Real = 0.0, [unit = "m"]
        Ay::Real = 0.0, [unit = "m"]
        Az::Real = 0.0, [unit = "m"]
        Cx::Real = 0.0, [unit = "m"]
        Cy::Real = 0.0, [unit = "m"]
        Cz::Real = 0.0, [unit = "m"]
        Bx::Real = 0.0, [unit = "m"]
        By::Real = 0.0, [unit = "m"]
        Bz::Real = 0.0, [unit = "m"]
        Dx::Real = 0.0, [unit = "m", description = "Drawn lip point x"]
        Dy::Real = 0.0, [unit = "m", description = "Drawn lip point y"]
        Dz::Real = 0.0, [unit = "m", description = "Drawn lip point z"]
        Lb::Real = 0.03, [unit = "m", description = "Drawn bellows length"]
        ux::Real = 0.0, [unit = "1"]
        uy::Real = 0.0, [unit = "1"]
        uz::Real = -1.0, [unit = "1"]
        rw::Real = 1.0, [unit = "1", description = "Relative quaternion w"]
        rx::Real = 0.0, [unit = "1"]
        ry::Real = 0.0, [unit = "1"]
        rz::Real = 0.0, [unit = "1"]
        holds::Real = 1.0, [unit = "1", description = "Held latch"]
        zd::Real = -1.0, [unit = "m", description = "Gated drop margin"]
    end
    @outputs begin
        bel::Vec{6}, [description = "Bellows body segment: mount to lip (world, m)"]
        ring1::Vec{6}, [description = "Fold ring 1 segment (world, m)"]
        ring2::Vec{6}, [description = "Fold ring 2 segment (world, m)"]
        lip::Vec{6}, [description = "Lip disc segment (world, m)"]
        sway::Real, [unit = "1", description = "Payload tilt relative to the tool, degrees"]
        dlip::Real, [unit = "m", description = "Lip displacement from its unloaded place"]
        held::Real, [unit = "1", description = "1 while the payload is held, 0 after a drop"]
        ext_c::Real, [unit = "m", description = "Axial extension while sealed (0 after)"]
        T_c::Real, [unit = "N", description = "Transmitted pull while sealed (0 after)"]
    end
    @equations begin
        nt ~ gt[1] * gt[1] + gt[2] * gt[2] + gt[3] * gt[3] + gt[4] * gt[4]
        Rt[1, 1] ~ (gt[1] * gt[1] + gt[2] * gt[2] - gt[3] * gt[3] - gt[4] * gt[4]) / nt
        Rt[1, 2] ~ 2 * (gt[2] * gt[3] - gt[1] * gt[4]) / nt
        Rt[1, 3] ~ 2 * (gt[2] * gt[4] + gt[1] * gt[3]) / nt
        Rt[2, 1] ~ 2 * (gt[2] * gt[3] + gt[1] * gt[4]) / nt
        Rt[2, 2] ~ (gt[1] * gt[1] - gt[2] * gt[2] + gt[3] * gt[3] - gt[4] * gt[4]) / nt
        Rt[2, 3] ~ 2 * (gt[3] * gt[4] - gt[1] * gt[2]) / nt
        Rt[3, 1] ~ 2 * (gt[2] * gt[4] - gt[1] * gt[3]) / nt
        Rt[3, 2] ~ 2 * (gt[3] * gt[4] + gt[1] * gt[2]) / nt
        Rt[3, 3] ~ (gt[1] * gt[1] - gt[2] * gt[2] - gt[3] * gt[3] + gt[4] * gt[4]) / nt
        np_ ~ gp[1] * gp[1] + gp[2] * gp[2] + gp[3] * gp[3] + gp[4] * gp[4]
        Rp[1, 1] ~ (gp[1] * gp[1] + gp[2] * gp[2] - gp[3] * gp[3] - gp[4] * gp[4]) / np_
        Rp[1, 2] ~ 2 * (gp[2] * gp[3] - gp[1] * gp[4]) / np_
        Rp[1, 3] ~ 2 * (gp[2] * gp[4] + gp[1] * gp[3]) / np_
        Rp[2, 1] ~ 2 * (gp[2] * gp[3] + gp[1] * gp[4]) / np_
        Rp[2, 2] ~ (gp[1] * gp[1] - gp[2] * gp[2] + gp[3] * gp[3] - gp[4] * gp[4]) / np_
        Rp[2, 3] ~ 2 * (gp[3] * gp[4] - gp[1] * gp[2]) / np_
        Rp[3, 1] ~ 2 * (gp[2] * gp[4] - gp[1] * gp[3]) / np_
        Rp[3, 2] ~ 2 * (gp[3] * gp[4] + gp[1] * gp[2]) / np_
        Rp[3, 3] ~ (gp[1] * gp[1] - gp[2] * gp[2] - gp[3] * gp[3] + gp[4] * gp[4]) / np_
        Ax ~ gt[5] + Rt[1, 1] * mx + Rt[1, 2] * my
        Ay ~ gt[6] + Rt[2, 1] * mx + Rt[2, 2] * my
        Az ~ gt[7] + Rt[3, 1] * mx + Rt[3, 2] * my
        Cx ~ Ax - Rt[1, 3] * L0
        Cy ~ Ay - Rt[2, 3] * L0
        Cz ~ Az - Rt[3, 3] * L0
        Bx ~ gp[5] + Rp[1, 1] * bx + Rp[1, 2] * by + Rp[1, 3] * bz
        By ~ gp[6] + Rp[2, 1] * bx + Rp[2, 2] * by + Rp[2, 3] * bz
        Bz ~ gp[7] + Rp[3, 1] * bx + Rp[3, 2] * by + Rp[3, 3] * bz
        Dx ~ sealed * Bx + (1 - sealed) * Cx
        Dy ~ sealed * By + (1 - sealed) * Cy
        Dz ~ sealed * Bz + (1 - sealed) * Cz
        Lb ~ sqrt((Dx - Ax)^2 + (Dy - Ay)^2 + (Dz - Az)^2 + 1.0e-12)
        ux ~ (Dx - Ax) / Lb
        uy ~ (Dy - Ay) / Lb
        uz ~ (Dz - Az) / Lb
        bel[1] ~ Ax
        bel[2] ~ Ay
        bel[3] ~ Az
        bel[4] ~ Dx - t_l * ux
        bel[5] ~ Dy - t_l * uy
        bel[6] ~ Dz - t_l * uz
        ring1[1] ~ Ax + s_r1 * (Dx - Ax) - 0.5 * t_r * ux
        ring1[2] ~ Ay + s_r1 * (Dy - Ay) - 0.5 * t_r * uy
        ring1[3] ~ Az + s_r1 * (Dz - Az) - 0.5 * t_r * uz
        ring1[4] ~ Ax + s_r1 * (Dx - Ax) + 0.5 * t_r * ux
        ring1[5] ~ Ay + s_r1 * (Dy - Ay) + 0.5 * t_r * uy
        ring1[6] ~ Az + s_r1 * (Dz - Az) + 0.5 * t_r * uz
        ring2[1] ~ Ax + s_r2 * (Dx - Ax) - 0.5 * t_r * ux
        ring2[2] ~ Ay + s_r2 * (Dy - Ay) - 0.5 * t_r * uy
        ring2[3] ~ Az + s_r2 * (Dz - Az) - 0.5 * t_r * uz
        ring2[4] ~ Ax + s_r2 * (Dx - Ax) + 0.5 * t_r * ux
        ring2[5] ~ Ay + s_r2 * (Dy - Ay) + 0.5 * t_r * uy
        ring2[6] ~ Az + s_r2 * (Dz - Az) + 0.5 * t_r * uz
        lip[1] ~ Dx - t_l * ux
        lip[2] ~ Dy - t_l * uy
        lip[3] ~ Dz - t_l * uz
        lip[4] ~ Dx
        lip[5] ~ Dy
        lip[6] ~ Dz
        # payload tilt relative to the tool: q_rel = conj(q_T) (x) q_P
        rw ~ gt[1] * gp[1] + gt[2] * gp[2] + gt[3] * gp[3] + gt[4] * gp[4]
        rx ~ gt[1] * gp[2] - gp[1] * gt[2] - (gt[3] * gp[4] - gt[4] * gp[3])
        ry ~ gt[1] * gp[3] - gp[1] * gt[3] - (gt[4] * gp[2] - gt[2] * gp[4])
        rz ~ gt[1] * gp[4] - gp[1] * gt[4] - (gt[2] * gp[3] - gt[3] * gp[2])
        sway ~ 2 * atan(sqrt(rx * rx + ry * ry), sqrt(rw * rw + rz * rz)) * 180 / 3.141592653589793
        dlip ~ sqrt((Bx - Cx)^2 + (By - Cy)^2 + (Bz - Cz)^2)
        zd ~ ifelse(t < t_rel, dlip - d_drop, -1.0)
        ddt(holds) ~ 0.0
        held ~ holds
        ext_c ~ sealed * ext
        T_c ~ sealed * T
    end
    @events begin
        zd > 0 => begin
            reinit(holds, 0.0)
        end
    end
end
