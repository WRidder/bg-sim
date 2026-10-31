@block Luenberger begin
    # Luenberger state observer for the SISO plant x' = A*x + B*u, y = C*x + D*u (the
    # StateSpace block): from the plant input u and the measured output y it estimates
    #   x_hat' = A*x_hat + B*u + L*(y - y_hat),  y_hat = C*x_hat + D*u.
    # The estimation error e = x - x_hat obeys e' = (A - L*C')*e, so place the eigenvalues of
    # A - L*C' (left of the plant's, for a fast observer) with the gain L. The estimate starts
    # at the start value of x (zero by default).
    @constants N::Int = 2, [min = 1, description = "Number of states"]
    @inputs begin
        u::Real, [description = "Plant input"]
        y::Real, [description = "Measured plant output"]
    end
    @outputs begin
        x_hat::Vec{N}, [description = "Estimated plant state"]
        y_hat::Real, [description = "Estimated plant output C*x_hat + D*u"]
    end
    @parameters begin
        A::Mat{N,N} = [0.0 1.0; -1.0 -2.0], [description = "Plant state matrix A (the default is the StateSpace default)"]
        B::Vec{N} = [0.0, 1.0], [description = "Plant input vector B"]
        C::Vec{N} = [1.0, 0.0], [description = "Plant output vector C"]
        D::Real = 0.0, [description = "Plant feedthrough D"]
        L::Vec{N} = [9.0, 11.0], [description = "Observer gain; the error dynamics are A - L*C' (the default puts its eigenvalues at -5 and -6)"]
    end
    @variables x::Vec{N} = [0.0, 0.0], [description = "Observer state (the estimate)"]
    @equations begin
        ddt(x) ~ A * x + B * u + L * (y - y_hat)
        y_hat ~ dot(C, x) + D * u
        x_hat ~ x
    end
end
