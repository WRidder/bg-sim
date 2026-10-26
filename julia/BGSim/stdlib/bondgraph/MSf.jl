@block MSf begin
    @ports p::Power{Generic}
    @inputs u::Real
    @parameters gain::Real = 1.0, [unit = "flow", description = "Flow gain on the input"]
    @equations p.f ~ gain * u
    @causality p => (:flow_out, :fixed)
end
