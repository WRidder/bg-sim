@block GrowthRate begin
    # Instantaneous growth rate of a pitch-attitude deviation, lambda = q/(theta - theta0).
    #
    # On a pure linear mode every state grows as exp(lambda t); for the pitch angle the
    # kinematics give d(theta)/dt = q exactly in wings-level flight, so q/(theta - theta0) is the
    # mode's eigenvalue without differentiating anything numerically. An airframe released on the
    # unstable eigenvector reads its unstable pole here while the deviation is small.
    @inputs begin
        q::Real, [unit = "rad/s", description = "Pitch rate (body, FRD)"]
        theta::Real, [unit = "rad", description = "Pitch angle"]
    end
    @outputs lambda::Real, [unit = "1/s", description = "Growth rate q/(theta - theta0)"]
    @parameters theta0::Real = 0.0, [unit = "rad", description = "Trim pitch angle"]
    @equations lambda ~ q / (theta - theta0)
end
