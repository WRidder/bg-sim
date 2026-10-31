@block PolynomialProfile begin
    # Quintic (3-4-5) polynomial point-to-point move from q_start to q_end in `duration`
    # seconds, with zero velocity and acceleration at both ends (20-sim's motion profile
    # library; Biagiotti and Melchiorri section 2.1.4). With x = (t - t_start)/duration in
    # [0, 1] and h = q_end - q_start:
    #   q = q_start + h*(10*x^3 - 15*x^4 + 6*x^5)
    #   v = h/duration*30*x^2*(1 - x)^2
    #   a = h/duration^2*60*x*(1 - x)*(1 - 2*x)
    #   jerk = h/duration^3*60*(1 - 6*x + 6*x^2)
    # The peak velocity is 1.875*h/duration and the peak acceleration 5.7735*h/duration^2.
    # Position, velocity and acceleration are continuous; the jerk jumps at the start and at
    # the end. Before t_start the outputs are q_start and 0, from t_start + duration on q_end
    # (exactly) and 0. The end switch time is the product 2*(0.5*t_start + 0.5*duration),
    # one atom in the event condition, as in TrapezoidalProfile.
    @outputs begin
        q::Real, [description = "Position"]
        v::Real, [description = "Velocity, in position units per second"]
        a::Real, [description = "Acceleration, in position units per second squared"]
        jerk::Real, [description = "Jerk, in position units per second cubed"]
    end
    @parameters begin
        q_start::Real = 0.0, [description = "Start position: the output before t_start"]
        q_end::Real = 1.0, [description = "End position, reached exactly at t_start + duration"]
        t_start::Real = 0.0, [unit = "s", description = "Time at which the move starts"]
        duration::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Duration of the move"]
    end
    @variables begin
        t_stop::Real = 0.0, [unit = "s", description = "Time at which the move ends"]
        x::Real = 0.0, [description = "Fraction of the move, (t - t_start)/duration while it runs"]
        h::Real = 0.0, [description = "Signed length of the move, q_end - q_start"]
    end
    @equations begin
        t_stop ~ 2.0 * (0.5 * t_start + 0.5 * duration)
        x ~ (t - t_start) / duration
        h ~ q_end - q_start
        q ~ ifelse(
            t < t_start,
            q_start,
            ifelse(t < t_stop, q_start + h * x^3 * (10.0 - 15.0 * x + 6.0 * x^2), q_end),
        )
        v ~ ifelse(
            t < t_start || t >= t_stop,
            0.0,
            30.0 * h / duration * x^2 * (1.0 - x)^2,
        )
        a ~ ifelse(
            t < t_start || t >= t_stop,
            0.0,
            60.0 * h / duration^2 * x * (1.0 - x) * (1.0 - 2.0 * x),
        )
        jerk ~ ifelse(
            t < t_start || t >= t_stop,
            0.0,
            60.0 * h / duration^3 * (1.0 - 6.0 * x + 6.0 * x^2),
        )
    end
end
