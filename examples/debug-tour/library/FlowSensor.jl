@block FlowSensor begin
    @ports p::Power{Translation}
    @orientation p => :in
    @outputs y::Real = 0.0
    @equations begin
        p.e ~ 0.0
        y ~ p.f
    end
    @causality p => (:effort_out, :fixed)
end
