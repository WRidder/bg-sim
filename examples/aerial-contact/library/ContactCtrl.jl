@block ContactCtrl begin
    # The contact controller of the paper: a purely angular, position-independent, gain-scheduled LQR
    # at 250 Hz (design/design.py derives A(theta_sp), B(theta_sp) from the constrained dynamics and the
    # gains K(theta_sp) on a grid of pitch set-points).
    #
    #   X   = [phi, phi', theta, theta', psi, psi']'        (Z-Y-X Euler angles and rates of the multirotor,
    #                                                        from the navigation filter's attitude and gyro)
    #   U   = [tau_x, F, tau_z, tau_y]'
    #   U   = -K(theta_sp) (X - X_sp) + U_eq(theta_sp),     X_sp = [0, 0, theta_sp, 0, psi_sp, 0]'
    #   U_eq = [0, F_eq, 0, tau_eq],   F_eq = m g / cos(theta_sp)  (wall force m g tan(theta_sp)),
    #                                  tau_eq = -m_arm g L_m / 2   (the arm's weight moment: with it the
    #                                  wall reaction is horizontal, so the wheels carry no load of the
    #                                  multirotor)
    #
    # K is stored for the grid `th` (rad, uniform) as `Ktab` (one row of 24 numbers per grid point, the
    # 4 x 6 gain row by row) and interpolated linearly with hat functions. K has the sparsity structure of
    # the paper (rows tau_x, tau_z: only the phi and psi columns; rows F, tau_y: only theta, theta').
    # `K` and `Xe` are exported so that the structure is a measurable signal: `kzero` is the sum of |K| over
    # the twelve entries that must vanish, `sa` the (interpolated) spectral abscissa of A - B K from the design. Position independent: there
    # is no x, y, z anywhere in this block.
    @constants NT::Int = 8
    @inputs begin
        q::Vec{4}
        w::Vec{3}
        theta_sp::Real
        psi_sp::Real
    end
    @outputs begin
        tau::Vec{3} = [0.0, 0.0, 0.0]
        F::Real = 0.0, [unit = "N"]
        K::Vec{24} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        Xe::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        kzero::Real = 0.0, [description = "Sum of |K| over the entries that the paper's structure requires to be zero"]
        sa::Real = 0.0, [unit = "1/s", description = "Spectral abscissa of the linearised closed loop A - B K at theta_sp (design.py, interpolated)"]
    end
    @parameters begin
        th::Vec{NT} = [0.17453, 0.26180, 0.34907, 0.43633, 0.52360, 0.61087, 0.69813, 0.78540], [unit = "rad", description = "Grid of pitch set-points"]
        Ktab::Mat{NT,24} = [19.9892421 1.81759658 0 0 8.89617749 5.46732236 0 0 6.94095431 2.83490713 0 0 0.647206114 -0.0221409717 0 0 0.659030379 0.352324794 0 0 8.15744178 3.33175941 0 0; 18.7384462 1.46694558 0 0 8.86219283 5.34907812 0 0 6.85154176 2.80573938 0 0 0.647409294 -0.04183124 0 0 0.677097874 0.365991913 0 0 8.20976618 3.36193883 0 0; 17.5468268 1.1566653 0 0 8.80734222 5.23607008 0 0 6.72444948 2.76368104 0 0 0.652484393 -0.0636139149 0 0 0.705144608 0.385825366 0 0 8.28241859 3.40399066 0 0; 16.4122231 0.885561925 0 0 8.72757044 5.12440663 0 0 6.55780566 2.70751151 0 0 0.661533941 -0.0884326446 0 0 0.743761096 0.412477319 0 0 8.37469671 3.45764862 0 0; 15.3263553 0.65365173 0 0 8.61645635 5.00782721 0 0 6.34928061 2.63567573 0 0 0.673512941 -0.117401363 0 0 0.793893694 0.446898549 0 0 8.48555291 3.52247243 0 0; 14.2761216 0.463496108 0 0 8.4643013 4.87666114 0 0 6.09617211 2.54631343 0 0 0.687008204 -0.151845788 0 0 0.8568688 0.490353912 0 0 8.6134861 3.59777168 0 0; 13.2447846 0.322038499 0 0 8.25676587 4.71608424 0 0 5.7955414 2.43731685 0 0 0.699869725 -0.193287677 0 0 0.934362187 0.544368102 0 0 8.75641431 3.68251294 0 0; 12.2135917 0.243243033 0 0 7.97301212 4.50342403 0 0 5.44441706 2.30643081 0 0 0.708600403 -0.24326136 0 0 1.02822328 0.610473279 0 0 8.91153758 3.77521498 0 0], [description = "LQR gains on the grid, row-major 4 x 6 per grid point"]
        sa_tab::Vec{NT} = [-2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0], [unit = "1/s", description = "Spectral abscissa of A - B K on the grid"]
        dth::Real = 0.08726646259971647, [unit = "rad", description = "Grid spacing"]
        m_d::Real = 2.33, [unit = "kg", min = 0, description = "Mass carried by the thrust in contact (multirotor + arm)"]
        g0::Real = 9.81, [unit = "m/s^2"]
        tau_eq::Real = -0.6772, [unit = "N*m", description = "Equilibrium pitch torque, -m_arm g L_m / 2"]
        F_max::Real = 60.0, [unit = "N", description = "Thrust limit"]
    end
    @discrete Ts = 4e-3 begin
        r11 = 1 - 2 * (q[3] * q[3] + q[4] * q[4])
        r21 = 2 * (q[2] * q[3] + q[1] * q[4])
        r31 = 2 * (q[2] * q[4] - q[1] * q[3])
        r32 = 2 * (q[3] * q[4] + q[1] * q[2])
        r33 = 1 - 2 * (q[2] * q[2] + q[3] * q[3])
        phi = atan(r32, r33)
        theta = atan(-r31, hypot(r32, r33))
        psi = atan(r21, r11)
        sf = sin(phi)
        cf = cos(phi)
        ct = max(cos(theta), 0.2)
        qs = w[2] * sf + w[3] * cf
        phid = w[1] + qs * sin(theta) / ct
        thed = w[2] * cf - w[3] * sf
        psid = qs / ct
        e0 = psi - psi_sp
        epsi = e0 - 6.283185307179586 * round(e0 / 6.283185307179586)
        xe = [phi, phid, theta - theta_sp, thed, epsi, psid]
        ths = clamp(theta_sp, th[1], th[NT])
        kv = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for k in 1:NT
            wk = max(0.0, 1.0 - abs(ths - th[k]) / dth)
            for j in 1:24
                kv[j] = kv[j] + wk * Ktab[k, j]
            end
        end
        sav = 0.0
        for k in 1:NT
            sav = sav + max(0.0, 1.0 - abs(ths - th[k]) / dth) * sa_tab[k]
        end
        un = [0.0, 0.0, 0.0, 0.0]
        for i in 1:4
            acc = 0.0
            for j in 1:6
                acc = acc + kv[6 * (i - 1) + j] * xe[j]
            end
            un[i] = -acc
        end
        feq = m_d * g0 / max(cos(theta_sp), 0.3)
        tau = [un[1], tau_eq + un[4], un[3]]
        F = clamp(feq + un[2], 0.0, F_max)
        K = kv
        Xe = xe
        sa = sav
        kzero = abs(kv[3]) + abs(kv[4]) + abs(kv[7]) + abs(kv[8]) + abs(kv[11]) + abs(kv[12]) + abs(kv[15]) + abs(kv[16]) + abs(kv[19]) + abs(kv[20]) + abs(kv[23]) + abs(kv[24])
    end
end
