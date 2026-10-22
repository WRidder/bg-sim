@block ForceSource begin
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @inputs u::Real
    @parameters F::Real = 1.0, [unit = "N", description = "Force gain on the control input"]
    @equations begin
        a.e ~ F * u
        b.e ~ -a.e
    end
end
