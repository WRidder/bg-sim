@block Demux2 begin
    # A two-element vector as two scalar signals, y1 = u[1], y2 = u[2] (Simulink's Demux);
    # the inverse of Mux2. Select takes one element of a vector of any size.
    @inputs u::Vec{2}
    @outputs begin
        y1::Real, [description = "Element 1 of the input"]
        y2::Real, [description = "Element 2 of the input"]
    end
    @equations begin
        y1 ~ u[1]
        y2 ~ u[2]
    end
end
