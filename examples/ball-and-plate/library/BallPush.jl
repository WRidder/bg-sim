@block BallPush begin
    # A push on the ball (a finger flick): a horizontal force F(t) = (Fx, Fy) sin(pi (t - t_push) / dur)
    # in the WORLD frame for t_push <= t < t_push + dur, an impulse of 2 |F| dur / pi. The ball's
    # body frame turns with the ball, so the block rotates the world force into the body frame
    # (R(gb)' F) for an `ExternalWrenchSpatial` on the ball, whose port frame is the body frame at
    # the centre: the force acts through the centre, no torque.
    @inputs gb::Vec{7}, [description = "Ball pose (D-MB6 chart)"]
    @outputs begin
        fx::Real, [unit = "N", description = "Force on the ball, body x"]
        fy::Real, [unit = "N", description = "Force on the ball, body y"]
        fz::Real, [unit = "N", description = "Force on the ball, body z"]
        Fw::Real, [unit = "N", description = "Magnitude of the push (world)"]
    end
    @parameters begin
        t_push::Real = 15.0, [unit = "s", description = "Start of the push"]
        dur::Real = 0.05, [unit = "s", min = 1.0e-4, description = "Duration of the push"]
        Fx::Real = 0.0, [unit = "N", description = "Peak force, world x"]
        Fy::Real = 0.6, [unit = "N", description = "Peak force, world y"]
    end
    @variables begin
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm"]
        p::Real = 0.0, [unit = "1", description = "Pulse shape"]
        F1::Real = 0.0, [unit = "N", description = "World force x"]
        F2::Real = 0.0, [unit = "N", description = "World force y"]
    end
    @equations begin
        s ~ gb[1] * gb[1] + gb[2] * gb[2] + gb[3] * gb[3] + gb[4] * gb[4]
        p ~ ifelse(t >= t_push && t < t_push + dur, sin(3.141592653589793 * (t - t_push) / dur), 0.0)
        F1 ~ Fx * p
        F2 ~ Fy * p
        Fw ~ sqrt(F1 * F1 + F2 * F2)
        # body components = R' F (columns of R dotted with F; F has no z component)
        fx ~ ((gb[1] * gb[1] + gb[2] * gb[2] - gb[3] * gb[3] - gb[4] * gb[4]) * F1 + 2 * (gb[2] * gb[3] + gb[1] * gb[4]) * F2) / s
        fy ~ (2 * (gb[2] * gb[3] - gb[1] * gb[4]) * F1 + (gb[1] * gb[1] - gb[2] * gb[2] + gb[3] * gb[3] - gb[4] * gb[4]) * F2) / s
        fz ~ (2 * (gb[2] * gb[4] + gb[1] * gb[3]) * F1 + 2 * (gb[3] * gb[4] - gb[1] * gb[2]) * F2) / s
    end
end
