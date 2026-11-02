@block MoveSum begin
    # The shaped X reference of the gantry: the sum of six jerk-limited moves (SCurveProfile),
    # three impulses of the input shaper for the move out and three for the move back.
    #
    # An input shaper convolves the move with impulses A_j at times t_j (ZV: two, ZVD: three).
    # A jerk-limited move scaled in distance, velocity, acceleration and jerk by the same A_j
    # keeps its timing, so the convolution is exactly the sum of the six scaled moves, each
    # starting at its impulse time: q = sum q_j, v = sum v_j, a = sum a_j. The amplitudes and
    # delays are global parameters of the model (shaping, f_s, zeta_s).
    @inputs begin
        q1::Real, [unit = "m"]
        q2::Real, [unit = "m"]
        q3::Real, [unit = "m"]
        q4::Real, [unit = "m"]
        q5::Real, [unit = "m"]
        q6::Real, [unit = "m"]
        v1::Real, [unit = "m/s"]
        v2::Real, [unit = "m/s"]
        v3::Real, [unit = "m/s"]
        v4::Real, [unit = "m/s"]
        v5::Real, [unit = "m/s"]
        v6::Real, [unit = "m/s"]
        a1::Real, [unit = "m/s^2"]
        a2::Real, [unit = "m/s^2"]
        a3::Real, [unit = "m/s^2"]
        a4::Real, [unit = "m/s^2"]
        a5::Real, [unit = "m/s^2"]
        a6::Real, [unit = "m/s^2"]
    end
    @outputs begin
        q::Real, [unit = "m", description = "Reference position"]
        v::Real, [unit = "m/s", description = "Reference velocity"]
        a::Real, [unit = "m/s^2", description = "Reference acceleration"]
    end
    @equations begin
        q ~ q1 + q2 + q3 + q4 + q5 + q6
        v ~ v1 + v2 + v3 + v4 + v5 + v6
        a ~ a1 + a2 + a3 + a4 + a5 + a6
    end
end
