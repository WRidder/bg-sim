@block Time begin
    @outputs y::Real, [unit = "s", description = "Simulation time"]
    @equations y ~ t
end
