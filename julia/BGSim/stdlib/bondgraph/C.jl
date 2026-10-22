@block C begin
    @ports p::Power{Generic}
    @parameters c::Real = 1.0, [unit = "flow*s/effort", min = 0, description = "Compliance"]
    @variables q::Real = 0.0, [unit = "flow*s", state = :prefer, description = "Displacement"]
    @equations begin
        ddt(q) ~ p.f
        p.e ~ q / c
    end
    @causality p => :effort_out
end
