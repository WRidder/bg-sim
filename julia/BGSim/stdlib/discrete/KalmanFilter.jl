@block KalmanFilter begin
    # Time-varying discrete Kalman filter for the plant of DiscreteSS with noise,
    #   x[k+1] = A*x[k] + B*u[k] + w[k],  y[k] = C'*x[k] + D*u[k] + v[k],
    # w ~ N(0, Q) and v ~ N(0, R), on the clock sample_period. At each tick the measurement y
    # corrects the prediction x (the "current estimator"), then the model predicts the next
    # tick:
    #   S = C'*P*C + R,  K = P*C / S,  x_hat = x + K*(y - C'*x - D*u),  Pf = P - K*(P*C)'
    #   x = A*x_hat + B*u,  P = A*Pf*A' + Q (kept symmetric).
    # x_hat is the filtered estimate x[k|k] and y_hat = C'*x_hat + D*u. P converges to the
    # steady-state filter's covariance, so the gain K becomes the steady-state Kalman gain.
    # The prediction x and its covariance P start at their start values (zero state and the
    # identity by default: set the start of P to the initial uncertainty).
    @constants N::Int = 2, [min = 1, description = "Number of states"]
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs begin
        u::Real, [description = "Plant input"]
        y::Real, [description = "Measured plant output"]
    end
    @outputs begin
        x_hat::Vec{N} = [0.0, 0.0], [description = "Filtered state estimate x[k|k]"]
        y_hat::Real = 0.0, [description = "Filtered output estimate C'*x_hat + D*u"]
    end
    @parameters begin
        A::Mat{N,N} = [1.0 0.001; 0.0 1.0], [description = "Plant state matrix A"]
        B::Vec{N} = [0.0, 0.001], [description = "Plant input vector B"]
        C::Vec{N} = [1.0, 0.0], [description = "Plant output vector C"]
        D::Real = 0.0, [description = "Plant feedthrough D"]
        Q::Mat{N,N} = [1.0e-6 0.0; 0.0 1.0e-4], [description = "Process noise covariance"]
        R::Real = 1.0e-2, [min = 1.0e-300, description = "Measurement noise variance"]
    end
    @variables begin
        x::Vec{N} = [0.0, 0.0], [description = "Predicted state x[k|k-1]"]
        P::Mat{N,N} = [1.0 0.0; 0.0 1.0], [description = "Predicted error covariance P[k|k-1]"]
        K::Vec{N} = [0.0, 0.0], [description = "Kalman gain of the last tick"]
    end
    @discrete Ts = sample_period begin
        pc = P * C
        K = pc / (dot(C, pc) + R)
        xf = x + K * (y - dot(C, x) - D * u)
        pf = P
        for i in 1:N
            for j in 1:N
                pf[i, j] = P[i, j] - K[i] * pc[j]
            end
        end
        x_hat = xf
        y_hat = dot(C, xf) + D * u
        x = A * xf + B * u
        # pn = A*pf*A' + Q, then P its symmetric part (rounding keeps P symmetric).
        pn = Q
        for i in 1:N
            for j in 1:N
                s = 0.0
                for k in 1:N
                    for l in 1:N
                        s = s + A[i, k] * pf[k, l] * A[j, l]
                    end
                end
                pn[i, j] = s + Q[i, j]
            end
        end
        for i in 1:N
            for j in 1:N
                P[i, j] = 0.5 * (pn[i, j] + pn[j, i])
            end
        end
    end
end
