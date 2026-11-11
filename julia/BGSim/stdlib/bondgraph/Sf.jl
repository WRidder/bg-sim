@block Sf begin
    @ports p::Power{Generic}
    @parameters f::Real = 1.0, [unit = "flow", description = "Flow value"]
    # Port flows count into the block, so a source that delivers the flow f imposes
    # p.f = -f: bonded from the source to a junction (the declared `out`), the junction
    # receives +f.
    @equations p.f ~ -f
    @causality p => (:flow_out, :fixed)
    @orientation p => :out
end
