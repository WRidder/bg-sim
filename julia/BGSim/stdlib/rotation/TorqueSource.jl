@block TorqueSource begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @inputs u::Real
    @parameters T::Real = 1.0, [unit = "N*m", description = "Torque gain on the control input"]
    @equations begin
        a.e ~ T * u
        b.e ~ -a.e
    end
end
