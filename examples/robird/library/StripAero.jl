@block StripAero begin
    # Quasi-steady strip-theory aerodynamics of one rigid wing (or tail) segment, after van der Grinten
    # et al. (2015) eq. (8)-(11): the lift and the drag of every strip are
    #
    #   F_L = 1/2 rho v^2 S C_L(alpha),    C_L = La alpha + Lb          (affine in the angle of attack)
    #   F_D = 1/2 rho v^2 S C_D(alpha),    C_D = Db + Da |alpha|        (affine in |alpha|, smoothed)
    #
    # with v the speed of the strip relative to the air, in the plane of the chord and the surface
    # normal. The segment body frame is the joint child frame (origin on the span line through the
    # torsion axis); `ele` is the unit vector along the chord towards the leading edge, `en` the surface
    # normal (lift side), `es` the span direction, all in the body frame. Strip i sits at `rs[i]` along
    # the span and `xc[i]` along `ele` (negative = behind the torsion axis, where the centre of pressure
    # is) and has the area `S[i]`.
    #
    # Input: the body twist V = [w; v] of the `RigidBody3D` (body frame, at the centre of mass), the pose
    # chart (for the rotation of the world wind). The strip velocity relative to the air is
    # w_i = v + w x r_i - R^T wind. Output: the six scalar wrench components about the body origin that
    # `stdlib:multibond/ExternalWrenchSpatial` applies, so the power of the air force is exactly the sum
    # of F_i . w_i (`Pa` = the power given to the air). The angle of attack is limited smoothly to
    # +-amax (stall) by amax tanh(alpha / amax).
    @constants begin
        NS::Int = 3
    end
    @inputs begin
        V::Vec{6}
        pose::Vec{7}
        wind::Vec{3}
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        Pa::Real, [unit = "W"]
        alpha1::Real, [unit = "rad"]
        alphaN::Real, [unit = "rad"]
        Lift::Real, [unit = "N"]
    end
    @parameters begin
        ele::Vec{3} = [0.0, 0.0, 1.0], [description = "Unit vector along the chord towards the leading edge (body frame)"]
        en::Vec{3} = [0.0, 1.0, 0.0], [description = "Unit surface normal, lift side (body frame)"]
        es::Vec{3} = [1.0, 0.0, 0.0], [description = "Unit span direction (body frame)"]
        rs::Vec{NS} = [0.05, 0.10, 0.15], [unit = "m", description = "Strip positions along the span from the body origin"]
        xc::Vec{NS} = [-0.015, -0.015, -0.015], [unit = "m", description = "Strip centre of pressure along the leading-edge direction from the torsion axis"]
        S::Vec{NS} = [0.01, 0.01, 0.01], [unit = "m^2", min = 0, description = "Strip areas"]
        onev::Vec{NS} = [1.0, 1.0, 1.0], [description = "Summation vector"]
        rho::Real = 1.2, [unit = "kg/m^3", min = 0, description = "Air density"]
        La::Real = 4.5, [unit = "1/rad", description = "Lift slope (thesis L_a)"]
        Lb::Real = 0.2, [description = "Lift coefficient at zero angle of attack (thesis L_b)"]
        Da::Real = 0.6, [unit = "1/rad", min = 0, description = "Drag slope on |alpha| (thesis ID_a)"]
        Db::Real = 0.04, [min = 0, description = "Drag coefficient at zero angle of attack (thesis ID_b)"]
        amax::Real = 0.45, [unit = "rad", min = 0.01, description = "Stall limit of the angle of attack"]
    end
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        ub::Vec{3} = [0.0, 0.0, 0.0], [description = "Velocity of the body origin relative to the air"]
        rx::Vec{NS} = [0.0, 0.0, 0.0]
        ry::Vec{NS} = [0.0, 0.0, 0.0]
        rz::Vec{NS} = [0.0, 0.0, 0.0]
        wx::Vec{NS} = [0.0, 0.0, 0.0]
        wy::Vec{NS} = [0.0, 0.0, 0.0]
        wz::Vec{NS} = [0.0, 0.0, 0.0]
        wl::Vec{NS} = [1.0, 1.0, 1.0], [description = "Chordwise speed (towards the leading edge)"]
        wn::Vec{NS} = [0.0, 0.0, 0.0], [description = "Normal speed"]
        vp::Vec{NS} = [1.0, 1.0, 1.0], [description = "In-plane speed"]
        al::Vec{NS} = [0.0, 0.0, 0.0], [description = "Angle of attack, limited"]
        qd::Vec{NS} = [0.0, 0.0, 0.0], [description = "Dynamic pressure times area"]
        cl::Vec{NS} = [0.0, 0.0, 0.0]
        cd::Vec{NS} = [0.0, 0.0, 0.0]
        gx::Vec{NS} = [0.0, 0.0, 0.0]
        gy::Vec{NS} = [0.0, 0.0, 0.0]
        gz::Vec{NS} = [0.0, 0.0, 0.0]
        Fx::Vec{NS} = [0.0, 0.0, 0.0]
        Fy::Vec{NS} = [0.0, 0.0, 0.0]
        Fz::Vec{NS} = [0.0, 0.0, 0.0]
        Mx::Vec{NS} = [0.0, 0.0, 0.0]
        My::Vec{NS} = [0.0, 0.0, 0.0]
        Mz::Vec{NS} = [0.0, 0.0, 0.0]
        Pw::Vec{NS} = [0.0, 0.0, 0.0]
        Ls::Vec{NS} = [0.0, 0.0, 0.0]
    end
    @equations begin
        s ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        R[1, 1] ~ (pose[1] * pose[1] + pose[2] * pose[2] - pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[1, 2] ~ 2 * (pose[2] * pose[3] - pose[1] * pose[4]) / s
        R[1, 3] ~ 2 * (pose[2] * pose[4] + pose[1] * pose[3]) / s
        R[2, 1] ~ 2 * (pose[2] * pose[3] + pose[1] * pose[4]) / s
        R[2, 2] ~ (pose[1] * pose[1] - pose[2] * pose[2] + pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[2, 3] ~ 2 * (pose[3] * pose[4] - pose[1] * pose[2]) / s
        R[3, 1] ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        R[3, 2] ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        R[3, 3] ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
        ub[1] ~ V[4] - (R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3])
        ub[2] ~ V[5] - (R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3])
        ub[3] ~ V[6] - (R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3])
        for i in 1:NS
            rx[i] ~ rs[i] * es[1] + xc[i] * ele[1]
            ry[i] ~ rs[i] * es[2] + xc[i] * ele[2]
            rz[i] ~ rs[i] * es[3] + xc[i] * ele[3]
            wx[i] ~ ub[1] + V[2] * rz[i] - V[3] * ry[i]
            wy[i] ~ ub[2] + V[3] * rx[i] - V[1] * rz[i]
            wz[i] ~ ub[3] + V[1] * ry[i] - V[2] * rx[i]
            wl[i] ~ wx[i] * ele[1] + wy[i] * ele[2] + wz[i] * ele[3]
            wn[i] ~ wx[i] * en[1] + wy[i] * en[2] + wz[i] * en[3]
            vp[i] ~ sqrt(wl[i] * wl[i] + wn[i] * wn[i] + 0.01)
            al[i] ~ amax * tanh(atan(-wn[i], sqrt(wl[i] * wl[i] + 0.01)) / amax)
            qd[i] ~ 0.5 * rho * vp[i] * vp[i] * S[i]
            cl[i] ~ La * al[i] + Lb
            cd[i] ~ Db + Da * sqrt(al[i] * al[i] + 1.0e-4)
            Ls[i] ~ qd[i] * cl[i]
            gx[i] ~ (wl[i] * en[1] - wn[i] * ele[1]) / vp[i]
            gy[i] ~ (wl[i] * en[2] - wn[i] * ele[2]) / vp[i]
            gz[i] ~ (wl[i] * en[3] - wn[i] * ele[3]) / vp[i]
            Fx[i] ~ qd[i] * (cl[i] * gx[i] - cd[i] * (wl[i] * ele[1] + wn[i] * en[1]) / vp[i])
            Fy[i] ~ qd[i] * (cl[i] * gy[i] - cd[i] * (wl[i] * ele[2] + wn[i] * en[2]) / vp[i])
            Fz[i] ~ qd[i] * (cl[i] * gz[i] - cd[i] * (wl[i] * ele[3] + wn[i] * en[3]) / vp[i])
            Mx[i] ~ ry[i] * Fz[i] - rz[i] * Fy[i]
            My[i] ~ rz[i] * Fx[i] - rx[i] * Fz[i]
            Mz[i] ~ rx[i] * Fy[i] - ry[i] * Fx[i]
            Pw[i] ~ -(Fx[i] * wx[i] + Fy[i] * wy[i] + Fz[i] * wz[i])
        end
        fx ~ dot(Fx, onev)
        fy ~ dot(Fy, onev)
        fz ~ dot(Fz, onev)
        tx ~ dot(Mx, onev)
        ty ~ dot(My, onev)
        tz ~ dot(Mz, onev)
        Pa ~ dot(Pw, onev)
        Lift ~ dot(Ls, onev)
        alpha1 ~ al[1]
        alphaN ~ al[NS]
    end
end
