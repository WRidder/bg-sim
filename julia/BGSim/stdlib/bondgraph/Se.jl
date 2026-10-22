@block Se begin
    @ports p::Power{Generic}
    @parameters e::Real = 1.0, [unit = "effort", description = "Effort value"]
    @equations p.e ~ e
    @causality p => (:effort_out, :fixed)
end
