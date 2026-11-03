@block RigViz begin
    # Poses for the 3D view only (no feedback): the two push rods from the crank tips to their
    # attachment points under the plate edge, and the reference marker on the plate.
    # Crank X: shaft at (-L - r, 0, z_s), tip at shaft + r (cos thx, 0, sin thx); its rod goes to
    # the plate point (-L, 0, -t/2). Crank Y: shaft at (0, -L - r, z_s), tip at
    # shaft + r (0, cos thy, sin thy); rod to the plate point (0, -L, -t/2). A rod pose has its z
    # axis along the rod (the axis of an SDF cylinder) and its origin at the rod's middle. The
    # marker sits on the plate surface at the reference (xd, yd) of the plate frame.
    @inputs begin
        gp::Vec{7}, [description = "Plate pose"]
        thx::Real, [unit = "rad", description = "Servo X angle"]
        thy::Real, [unit = "rad", description = "Servo Y angle"]
        xd::Real, [unit = "m", description = "Reference x"]
        yd::Real, [unit = "m", description = "Reference y"]
    end
    @outputs begin
        rodx::Vec{7}, [description = "Pose of push rod X"]
        rody::Vec{7}, [description = "Pose of push rod Y"]
        target::Vec{7}, [description = "Pose of the reference marker"]
        tipx::Vec{3}, [unit = "m", description = "Crank X tip, world (checks the joint axis of the scene)"]
        tipy::Vec{3}, [unit = "m", description = "Crank Y tip, world"]
    end
    @parameters begin
        L::Real = 0.16, [unit = "m", description = "Rod attachment distance from the gimbal centre"]
        r::Real = 0.0254, [unit = "m", description = "Crank radius"]
        z_s::Real = 0.06, [unit = "m", description = "Height of the servo shafts"]
        tp::Real = 0.006, [unit = "m", description = "Plate thickness"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Plate rotation"]
        ax::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Rod X attachment, world"]
        ay::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Rod Y attachment, world"]
        bx::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Crank X tip, world"]
        by::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Crank Y tip, world"]
        dx::Vec{3} = [0.0, 0.0, 1.0], [unit = "1", description = "Rod X direction"]
        dy::Vec{3} = [0.0, 0.0, 1.0], [unit = "1", description = "Rod Y direction"]
        nx::Real = 1.0, [unit = "1", description = "Normalisation of the X rod quaternion"]
        ny::Real = 1.0, [unit = "1", description = "Normalisation of the Y rod quaternion"]
        lx::Real = 0.1, [unit = "m", description = "Rod X length"]
        ly::Real = 0.1, [unit = "m", description = "Rod Y length"]
    end
    @equations begin
        s ~ gp[1] * gp[1] + gp[2] * gp[2] + gp[3] * gp[3] + gp[4] * gp[4]
        R[1, 1] ~ (gp[1] * gp[1] + gp[2] * gp[2] - gp[3] * gp[3] - gp[4] * gp[4]) / s
        R[1, 2] ~ 2 * (gp[2] * gp[3] - gp[1] * gp[4]) / s
        R[1, 3] ~ 2 * (gp[2] * gp[4] + gp[1] * gp[3]) / s
        R[2, 1] ~ 2 * (gp[2] * gp[3] + gp[1] * gp[4]) / s
        R[2, 2] ~ (gp[1] * gp[1] - gp[2] * gp[2] + gp[3] * gp[3] - gp[4] * gp[4]) / s
        R[2, 3] ~ 2 * (gp[3] * gp[4] - gp[1] * gp[2]) / s
        R[3, 1] ~ 2 * (gp[2] * gp[4] - gp[1] * gp[3]) / s
        R[3, 2] ~ 2 * (gp[3] * gp[4] + gp[1] * gp[2]) / s
        R[3, 3] ~ (gp[1] * gp[1] - gp[2] * gp[2] - gp[3] * gp[3] + gp[4] * gp[4]) / s
        ax[1] ~ gp[5] - L * R[1, 1] - 0.5 * tp * R[1, 3]
        ax[2] ~ gp[6] - L * R[2, 1] - 0.5 * tp * R[2, 3]
        ax[3] ~ gp[7] - L * R[3, 1] - 0.5 * tp * R[3, 3]
        ay[1] ~ gp[5] - L * R[1, 2] - 0.5 * tp * R[1, 3]
        ay[2] ~ gp[6] - L * R[2, 2] - 0.5 * tp * R[2, 3]
        ay[3] ~ gp[7] - L * R[3, 2] - 0.5 * tp * R[3, 3]
        bx[1] ~ -L - r + r * cos(thx)
        bx[2] ~ 0.0
        bx[3] ~ z_s + r * sin(thx)
        by[1] ~ 0.0
        by[2] ~ -L - r + r * cos(thy)
        by[3] ~ z_s + r * sin(thy)
        lx ~ sqrt((ax[1] - bx[1]) * (ax[1] - bx[1]) + (ax[2] - bx[2]) * (ax[2] - bx[2]) + (ax[3] - bx[3]) * (ax[3] - bx[3]))
        ly ~ sqrt((ay[1] - by[1]) * (ay[1] - by[1]) + (ay[2] - by[2]) * (ay[2] - by[2]) + (ay[3] - by[3]) * (ay[3] - by[3]))
        dx[1] ~ (ax[1] - bx[1]) / lx
        dx[2] ~ (ax[2] - bx[2]) / lx
        dx[3] ~ (ax[3] - bx[3]) / lx
        dy[1] ~ (ay[1] - by[1]) / ly
        dy[2] ~ (ay[2] - by[2]) / ly
        dy[3] ~ (ay[3] - by[3]) / ly
        # quaternion turning z onto d: (1 + d_z, -d_y, d_x, 0) normalised
        nx ~ sqrt((1 + dx[3]) * (1 + dx[3]) + dx[2] * dx[2] + dx[1] * dx[1])
        ny ~ sqrt((1 + dy[3]) * (1 + dy[3]) + dy[2] * dy[2] + dy[1] * dy[1])
        rodx[1] ~ (1 + dx[3]) / nx
        rodx[2] ~ -dx[2] / nx
        rodx[3] ~ dx[1] / nx
        rodx[4] ~ 0.0
        rodx[5] ~ 0.5 * (ax[1] + bx[1])
        rodx[6] ~ 0.5 * (ax[2] + bx[2])
        rodx[7] ~ 0.5 * (ax[3] + bx[3])
        rody[1] ~ (1 + dy[3]) / ny
        rody[2] ~ -dy[2] / ny
        rody[3] ~ dy[1] / ny
        rody[4] ~ 0.0
        rody[5] ~ 0.5 * (ay[1] + by[1])
        rody[6] ~ 0.5 * (ay[2] + by[2])
        rody[7] ~ 0.5 * (ay[3] + by[3])
        target[1] ~ gp[1]
        target[2] ~ gp[2]
        target[3] ~ gp[3]
        target[4] ~ gp[4]
        target[5] ~ gp[5] + R[1, 1] * xd + R[1, 2] * yd + (0.5 * tp + 0.0005) * R[1, 3]
        target[6] ~ gp[6] + R[2, 1] * xd + R[2, 2] * yd + (0.5 * tp + 0.0005) * R[2, 3]
        target[7] ~ gp[7] + R[3, 1] * xd + R[3, 2] * yd + (0.5 * tp + 0.0005) * R[3, 3]
        for i in 1:3
            tipx[i] ~ bx[i]
            tipy[i] ~ by[i]
        end
    end
end
