@block Telemetry begin
    # What a data logger on the car records: speed, the attitude (yaw, pitch, roll: z-y-x Euler
    # angles of the chassis, pitch positive nose down, roll positive right side down), the body
    # slip angle, the yaw rate and the accelerations an accelerometer at the CG reads (the
    # specific force in the chassis frame: the four tyre forces and the aerodynamic force
    # divided by the total mass, in g).
    @inputs begin
        g::Vec{7}, [description = "Chassis pose (D-MB6 chart)"]
        V::Vec{6}, [description = "Chassis twist [w; v] in the chassis frame"]
        fx1::Real, [unit = "N", description = "Tyre force on wheel FL, world x"]
        fy1::Real, [unit = "N", description = "Tyre force on wheel FL, world y"]
        fz1::Real, [unit = "N", description = "Tyre force on wheel FL, world z"]
        fx2::Real, [unit = "N", description = "Tyre force on wheel FR, world x"]
        fy2::Real, [unit = "N", description = "Tyre force on wheel FR, world y"]
        fz2::Real, [unit = "N", description = "Tyre force on wheel FR, world z"]
        fx3::Real, [unit = "N", description = "Tyre force on wheel RL, world x"]
        fy3::Real, [unit = "N", description = "Tyre force on wheel RL, world y"]
        fz3::Real, [unit = "N", description = "Tyre force on wheel RL, world z"]
        fx4::Real, [unit = "N", description = "Tyre force on wheel RR, world x"]
        fy4::Real, [unit = "N", description = "Tyre force on wheel RR, world y"]
        fz4::Real, [unit = "N", description = "Tyre force on wheel RR, world z"]
        fax::Real, [unit = "N", description = "Aerodynamic force, chassis x"]
        fay::Real, [unit = "N", description = "Aerodynamic force, chassis y"]
        faz::Real, [unit = "N", description = "Aerodynamic force, chassis z"]
    end
    @outputs begin
        speed::Real, [unit = "m/s", description = "Speed of the CG (along the ground on a slope, as a speedometer)"]
        kmh::Real, [unit = "1", description = "Speed in km/h"]
        u::Real, [unit = "m/s", description = "Forward velocity (chassis x)"]
        v::Real, [unit = "m/s", description = "Lateral velocity (chassis y, left)"]
        ax::Real, [unit = "1", description = "Longitudinal acceleration (g, forward +)"]
        ay::Real, [unit = "1", description = "Lateral acceleration (g, left +)"]
        az::Real, [unit = "1", description = "Vertical specific force (g, 1 at rest)"]
        yaw::Real, [unit = "rad", description = "Heading, about world z (0 = world x)"]
        pitch::Real, [unit = "rad", description = "Pitch angle (nose down +)"]
        roll::Real, [unit = "rad", description = "Roll angle (right side down +)"]
        r::Real, [unit = "rad/s", description = "Yaw rate (chassis z)"]
        beta::Real, [unit = "rad", description = "Body slip angle atan(v/u)"]
        x::Real, [unit = "m", description = "Position, world x"]
        y::Real, [unit = "m", description = "Position, world y"]
        z::Real, [unit = "m", description = "CG height, world z"]
    end
    @parameters begin
        m::Real = 740.0, [unit = "kg", min = 1.0e-6, description = "Total mass of the vehicle"]
        g0::Real = 9.81, [unit = "m/s^2", min = 1.0e-6, description = "Gravitational acceleration (1 g)"]
        c_kmh::Real = 3.6, [unit = "s/m", description = "km/h per m/s"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1", description = "|q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Chassis rotation"]
        Fx::Real = 0.0, [unit = "N", description = "Total tyre force, world x"]
        Fy::Real = 0.0, [unit = "N", description = "Total tyre force, world y"]
        Fz::Real = 0.0, [unit = "N", description = "Total tyre force, world z"]
        vwx::Real = 0.0, [unit = "m/s", description = "Velocity, world x"]
        vwy::Real = 0.0, [unit = "m/s", description = "Velocity, world y"]
    end
    @equations begin
        s ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / s
        R[1, 2] ~ 2 * (g[2] * g[3] - g[1] * g[4]) / s
        R[1, 3] ~ 2 * (g[2] * g[4] + g[1] * g[3]) / s
        R[2, 1] ~ 2 * (g[2] * g[3] + g[1] * g[4]) / s
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / s
        R[2, 3] ~ 2 * (g[3] * g[4] - g[1] * g[2]) / s
        R[3, 1] ~ 2 * (g[2] * g[4] - g[1] * g[3]) / s
        R[3, 2] ~ 2 * (g[3] * g[4] + g[1] * g[2]) / s
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / s
        Fx ~ fx1 + fx2 + fx3 + fx4
        Fy ~ fy1 + fy2 + fy3 + fy4
        Fz ~ fz1 + fz2 + fz3 + fz4
        ax ~ (R[1, 1] * Fx + R[2, 1] * Fy + R[3, 1] * Fz + fax) / (m * g0)
        ay ~ (R[1, 2] * Fx + R[2, 2] * Fy + R[3, 2] * Fz + fay) / (m * g0)
        az ~ (R[1, 3] * Fx + R[2, 3] * Fy + R[3, 3] * Fz + faz) / (m * g0)
        vwx ~ R[1, 1] * V[4] + R[1, 2] * V[5] + R[1, 3] * V[6]
        vwy ~ R[2, 1] * V[4] + R[2, 2] * V[5] + R[2, 3] * V[6]
        speed ~ sqrt(V[4] * V[4] + V[5] * V[5] + V[6] * V[6])
        kmh ~ c_kmh * speed
        u ~ V[4]
        v ~ V[5]
        yaw ~ atan(R[2, 1], R[1, 1])
        pitch ~ -asin(clamp(R[3, 1], -1.0, 1.0))
        roll ~ atan(R[3, 2], R[3, 3])
        r ~ V[3]
        beta ~ atan(V[5], sqrt(V[4] * V[4] + 1.0e-4))
        x ~ g[5]
        y ~ g[6]
        z ~ g[7]
    end
end
