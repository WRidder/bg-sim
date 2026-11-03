@block PlateLQG begin
    # Outer loop of the LQR controller (one axis), at the camera frame rate: a steady-state
    # Kalman filter that knows the camera is one frame late, an LQR with integral action and a
    # reference feed-forward for tracking. design/design.py writes every number below.
    #
    # Estimator model (30 Hz, ZOH of the linear axis with the closed servo loop):
    #   z = [x, v, theta, omega, c_prev],  z+ = Ae z + Be u,
    # where c_prev is the camera quantity x + h alpha of the previous frame, so the camera
    # reading y_k measures z[5] and the encoder measures z[3]. Per tick (current-estimator form):
    #   zf = zh + L [y - zh[5]; theta - zh[3]]                  (filtered estimate z[k|k])
    #   th_ff = a_r / K_bb,  w_ff = j_r / K_bb                    (the plate angle the reference needs)
    #   u_ff = th_ff + tau_s w_ff - cbw x_r                       (servo lag, ball weight on the servo)
    #   xi   = xi + Ts (zf[1] - x_r)                              (integral of the error)
    #   u    = clamp(u_ff - K[1:4] . (zf[1:4] - [x_r, v_r, th_ff, w_ff]) - K[5] xi, -th_max, th_max)
    #   zh   = Ae zf + Be u                                       (prediction for the next frame)
    # The integral stops while the output is clamped (anti-windup).
    @inputs begin
        y::Real, [unit = "m", description = "Camera reading (one frame late)"]
        theta::Real, [unit = "rad", description = "Servo angle (encoder)"]
        xr::Real, [unit = "m", description = "Reference position"]
        vr::Real, [unit = "m/s", description = "Reference velocity"]
        ar::Real, [unit = "m/s^2", description = "Reference acceleration"]
        jr::Real, [unit = "m/s^3", description = "Reference jerk"]
    end
    @outputs begin
        th_ref::Real = 0.0, [unit = "rad", description = "Servo angle set-point"]
        xhat::Real = 0.0, [unit = "m", description = "Estimated ball position (now, not one frame ago)"]
        vhat::Real = 0.0, [unit = "m/s", description = "Estimated ball velocity"]
        err::Real = 0.0, [unit = "m", description = "Estimated tracking error x_hat - x_r"]
    end
    @parameters begin
        K::Vec{5} = [6.138, 4.224, 0.093, 0.003, 0.121], [description = "LQR gain on [x, v, theta, omega, integral]"]
        L::Mat{5,2} = [1.18 0.0; 13.2 0.04; 0.0 0.97; 0.56 -20.3; 0.74 0.0], [description = "Kalman gain (camera, encoder)"]
        Ae::Mat{5,5} = [1.0 0.0333 0.0 0.0 0.0; 0.0 1.0 0.037 0.0 0.0; 0.0 0.0 1.0 0.0 0.0; 0.0 0.0 0.0 1.0 0.0; 1.0 0.0 0.0025 0.0 0.0], [description = "Estimator model (one frame)"]
        Be::Vec{5} = [0.0, 0.0, 0.0, 0.0, 0.0], [description = "Estimator input vector"]
        kbb::Real = 1.112, [unit = "m/(s^2*rad)", description = "Ball acceleration per servo angle"]
        tau_s::Real = 0.032, [unit = "s", description = "Lag of the closed servo loop, 2 zeta / omega"]
        cbw::Real = 0.0181, [unit = "rad/m", description = "Servo set-point that holds the ball's weight per metre"]
        th_max::Real = 1.0471975511965976, [unit = "rad", min = 0, description = "Output limit (servo travel)"]
    end
    @variables begin
        zh::Vec{5} = [0.0, 0.0, 0.0, 0.0, 0.0], [description = "Predicted state z[k|k-1]"]
        xi::Real = 0.0, [unit = "m*s", description = "Integral of the error"]
    end
    @discrete Ts = 0.033333333 begin
        e1 = y - zh[5]
        e2 = theta - zh[3]
        zf = [zh[1] + L[1, 1] * e1 + L[1, 2] * e2, zh[2] + L[2, 1] * e1 + L[2, 2] * e2, zh[3] + L[3, 1] * e1 + L[3, 2] * e2, zh[4] + L[4, 1] * e1 + L[4, 2] * e2, zh[5] + L[5, 1] * e1 + L[5, 2] * e2]
        thff = ar / kbb
        wff = jr / kbb
        uff = thff + tau_s * wff - cbw * xr
        xin = xi + Ts * (zf[1] - xr)
        un = uff - (K[1] * (zf[1] - xr) + K[2] * (zf[2] - vr) + K[3] * (zf[3] - thff) + K[4] * (zf[4] - wff)) - K[5] * xin
        u = clamp(un, -th_max, th_max)
        if abs(un) <= th_max
            xi = xin
        end
        zh = Ae * zf + Be * u
        th_ref = u
        xhat = zf[1]
        vhat = zf[2]
        err = zf[1] - xr
    end
end
