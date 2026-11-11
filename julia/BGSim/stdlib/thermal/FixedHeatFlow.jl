@block FixedHeatFlow begin
    @ports a::Power{Thermal}
    @parameters Q::Real = 1.0, [unit = "W", description = "Heat flow injected into the network at a"]
    @equations begin
        # Port flows count into the block, so injecting Q into the network is a.f = -Q.
        a.f ~ -Q
    end
    @causality a => (:flow_out, :fixed)
    @orientation a => :in
end
