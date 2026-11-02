@block Governor begin
    # Engine-governor (ours: the report keeps the rotor speed constant and recommends a second-
    # order rotor-engine-governor model, section V.B). A PI law on the rotor speed relative to
    # the airframe (the gearbox junction's flow, what an Nr sensor reads),
    #
    #     Q_cmd = Kp (om_ref - om) + xi,   xi' = Ki (om_ref - om)   (not while limited)
    #
    # with the rotor inertia J this is the spring-mass-damper J s^2 + Kp s + Ki the report asks
    # for. The engine torque is limited to 0 .. P_max/om (the installed take-off power) and cut
    # by `on` = 0 (an engine failure: autorotation). The output drives the engine's modulated
    # effort source on the gearbox junction.
    @inputs begin
        om::Real, [description = "Rotor speed relative to the airframe (rad/s)"]
        on::Real, [description = "1: engines running; 0: cut"]
    end
    @outputs begin
        q::Real, [description = "Engine torque at the rotor shaft (N m)"]
        nr::Real, [description = "Rotor speed, percent of nominal"]
        power_hp::Real, [description = "Engine power (hp)"]
    end
    @parameters begin
        om_ref::Real = 40.317, [description = "Governed rotor speed (rad/s)"]
        Kp::Real = 5000.0, [description = "Proportional gain (N m s/rad)"]
        Ki::Real = 8000.0, [description = "Integral gain (N m/rad)"]
        p_max::Real = 551820.0, [description = "Maximum engine power (W)"]
    end
    @variables begin
        xi::Real = 0.0, [state = :prefer, description = "Integrator (N m)"]
        err::Real = 0.0
        qcmd::Real = 0.0
        qmax::Real = 0.0
    end
    @equations begin
        err ~ om_ref - om
        qmax ~ p_max / om
        qcmd ~ Kp * err + xi
        ddt(xi) ~ ifelse(qcmd > 0.0, ifelse(qcmd < qmax, Ki * err, 0.0), 0.0)
        q ~ on * clamp(qcmd, 0.0, qmax)
        nr ~ 100.0 * om / om_ref
        power_hp ~ q * om / 745.6998715822702
    end
end
