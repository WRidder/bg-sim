@block Mass begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters m::Real = 1.0, [unit = "kg", min = 0, description = "Mass"]
    @variables begin
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Relative position"]
        v::Real = 0.0, [unit = "m/s", state = :prefer, description = "Relative velocity"]
    end
    @equations begin
        v ~ a.f - b.f
        ddt(x) ~ v
        a.e ~ m * ddt(v)
        b.e ~ -a.e
    end
end
