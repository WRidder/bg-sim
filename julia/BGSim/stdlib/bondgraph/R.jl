@block R begin
    @ports p::Power{Generic}
    @parameters r::Real = 1.0, [unit = "effort/flow", min = 0, description = "Resistance"]
    @equations p.e ~ r * p.f
end
