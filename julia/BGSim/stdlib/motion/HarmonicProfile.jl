@block HarmonicProfile begin
    # Harmonic (cosine) point-to-point move from q_start to q_end in `duration` seconds
    # (20-sim's motion profile library; Biagiotti and Melchiorri section 2.2.1). With x =
    # (t - t_start)/duration in [0, 1] and h = q_end - q_start:
    #   q = q_start + h/2*(1 - cos(pi*x))
    #   v = pi*h/(2*duration)*sin(pi*x)
    #   a = pi^2*h/(2*duration^2)*cos(pi*x)
    # Position and velocity are continuous; the acceleration jumps at the start and at the
    # end (use CycloidalProfile or PolynomialProfile for a continuous acceleration). Before
    # t_start the outputs are q_start and 0, from t_start + duration on q_end (exactly) and
    # 0. The end switch time is the product 2*(0.5*t_start + 0.5*duration), one atom in the
    # event condition, as in TrapezoidalProfile.
    @outputs begin
        q::Real, [description = "Position"]
        v::Real, [description = "Velocity, in position units per second"]
        a::Real, [description = "Acceleration, in position units per second squared"]
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
            ifelse(t < t_stop, q_start + h / 2.0 * (1.0 - cos(3.141592653589793 * x)), q_end),
        )
        v ~ ifelse(
            t < t_start || t >= t_stop,
            0.0,
            1.5707963267948966 * h / duration * sin(3.141592653589793 * x),
        )
        a ~ ifelse(
            t < t_start || t >= t_stop,
            0.0,
            4.934802200544679 * h / duration^2 * cos(3.141592653589793 * x),
        )
    end
end
