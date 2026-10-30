@block Pack4 begin
    # Four scalar signals into a Vec{4}.
    @inputs begin
        u1::Real
        u2::Real
        u3::Real
        u4::Real
    end
    @outputs y::Vec{4}
    @equations begin
        y[1] ~ u1
        y[2] ~ u2
        y[3] ~ u3
        y[4] ~ u4
    end
end
