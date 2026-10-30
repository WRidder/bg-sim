@block Gust begin
    # First-order lag of a 3-vector signal (the wind gusts reach the airframe smoothed).
    @inputs u::Vec{3}
    @outputs y::Vec{3}
    @parameters tau::Real = 1.0, [unit = "s", min = 1.0e-9, description = "Time constant"]
    @variables x::Vec{3} = [0.4, -0.2, 0.0], [description = "Lag state (starts at the mean wind)"]
    @equations begin
        ddt(x[1]) ~ (u[1] - x[1]) / tau
        ddt(x[2]) ~ (u[2] - x[2]) / tau
        ddt(x[3]) ~ (u[3] - x[3]) / tau
        y[1] ~ x[1]
        y[2] ~ x[2]
        y[3] ~ x[3]
    end
end
