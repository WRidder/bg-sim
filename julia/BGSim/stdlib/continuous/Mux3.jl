@block Mux3 begin
    # Three scalar signals as one vector, y = [u1, u2, u3] (Simulink's Mux), for the blocks
    # with a vector input (Sum, Product, Scope, MultiportSwitch, ...). Demux3 splits it again.
    @inputs begin
        u1::Real, [description = "Element 1 of the output"]
        u2::Real, [description = "Element 2 of the output"]
        u3::Real, [description = "Element 3 of the output"]
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ u1
        y[2] ~ u2
        y[3] ~ u3
    end
end
