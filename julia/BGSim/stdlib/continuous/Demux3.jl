@block Demux3 begin
    # A three-element vector as three scalar signals, y1..y3 = u[1]..u[3] (Simulink's Demux);
    # the inverse of Mux3. Select takes one element of a vector of any size.
    @inputs u::Vec{3}
    @outputs begin
        y1::Real, [description = "Element 1 of the input"]
        y2::Real, [description = "Element 2 of the input"]
        y3::Real, [description = "Element 3 of the input"]
    end
    @equations begin
        y1 ~ u[1]
        y2 ~ u[2]
        y3 ~ u[3]
    end
end
