@block Df begin
    @ports p::Power{Generic}
    @outputs y::Real
    @equations begin
        p.e ~ 0.0
        y ~ p.f
    end
    @causality p => (:flow_out, :fixed)
end
