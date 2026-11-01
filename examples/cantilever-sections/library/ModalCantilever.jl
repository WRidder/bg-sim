@block ModalCantilever begin
    # A clamped-free Euler-Bernoulli beam (wall at s = 0, free end at s = L) by the
    # assumed-modes method with its first three bending modes, loaded at the tip through the
    # translational port `tip` (effort: the tip force, positive down; flow: the tip velocity,
    # positive down) and by its own weight (g0). The section enters only through A, I and the
    # outer-fibre distance c, so one block serves a round bar, a square bar and an I-beam.
    #
    # Modal bond graph (the scalar graph of the cantilever-modes example, one more mode):
    #
    #   tip 0-junction --- TF phi_n(L) --- mode n 1-junction --- I m, C 1/k_n, R d_n
    #                                                       \--- Se m g0 a_n (own weight)
    #
    # with w(s, t) = sum_n phi_n(s) eta_n(t), the closed-form clamped-free shapes
    # phi_n = cosh(b s) - cos(b s) - sigma_n (sinh(b s) - sin(b s)), b = lambda_n / L,
    # normalised (1/L) int phi_n^2 ds = 1 (the viewer's deformation-binding contract, the same
    # shapes as stdlib FlexibleBeam3D). Then every mode has the modal mass m = rho A L, the
    # stiffness k_n = lambda_n^4 E I / L^3, the tip value phi_n(L) = +2, -2, +2 and the
    # damping d_n = 2 zeta sqrt(k_n m):
    #
    #   m eta_n'' + d_n eta_n' + k_n eta_n = phi_n(L) F + m g0 a_n,   a_n = (1/L) int phi_n ds
    #
    # Readouts:
    #   w      tip deflection sum phi_n(L) eta_n (99.86 % of F L^3/(3 E I) statically);
    #   M      root bending moment from the equilibrium of the whole beam (force summation),
    #          M = F L + m g0 L/2 - m L sum b_n eta_n'',  b_n = (1/L^2) int s phi_n ds:
    #          exact in the static limit and fast-converging in dynamics;
    #   M_modal  the same moment from the modal curvature, E I sum phi_n''(0) eta_n with
    #          phi_n''(0) = 2 lambda_n^2 / L^2: a slowly converging series (102.1 % of F L
    #          statically with three modes). The viewer's strain colouring uses this curvature;
    #   sigma  the largest bending stress M c / I (outer fibre at the wall), util |sigma| / fy.
    # Linear Euler-Bernoulli: no shear deformation or rotary inertia (Timoshenko), small
    # deflections, no buckling or plasticity.
    @ports tip::Power{Translation}
    @outputs begin
        eta::Vec{3}, [unit = "m", description = "Modal coordinates eta_1..eta_3 (bind them to the beam visual)"]
        w::Real, [unit = "m", description = "Tip deflection, positive down"]
        w_mm::Real, [description = "Tip deflection in mm, positive down"]
        M::Real, [unit = "N*m", description = "Root bending moment from equilibrium (force summation)"]
        M_modal::Real, [unit = "N*m", description = "Root bending moment from the modal curvature E I w''(0)"]
        sigma::Real, [unit = "Pa", description = "Largest bending stress M c / I (outer fibre at the wall)"]
        sigma_MPa::Real, [description = "Largest bending stress in MPa"]
        util::Real, [unit = "1", description = "Utilisation |sigma| / fy (1: first yield at the wall)"]
        f::Vec{3}, [unit = "Hz", description = "Eigenfrequencies of the three modes"]
        Ek::Real, [unit = "J", description = "Kinetic energy"]
        Ee::Real, [unit = "J", description = "Strain energy"]
    end
    @parameters begin
        L::Real = 2.0, [unit = "m", min = 1.0e-9, description = "Length, wall to tip"]
        E::Real = 2.1e11, [unit = "Pa", min = 0, description = "Young's modulus"]
        rho::Real = 7850.0, [unit = "kg/m^3", min = 1.0e-9, description = "Density"]
        A::Real = 1.0e-3, [unit = "m^2", min = 1.0e-12, description = "Cross-section area"]
        I::Real = 1.0e-7, [unit = "m^4", min = 1.0e-20, description = "Second moment of area about the bending axis"]
        c::Real = 0.02, [unit = "m", min = 0, description = "Distance of the outer fibre from the neutral axis"]
        fy::Real = 2.35e8, [unit = "Pa", min = 1.0e-9, description = "Yield strength"]
        zeta::Real = 0.02, [unit = "1", min = 0, description = "Modal damping ratio (every mode)"]
        g0::Real = 0.0, [unit = "m/s^2", min = 0, description = "Gravity on the own weight, downward (0: tip force only)"]
    end
    @variables begin
        q::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Modal coordinates (states)"]
        v::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", state = :prefer, description = "Modal velocities"]
        acc::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s^2", description = "Modal accelerations"]
        k::Vec{3} = [1.0, 1.0, 1.0], [unit = "N/m", description = "Modal stiffnesses lambda_n^4 E I / L^3"]
        d::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*s/m", description = "Modal damping 2 zeta sqrt(k_n m)"]
        m::Real = 1.0, [unit = "kg", description = "Modal mass rho A L (= beam mass)"]
        Fd::Real = 0.0, [unit = "N", description = "Tip force, positive down"]
        # mode tables of the clamped-free basis (design/reference.py; stdlib ModalBeam3D)
        lam::Vec{3} = [1.0, 1.0, 1.0], [unit = "1", description = "Eigenvalues lambda_n"]
        phiL::Vec{3} = [2.0, -2.0, 2.0], [unit = "1", description = "Tip values phi_n(L)"]
        ta::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L) int phi_n ds"]
        tb::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", description = "(1/L^2) int s phi_n ds"]
    end
    @equations begin
        lam[1] ~ 1.87510407
        lam[2] ~ 4.69409113
        lam[3] ~ 7.85475744
        phiL[1] ~ 2.0
        phiL[2] ~ -2.0
        phiL[3] ~ 2.0
        ta[1] ~ 0.7829917564063
        ta[2] ~ 0.433935895432
        ta[3] ~ 0.2544252968097
        tb[1] ~ 0.5688257439265
        tb[2] ~ 0.09076678726647
        tb[3] ~ 0.03241637441233
        m ~ rho * A * L
        Fd ~ tip.e
        for i in 1:3
            k[i] ~ lam[i]^4 * E * I / (L * L * L)
            d[i] ~ 2.0 * zeta * sqrt(k[i] * m)
            f[i] ~ lam[i]^2 / 6.283185307179586 * sqrt(E * I / (rho * A)) / (L * L)
            ddt(q[i]) ~ v[i]
            eta[i] ~ q[i]
            ddt(v[i]) ~ acc[i]
            m * acc[i] ~ phiL[i] * Fd + m * g0 * ta[i] - d[i] * v[i] - k[i] * eta[i]
        end
        tip.f ~ phiL[1] * v[1] + phiL[2] * v[2] + phiL[3] * v[3]
        w ~ phiL[1] * eta[1] + phiL[2] * eta[2] + phiL[3] * eta[3]
        w_mm ~ 1000.0 * w
        M ~ Fd * L + m * g0 * L / 2.0 - m * L * (tb[1] * acc[1] + tb[2] * acc[2] + tb[3] * acc[3])
        M_modal ~ 2.0 * E * I / (L * L) * (lam[1]^2 * eta[1] + lam[2]^2 * eta[2] + lam[3]^2 * eta[3])
        sigma ~ M * c / I
        sigma_MPa ~ 1.0e-6 * sigma
        util ~ abs(sigma) / fy
        Ek ~ m * (v[1]^2 + v[2]^2 + v[3]^2) / 2.0
        Ee ~ (k[1] * eta[1]^2 + k[2] * eta[2]^2 + k[3] * eta[3]^2) / 2.0
    end
    @causality tip => :flow_out
end
