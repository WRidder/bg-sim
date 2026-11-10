@block SegwaySense begin
    # Measurements of the vehicle body, taken from its world pose `g` and body twist `V`
    # (the body frame has x forward, y to the left, z up at rest; its origin is the centre of
    # mass). A rate gyro and an inclinometer give the pitch and the yaw rate; the wheel
    # encoders are read in the controller.
    #
    #     pitch  theta = -asin(R31)   (ZYX Euler pitch of the body rotation R, positive forward)
    #     pitch rate   = V[2]         (body y rate)
    #     yaw rate     = (R V[1:3]).z (world vertical component of the body rate)
    #     heading      = integral of the yaw rate (no wrap: a figure of eight reads 0 .. 2 pi .. 0)
    #     axle         = body origin - l R e_z, the middle of the axle
    @parameters begin
        l::Real = 0.52, [unit = "m", min = 0, description = "Centre of mass above the axle"]
    end
    @inputs begin
        g::Vec{7}
        V::Vec{6}
    end
    @variables begin
        psi::Real = 0.0, [unit = "rad", state = :prefer, description = "Heading (integrated yaw rate)"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
        r31::Real = 0.0, [unit = "1", description = "Rotation matrix entry R31"]
        r32::Real = 0.0, [unit = "1", description = "Rotation matrix entry R32"]
        r33::Real = 1.0, [unit = "1", description = "Rotation matrix entry R33"]
        r13::Real = 0.0, [unit = "1", description = "Rotation matrix entry R13"]
        r23::Real = 0.0, [unit = "1", description = "Rotation matrix entry R23"]
    end
    @outputs begin
        theta::Real, [unit = "rad", description = "Body pitch from upright, positive forward"]
        w::Real, [unit = "rad/s", description = "Pitch rate"]
        wz::Real, [unit = "rad/s", description = "Yaw rate"]
        heading::Real, [unit = "rad", description = "Heading"]
        xa::Real, [unit = "m", description = "Axle middle x"]
        ya::Real, [unit = "m", description = "Axle middle y"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        r31 ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        r32 ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        r33 ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        r13 ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        r23 ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        theta ~ -asin(r31)
        w ~ V[2]
        wz ~ r31 * V[1] + r32 * V[2] + r33 * V[3]
        ddt(psi) ~ wz
        heading ~ psi
        xa ~ g[5] - l * r13
        ya ~ g[6] - l * r23
    end
end
