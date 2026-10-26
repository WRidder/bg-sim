@block StateSpace begin
    @constants N::Int = 2
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        A::Mat{N,N} = [0.0 1.0; -1.0 -2.0], [description = "State matrix A"]
        B::Vec{N} = [0.0, 1.0], [description = "Input vector B"]
        C::Vec{N} = [1.0, 0.0], [description = "Output vector C"]
        D::Real = 0.0, [description = "Feedthrough D"]
    end
    @variables x::Vec{N} = [0.0, 0.0], [description = "State vector"]
    @equations begin
        ddt(x) ~ A * x + B * u
        y ~ dot(C, x) + D * u
    end
end
