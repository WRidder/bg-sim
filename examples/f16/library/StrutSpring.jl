@block StrutSpring begin
    # The spring of a landing-gear leg (JSBSim's FGLGear spring, a C on the contact's normal
    # 1-junction): the state q is the integral of the penetration rate (the junction flow), i.e.
    # the compression of tyre and strut, started at the contact point's geometric penetration.
    # It cannot pull: the force is k sp(q), sp the smooth positive part (cancellation-free, as
    # stdlib ContactPoint) over `eps`; sig = d sp/dq tells the damper when the wheel is down.
    #   power in = j.e j.f = k sp(q) dq/dt = dE/dt,   E = k int sp(q) dq
    @ports j::Power{Translation}
    @parameters begin
        k::Real = 78807.0, [unit = "N/m", min = 0, description = "Spring rate (JSBSim spring_coeff)"]
        eps::Real = 1.0e-3, [unit = "m", min = 1.0e-12, description = "Smoothing length of the positive part"]
    end
    @variables begin
        q::Real = 0.0, [unit = "m", state = :prefer, description = "Compression (penetration of the contact point)"]
        rq::Real = 1.0e-3, [unit = "m"]
        xp::Real = 0.0, [unit = "m", description = "Smooth positive compression"]
    end
    @outputs begin
        Fk::Real, [unit = "N", description = "Spring force"]
        sig::Real, [description = "d sp/dq (1 on the ground, 0 in the air)"]
        compression::Real, [unit = "m"]
    end
    @equations begin
        ddt(q) ~ j.f
        rq ~ sqrt(q * q + eps * eps)
        xp ~ ifelse(q < 0.0, 0.5 * eps * eps / (rq - q), 0.5 * (q + rq))
        sig ~ xp / rq
        Fk ~ k * xp
        j.e ~ Fk
        compression ~ q
    end
    @causality j => :effort_out
    @orientation j => :in
end
