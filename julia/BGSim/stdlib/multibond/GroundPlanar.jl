@block GroundPlanar begin
    @ports p::Power{Planar}, [frame = "world"]
    @equations begin
        p.f[1] ~ 0.0
        p.f[2] ~ 0.0
        p.f[3] ~ 0.0
    end
    @causality p => (:flow_out, :fixed)
end
