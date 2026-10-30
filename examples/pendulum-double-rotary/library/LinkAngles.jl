@block LinkAngles begin
    # Absolute link angles from upright, phi_k = q_1 + ... + q_k (the joint angles are relative),
    # and the largest absolute deviation of any link from upright. For plots and checks.
    @inputs begin
        q1::Real, [unit = "rad"]
        q2::Real, [unit = "rad"]
    end
    @outputs begin
        phi1::Real, [unit = "rad"]
        phi2::Real, [unit = "rad"]
        dev::Real, [unit = "rad"]
    end
    @equations begin
        phi1 ~ q1
        phi2 ~ q1 + q2
        dev ~ max(abs(phi1), abs(phi2))
    end
end
