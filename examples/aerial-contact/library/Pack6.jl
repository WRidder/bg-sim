@block Pack6 begin
    # Six scalar signals into a Vec{6}.
    @inputs begin
        u1::Real
        u2::Real
        u3::Real
        u4::Real
        u5::Real
        u6::Real
    end
    @outputs y::Vec{6}
    @equations begin
        y[1] ~ u1
        y[2] ~ u2
        y[3] ~ u3
        y[4] ~ u4
        y[5] ~ u5
        y[6] ~ u6
    end
end
