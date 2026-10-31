@block ProfileSelect begin
    # Picks one of the four transfer profiles by the parameter `kind`:
    # 1 trapezoidal (infinite jerk), 2 S-curve (jerk-limited, 7 segments), 3 polynomial 3-4-5,
    # 4 cycloidal. All four stdlib profile blocks run side by side; the selection weights are
    # functions of the parameter only, so they create no events. The trapezoid has no jerk
    # output: its jerk is a train of impulses, reported here as 0.
    @inputs begin
        q1::Real
        v1::Real
        a1::Real
        q2::Real
        v2::Real
        a2::Real
        j2::Real
        q3::Real
        v3::Real
        a3::Real
        j3::Real
        q4::Real
        v4::Real
        a4::Real
        j4::Real
    end
    @parameters kind::Real = 2.0, [unit = "1", min = 1, max = 4, description = "Profile: 1 trapezoidal, 2 S-curve, 3 polynomial 3-4-5, 4 cycloidal"]
    @variables begin
        w1::Real = 0.0, [unit = "1", description = "Weight of the trapezoid"]
        w2::Real = 1.0, [unit = "1", description = "Weight of the S-curve"]
        w3::Real = 0.0, [unit = "1", description = "Weight of the 3-4-5 polynomial"]
        w4::Real = 0.0, [unit = "1", description = "Weight of the cycloid"]
    end
    @outputs begin
        q::Real, [unit = "m", description = "Position along the path"]
        v::Real, [unit = "m/s", description = "Velocity along the path"]
        a::Real, [unit = "m/s^2", description = "Acceleration along the path"]
        jerk::Real, [unit = "m/s^3", description = "Jerk along the path (0 for the trapezoid)"]
    end
    @equations begin
        w1 ~ ifelse(abs(kind - 1) < 0.5, 1.0, 0.0)
        w2 ~ ifelse(abs(kind - 2) < 0.5, 1.0, 0.0)
        w3 ~ ifelse(abs(kind - 3) < 0.5, 1.0, 0.0)
        w4 ~ ifelse(abs(kind - 4) < 0.5, 1.0, 0.0)
        q ~ w1 * q1 + w2 * q2 + w3 * q3 + w4 * q4
        v ~ w1 * v1 + w2 * v2 + w3 * v3 + w4 * v4
        a ~ w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
        jerk ~ w2 * j2 + w3 * j3 + w4 * j4
    end
end
