@block StateSpace begin
    # Continuous SISO state space x' = A*x + B*u, y = C'*x + D*u.
    #
    # The feedthrough D is a structural constant, not a parameter: D = 0 (the default) folds
    # the D*u term away at compile time, so the block is strictly proper and closes no
    # algebraic loop, as in Simulink. Any other D keeps the direct feedthrough. A, B and C
    # stay runtime parameters.
    @constants begin
        N::Int = 2
        D::Real = 0.0, [structural = true, description = "Feedthrough D (structural: 0 means no direct feedthrough)"]
    end
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        A::Mat{N,N} = [0.0 1.0; -1.0 -2.0], [description = "State matrix A"]
        B::Vec{N} = [0.0, 1.0], [description = "Input vector B"]
        C::Vec{N} = [1.0, 0.0], [description = "Output vector C"]
    end
    @variables x::Vec{N} = [0.0, 0.0], [description = "State vector"]
    @equations begin
        ddt(x) ~ A * x + B * u
        y ~ dot(C, x) + D * u
    end
end
