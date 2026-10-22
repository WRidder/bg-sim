@block Sf begin
    @ports p::Power{Generic}
    @parameters f::Real = 1.0, [unit = "flow", description = "Flow value"]
    @equations p.f ~ f
    @causality p => (:flow_out, :fixed)
end
