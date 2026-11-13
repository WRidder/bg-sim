@block MjBacklash begin
    # Gear play as microduck_rl trains with it (add_backlash.py): a passive hinge in series with
    # the servo output, free within +-gap/2, with its own armature `jb` and damping `c` on the
    # play angle, and MuJoCo's soft joint limit at both ends. Port `a` is the gear (motor) side,
    # `b` the load (horn) side; phi = a - b, w = a.f - b.f.
    #
    # MuJoCo's limit (mujoco.readthedocs.io, Computation, "Soft constraints"): with the impedance
    # d(p) of solimp, the regulariser R = (1 - d)/d invw (invw = the hinge's dof_invweight0) and
    # the reference acceleration aref = -bs v - ks d p (bs = 2/(dmax tc), ks = 1/(dmax tc zeta)^2,
    # p the penetration, v its rate), a row pushes with f = max(0, aref - a)/R. So inside a stop
    # the play angle follows the critically damped reference (time constant tc) whatever loads it,
    # up to a compliance R/(ks d): statically a stiffness Ms ks d with Ms = d/((1 - d) invw), which
    # rises with d from about 200 to 1.1e4 N m/rad over solimp's first 0.1 mrad (with microduck_rl's
    # limits a load of 0.3 N m sinks the play about 0.09 mrad into the stop), and an arriving play
    # angle overshoots the stop by about its speed times tc/e before it is brought back.
    #
    # Written with the acceleration inside a max (f = Ms max(0, pdd + bs pd + ks d p)) the law is
    # an inertia that switches on and off with the contact, which a linearly implicit solver
    # cannot step through. Here the reference is carried as a state instead: while a stop pushes,
    # `r` is the reference play rate and follows aref (r' = -bs r -+ ks d p), and the stop is the
    # damper
    #
    #   f = Ms bs (w - r)        (forward stop; the backward stop mirrored)
    #
    # which holds w on r. That is MuJoCo's row law where it matters: the play angle follows the
    # reference dynamics, the static stiffness is the same Ms ks d (the damper force at rest is
    # Ms bs |r| with r = -ks d p / bs), and the force is MuJoCo's up to its (1 - d) leakage. While
    # no stop pushes, r tracks w with the lag `tr`, so (w - r)/tr is the play's acceleration and
    # r starts from w when a stop closes (aref from the present play rate, as in MuJoCo).
    #
    # The damper is stiff (Ms bs invw = bs d/(1 - d), up to 2e5 1/s), so whether a stop pushes is
    # a mode held between the ticks of a 1 ms clock (m1, m2). Inside a stop a free play closes it
    # when the force MuJoCo's row would push with, (a + bs w + ks d p)/invw, exceeds +eps, and a
    # pushing stop lets go when its force falls below -eps (MuJoCo's max(0, .), with a hysteresis
    # that keeps the mode from chattering); outside the stop the mode is off. A fixed-step export
    # then integrates every step with the mode its Jacobian was formed with: a stop that switched
    # on inside a step with the Jacobian of the free play makes the step explode (the export at
    # 1 ms, 0.5 ms and 0.25 ms did, on the bench). The cost: a play arriving between two ticks goes
    # up to its speed times 1 ms deeper before the stop closes, and a stop the load pulls away
    # from holds for up to 1 ms.
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Period at which the contact modes are updated"]
    @parameters begin
        gap::Real = 0.03490658503988659, [unit = "rad", min = 0, description = "Total play (microduck_rl: 2 deg)"]
        jb::Real = 0.001, [unit = "kg*m^2", min = 0, description = "Armature of the play hinge (MuJoCo armature)"]
        c::Real = 0.01, [unit = "N*m*s/rad", min = 0, description = "Damping of the play hinge (MuJoCo damping)"]
        invw::Real = 900.0, [unit = "1/(kg*m^2)", min = 1.0e-9, description = "MuJoCo dof_invweight0 of the play hinge"]
        tc::Real = 0.01, [unit = "s", min = 1.0e-9, description = "solreflimit time constant"]
        zeta::Real = 1.0, [unit = "1", min = 1.0e-9, description = "solreflimit damping ratio"]
        dmin::Real = 0.95, [unit = "1", min = 0, max = 1, description = "solimplimit dmin"]
        dmax::Real = 0.999, [unit = "1", min = 0, max = 1, description = "solimplimit dmax"]
        width::Real = 1.0e-4, [unit = "rad", min = 1.0e-12, description = "solimplimit width"]
        mid::Real = 0.5, [unit = "1", min = 0, max = 1, description = "solimplimit midpoint"]
        power::Real = 2.0, [unit = "1", min = 1, description = "solimplimit power"]
        tr::Real = 1.0e-4, [unit = "s", min = 1.0e-12, description = "Time constant of the reference rate tracking w while no stop pushes"]
        eps::Real = 1.0e-3, [unit = "N*m", min = 0, description = "Hysteresis of the stop's contact: it closes at +eps and lets go at -eps"]
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Play angle, gear minus horn"]
        w::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Play rate"]
        r::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Reference play rate (MuJoCo's aref, integrated)"]
        m1::Real = 0.0, [unit = "1", description = "1 while the forward stop pushes (held between the ticks)"]
        m2::Real = 0.0, [unit = "1", description = "1 while the backward stop pushes (held between the ticks)"]
        p1::Real = 0.0, [unit = "rad", description = "Penetration of the forward stop (gear ahead)"]
        p2::Real = 0.0, [unit = "rad", description = "Penetration of the backward stop"]
        x1::Real = 0.0, [unit = "1", description = "Penetration of the forward stop over the solimp width, clamped to [0, 1]"]
        x2::Real = 0.0, [unit = "1", description = "Penetration of the backward stop over the solimp width, clamped to [0, 1]"]
        d1::Real = 0.95, [unit = "1", description = "Impedance of the forward stop"]
        d2::Real = 0.95, [unit = "1", description = "Impedance of the backward stop"]
        z1::Real = 0.0, [unit = "N*m", description = "Force of the forward stop while it pushes"]
        z2::Real = 0.0, [unit = "N*m", description = "Force of the backward stop while it pushes"]
        y1::Real = 0.0, [unit = "N*m", description = "Force the forward stop would push with, while it does not"]
        y2::Real = 0.0, [unit = "N*m", description = "Force the backward stop would push with, while it does not"]
        f1::Real = 0.0, [unit = "N*m", description = "Force of the forward stop"]
        f2::Real = 0.0, [unit = "N*m", description = "Force of the backward stop"]
        T::Real = 0.0, [unit = "N*m", description = "Torque carried from a to b"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        p1 ~ phi - gap / 2
        p2 ~ -phi - gap / 2
        # solimp's impedance curve. The argument and the result are clamped with min/max, so the
        # branch a fixed-step export holds for a whole step stays inside [dmin, dmax] even when the
        # penetration crosses the 0.1 mrad width within the step (a d above 1 turns the stop's
        # damper negative)
        x1 ~ max(min(p1 / width, 1.0), 0.0)
        x2 ~ max(min(p2 / width, 1.0), 0.0)
        d1 ~ dmin + (dmax - dmin) * max(min(ifelse(x1 < mid, x1^power / mid^(power - 1),
            1 - (1 - x1)^power / (1 - mid)^(power - 1)), 1.0), 0.0)
        d2 ~ dmin + (dmax - dmin) * max(min(ifelse(x2 < mid, x2^power / mid^(power - 1),
            1 - (1 - x2)^power / (1 - mid)^(power - 1)), 1.0), 0.0)
        ddt(r) ~ m1 * (-2 / (dmax * tc) * r - d1 / (dmax * tc * zeta)^2 * p1) +
                 m2 * (-2 / (dmax * tc) * r + d2 / (dmax * tc * zeta)^2 * p2) +
                 (1 - m1 - m2) * (w - r) / tr
        z1 ~ d1 / ((1 - d1) * invw) * 2 / (dmax * tc) * (w - r)
        z2 ~ d2 / ((1 - d2) * invw) * 2 / (dmax * tc) * (r - w)
        # free, r lags w by tr: (w - r)/tr is the play's acceleration, and MuJoCo's row would push
        # with (a + bs w + ks d p)/invw
        y1 ~ ((w - r) / tr + 2 / (dmax * tc) * w + d1 / (dmax * tc * zeta)^2 * p1) / invw
        y2 ~ ((r - w) / tr - 2 / (dmax * tc) * w + d2 / (dmax * tc * zeta)^2 * p2) / invw
        f1 ~ m1 * z1
        f2 ~ m2 * z2
        T ~ jb * ddt(w) + c * w + f1 - f2
        a.e ~ T
        b.e ~ -T
    end
    @discrete Ts = sample_period begin
        # in a stop: a pushing stop lets go below -eps, a free one closes above +eps
        m1 = ifelse(p1 > 0.0, ifelse(m1 > 0.5, ifelse(z1 > -eps, 1.0, 0.0), ifelse(y1 > eps, 1.0, 0.0)), 0.0)
        m2 = ifelse(p2 > 0.0, ifelse(m2 > 0.5, ifelse(z2 > -eps, 1.0, 0.0), ifelse(y2 > eps, 1.0, 0.0)), 0.0)
    end
    @orientation begin
        a => :in
        b => :in
    end
end
