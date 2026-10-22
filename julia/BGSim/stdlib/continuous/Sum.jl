@block Sum begin
    @constants N::Int = 2
    @inputs u::Vec{N}
    @outputs y::Real
    @parameters signs::Vec{N} = [1.0, 1.0], [description = "Sign of every input, +1 or -1"]
    @equations y ~ dot(signs, u)
end
