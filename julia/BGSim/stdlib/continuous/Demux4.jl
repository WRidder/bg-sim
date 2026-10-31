@block Demux4 begin
    # A four-element vector as four scalar signals, y1..y4 = u[1]..u[4] (Simulink's Demux);
    # the inverse of Mux4. Select takes one element of a vector of any size.
    @inputs u::Vec{4}
    @outputs begin
        y1::Real, [description = "Element 1 of the input"]
        y2::Real, [description = "Element 2 of the input"]
        y3::Real, [description = "Element 3 of the input"]
        y4::Real, [description = "Element 4 of the input"]
    end
    @equations begin
        y1 ~ u[1]
        y2 ~ u[2]
        y3 ~ u[3]
        y4 ~ u[4]
    end
end
