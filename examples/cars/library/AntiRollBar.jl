@block AntiRollBar begin
    # Anti-roll bar between the left and the right strut of an axle (each port on the 1-junction
    # of that corner's suspension travel, as the `Strut`): a torsion spring on the difference
    # of the two wheel travels, given as the rate at the wheel; each port flow is the travel
    # rate of its wheel (bump positive). The left wheel is pushed down
    # by F = k (x_l - x_r) and the right one pulled up by as much, so the bar adds roll
    # stiffness k t^2 per axle (t the track; a spring of rate k at each wheel adds k t^2/2)
    # and nothing in heave. Lossless:
    # port power = d(k d^2/2)/dt.
    @ports begin
        jl::Power{Translation}
        jr::Power{Translation}
    end
    @parameters k::Real = 20000.0, [unit = "N/m", min = 0, description = "Bar rate at the wheel, per unit of travel difference"]
    @variables d::Real = 0.0, [unit = "m", state = :prefer, description = "Travel difference x_l - x_r"]
    @outputs begin
        F::Real, [unit = "N", description = "Force pushing the left wheel down (and the right one up)"]
        E::Real, [unit = "J", description = "Energy stored in the bar"]
    end
    @equations begin
        ddt(d) ~ jl.f - jr.f
        F ~ k * d
        jl.e ~ F
        jr.e ~ -F
        E ~ 0.5 * k * d * d
    end
    @causality begin
        jl => :effort_out
        jr => :effort_out
    end
    @orientation begin
        jl => :in
        jr => :in
    end
end
