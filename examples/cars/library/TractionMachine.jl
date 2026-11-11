@block TractionMachine begin
    # Inverter and traction motor as one power-conserving modulated transformer between the DC
    # bus and the rotor: shaft torque = u x bus voltage, bus current = u x rotor speed (the MTF
    # of the bond graph with an electrical and a rotational port). Power positive into each
    # port: shaft.e shaft.f + dc.e dc.f = 0. The modulus u (N m per volt) comes from
    # `EMotorControl`; the losses are elsewhere (the battery resistance, the rotor drag).
    @ports begin
        shaft::Power{Rotation}
        dc::Power{Electrical}
    end
    @inputs u::Real, [unit = "N*m/V", description = "Modulus: torque per bus volt (= current per rad/s)"]
    @equations begin
        shaft.e ~ u * dc.e
        dc.f ~ -u * shaft.f
    end
    @causality (shaft, dc) => :transformer
    @orientation (dc, shaft) => :through
end
