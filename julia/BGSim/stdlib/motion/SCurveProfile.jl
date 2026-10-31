@block SCurveProfile begin
    # Jerk-limited point-to-point move from q_start to q_end (the seven-segment "S-curve" of
    # 20-sim's motion profiles and Simulink's jerk-limited trajectories, Biagiotti and
    # Melchiorri section 3.4 with zero boundary velocities and accelerations). From t_start:
    #   1 jerk +j_max until the acceleration reaches a_peak,
    #   2 constant acceleration a_peak,
    #   3 jerk -j_max until the acceleration is 0 at the velocity v_peak,
    #   4 constant velocity v_peak,
    #   5-7 the mirror image of 1-3, ending at rest exactly at q_end.
    # a_peak = a_max and v_peak = v_max when the move is long enough; a shorter move drops
    # the cruise (4), then the constant acceleration (2 and 6): the peaks shrink so that the
    # distance is covered exactly. Position, velocity and acceleration are continuous; the
    # jerk is piecewise constant. Before t_start the outputs are q_start and 0, after the
    # move q_end (exactly) and 0. A move with q_end < q_start runs backwards.
    #
    # Peaks: without a velocity limit a move of length dist reaches the acceleration
    # min(a_max, (dist*j_max^2/2)^(1/3)); with v_max reached it is min(a_max, sqrt(v_max*j_max)),
    # and v_max is reached when dist covers the acceleration and deceleration to v_max,
    # dist >= v_max*(a/j_max + v_max/a). Without a cruise, the acceleration phase lasts
    # T_acc = (T_j + sqrt(T_j^2 + 4*dist/a_peak))/2 (from dist = a_peak*(T_acc - T_j)*T_acc).
    #
    # Exact switches: as in TrapezoidalProfile, every switch time `b[i]` is the product
    # 2*(0.5*t_start + 0.5*T[i]), one atom in the event condition `t - b[i]`, so a switch on
    # an output-grid time is consumed in one event.
    @outputs begin
        q::Real, [description = "Position"]
        v::Real, [description = "Velocity, in position units per second"]
        a::Real, [description = "Acceleration, in position units per second squared"]
        jerk::Real, [description = "Jerk, in position units per second cubed"]
    end
    @parameters begin
        q_start::Real = 0.0, [description = "Start position: the output before t_start"]
        q_end::Real = 1.0, [description = "End position, reached exactly when the move stops"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the move starts"]
        v_max::Real = 1.0, [min = 1.0e-12, description = "Largest velocity, in position units per second"]
        a_max::Real = 2.0, [min = 1.0e-12, description = "Largest acceleration and deceleration, in position units per second squared"]
        j_max::Real = 10.0, [min = 1.0e-12, description = "Jerk during the acceleration changes, in position units per second cubed"]
    end
    @variables begin
        dist::Real = 0.0, [description = "Length of the move, |q_end - q_start|"]
        dir::Real = 0.0, [description = "Direction of the move: 1, -1, or 0 for no move"]
        a_v::Real = 0.0, [description = "Peak acceleration of a move that reaches v_max"]
        dist_v::Real = 0.0, [description = "Shortest move that reaches v_max"]
        cruise::Real = 0.0, [description = "1 when the move reaches v_max, else 0"]
        a_peak::Real = 0.0, [description = "Peak acceleration"]
        T_j::Real = 0.0, [unit = "s", description = "Duration of each jerk phase"]
        v_peak::Real = 0.0, [description = "Peak velocity"]
        T_acc::Real = 0.0, [unit = "s", description = "Duration of the acceleration (segments 1-3) and of the deceleration (5-7)"]
        T_cruise::Real = 0.0, [unit = "s", description = "Duration of the constant-velocity segment 4"]
        q_acc::Real = 0.0, [description = "Distance covered during the acceleration, v_peak*T_acc/2"]
        b::Vec{7}, [unit = "s", description = "Switch times: the end of each of the seven segments"]
    end
    @equations begin
        dist ~ abs(q_end - q_start)
        dir ~ sign(q_end - q_start)
        a_v ~ min(a_max, sqrt(v_max * j_max))
        dist_v ~ v_max * (a_v / j_max + v_max / a_v)
        cruise ~ ifelse(dist >= dist_v, 1.0, 0.0)
        a_peak ~ cruise * a_v +
                 (1.0 - cruise) * min(a_max, (max(dist, 1.0e-300) * j_max^2 / 2.0)^(1.0 / 3.0))
        T_j ~ a_peak / j_max
        v_peak ~ cruise * v_max + (1.0 - cruise) * a_peak *
                                  (sqrt(T_j^2 + 4.0 * dist / a_peak) - T_j) / 2.0
        T_acc ~ T_j + v_peak / a_peak
        T_cruise ~ cruise * max(dist / v_max - T_acc, 0.0)
        q_acc ~ v_peak * T_acc / 2.0
        b[1] ~ 2.0 * (0.5 * t_start + 0.5 * T_j)
        b[2] ~ 2.0 * (0.5 * t_start + 0.5 * (T_acc - T_j))
        b[3] ~ 2.0 * (0.5 * t_start + 0.5 * T_acc)
        b[4] ~ 2.0 * (0.5 * t_start + 0.5 * (T_acc + T_cruise))
        b[5] ~ 2.0 * (0.5 * t_start + 0.5 * (T_acc + T_cruise + T_j))
        b[6] ~ 2.0 * (0.5 * t_start + 0.5 * (2.0 * T_acc + T_cruise - T_j))
        b[7] ~ 2.0 * (0.5 * t_start + 0.5 * (2.0 * T_acc + T_cruise))
        # Segment-local times: from the start (1, 2), to the end of the acceleration (3), from
        # the start of the deceleration (4, 5) and to the end of the move (6, 7).
        q ~ ifelse(
            t < b[3],
            ifelse(
                t < b[1],
                ifelse(t < t_start, q_start, q_start + dir * j_max * (t - t_start)^3 / 6.0),
                ifelse(
                    t < b[2],
                    q_start + dir * a_peak *
                              ((t - t_start)^2 / 2.0 - T_j * (t - t_start) / 2.0 + T_j^2 / 6.0),
                    q_start + dir * (q_acc - v_peak * (b[3] - t) + j_max * (b[3] - t)^3 / 6.0),
                ),
            ),
            ifelse(
                t < b[5],
                ifelse(
                    t < b[4],
                    q_start + dir * (q_acc + v_peak * (t - b[3])),
                    q_end - dir * (q_acc - v_peak * (t - b[4]) + j_max * (t - b[4])^3 / 6.0),
                ),
                ifelse(
                    t < b[6],
                    q_end - dir * a_peak *
                            ((b[7] - t)^2 / 2.0 - T_j * (b[7] - t) / 2.0 + T_j^2 / 6.0),
                    ifelse(t < b[7], q_end - dir * j_max * (b[7] - t)^3 / 6.0, q_end),
                ),
            ),
        )
        v ~ dir * ifelse(
            t < b[3],
            ifelse(
                t < b[1],
                ifelse(t < t_start, 0.0, j_max * (t - t_start)^2 / 2.0),
                ifelse(
                    t < b[2],
                    a_peak * (t - t_start - T_j / 2.0),
                    v_peak - j_max * (b[3] - t)^2 / 2.0,
                ),
            ),
            ifelse(
                t < b[5],
                ifelse(t < b[4], v_peak, v_peak - j_max * (t - b[4])^2 / 2.0),
                ifelse(
                    t < b[6],
                    a_peak * (b[7] - t - T_j / 2.0),
                    ifelse(t < b[7], j_max * (b[7] - t)^2 / 2.0, 0.0),
                ),
            ),
        )
        a ~ dir * ifelse(
            t < b[3],
            ifelse(
                t < b[1],
                ifelse(t < t_start, 0.0, j_max * (t - t_start)),
                ifelse(t < b[2], a_peak, j_max * (b[3] - t)),
            ),
            ifelse(
                t < b[5],
                ifelse(t < b[4], 0.0, -j_max * (t - b[4])),
                ifelse(t < b[6], -a_peak, ifelse(t < b[7], -j_max * (b[7] - t), 0.0)),
            ),
        )
        jerk ~ dir * ifelse(
            t < b[3],
            ifelse(
                t < b[1],
                ifelse(t < t_start, 0.0, j_max),
                ifelse(t < b[2], 0.0, -j_max),
            ),
            ifelse(
                t < b[5],
                ifelse(t < b[4], 0.0, -j_max),
                ifelse(t < b[6], 0.0, ifelse(t < b[7], j_max, 0.0)),
            ),
        )
    end
end
