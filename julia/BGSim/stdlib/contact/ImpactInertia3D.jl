@block ImpactInertia3D begin
    # `ISpatial` (same ports, parameters and equations) plus the **impact map** of J-MB14
    # (F12, D-MB11): when the guard `sw` crosses 0.5 upward, the body momentum `P` is replaced
    # by the projection of the pre-impact twist onto the motions allowed by `mode_new` at the
    # new pivot. A block-local event can only reinit its own states, so the body inertia and
    # the momentum state live here; `ImpactBody3D` wraps this block with the pivot mount.
    #
    # The pivot frame is the body frame translated so that the body centre of mass sits at
    # `c = (cx, cy, cz)` in the pivot frame (`r = -c` is the pivot origin in the body frame;
    # axes parallel to the principal axes; v1 limit). With
    # `X = [I 0; r^ I]` (pivot twist to body twist, `r = -c`) the effective inertia at the pivot is
    # `M = X^T diag(J, m I) X`, whose angular block is `A = J + m (|r|^2 I - r r^T)`. The
    # pivot-frame angular momentum is `H = h + c x p` (and `M V_pivot = [H; p]`), so the
    # corrected map `V+ = S (S^T M S)^-1 S^T M V-` reads, per mode (codes of
    # `Mech.switched_modes`):
    #   0 free    S = I6          P+ = P
    #   1 corner  S = [I3; 0]     w+ = A^-1 H,          v_pivot+ = 0
    #   2 edge    S = e3          w+ = (0, 0, H_z / A_33), v_pivot+ = 0
    #   3 face    S = (empty)     w+ = 0,               v_pivot+ = 0
    # and the new body momentum is `P+ = [J w+; m (w+ x c)]` (`v_c = v_pivot + w x c`). The
    # 3x3 solve of the corner is written with Cramer's rule. `test_switched_joint.jl` checks
    # this closed form against `Mech.impact_projection` on the simulated states. The inertia
    # is the same `J`, `m` that drive the body (no copy), and `c` is the single source of the
    # mount offset used by `ImpactBody3D`.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs begin
        sw::Real, [description = "Switch guard: an upward crossing of 0.5 applies the impact map"]
        mode_new::Real, [description = "Mode applied at the switch (0 free, 1 corner, 2 edge, 3 face)"]
    end
    @parameters begin
        J::Vec{3} = [0.1, 0.1, 0.1], [unit = "kg*m^2", description = "Principal moments of inertia about the body centre of mass (J[k] > 0)"]
        m::Real = 1.0, [unit = "kg", min = 1e-12, description = "Body mass (m > 0)"]
        cx::Real = 0.0, [unit = "m", description = "Body centre of mass x in the pivot frame"]
        cy::Real = 0.0, [unit = "m", description = "Body centre of mass y in the pivot frame"]
        cz::Real = 0.0, [unit = "m", description = "Body centre of mass z in the pivot frame"]
    end
    @variables P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer, description = "Momentum [angular; linear]"]
    @outputs begin
        Pm::Vec{6}
        twout::Vec{6}
    end
    @equations begin
        for k in 1:6
            ddt(P[k]) ~ p.e[k]
        end
        p.f[1] ~ P[1] / J[1]
        p.f[2] ~ P[2] / J[2]
        p.f[3] ~ P[3] / J[3]
        p.f[4] ~ P[4] / m
        p.f[5] ~ P[5] / m
        p.f[6] ~ P[6] / m
        Pm ~ P
        for k in 1:6
            twout[k] ~ p.f[k]
        end
    end
    @events begin
        sw > 0.5 => begin
            # Pivot-frame angular momentum H = h - r x p.
            Hx = P[1] + (cy * P[6] - cz * P[5])
            Hy = P[2] + (cz * P[4] - cx * P[6])
            Hz = P[3] + (cx * P[5] - cy * P[4])
            # Angular block of the pivot inertia, A = J + m (|r|^2 I - r r^T).
            a11 = J[1] + m * (cy * cy + cz * cz)
            a22 = J[2] + m * (cx * cx + cz * cz)
            a33 = J[3] + m * (cx * cx + cy * cy)
            a12 = -m * cx * cy
            a13 = -m * cx * cz
            a23 = -m * cy * cz
            c11 = a22 * a33 - a23 * a23
            c12 = a13 * a23 - a12 * a33
            c13 = a12 * a23 - a13 * a22
            c22 = a11 * a33 - a13 * a13
            c23 = a12 * a13 - a11 * a23
            c33 = a11 * a22 - a12 * a12
            det3 = a11 * c11 + a12 * c12 + a13 * c13
            wx = 0.0
            wy = 0.0
            wz = 0.0
            if mode_new > 2.5
                wx = 0.0
            elseif mode_new > 1.5
                wz = Hz / a33
            elseif mode_new > 0.5
                wx = (c11 * Hx + c12 * Hy + c13 * Hz) / det3
                wy = (c12 * Hx + c22 * Hy + c23 * Hz) / det3
                wz = (c13 * Hx + c23 * Hy + c33 * Hz) / det3
            end
            keep = ifelse(mode_new < 0.5, 1.0, 0.0)
            reinit(P, [keep * P[1] + (1.0 - keep) * J[1] * wx,
                       keep * P[2] + (1.0 - keep) * J[2] * wy,
                       keep * P[3] + (1.0 - keep) * J[3] * wz,
                       keep * P[4] + (1.0 - keep) * m * (cz * wy - cy * wz),
                       keep * P[5] + (1.0 - keep) * m * (cx * wz - cz * wx),
                       keep * P[6] + (1.0 - keep) * m * (cy * wx - cx * wy)])
        end
    end
    @causality p => :flow_out
end
