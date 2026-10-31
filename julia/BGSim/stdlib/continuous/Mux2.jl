@block Mux2 begin
    # Two scalar signals as one vector, y = [u1, u2] (Simulink's Mux), for the blocks with a
    # vector input (Sum, Product, Scope, MultiportSwitch, ...). Demux2 splits it again.
    @inputs begin
        u1::Real, [description = "Element 1 of the output"]
        u2::Real, [description = "Element 2 of the output"]
    end
    @outputs y::Vec{2}
    @equations begin
        y[1] ~ u1
        y[2] ~ u2
    end
end
