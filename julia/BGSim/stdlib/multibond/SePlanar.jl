@block SePlanar begin
    @ports p::Power{Planar}
    @inputs u::Vec{3}
    @equations begin
        p.e[1] ~ u[1]
        p.e[2] ~ u[2]
        p.e[3] ~ u[3]
    end
    @causality p => (:effort_out, :fixed)
end
