# Soil

`SoilCutting2D` (custom) is a nonlinear resistive element on the bucket's planar bond. It uses the **fundamental
earthmoving equation** (Reece 1964, in McKyes' form) for a tool of width w at the cutting depth d:

$$F = w\,(\gamma d^2 N_\gamma + c\,d\,N_c) + \rho\,w\,d\,|v|^2,$$

against the tooth velocity v. The factors N_γ = 1.436 and N_c = 1.998 come from `design.py`: the flat-ground form
(Wagner 2025, eq. 15) for a 45° rake angle, an internal friction angle of 30° and a soil-tool friction of 20°,
minimised over the failure angle. The soil is a loam: unit weight 18 kN/m³, cohesion 15 kPa (the dashboard
slider goes to 60 kPa, stiff clay), density 1835 kg/m³.

**Fill.** The bucket takes the swept volume w·d·|v| times the swell factor 1.25 until it is full (0.93 m³
heaped) and spills once its mouth faces down. The soil in the bucket adds its weight at the centre of the
bucket (its inertia is not modelled). The depth is a smooth positive part of the penetration, so the force is
continuous and there are no events.

**Ground contact.** The cutting force grows with d², so the bucket cannot sink far: in the dig cycle the teeth
reach 0.43 m. The ground itself is flat at 1.95 m below the boom foot.
