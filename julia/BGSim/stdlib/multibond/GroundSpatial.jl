@block GroundSpatial begin
    # Spatial reference node: holds its port at zero twist in the world frame.
    @ports p::Power{Spatial}, [frame = "world"]
    @equations begin
        p.f[1] ~ 0.0
        p.f[2] ~ 0.0
        p.f[3] ~ 0.0
        p.f[4] ~ 0.0
        p.f[5] ~ 0.0
        p.f[6] ~ 0.0
    end
    @causality p => (:flow_out, :fixed)
end
