@block RotorWrench begin
    # Wrench of the N rotors and of the air on the airframe (body frame, about the centre of mass),
    # as the six scalar inputs of `stdlib:multibond/ExternalWrenchSpatial`. Reusable for any rotor
    # layout: positions `rx`, `ry` (m), spin signs `spin` (+1 = counter-clockwise seen from above, a
    # positive rotation about the body z axis) and `onev` (all ones) are parameters; N is a constant.
    #
    # Inputs: the rotor thrusts `T` (from `Propeller`), the motor currents `i` and the rotor speeds `w`
    # relative to the airframe (from `ElectricDrive`) and the body twist `V` of the `RigidBody3D`
    # ([w; v], body frame).
    #
    # Terms (body frame, thrust along +z):
    #   thrust          F = (0, 0, sum T) and its moment about the centre of mass, r_k x F_k
    #   motor reaction  -spin_k (k_t i_k - b_m w_k) about z: the torque the stator (the airframe)
    #                   feels from rotor k: the rotor's inertia torque plus the propeller drag torque,
    #                   so the motor power balances
    #   gyroscopic      -Omega x h with h = Jr sum(spin_k w_k) e_z, the rotors' spin momentum
    #   air             -cd v per axis (linear drag, still air: the sample flies indoors) and -cdr Omega
    #
    # The manipulator is a separate body bonded to the airframe through the servo joint; its reaction
    # reaches the airframe through that joint, never through this block.
    @constants N::Int = 6
    @inputs begin
        T::Vec{N}
        i::Vec{N}
        w::Vec{N}
        V::Vec{6}
    end
    @outputs begin
        tx::Real, [unit = "N*m"]
        ty::Real, [unit = "N*m"]
        tz::Real, [unit = "N*m"]
        fx::Real, [unit = "N"]
        fy::Real, [unit = "N"]
        fz::Real, [unit = "N"]
    end
    @parameters begin
        rx::Vec{N} = [0.3464, 0.0, -0.3464, -0.3464, 0.0, 0.3464], [unit = "m", description = "Rotor x position in the body frame (forward)"]
        ry::Vec{N} = [0.2, 0.4, 0.2, -0.2, -0.4, -0.2], [unit = "m", description = "Rotor y position in the body frame (left)"]
        spin::Vec{N} = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0], [description = "Spin direction of each rotor, +1 counter-clockwise from above"]
        onev::Vec{N} = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0], [description = "Summation vector over the rotors"]
        kt::Real = 0.01005, [unit = "N*m/A", description = "Motor torque constant"]
        bm::Real = 2.0e-6, [unit = "N*m*s/rad", description = "Motor viscous loss (as in the ElectricDrive b_m)"]
        Jr::Real = 5.0e-5, [unit = "kg*m^2", description = "Rotor plus propeller inertia (as in the ElectricDrive J_m)"]
        cdx::Real = 0.25, [unit = "N*s/m", min = 0, description = "Linear air drag, body x"]
        cdy::Real = 0.25, [unit = "N*s/m", min = 0, description = "Linear air drag, body y"]
        cdz::Real = 0.35, [unit = "N*s/m", min = 0, description = "Linear air drag, body z (rotor discs)"]
        cdr::Real = 3.0e-3, [unit = "N*m*s/rad", min = 0, description = "Rotational air damping about every axis"]
    end
    @variables hz::Real = 0.0, [description = "Rotor spin momentum along z"]
    @equations begin
        hz ~ Jr * dot(spin, w)
        fx ~ -cdx * V[4]
        fy ~ -cdy * V[5]
        fz ~ dot(T, onev) - cdz * V[6]
        tx ~ dot(ry, T) - V[2] * hz - cdr * V[1]
        ty ~ -dot(rx, T) + V[1] * hz - cdr * V[2]
        tz ~ -(kt * dot(spin, i) - bm * dot(spin, w)) - cdr * V[3]
    end
end
