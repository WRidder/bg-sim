@block Bias begin
    # Adds a constant: y = u + b. Turns the absolute current into the deviation input of a
    # frozen linear model (b = -i_trim) and its deviation output back into a gap (b = p).
    @inputs u::Real
    @outputs y::Real
    @parameters b::Real = 0.0, [description = "Offset added to the input"]
    @equations y ~ u + b
end
