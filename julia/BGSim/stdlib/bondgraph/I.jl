@block I begin
    @ports p::Power{Generic}
    @parameters i::Real = 1.0, [unit = "effort*s/flow", min = 0, description = "Inertia"]
    @variables P::Real = 0.0, [unit = "effort*s", state = :prefer, description = "Momentum"]
    @equations begin
        ddt(P) ~ p.e
        p.f ~ P / i
    end
    @causality p => :flow_out
end
