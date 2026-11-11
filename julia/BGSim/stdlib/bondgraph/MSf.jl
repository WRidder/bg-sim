@block MSf begin
    @ports p::Power{Generic}
    @inputs u::Real
    @parameters gain::Real = 1.0, [unit = "flow", description = "Flow gain on the input"]
    # Port flows count into the block, so a source that delivers the flow gain*u imposes
    # p.f = -gain*u: bonded from the source to a junction (the declared `out`), the junction
    # receives +gain*u.
    @equations p.f ~ -gain * u
    @causality p => (:flow_out, :fixed)
    @orientation p => :out
end
