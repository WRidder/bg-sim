@block PhaseSelect begin
    # Controller switch of the phase machine at 250 Hz: which attitude set-point and which collective
    # thrust reach the attitude controller and the mixer. Free flight and disengage use the position
    # controller (`qd_pos`, `F_pos`), the engage phase the angle references (`qd_eng`, `F_eng`) and the
    # contact phase the thrust of the contact controller (`F_lqr`; its torques bypass the attitude and
    # rate loops, the mixer selects them with the same `sel_lqr`).
    @inputs begin
        qd_pos::Vec{4}
        F_pos::Real
        qd_eng::Vec{4}
        F_eng::Real
        F_lqr::Real
        sel_eng::Real
        sel_lqr::Real
    end
    @outputs begin
        qd::Vec{4} = [1.0, 0.0, 0.0, 0.0]
        F::Real = 24.3, [unit = "N", description = "Collective thrust (starts at the hover thrust)"]
    end
    @discrete Ts = 4e-3 begin
        qd = ifelse(sel_eng > 0.5, qd_eng, qd_pos)
        F = ifelse(sel_lqr > 0.5, F_lqr, ifelse(sel_eng > 0.5, F_eng, F_pos))
    end
end
