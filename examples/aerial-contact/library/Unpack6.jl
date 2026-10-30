@block Unpack6 begin
    # A Vec{6} into six scalar signals.
    @inputs u::Vec{6}
    @outputs begin
        y1::Real
        y2::Real
        y3::Real
        y4::Real
        y5::Real
        y6::Real
    end
    @equations begin
        y1 ~ u[1]
        y2 ~ u[2]
        y3 ~ u[3]
        y4 ~ u[4]
        y5 ~ u[5]
        y6 ~ u[6]
    end
end
