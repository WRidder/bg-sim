@block GrowthRate begin
    # Instantaneous growth rate of a deviation, lambda = (dx/dt)/(x - x0).
    #
    # On a pure linear mode every state grows as exp(lambda t), so the ratio of a state's rate
    # to its deviation is the mode's eigenvalue without differentiating anything numerically.
    # The Beaver's roll and spiral modes read it from the bank angle and its exact Euler rate.
    @inputs begin
        xdot::Real, [description = "Rate of the state"]
        x::Real, [description = "The state"]
    end
    @outputs lambda::Real, [unit = "1/s", description = "Growth rate xdot/(x - x0)"]
    @parameters x0::Real = 0.0, [description = "Trim value of the state"]
    @equations lambda ~ xdot / (x - x0)
end
