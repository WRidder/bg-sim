@block LQGController begin
    # Plan 9.5's discrete LQG firmware at Ts = 1 ms. `design/design.py` writes the
    # matrices below into the model document; the defaults here are only a shape-valid
    # placeholder so the block can be inspected before the design has been run.
    #
    # xhat = [theta_m, omega_m, theta_L, omega_L, T_load_hat]
    # The first four states are the plan's; the fifth is a random-walk load-torque
    # state, without which the Kalman filter biases the load speed under the
    # 0.5 N m step and cannot meet the estimation check (see the README).
    @constants begin
        nx::Int = 5
        nu::Int = 1
        ny::Int = 1
    end
    @parameters begin
        Ad::Mat{nx,nx} = [0.996 0.001 0.0 0.0 0.0; 0.0 0.84 0.0 0.0 0.0; 0.0 0.0 0.988 0.001 0.0; 0.0 0.0 0.0 0.978 0.0; 0.0 0.0 0.0 0.0 1.0], [description = "Discrete state matrix (5 states: the plan's 4 plus the load torque)"]
        Bd::Vec{nx} = [0.0, 1.5, 0.0, 0.0, 0.0], [description = "Discrete input vector (volts)"]
        Cd::Vec{nx} = [1.0, 0.0, 0.0, 0.0, 0.0], [description = "Measurement vector: the motor angle"]
        L::Vec{nx} = [0.3, 60.0, 0.2, 10.0, -5.0], [description = "Steady-state Kalman gain"]
        K::Vec{nx} = [170.0, 0.4, -1700.0, 12.0, 0.0], [description = "LQR state gain, absolute states; the 5th entry is zero"]
        Ki::Real = 200.0, [description = "Integral gain on the load-speed error"]
        Kff::Real = 17.0, [unit = "V*s/rad", description = "Reference feedforward: back-EMF k*n plus the speed-feedback cancellation"]
        umax::Real = 24.0, [unit = "V", min = 0.0, description = "Voltage limit"]
    end
    @inputs begin
        theta_m::Real
        w_ref::Real
    end
    @outputs begin
        u::Real = 0.0, [unit = "V"]
        w_load_hat::Real = 0.0, [unit = "rad/s"]
    end
    @variables begin
        xhat::Vec{nx} = [0.0, 0.0, 0.0, 0.0, 0.0], [description = "State estimate, refreshed every tick"]
        z::Real = 0.0, [description = "Integral of the load-speed error"]
    end
    @discrete Ts = 1e-3 begin
        for j in 1:ny
            y = theta_m
        end
        xhat = xhat + L * (y - dot(Cd, xhat))            # measurement update
        z += Ts * (w_ref - xhat[4])                      # integral of the load-speed error
        v = -dot(K, xhat) + Ki * z + Kff * w_ref
        for j in 1:nu
            u = clamp(v, -umax, umax)
        end
        if abs(v) > umax
            z -= Ts * (w_ref - xhat[4])                  # anti-windup: undo the integration
        end
        xhat = Ad * xhat + Bd * u                        # time update
        w_load_hat = xhat[4]
    end
end
