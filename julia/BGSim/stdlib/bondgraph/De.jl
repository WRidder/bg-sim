@block De begin
    @ports p::Power{Generic}
    @outputs y::Real
    @equations begin
        p.f ~ 0.0
        y ~ p.e
    end
    @causality p => (:effort_out, :fixed)
end
