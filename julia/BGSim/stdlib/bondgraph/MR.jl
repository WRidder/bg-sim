@block MR begin
    @ports p::Power{Generic}
    @inputs u::Real
    @parameters gain::Real = 1.0, [unit = "effort/flow", description = "Resistance gain on the input; the modulated resistance is gain*u"]
    @equations p.e ~ gain * u * p.f
end
