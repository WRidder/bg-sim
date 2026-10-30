@block Unpack4 begin
    # A Vec{4} into four scalar signals.
    @inputs u::Vec{4}
    @outputs begin
        y1::Real
        y2::Real
        y3::Real
        y4::Real
    end
    @equations begin
        y1 ~ u[1]
        y2 ~ u[2]
        y3 ~ u[3]
        y4 ~ u[4]
    end
end
