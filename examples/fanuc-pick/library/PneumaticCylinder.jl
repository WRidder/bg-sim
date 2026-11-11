@block PneumaticCylinder begin
    # The pneumatic cylinder of one gripper zone, as the drive of its rod's prismatic joint
    # (bonded to `Prismatic3DLimit.drive` through a 1-junction; positive force and speed extend
    # the rod). It is an effort source: the port is `out` (the bond runs from the cylinder to
    # the junction), and its variables count power INTO the cylinder, so the port flow is minus
    # the rod speed: v = -p.f, and the cylinder delivers F v to the rod.
    #
    # A 5/2 valve `u` (+1 extend, -1 retract) puts the extend force `F_ext` (supply pressure on
    # the bore) or the retract force `F_ret` (on the annulus) on the piston, and the meter-out
    # flow control throttles the exhaust like a damper that sets the free speed:
    #
    #     F = 0.5 (1 + u) F_ext - 0.5 (1 - u) F_ret - b(u) v,
    #     b(u) = 0.5 (1 + u) F_ext / v_ext + 0.5 (1 - u) F_ret / v_ret,
    #
    # so an unloaded rod runs out at `v_ext` and in at `v_ret`, and a rod at its end stop presses
    # with the full force. The end stops (cushions) are the limits of the joint. The air
    # dynamics (filling time, compressibility) are left out; `F` is linear in `u`, so the valve
    # switch is a step at the planner tick and makes no zero-crossing.
    @ports p::Power{Translation}
    @inputs u::Real, [unit = "1", description = "Valve: +1 extend, -1 retract"]
    @parameters begin
        F_ext::Real = 120.0, [unit = "N", min = 0, description = "Extend force (supply pressure x bore area)"]
        F_ret::Real = 100.0, [unit = "N", min = 0, description = "Retract force (supply pressure x annulus area)"]
        v_ext::Real = 0.5, [unit = "m/s", min = 1.0e-6, description = "Free extend speed (flow control)"]
        v_ret::Real = 0.5, [unit = "m/s", min = 1.0e-6, description = "Free retract speed (flow control)"]
    end
    @outputs begin
        F::Real, [unit = "N", description = "Force on the rod (extend > 0)"]
        v::Real, [unit = "m/s", description = "Rod speed (extend > 0)"]
    end
    @equations begin
        v ~ -p.f
        F ~ 0.5 * (1 + u) * F_ext - 0.5 * (1 - u) * F_ret -
            (0.5 * (1 + u) * F_ext / v_ext + 0.5 * (1 - u) * F_ret / v_ret) * v
        p.e ~ F
    end
    @causality p => :effort_out
    @orientation p => :out
end
