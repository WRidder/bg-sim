@block Capacitor begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
    end
    @parameters C::Real = 1e-6, [unit = "F", min = 0, description = "Capacitance"]
    @variables v::Real = 0.0, [unit = "V", state = :prefer, description = "Voltage across the capacitor"]
    @equations begin
        p.f + n.f ~ 0.0
        ddt(v) ~ p.f / C
        p.e - n.e ~ v
    end
end
