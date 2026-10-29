@block SeSpatial begin
    # Spatial effort source (the spatial `Se`): imposes a `Vec{6}` wrench on its bond with
    # fixed effort-out causality. The input is a single `Vec{6}` signal, exactly like
    # `SePlanar`; the *components of the port* keep their own units
    # (`p.e[1]` N*m, `p.e[4]` N), which is the D-MB10 rule.
    #
    # Limitation (v1 contract deviation, ADR-MB1 "M3 final"): a `Vec{6}` **signal** has one unit slot in v1, so the
    # wrench *input* `u` is unit-homogeneous in the catalog and the manifest cannot show a
    # torque next to a force for it. The power port itself is per-component (asserted in
    # `test_spatial_slice.jl`); a per-component signal declaration is a contract change
    # (`signalDecl.size` plus a unit array); C-MB2 recorded it as a v1 deviation (ADR-MB1,
    # "M3 final"): per-component units are authoritative on the power port.
    # `ExternalWrenchSpatial` is the six-scalar form where each component does carry its own
    # unit.
    @ports p::Power{Spatial}
    @inputs u::Vec{6}
    @equations begin
        p.e[1] ~ u[1]
        p.e[2] ~ u[2]
        p.e[3] ~ u[3]
        p.e[4] ~ u[4]
        p.e[5] ~ u[5]
        p.e[6] ~ u[6]
    end
    @causality p => (:effort_out, :fixed)
end
