@block WallForce begin
    # Sensor tap (plots and checks, not part of the firmware): the total normal force of the three
    # wheels on the wall, N = f1 + f2 + f3, and the quasi-static prediction of the paper,
    # Npred = m g tan(theta_sp): the thrust F = m g / cos(theta) tilted by theta carries the weight and
    # leaves m g tan(theta) as the horizontal push. `m_d` is the mass the thrust carries in contact
    # (multirotor + arm; the end-effector hangs on the wall by friction).
    @inputs begin
        f1::Real
        f2::Real
        f3::Real
        theta_sp::Real
    end
    @outputs begin
        N::Real, [unit = "N"]
        Npred::Real, [unit = "N"]
    end
    @parameters begin
        m_d::Real = 2.33, [unit = "kg", min = 0, description = "Mass carried by the thrust in contact"]
        g0::Real = 9.81, [unit = "m/s^2"]
    end
    @equations begin
        N ~ f1 + f2 + f3
        Npred ~ m_d * g0 * tan(theta_sp)
    end
end
