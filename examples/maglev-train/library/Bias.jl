@block Bias begin
    # Adds a constant: y = u + b (here the gap deviation from the nominal gap, b = -h_nom).
    @inputs u::Real
    @outputs y::Real
    @parameters b::Real = 0.0, [description = "Offset added to the input"]
    @equations y ~ u + b
end
