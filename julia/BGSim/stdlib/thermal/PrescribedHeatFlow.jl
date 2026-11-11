@block PrescribedHeatFlow begin
    @ports a::Power{Thermal}
    @inputs Q::Real, [unit = "W"]
    @equations begin
        # Port flows count into the block, so injecting Q into the network is a.f = -Q.
        a.f ~ -Q
    end
    @causality a => (:flow_out, :fixed)
    @orientation a => :in
end
