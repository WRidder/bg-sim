@block RotorWrench begin
    # Wrench of N rotors and of the air on the airframe (body frame, about the centre of mass),
    # as the six scalar inputs of `stdlib:multibond/ExternalWrenchSpatial`. Reusable for any
    # rotor layout: positions `rx`, `ry` (m), spin signs `spin` (+1 = counter-clockwise seen
    # from above, i.e. a positive rotation about the body z axis) and `onev` (all ones) are
    # parameters; N is a structural constant.
    #
    # Inputs: the rotor thrusts `T` (from `Propeller`), the motor currents `i` and the rotor
    # speeds `w` relative to the airframe (from `ElectricDrive`), the body twist `V` of the
    # `RigidBody3D` ([w; v], body frame), the pose chart of the body and the world wind velocity.
    #
    # Terms (body frame, thrust along +z):
    #   thrust          F = (0, 0, sum T) and its moment about the centre of mass, r_k x F_k
    #   motor reaction  -spin_k (k_t i_k - b_m w_k) about z: the torque the stator (the airframe)
    #                   feels from rotor k. It is the electromagnetic torque minus the bearing
    #                   friction, i.e. the rotor's inertia torque plus the propeller drag torque,
    #                   so the motor power balances
    #   gyroscopic      -Omega x h with h = Jr sum(spin_k w_k) e_z, the rotors' spin momentum
    #                   (its rate of change is already the reaction torque above)
    #   air             -cd (v - R^T wind) per axis (linear drag) and -cdr Omega (rotational damping)
    #
    # `leg` are the normal forces of the landing-gear contacts (world z, `ContactPoint.f_n`); they are
    # not part of the wrench (the contacts are bonded to the body themselves) but the accelerometer
    # feels them: standing on the ground it reads +g.
    #
    # `fs` is the specific force (non-gravitational force over mass) an accelerometer at the
    # centre of mass measures: thrust and drag, never gravity.
    @constants begin
        N::Int = 4
        NL::Int = 4
    end
    @inputs begin
        T::Vec{N}
        i::Vec{N}
        w::Vec{N}
        V::Vec{6}
        pose::Vec{7}
        wind::Vec{3}
        leg::Vec{NL}
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
        fs::Vec{3}
    end
    @parameters begin
        rx::Vec{N} = [0.159, -0.159, 0.159, -0.159], [unit = "m", description = "Rotor x position in the body frame (forward)"]
        ry::Vec{N} = [-0.159, 0.159, 0.159, -0.159], [unit = "m", description = "Rotor y position in the body frame (left)"]
        spin::Vec{N} = [1.0, 1.0, -1.0, -1.0], [description = "Spin direction of each rotor, +1 counter-clockwise from above"]
        onev::Vec{N} = [1.0, 1.0, 1.0, 1.0], [description = "Summation vector over the rotors"]
        onel::Vec{NL} = [1.0, 1.0, 1.0, 1.0], [description = "Summation vector over the landing-gear contacts"]
        kt::Real = 0.01038, [unit = "N*m/A", description = "Motor torque constant"]
        bm::Real = 2.0e-6, [unit = "N*m*s/rad", description = "Motor viscous loss (as in the ElectricDrive b_m)"]
        Jr::Real = 5.0e-5, [unit = "kg*m^2", description = "Rotor plus propeller inertia (as in the ElectricDrive J_m)"]
        m::Real = 1.35, [unit = "kg", min = 0, description = "Total mass (for the specific force)"]
        cdx::Real = 0.25, [unit = "N*s/m", min = 0, description = "Linear air drag, body x"]
        cdy::Real = 0.25, [unit = "N*s/m", min = 0, description = "Linear air drag, body y"]
        cdz::Real = 0.35, [unit = "N*s/m", min = 0, description = "Linear air drag, body z (rotor discs)"]
        cdr::Real = 2.0e-3, [unit = "N*m*s/rad", min = 0, description = "Rotational air damping about every axis"]
    end
    @variables begin
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        s::Real = 1.0, [description = "Squared quaternion norm"]
        vax::Real = 0.0, [description = "Air-relative velocity, body x"]
        vay::Real = 0.0, [description = "Air-relative velocity, body y"]
        vaz::Real = 0.0, [description = "Air-relative velocity, body z"]
        hz::Real = 0.0, [description = "Rotor spin momentum along z"]
        fc::Real = 0.0, [unit = "N", description = "Total normal contact force of the landing gear (world z)"]
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
        vax ~ V[4] - (R[1, 1] * wind[1] + R[2, 1] * wind[2] + R[3, 1] * wind[3])
        vay ~ V[5] - (R[1, 2] * wind[1] + R[2, 2] * wind[2] + R[3, 2] * wind[3])
        vaz ~ V[6] - (R[1, 3] * wind[1] + R[2, 3] * wind[2] + R[3, 3] * wind[3])
        hz ~ Jr * dot(spin, w)
        fx ~ -cdx * vax
        fy ~ -cdy * vay
        fz ~ dot(T, onev) - cdz * vaz
        tx ~ dot(ry, T) - V[2] * hz - cdr * V[1]
        ty ~ -dot(rx, T) + V[1] * hz - cdr * V[2]
        tz ~ -(kt * dot(spin, i) - bm * dot(spin, w)) - cdr * V[3]
        fc ~ dot(leg, onel)
        fs[1] ~ fx / m + R[3, 1] * fc / m
        fs[2] ~ fy / m + R[3, 2] * fc / m
        fs[3] ~ fz / m + R[3, 3] * fc / m
    end
end
