@block Pack3 begin
    # Three scalar signals into a Vec{3}.
    @inputs begin
        u1::Real
        u2::Real
        u3::Real
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ u1
        y[2] ~ u2
        y[3] ~ u3
    end
end
