@block Guideway begin
    # Vertical profile of the guideway under a levitation module at the track coordinate s: a
    # row of simply supported spans that sag between the pillars, plus one smooth misalignment
    # bump (a joint between two beams). The module sits x_off ahead of the input coordinate s. The profile is positive downward (towards the vehicle):
    #   z(s) = A_sag*sin^2(pi*s/L_span)                       (one half-wave of sag per span)
    #        + A_b/2*(1 - cos(2*pi*(s - s_b)/lam_b))           for s_b <= s <= s_b + lam_b
    # and the rail velocity (positive upward) the module sees while it runs at speed v is w = -v*dz/ds.
    @inputs begin
        s::Real, [unit = "m", description = "Track coordinate of the module"]
        v::Real, [unit = "m/s", description = "Speed along the track"]
    end
    @outputs begin
        z::Real, [unit = "m", description = "Guideway deflection, positive towards the vehicle"]
        w::Real, [unit = "m/s", description = "Guideway velocity seen by the module, positive upward: -v*dz/ds"]
        ph::Real, [unit = "m", description = "Position of the input coordinate within its span, s mod L_span (scrolls the pillars of the scene)"]
    end
    @parameters begin
        L_span::Real = 24.768, [unit = "m", min = 1.0e-6, description = "Span length (a double-span beam of the Transrapid)"]
        A_sag::Real = 0.003, [unit = "m", description = "Sag of a span at mid-span"]
        s_b::Real = 1000.0, [unit = "m", description = "Track coordinate where the bump starts"]
        A_b::Real = 0.002, [unit = "m", description = "Height of the bump"]
        lam_b::Real = 12.0, [unit = "m", min = 1.0e-6, description = "Length of the bump"]
        x_off::Real = 0.0, [unit = "m", description = "Position of the module relative to the track coordinate input (front +)"]
    end
    @variables begin
        sm::Real = 0.0, [unit = "m", description = "Track coordinate of the module, s + x_off"]
        inb::Real = 0.0, [description = "1 on the bump, else 0"]
        dzds::Real = 0.0, [description = "Slope dz/ds"]
    end
    @equations begin
        sm ~ s + x_off
        inb ~ ifelse(sm > s_b, ifelse(sm < s_b + lam_b, 1.0, 0.0), 0.0)
        z ~ A_sag * sin(3.141592653589793 * sm / L_span)^2 +
            inb * 0.5 * A_b * (1.0 - cos(6.283185307179586 * (sm - s_b) / lam_b))
        dzds ~ A_sag * (3.141592653589793 / L_span) * sin(6.283185307179586 * sm / L_span) +
               inb * A_b * (3.141592653589793 / lam_b) * sin(6.283185307179586 * (sm - s_b) / lam_b)
        w ~ -v * dzds
        ph ~ s - L_span * floor(s / L_span)
    end
end
