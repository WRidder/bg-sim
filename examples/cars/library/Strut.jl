@block Strut begin
    # Suspension strut on the drive port of the corner's `Prismatic3D` (bond: the joint's drive
    # -> a 1-junction -> this element): a coil spring that cannot pull, progressive bump and
    # droop stops and a damper with separate bump and rebound rates. `x` is the wheel travel
    # from the static ride position (bump positive), so the port flow is -dx/dt.
    #
    #   spring   F_s = k sp(x + x0),        sp the smooth positive part, x0 = F0/k (static
    #                                        compression: the spring carries F0 at x = 0)
    #   bump     F_b = k_stop sp(x - bump)^2       droop  F_d = -k_stop sp(-x - droop)^2
    #   damper   F_v = (cb + cr)/2 v + (cb - cr)/2 (sqrt(v^2 + ve^2) - ve),   v = dx/dt
    #   F = F_s sig_s + F_b sig_b + F_d sig_d + F_v      (sig: the derivative of the smooth part)
    #
    # The force pushes the wheel down (away from the chassis), so the port effort is -F. Port
    # power = dE/dt + Pd with E = k sp(x+x0)^2/2 + k_stop (sp(x-bump)^3 + sp(-x-droop)^3)/3 and
    # Pd = F_v v >= 0 (the rebound term is at most |v|).
    @ports j::Power{Translation}
    @parameters begin
        k::Real = 50000.0, [unit = "N/m", min = 0, description = "Spring rate at the wheel"]
        F0::Real = 1500.0, [unit = "N", min = 0, description = "Spring force at the static ride position (x = 0)"]
        cb::Real = 3000.0, [unit = "N*s/m", min = 0, description = "Damping in bump (x increasing)"]
        cr::Real = 4000.0, [unit = "N*s/m", min = 0, description = "Damping in rebound"]
        ve::Real = 0.01, [unit = "m/s", min = 1.0e-9, description = "Smoothing speed of the bump/rebound switch"]
        bump::Real = 0.05, [unit = "m", min = 0, description = "Bump travel to the bump stop"]
        droop::Real = 0.06, [unit = "m", min = 0, description = "Droop travel to the droop stop"]
        k_stop::Real = 4.0e7, [unit = "N/m^2", min = 0, description = "Progressive stop rate: F = k_stop d^2"]
        eps::Real = 1.0e-4, [unit = "m", min = 1.0e-12, description = "Smoothing length of the positive parts"]
    end
    @variables begin
        x::Real = 0.0, [unit = "m", state = :prefer, description = "Wheel travel from the static position (bump +)"]
        v::Real = 0.0, [unit = "m/s", description = "Travel rate"]
        ys::Real = 0.0, [unit = "m", description = "Spring compression x + x0"]
        rs::Real = 1.0, [unit = "m", description = "sqrt(ys^2 + eps^2)"]
        ss::Real = 0.0, [unit = "m", description = "Smooth positive spring compression"]
        yb::Real = 0.0, [unit = "m", description = "Bump-stop penetration x - bump"]
        rb::Real = 1.0, [unit = "m", description = "sqrt(yb^2 + eps^2)"]
        sb::Real = 0.0, [unit = "m", description = "Smooth positive bump-stop penetration"]
        yd::Real = 0.0, [unit = "m", description = "Droop-stop penetration -x - droop"]
        rd::Real = 1.0, [unit = "m", description = "sqrt(yd^2 + eps^2)"]
        sd::Real = 0.0, [unit = "m", description = "Smooth positive droop-stop penetration"]
        Fv::Real = 0.0, [unit = "N", description = "Damper force"]
    end
    @outputs begin
        travel::Real, [unit = "m", description = "Wheel travel from the static ride position (bump +)"]
        F::Real, [unit = "N", description = "Strut force pushing the wheel away from the chassis"]
        E::Real, [unit = "J", description = "Energy stored in the spring and the stops"]
        Pd::Real, [unit = "W", description = "Power dissipated in the damper"]
    end
    @equations begin
        v ~ -j.f
        ddt(x) ~ v
        ys ~ x + F0 / k
        rs ~ sqrt(ys * ys + eps * eps)
        ss ~ 0.5 * (ys + rs)
        yb ~ x - bump
        rb ~ sqrt(yb * yb + eps * eps)
        sb ~ 0.5 * (yb + rb)
        yd ~ -x - droop
        rd ~ sqrt(yd * yd + eps * eps)
        sd ~ 0.5 * (yd + rd)
        Fv ~ 0.5 * (cb + cr) * v + 0.5 * (cb - cr) * (sqrt(v * v + ve * ve) - ve)
        F ~ k * ss * ss / rs + k_stop * sb * sb * sb / rb - k_stop * sd * sd * sd / rd + Fv
        j.e ~ -F
        travel ~ x
        E ~ 0.5 * k * ss * ss + k_stop * (sb * sb * sb + sd * sd * sd) / 3
        Pd ~ Fv * v
    end
    @causality j => :effort_out
end
