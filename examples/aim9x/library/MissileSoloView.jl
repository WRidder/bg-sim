@block MissileSoloView begin
    # Poses and display factors for the missile's own 3D view (a tap: no physics). The missile
    # stays at the origin with its attitude; the plume scales with the motor thrust.
    #
    #   m_pose   the body attitude at the origin
    #   plume    motor thrust over the reference thrust, for a scale binding
    @inputs begin
        g::Vec{7}, [description = "Missile pose"]
        T::Real, [unit = "N", description = "Motor thrust"]
    end
    @parameters begin
        T_ref::Real = 20000.0, [unit = "N", min = 1.0, description = "Thrust that draws the full plume"]
        z0::Real = 2.5, [unit = "m", description = "Display height above the reference grid"]
    end
    @outputs begin
        m_pose::Vec{7}
        plume::Real, [description = "Plume scale, 0..1.2"]
    end
    @equations begin
        m_pose[1] ~ g[1]
        m_pose[2] ~ g[2]
        m_pose[3] ~ g[3]
        m_pose[4] ~ g[4]
        m_pose[5] ~ 0.0
        m_pose[6] ~ 0.0
        m_pose[7] ~ z0
        plume ~ clamp(T / T_ref, 0.0, 1.2)
    end
end
