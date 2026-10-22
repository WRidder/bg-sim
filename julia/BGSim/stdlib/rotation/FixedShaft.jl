@block FixedShaft begin
    @ports a::Power{Rotation}
    @equations a.f ~ 0.0
    @causality a => (:flow_out, :fixed)
end
