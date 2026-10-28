@block DfPlanar begin
    @ports p::Power{Planar}
    @outputs y::Vec{3}
    @equations begin
        p.e[1] ~ 0.0
        p.e[2] ~ 0.0
        p.e[3] ~ 0.0
        y[1] ~ p.f[1]
        y[2] ~ p.f[2]
        y[3] ~ p.f[3]
    end
    @causality p => (:effort_out, :fixed)
end
