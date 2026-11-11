@block OpAmp begin
    @constants ideal::Int = 1, [options = ["finite gain", "ideal"], description = "1: ideal (infinite gain, the feedback holds the inputs equal, no saturation); 0: finite gain A with an output lag T_o and the output limited to the rails"]
    @ports begin
        in_p::Power{Electrical}
        in_n::Power{Electrical}
        out::Power{Electrical}
    end
    @parameters begin
        A::Real = 1.0e5, [unit = "1", min = 0, description = "Open-loop gain (finite-gain mode)"]
        T_o::Real = 1.0e-6, [unit = "s", min = 1.0e-15, description = "Output time constant (finite-gain mode); A/T_o is the gain-bandwidth product in rad/s"]
        V_pos::Real = 15.0, [unit = "V", description = "Positive supply rail: the highest output voltage (finite-gain mode)"]
        V_neg::Real = -15.0, [unit = "V", description = "Negative supply rail: the lowest output voltage (finite-gain mode)"]
    end
    @variables v_o::Real = 0.0, [unit = "V", state = :prefer, description = "Output voltage of the finite-gain mode (held at its start and unused in the ideal mode)"]
    @equations begin
        # Infinite input impedance: no current into either input.
        in_p.f ~ 0.0
        in_n.f ~ 0.0
        # The output is a voltage to ground whose current is free (it comes from the
        # supply). Ideal: a nullor, the feedback keeps the two inputs at equal voltage.
        # Finite gain: the amplified difference, limited to the rails, through a first-order
        # lag. The lag keeps the rail limit off the algebraic feedback loop, so entering
        # and leaving saturation are clean switching instants (no windup either).
        0.0 ~ ifelse(ideal == 1, in_p.e - in_n.e, out.e - v_o)
        ddt(v_o) ~ ifelse(
            ideal == 1,
            0.0,
            (clamp(A * (in_p.e - in_n.e), V_neg, V_pos) - v_o) / T_o,
        )
    end
    @orientation begin
        in_p => :in
        in_n => :in
        out => :in
    end
end
