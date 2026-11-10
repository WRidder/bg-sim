# Parameters and sources

The README of the example lists every number with its source; `design/data.py` holds them.

- **Published.** Apollo 11 Mission Report (MSC-00171): masses and moments of inertia at PDI, landing, lift-off and insertion; event times; ascent engine thrust and specific impulse; touchdown velocities. *Apollo by the Numbers* (SP-2000-4029): the descent propellant budget (17,414 lb consumed, 770 lb left, 674 lb of it usable). TN D-6846: the throttle logic (10 to 60 %, recovery at 57 %, 26 s at trim), the premission descent profile, the ascent targets. TN D-6850: the footpad radius (167.57 in), the probes, the touchdown envelope, the strut cartridges. Descent engine: rated 10,500 lbf, fixed throttle position 9,870 lbf, specific impulse 305 s.
- **Estimated.** Thrust lags, the attitude loop, the RCS moment arm, the centre of mass above the pads (put at the guidance's 6.4 ft altitude reference), the pad damping.
- **Fitted.** The PDI range to the landing site (481 km; the report says about 260 n mi = 482 km) is fitted to the throttle recovery at 386 s. The braking-phase target is fitted to high gate (7,129 ft at 125 ft/s descent, 507 s). The approach-phase target is fitted to Aldrin's first four callouts. The pad stiffness is chosen so that the LM settles 3 in into the soil (MR: 2.5 to 3.5 in).
- **Pilot model.** In the landing phase the LM follows Aldrin's called descent rates and forward speeds as functions of altitude.

**Limits.** A non-rotating spherical Moon of the mean radius; no centre-of-mass shift and no products of inertia; an ideal saturated RCS loop with no jet logic; no gimbal trim, no slosh, no RCS propellant; rigid struts (the gear is four compliant pads). The 2.1 ft/s lateral drift at touchdown is not modelled.
