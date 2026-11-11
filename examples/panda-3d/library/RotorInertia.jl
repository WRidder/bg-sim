@block RotorInertia begin
    # Motor-side rotor inertia of a Panda joint drive: the bond-graph I element of the stdlib with a
    # rotational port. The stdlib `I` is Generic, and the motor side of the gear (source, rotor,
    # 1-junction) holds no other concrete element, so its island would stay Generic and the TF
    # between it and the Rotation link side could not adopt one domain (E102). Same law as `I`.
    @ports p::Power{Rotation}
    @orientation p => :in
    @parameters i::Real = 1.0e-4, [unit = "kg*m^2", min = 0, description = "Rotor inertia (motor side)"]
    @variables P::Real = 0.0, [unit = "N*m*s", state = :prefer, description = "Rotor angular momentum"]
    @equations begin
        ddt(P) ~ p.e
        p.f ~ P / i
    end
    @causality p => :flow_out
end
