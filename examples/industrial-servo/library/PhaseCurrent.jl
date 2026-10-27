@block PhaseCurrent begin
    # A recording sensor: the peak phase-current amplitude sqrt(i_d^2 + i_q^2) of the dq
    # currents (amplitude-invariant Park transform).  Not part of the plant.
    @inputs begin
        id::Real, [unit = "A"]
        iq::Real, [unit = "A"]
    end
    @outputs y::Real = 0.0, [unit = "A"]
    @equations y ~ sqrt(id * id + iq * iq)
end
