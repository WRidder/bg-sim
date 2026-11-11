@block WedgeHook begin
    # Wedge-hook jaw drive of a parallel gripper: the axial nut stroke `a` moves BOTH jaws through
    # inclined wedge faces, so each jaw closes at `i_w` times the nut speed and the two jaws stay
    # synchronised (centric gripping). Port `b` is the common jaw-closing coordinate: its flow is
    # the closing speed of each jaw and its effort is the SUM of the closing forces of the two
    # jaws (one jaw node carries both jaws; a jaw's own force is half of it when the part is
    # centred). Ideal transformer: `b.f = i_w a.f`, `a.e = -i_w b.e` (power-continuous); the
    # sliding friction of the wedge is lumped into the lead-screw efficiency.
    #
    # i_w = tan(wedge angle) for a hook whose wedge faces make that angle with the stroke:
    # i_w = 0.5 is a 26.6 deg wedge, which doubles the force (F_jaws = F_nut / i_w).
    @ports begin
        a::Power{Translation}
        b::Power{Translation}
    end
    @parameters i_w::Real = 0.5, [unit = "1", min = 1.0e-6, description = "Jaw closing speed over nut speed (tan of the wedge angle)"]
    @equations begin
        b.f ~ i_w * a.f
        a.e ~ -i_w * b.e
    end
    @causality (a, b) => :transformer
    @orientation begin
        a => :in
        b => :in
    end
end
