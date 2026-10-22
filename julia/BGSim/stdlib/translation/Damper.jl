@block Damper begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters d::Real = 10.0, [unit = "N*s/m", min = 0, description = "Damping coefficient"]
    @equations begin
        a.e ~ d * (a.f - b.f)
        b.e ~ -a.e
    end
end
