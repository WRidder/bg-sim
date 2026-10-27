@block DiscreteSS begin
    @constants N::Int = 2
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Output of the discrete state-space model"]
    @parameters begin
        A::Mat{N,N} = [0.5 0.25; 0.0 0.5], [description = "State matrix A"]
        B::Vec{N} = [1.0, 0.0], [description = "Input vector B"]
        C::Vec{N} = [1.0, 1.0], [description = "Output vector C"]
        D::Real = 0.0, [description = "Feedthrough D"]
    end
    @variables x::Vec{N} = [0.0, 0.0], [description = "Discrete state vector"]
    @discrete Ts = sample_period begin
        x = A * x + B * u
        y = dot(C, x) + D * u
    end
end
