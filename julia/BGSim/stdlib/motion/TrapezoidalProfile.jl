@block TrapezoidalProfile begin
    # Point-to-point move from q_start to q_end with a trapezoidal velocity (20-sim's motion
    # profile library, Simulink's Trapezoidal Velocity Profile Trajectory): from t_start the
    # acceleration is +a_max until the velocity reaches v_max, the velocity stays at v_max,
    # and the acceleration is -a_max until the move stops exactly at q_end. When the distance
    # is too short to reach v_max the cruise phase vanishes and the velocity is a triangle
    # with the peak sqrt(a_max*|q_end - q_start|). Position and velocity are continuous; the
    # acceleration jumps at the three switches. Before t_start the outputs are q_start and 0,
    # after the move q_end (exactly) and 0. A move with q_end < q_start runs backwards.
    #
    # Exact switches: every switch is a comparison of `t` with a switch time `b[i]` written
    # as 2*(0.5*t_start + 0.5*T[i]), a product, so the compiler keeps it one atom when it
    # substitutes it into the event condition and `t - b[i]` has its exact zero at the
    # switch (see the comment in sources/Sawtooth). A switch on an output-grid time is then
    # consumed in one event, never a W206 flood.
    @outputs begin
        q::Real, [description = "Position"]
        v::Real, [description = "Velocity, in position units per second"]
        a::Real, [description = "Acceleration, in position units per second squared"]
    end
    @parameters begin
        q_start::Real = 0.0, [description = "Start position: the output before t_start"]
        q_end::Real = 1.0, [description = "End position, reached exactly when the move stops"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the move starts"]
        v_max::Real = 1.0, [min = 1.0e-12, description = "Largest velocity, in position units per second"]
        a_max::Real = 1.0, [min = 1.0e-12, description = "Acceleration and deceleration, in position units per second squared"]
    end
    @variables begin
        dist::Real = 0.0, [description = "Length of the move, |q_end - q_start|"]
        dir::Real = 0.0, [description = "Direction of the move: 1, -1, or 0 for no move"]
        v_peak::Real = 0.0, [description = "Peak velocity: v_max, or sqrt(a_max*dist) for a triangular profile"]
        T_acc::Real = 0.0, [unit = "s", description = "Duration of the acceleration (and of the deceleration)"]
        T_cruise::Real = 0.0, [unit = "s", description = "Duration of the constant-velocity phase (0 for a triangular profile)"]
        b::Vec{3}, [unit = "s", description = "Switch times: end of the acceleration, start of the deceleration, end of the move"]
    end
    @equations begin
        dist ~ abs(q_end - q_start)
        dir ~ sign(q_end - q_start)
        v_peak ~ min(v_max, sqrt(a_max * dist))
        T_acc ~ v_peak / a_max
        T_cruise ~ max(dist / max(v_peak, 1.0e-300) - T_acc, 0.0)
        b[1] ~ 2.0 * (0.5 * t_start + 0.5 * T_acc)
        b[2] ~ 2.0 * (0.5 * t_start + 0.5 * (T_acc + T_cruise))
        b[3] ~ 2.0 * (0.5 * t_start + 0.5 * (2.0 * T_acc + T_cruise))
        q ~ ifelse(
            t < b[1],
            ifelse(t < t_start, q_start, q_start + dir * 0.5 * a_max * (t - t_start)^2),
            ifelse(
                t < b[2],
                q_start + dir * (0.5 * a_max * T_acc^2 + v_peak * (t - b[1])),
                ifelse(t < b[3], q_end - dir * 0.5 * a_max * (b[3] - t)^2, q_end),
            ),
        )
        v ~ dir * ifelse(
            t < b[1],
            ifelse(t < t_start, 0.0, a_max * (t - t_start)),
            ifelse(t < b[2], v_peak, ifelse(t < b[3], a_max * (b[3] - t), 0.0)),
        )
        a ~ dir * ifelse(
            t < b[1],
            ifelse(t < t_start, 0.0, a_max),
            ifelse(t < b[2], 0.0, ifelse(t < b[3], -a_max, 0.0)),
        )
    end
end
