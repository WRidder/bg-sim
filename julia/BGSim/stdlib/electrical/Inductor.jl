@block Inductor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @parameters L::Real = 1e-3, [unit = "H", min = 0, description = "Inductance"]
    @variables i::Real = 0.0, [unit = "A", state = :prefer, description = "Current through the inductor"]
    @equations begin
        p.f + n.f ~ 0.0
        ddt(i) ~ (p.e - n.e) / L
        p.f ~ i
    end
end
