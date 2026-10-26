@block Relay begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        hi::Real = 0.5, [tunable = true, description = "Input threshold that turns the relay on"]
        lo::Real = -0.5, [tunable = true, description = "Input threshold that turns the relay off"]
        on_value::Real = 1.0, [tunable = true, description = "Output while the relay is on"]
        off_value::Real = 0.0, [tunable = true, description = "Output while the relay is off"]
        leak::Real = 0.0, [min = 0, description = "Held-state leak rate (0 holds exactly)"]
    end
    @variables s::Real = 0.0, [description = "Held relay state"]
    @equations begin
        ddt(s) ~ -leak * s
        y ~ s
    end
    @events begin
        u > hi => begin
            reinit(s, on_value)
        end
        u < lo => begin
            reinit(s, off_value)
        end
    end
end
