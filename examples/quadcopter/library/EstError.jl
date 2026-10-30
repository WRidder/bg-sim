@block EstError begin
    # Error taps against the ground truth (plotting and checking, not part of the firmware): the
    # navigation filter errors, position error `pos` (m), velocity error `vel` (m/s) and attitude error
    # angle `att` (rad, the rotation angle of conj(q_est) (x) q_true), and the tracking error `track`
    # (m), the distance of the true position from the mission set-point.
    @inputs begin
        phat::Vec{3}
        vhat::Vec{3}
        qhat::Vec{4}
        p::Vec{3}
        v::Vec{3}
        q::Vec{4}
        p_sp::Vec{3}
    end
    @outputs begin
        track::Real, [unit = "m"]
        pos::Real, [unit = "m"]
        vel::Real, [unit = "m/s"]
        att::Real, [unit = "rad"]
    end
    @variables begin
        e0::Real = 1.0, [description = "Scalar part of conj(q_est) (x) q_true"]
        e1::Real = 0.0
        e2::Real = 0.0
        e3::Real = 0.0
    end
    @equations begin
        e0 ~ qhat[1] * q[1] + qhat[2] * q[2] + qhat[3] * q[3] + qhat[4] * q[4]
        e1 ~ qhat[1] * q[2] - qhat[2] * q[1] - qhat[3] * q[4] + qhat[4] * q[3]
        e2 ~ qhat[1] * q[3] + qhat[2] * q[4] - qhat[3] * q[1] - qhat[4] * q[2]
        e3 ~ qhat[1] * q[4] - qhat[2] * q[3] + qhat[3] * q[2] - qhat[4] * q[1]
        track ~ sqrt((p[1] - p_sp[1]) * (p[1] - p_sp[1]) + (p[2] - p_sp[2]) * (p[2] - p_sp[2]) + (p[3] - p_sp[3]) * (p[3] - p_sp[3]) + 1.0e-18)
        pos ~ sqrt((phat[1] - p[1]) * (phat[1] - p[1]) + (phat[2] - p[2]) * (phat[2] - p[2]) + (phat[3] - p[3]) * (phat[3] - p[3]) + 1.0e-18)
        vel ~ sqrt((vhat[1] - v[1]) * (vhat[1] - v[1]) + (vhat[2] - v[2]) * (vhat[2] - v[2]) + (vhat[3] - v[3]) * (vhat[3] - v[3]) + 1.0e-18)
        att ~ 2.0 * atan(sqrt(e1 * e1 + e2 * e2 + e3 * e3 + 1.0e-18), e0)
    end
end
