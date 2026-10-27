@block Tank begin
    @ports a::Power{Hydraulic}
    @parameters p::Real = 1.0e5, [unit = "Pa", description = "Tank pressure"]
    @equations a.e ~ p
    @causality a => (:effort_out, :fixed)
end
