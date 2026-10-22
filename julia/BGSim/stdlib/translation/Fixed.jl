@block Fixed begin
    @ports a::Power{Translation}
    @equations a.f ~ 0.0
    @causality a => (:flow_out, :fixed)
end
