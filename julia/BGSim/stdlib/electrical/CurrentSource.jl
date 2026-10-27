@block CurrentSource begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @inputs u::Real
    @parameters I::Real = 1.0, [unit = "A", description = "Current gain on the control input"]
    @equations begin
        p.f ~ I * u
        p.f + n.f ~ 0.0
    end
    @causality p => (:flow_out, :fixed)
end
