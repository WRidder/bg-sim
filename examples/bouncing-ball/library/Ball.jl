@block Ball begin
    @parameters begin
        g::Real = 9.81, [unit = "m/s^2"]
        e::Real = 0.8, [min = 0, max = 1, description = "restitution"]
    end
    @variables begin
        h::Real = 1.0, [unit = "m"]
        v::Real = 0.0, [unit = "m/s"]
    end
    @outputs height::Real
    @equations begin
        ddt(h) ~ v
        ddt(v) ~ -g
        height ~ h
    end
    @events begin
        h < 0 => begin
            reinit(v, -e * v)
        end
    end
end
