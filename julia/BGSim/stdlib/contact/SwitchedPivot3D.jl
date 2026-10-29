@block SwitchedPivot3D begin
    # Mode-switched spatial pivot between a parent (the ground) and one child body (J-MB14,
    # F11/D-MB11), with a **fixed structure**: the relative pose is integrated exactly as in
    # `Free3D` (quaternion `Q` plus the child origin `p` in the parent frame; all states are
    # always present, there is no zero screw column and no structural `ifelse`), and the
    # directions the current **mode** holds are pulled back by a stiff spring-damper whose force
    # is multiplied by a 0/1 mask. A free direction carries zero force; nothing becomes singular
    # at a switch.
    #
    # Modes (`mode` is a state held between events; the codes match `Mech.switched_modes`):
    #   0 free    nothing held
    #   1 corner  the three translations of the pivot frame origin are held (ball joint)
    #   2 edge    corner plus the two rotations about the pivot-frame x and y axes: a hinge about
    #             the pivot-frame **z axis** (the user places the pivot frame on the edge with
    #             `FixedTransform3D`, exactly like `Revolute3D`)
    #   3 face    all six directions are held
    # The masks `mt` (translations), `mr` (rotation about x and y) and `mz` (rotation about z) are
    # 0/1 states, constant between events and set from `mode_new` in the event.
    #
    # The held directions carry **deflection states** in the child frame (the Spherical3D
    # pattern, FIX-MB-5 transport by the absolute child rate `w_c = child.f[1:3]`): the translation
    # deflection `dl` (the pivot origin relative to its anchor) and the small-angle rotation
    # deflection `dth`:
    #     ddt(dl)  = mt (V_rel[4:6] - w_c x dl)
    #     ddt(dth) = (mr, mr, mz) .* (V_rel[1:3] - w_c x dth)
    # so a free direction does not accumulate and **the anchor reset at a switch is
    # `dl = dth = 0`**. Held wrench on the child (child frame):
    #     F = -mt (kt dl + bt wl),   T = -(mr, mr, mz) .* (kr dth + br wa)
    # whose stored energy `1/2 kt |dl|^2 + 1/2 kr |dth|^2` is exact (`d.(w x d) = 0`).
    #
    # The damper acts on a **lagged** relative velocity (`wl`, `wa`, time constant `tau`, a state
    # of its own) and the event zeroes it: then the held wrench is exactly zero on both sides of the
    # switch, so MTK's implicit event solve (which re-solves the algebraic efforts and would
    # otherwise shift unconstrained states of the body to absorb a force jump) moves nothing and
    # the event order against the body's impact map is irrelevant.
    #
    # Switch: the guard is the model-side input `sw`; an upward crossing of `sw` through 0.5
    # sets `mode = mode_new`, the masks, and zeroes the deflections. The impact map of the body
    # is applied by `ImpactInertia3D` on the same two signals (a block-local event can only
    # reinit its own states, so the momentum lives in that block).
    @ports begin
        parent::Power{Spatial}
        child::Power{Spatial}
    end
    @inputs begin
        sw::Real, [description = "Switch guard: an upward crossing of 0.5 applies mode_new"]
        mode_new::Real, [description = "Mode applied at the switch (0 free, 1 corner, 2 edge, 3 face)"]
    end
    @parameters begin
        kt::Real = 1.0e6, [unit = "N/m", min = 0, description = "Held translation stiffness"]
        bt::Real = 1.0e3, [unit = "N*s/m", min = 0, description = "Held translation damping"]
        kr::Real = 1.0e5, [unit = "N*m", min = 0, description = "Held rotation stiffness (per radian of the 2 vec error)"]
        br::Real = 1.0e2, [unit = "N*m*s", min = 0, description = "Held rotation damping"]
        leak::Real = 0.0, [unit = "1/s", min = 0, description = "Held mode/anchor leak rate (0 holds exactly; keeps the constant states in the initialisation system)"]
        tau::Real = 1.0e-4, [unit = "s", min = 1.0e-9, description = "Lag of the damper velocity (the damper acts on the lagged relative velocity, see the header)"]
    end
    @variables begin
        qw::Real = 1.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion scalar part (child in parent)"]
        qx::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion x"]
        qy::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion y"]
        qz::Real = 0.0, [unit = "1", state = :prefer, description = "Relative orientation quaternion z"]
        px::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin x in the parent frame"]
        py::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin y in the parent frame"]
        pz::Real = 0.0, [unit = "m", state = :prefer, description = "Child origin z in the parent frame"]
        mode::Real = 0.0, [unit = "1", state = :prefer, description = "Current mode code (0 free, 1 corner, 2 edge, 3 face)"]
        dl::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", state = :prefer, description = "Held translation deflection (child frame)"]
        dth::Vec{3} = [0.0, 0.0, 0.0], [unit = "1", state = :prefer, description = "Held small-angle rotation deflection (child frame)"]
        wl::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", state = :prefer, description = "Lagged relative linear velocity (damper input)"]
        wa::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", state = :prefer, description = "Lagged relative angular velocity (damper input)"]
        s::Real = 1.0, [unit = "1", description = "Squared quaternion norm |q|^2"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1", description = "Rotation of the relative orientation (child to parent)"]
        u::Vec{3} = [0.0, 0.0, 0.0], [description = "parent.f[4:6] - p x parent.f[1:3]"]
        Vrel::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [description = "Relative twist child - Ad(g)^-1 parent"]
        mt::Real = 0.0, [unit = "1", state = :prefer, description = "Translation hold mask"]
        mr::Real = 0.0, [unit = "1", state = :prefer, description = "x/y rotation hold mask"]
        mz::Real = 0.0, [unit = "1", state = :prefer, description = "z rotation hold mask"]
        Fc::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Held force on the child (child frame)"]
        Tc::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Held torque on the child (child frame)"]
        Wl::Vec{3} = [0.0, 0.0, 0.0], [unit = "N", description = "Linear wrench rotated into the parent frame"]
        Wa::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Angular wrench rotated into the parent frame"]
    end
    @outputs begin
        qrel::Vec{4}
        pose::Vec{7}
        Vrelout::Vec{6}
        modeout::Real
        Pd::Real, [unit = "W", description = "Dissipated power of the held-direction dampers"]
    end
    @equations begin
        s ~ qw * qw + qx * qx + qy * qy + qz * qz
        R[1, 1] ~ (qw * qw + qx * qx - qy * qy - qz * qz) / s
        R[1, 2] ~ 2 * (qx * qy - qw * qz) / s
        R[1, 3] ~ 2 * (qx * qz + qw * qy) / s
        R[2, 1] ~ 2 * (qx * qy + qw * qz) / s
        R[2, 2] ~ (qw * qw - qx * qx + qy * qy - qz * qz) / s
        R[2, 3] ~ 2 * (qy * qz - qw * qx) / s
        R[3, 1] ~ 2 * (qx * qz - qw * qy) / s
        R[3, 2] ~ 2 * (qy * qz + qw * qx) / s
        R[3, 3] ~ (qw * qw - qx * qx - qy * qy + qz * qz) / s
        u[1] ~ parent.f[4] - (py * parent.f[3] - pz * parent.f[2])
        u[2] ~ parent.f[5] - (pz * parent.f[1] - px * parent.f[3])
        u[3] ~ parent.f[6] - (px * parent.f[2] - py * parent.f[1])
        Vrel[1] ~ child.f[1] - (R[1, 1] * parent.f[1] + R[2, 1] * parent.f[2] + R[3, 1] * parent.f[3])
        Vrel[4] ~ child.f[4] - (R[1, 1] * u[1] + R[2, 1] * u[2] + R[3, 1] * u[3])
        Vrel[2] ~ child.f[2] - (R[1, 2] * parent.f[1] + R[2, 2] * parent.f[2] + R[3, 2] * parent.f[3])
        Vrel[5] ~ child.f[5] - (R[1, 2] * u[1] + R[2, 2] * u[2] + R[3, 2] * u[3])
        Vrel[3] ~ child.f[3] - (R[1, 3] * parent.f[1] + R[2, 3] * parent.f[2] + R[3, 3] * parent.f[3])
        Vrel[6] ~ child.f[6] - (R[1, 3] * u[1] + R[2, 3] * u[2] + R[3, 3] * u[3])
        ddt(qw) ~ -0.5 * (Vrel[1] * qx + Vrel[2] * qy + Vrel[3] * qz)
        ddt(qx) ~ 0.5 * (Vrel[1] * qw + Vrel[3] * qy - Vrel[2] * qz)
        ddt(qy) ~ 0.5 * (Vrel[2] * qw + Vrel[1] * qz - Vrel[3] * qx)
        ddt(qz) ~ 0.5 * (Vrel[3] * qw + Vrel[2] * qx - Vrel[1] * qy)
        ddt(px) ~ R[1, 1] * Vrel[4] + R[1, 2] * Vrel[5] + R[1, 3] * Vrel[6]
        ddt(py) ~ R[2, 1] * Vrel[4] + R[2, 2] * Vrel[5] + R[2, 3] * Vrel[6]
        ddt(pz) ~ R[3, 1] * Vrel[4] + R[3, 2] * Vrel[5] + R[3, 3] * Vrel[6]
        # The mode and the masks are constant between events (`leak` = 0).
        ddt(mode) ~ -leak * mode
        ddt(mt) ~ -leak * mt
        ddt(mr) ~ -leak * mr
        ddt(mz) ~ -leak * mz
        # Deflections with the transport by the absolute child rate.
        ddt(dl[1]) ~ mt * (Vrel[4] - (child.f[2] * dl[3] - child.f[3] * dl[2]))
        ddt(dl[2]) ~ mt * (Vrel[5] - (child.f[3] * dl[1] - child.f[1] * dl[3]))
        ddt(dl[3]) ~ mt * (Vrel[6] - (child.f[1] * dl[2] - child.f[2] * dl[1]))
        ddt(dth[1]) ~ mr * (Vrel[1] - (child.f[2] * dth[3] - child.f[3] * dth[2]))
        ddt(dth[2]) ~ mr * (Vrel[2] - (child.f[3] * dth[1] - child.f[1] * dth[3]))
        ddt(dth[3]) ~ mz * (Vrel[3] - (child.f[1] * dth[2] - child.f[2] * dth[1]))
        ddt(wl[1]) ~ (Vrel[4] - wl[1]) / tau
        ddt(wl[2]) ~ (Vrel[5] - wl[2]) / tau
        ddt(wl[3]) ~ (Vrel[6] - wl[3]) / tau
        ddt(wa[1]) ~ (Vrel[1] - wa[1]) / tau
        ddt(wa[2]) ~ (Vrel[2] - wa[2]) / tau
        ddt(wa[3]) ~ (Vrel[3] - wa[3]) / tau
        Fc[1] ~ -mt * (kt * dl[1] + bt * wl[1])
        Fc[2] ~ -mt * (kt * dl[2] + bt * wl[2])
        Fc[3] ~ -mt * (kt * dl[3] + bt * wl[3])
        Tc[1] ~ -mr * (kr * dth[1] + br * wa[1])
        Tc[2] ~ -mr * (kr * dth[2] + br * wa[2])
        Tc[3] ~ -mz * (kr * dth[3] + br * wa[3])
        # Bond convention (as Free3D, `child.e = -drive.e`): the port effort is minus the wrench on the
        # child body (Tc, Fc); the parent port receives the reaction.
        child.e[1] ~ -Tc[1]
        child.e[2] ~ -Tc[2]
        child.e[3] ~ -Tc[3]
        child.e[4] ~ -Fc[1]
        child.e[5] ~ -Fc[2]
        child.e[6] ~ -Fc[3]
        for k in 1:3
            Wa[k] ~ R[k, 1] * child.e[1] + R[k, 2] * child.e[2] + R[k, 3] * child.e[3]
            Wl[k] ~ R[k, 1] * child.e[4] + R[k, 2] * child.e[5] + R[k, 3] * child.e[6]
        end
        # parent.e = -[R W_ang + p x (R W_lin); R W_lin]
        parent.e[1] ~ -(Wa[1] + (py * Wl[3] - pz * Wl[2]))
        parent.e[2] ~ -(Wa[2] + (pz * Wl[1] - px * Wl[3]))
        parent.e[3] ~ -(Wa[3] + (px * Wl[2] - py * Wl[1]))
        parent.e[4] ~ -Wl[1]
        parent.e[5] ~ -Wl[2]
        parent.e[6] ~ -Wl[3]
        qrel[1] ~ qw
        qrel[2] ~ qx
        qrel[3] ~ qy
        qrel[4] ~ qz
        pose[1] ~ qw
        pose[2] ~ qx
        pose[3] ~ qy
        pose[4] ~ qz
        pose[5] ~ px
        pose[6] ~ py
        pose[7] ~ pz
        for k in 1:6
            Vrelout[k] ~ Vrel[k]
        end
        modeout ~ mode
        Pd ~ mt * bt * (wl[1] * Vrel[4] + wl[2] * Vrel[5] + wl[3] * Vrel[6]) + br * (mr * (wa[1] * Vrel[1] + wa[2] * Vrel[2]) + mz * wa[3] * Vrel[3])
    end
    @events begin
        sw > 0.5 => begin
            reinit(mode, mode_new)
            reinit(mt, ifelse(mode_new > 0.5, 1.0, 0.0))
            reinit(mr, ifelse(mode_new > 1.5, 1.0, 0.0))
            reinit(mz, ifelse(mode_new > 2.5, 1.0, 0.0))
            reinit(dl, [0.0, 0.0, 0.0])
            reinit(dth, [0.0, 0.0, 0.0])
            reinit(wl, [0.0, 0.0, 0.0])
            reinit(wa, [0.0, 0.0, 0.0])
        end
    end
    @causality begin
        parent => :effort_out
        child => :effort_out
    end
end
