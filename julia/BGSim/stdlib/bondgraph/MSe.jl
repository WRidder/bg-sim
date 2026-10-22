@block MSe begin
    @ports p::Power{Generic}
    @inputs u::Real
    @parameters gain::Real = 1.0, [unit = "effort", description = "Effort gain on the input"]
    @equations p.e ~ gain * u
    @causality p => (:effort_out, :fixed)
end
