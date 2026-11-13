# Lunar module: Apollo 11's Eagle on a variable-mass 3D bond graph

Three models of the Apollo 11 lunar module (LM-5, "Eagle"), all on the same 3D (multibond) bond graph of a rigid body that loses mass:

| model | what it is |
| --- | --- |
| `lm-descent` | the **powered descent**, from descent-engine ignition (PDI, 102:33:05) 15 km up at 1,695 m/s to touchdown on four footpads in the Sea of Tranquility: the braking phase (P63) and the approach phase (P64) on Apollo's quadratic guidance, the landing phase (P66) on a pilot model built from Aldrin's callouts, the descent engine's throttle logic, the face-up yaw manoeuvre and the RCS attitude loop |
| `lm-hover` | the **landing phase flown from the dashboard**: start in a hover with Armstrong's propellant at P66 entry, set the descent rate and a forward translation, and land before the hover time runs out |
| `lm-ascent` | the **ascent stage** from lift-off (124:22:00) to orbit insertion: vertical rise, pitch-over and Apollo's linear ascent guidance to 60,000 ft and 5,535 ft/s, cut on the target velocity |

Why the lunar module: the descent is one of the best documented powered flights there is. The **Apollo 11 Mission Report** (MSC-00171, 1969) gives the event times, the mass properties at every event, the engine performance and the touchdown velocities; *Apollo by the Numbers* (SP-2000-4029) the propellant budget; TN D-6846 the premission descent profile and the guidance design; TN D-6850 the landing gear; the Apollo Lunar Surface Journal the transcript with Aldrin's altitude callouts.

## The bond graph

The vehicle is a `stdlib:spatial/Free3D` joint from the ground (`World`) to the vehicle's 1-junction `Body`. On the junction sit:

- `Inertia`, project block `VariableInertia3D`: a **modulated spatial inertia** (MI). Its state is the body-frame momentum `P = [h; p]` as in `stdlib:multibond/ISpatial`, but the mass `m(t)` and the principal moments `J(t)` are input signals (from `Tank`).
- `Coriolis` (`CoriolisSpatial`, the gyroscopic terms) and `Twist` (`DfSpatial`, the twist tap).
- three `ExternalWrenchSpatial` sources: the engine thrust along the body x axis (`ThrustW`), the RCS torques (`RcsW`) and inverse-square lunar gravity (`GravityW`).
- six `stdlib:bondgraph/MR` elements `Out1..Out6` on the joint's drive ports, with resistance `r = -dm/dt` on the three linear and `r = -dJk/dt` on the three angular twist components: the propellant that leaves takes its momentum with it. With the MI this gives `m dv/dt = F` and `J dw/dt = M` (+ gyroscopic terms). The vacuum check (`lm-ascent-vacuum` in `expected.json`) proves it: without gravity and with the thrust held vertical the speed is Tsiolkovsky's `c ln(m0/m)` to 1e-6.
- `lm-descent` and `lm-hover` add the **landing gear**: four `stdlib:contact/ContactPoint`s, one per footpad, each mounted at its pad through a `FixedTransform3DNeutral` bonded to `Body`, with the lunar sphere below it (`LunarSurface3D`) as the contact plane. The pads sit 167.57 in from the thrust axis (TN D-6850). Each contact is a Hunt-Crossley spring-damper for pad, strut and soil with Coulomb friction 0.4. The footpads `Pad1..4` are instances of the library subsystem `LunarFoot` (`library/LunarFoot.bgsub.json`, generated: pad pose `Local` + `Compose`, the sphere below it `Surface`, the body-to-pad `Mount` and the `ContactPoint` named `Contact`; each instance pins its pad position), so a pad's force is `Pad<k>/Contact/f_n`.

The flight runs in a site frame: origin at the landing site, x downrange (west to east along the ground track), z up, the Moon's centre at `(0, 0, -R)`. The body axes are the LM's: X up the thrust axis, Y to the crew's right, Z forward through the hatch.

## Custom library blocks (`library/`)

| block | why it is needed |
| --- | --- |
| `VariableInertia3D` | the stdlib `ISpatial` has constant mass and inertia; this is the same element with them as inputs (a modulated I). Copied from the rocket example |
| `PropellantTank` | integrates the engine's flow into the mass; the moments of inertia linear in the mass between two published mass-property points; outputs the MR resistances `-dm/dt`, `-dJk/dt` and the usable propellant |
| `Engine3D` | thrust with a first-order lag, flow `T / c`, the wrench along body x |
| `CentralGravity3D` | inverse-square gravity of a sphere on the variable mass (a `gravity_scale` global) |
| `DpsThrottle` | the descent engine's throttle logic: 26 s at trim (10 %), the fixed throttle position (94 %) until the guidance asks for less than 57 % (throttle recovery, latched), then throttleable between 10 and 60 %; shutdown at touchdown or when the usable propellant is gone |
| `DescentGuidance` | P63 and P64 as Apollo's quadratic (target-referenced) guidance `a = aT + 12 (rT - r) / tgo^2 - 6 (v + vT) / tgo`; P66 a rate-of-descent and horizontal-velocity loop on the pilot's commands. Outputs the thrust direction and the thrust request |
| `AscentGuidance` | vertical rise to 40 ft/s radial rate, then linear guidance on radial position and rate with the remaining acceleration downrange; cutoff on the target downrange velocity |
| `AttitudeControl` | an ideal attitude loop on the RCS torque (saturated at four 445 N jets on a 1.67 m arm) that points body x along the guidance direction, with the windows' roll angle about it |
| `LMState`, `PropulsionStatus`, `OrbitElements` | readouts: altitude, range, radial and horizontal velocity, tilt, height of the lowest footpad; velocity gained, thrust-to-weight, hover time left; apolune and perilune |
| `LunarSurface3D` | the stdlib `ContactSurface` is one fixed plane; over the 480 km of the descent the site's plane is tens of kilometres off the surface, so the contact uses the tangent plane of the sphere straight below each pad |
| `LMView` | the 3D view keeps the vehicle at the origin and moves the world (the surface patch below the vehicle and the landing site) |

## Parameters and sources

Tags: **pub** published, **der** derived from published numbers, **est** estimated (no published number found), **fit** fitted to published data (`design/design.py`). All numbers live in `design/data.py` with their source.

| quantity | value | tag | source |
| --- | --- | --- | --- |
| LM mass at PDI (DOI cutoff) | 33,401.6 lb (15,151 kg) | pub | Mission Report (MR) app. A |
| LM mass at landing | 16,153.2 lb (7,327 kg) | pub | MR app. A |
| moments of inertia at PDI / landing | 23,480 / 25,978 / 25,871 and 12,582 / 13,667 / 16,204 slug ft² | pub | MR app. A (products of inertia omitted) |
| DPS propellant burned in powered descent | 17,146 lb | der | SP-2000-4029: 17,414 lb consumed less the 268 lb DOI burn (MR app. A) |
| DPS propellant left at cutoff | 770 lb, of which 674 lb usable | pub | SP-2000-4029 |
| DPS rated thrust | 10,500 lbf | pub | Wikipedia (Descent propulsion system) |
| fixed throttle position | 9,870 lbf (43,900 N) | pub | Chariots for Apollo (SP-4205) |
| throttleable range, recovery threshold | 10 .. 60 %, 57 % | pub | TN D-6846 |
| time at trim throttle | 26 s | pub | TN D-6846, MR 9.8 |
| DPS specific impulse | 305 s | pub | enginehistory.org (LMDE); Wikipedia gives 311 s at full and 285 s at 10 % thrust |
| thrust lag | 0.3 s (DPS), 0.2 s (APS) | est | |
| RCS torque | 4 × 445 N × 1.67 m | pub / est | 445 N per jet (Wikipedia); the moment arm is estimated |
| attitude loop | ωn 0.9 rad/s, ζ 0.9 | est | |
| footpad radius from the X axis | 167.57 in | pub | TN D-6850 |
| footpad diameter, probe length | 3 ft, 5.6 ft | pub | TN D-6850, TN D-6846 |
| centre of mass above the pad soles | 12 ft − 5.6 ft = 6.4 ft | der / est | TN D-6846 gives 12 ft altitude at probe contact; the CoM is put at the guidance's altitude reference |
| gear contact: stiffness, damping, friction | 3 kN at 3 in (Hertz exponent 3/2), c = 2 s/m, μ = 0.4 | fit / est / pub | the stiffness is chosen so that a pad settles 3 in under a quarter of the landing weight (MR 5.4: the pads penetrated 2.5 to 3.5 in); friction 0.4 from TN D-6850's postflight analysis; damping estimated |
| PDI state | 49,376 ft, 5,560 ft/s, −4 ft/s | pub | MR table 5-III, TN D-6846 table I |
| PDI range to the site | 481.3 km | **fit** | fitted to the throttle recovery at 386 s (MR 5.3); TN D-6846: "approximately 260 n mi" (482 km) |
| P63 target (high gate) | 7,129 ft at 125 ft/s descent, 507 s | pub, **fit** | MR 5.3 / table 5-I; the target acceleration is fitted to it |
| P64 target | 88.8 m above the site at 646 s, 1,100 ft beyond the initial aim point | **fit** / pub | fitted to Aldrin's callouts at 596 .. 611 s; the aim-point shift is MR 5.3 |
| P66 pilot model | descent rate and forward speed over altitude | pub | Aldrin's callouts (ALSJ), touchdown 1.7 ft/s (MR 5.4) |
| P66 loop time constants | 2 s (vertical), 5 s (horizontal), 0.6 m/s² limit | est | |
| face-up yaw manoeuvre | 232 .. 294 s | pub | MR table 5-I |
| ascent stage at lift-off / insertion | 10,776.6 / 5,928.6 lb | pub | MR app. A |
| ascent moments of inertia | 6,808 / 3,475 / 5,971 and 3,457 / 3,082 / 2,273 slug ft² | pub | MR app. A |
| APS propellant loaded | 5,238 lb | pub | SP-2000-4029 |
| APS thrust, Isp | 3,464 lbf, 309.4 s | pub | MR table 9.9-I (predicted, 10 s after ignition) |
| ascent targets | 60,000 ft, 32.2 ft/s radial, 5,534.9 ft/s downrange | pub | TN D-6846 table V |
| end of the vertical rise | 40 ft/s radial rate | pub | TN D-6846 |
| ascent-stage CoM at lift-off | 4.3 m above the surface | est | |
| Moon | μ = 4.9028e12 m³/s², R = 1,737.4 km | pub | |

## Validation

`expected.json` has three kinds of checks, each note saying which:

1. **scipy reference, tight.** `design/reference.py` integrates the same equations as an independent 6-DOF rigid body (quaternion attitude, DOP853 at rtol 1e-10, the mode switches as events). The models match it to 2e-4 in altitude and speed and 2e-5 in mass, and in the event times (throttle recovery, touchdown, ascent cutoff).
2. **analytic, exact.** Tsiolkovsky in vacuum (`lm-ascent-vacuum`), and the rocket equation of a hover (`lm-hover-hold`: a hover at 100 ft burns `m(t) = m0 exp(-g t / c)`, so the propellant is gone at `(c/g) ln(m0/m_empty)`).
3. **published, honest tolerances.** Fitted quantities are marked FITTED; the rest are independent comparisons:

| quantity | published | model (reference) | tolerance |
| --- | --- | --- | --- |
| throttle recovery | 386 s | 386.0 s | fitted |
| high gate | 7,129 ft, −125 ft/s | 7,160 ft, −124 ft/s | fitted |
| premission states at 176, 258, 384, 402 s | TN D-6846 table I | speeds within 4 %, altitudes up to 13 % lower | 4 %, 15 % |
| Aldrin's callouts 400 .. 20 ft | ALSJ | mostly within 10 ft; 58 ft at "40", 44 ft at "20" | 35 ft (in time order) |
| landing | 754.9 s | 758.3 s | 8 s |
| mass at engine cutoff | 7,374 kg (DPS only) | 7,426 kg | 1 % |
| usable propellant left | 674 lb (306 kg) | 358 kg | 25 % |
| velocity gained to high gate, low gate | 5,375, 6,176 ft/s (premission) | 5,411, 6,157 ft/s | 2 % |
| velocity gained to touchdown | about 6,775 ft/s | 6,997 ft/s | 5 % |
| touchdown vertical / horizontal | 1.7 ft/s / 2.1 ft/s | 1.6 / 2.6 ft/s | gear envelope 7 and 4 ft/s |
| footpad penetration at rest | 2.5 to 3.5 in | 3.0 in | fitted |
| peak footpad load | no primary-strut stroking (TN D-6850 table V): below the 4,500 lb cartridge | 21.9 kN = 4,930 lb on the forward pad | checked against the 9,500 lb cartridge only; see below |
| ascent burn | 434.88 s | 437.4 s | 6 s |
| ascent stage at insertion | 5,928.6 lb (2,689 kg) | 2,666 kg | 2 % |
| ascent velocity change | 6,070.1 ft/s | 6,036 ft/s | 2 % |
| orbit after the ascent burn | 48.0 × 9.1 n mi (88.9 × 16.9 km) | 88.3 × 16.9 km | 3 km |

The descent burns 0.7 % less propellant than Eagle did with the published 305 s, and the velocity gained to touchdown is 3 % high: the model has no gimbal trim, no slosh and no attitude jitter, and Armstrong's landing phase was flown with pitch and roll excursions that the pilot model leaves out.

The forward pad's peak load at touchdown is about 10 % above the 4,500 lb at which the primary strut's first honeycomb cartridge would crush, while no primary strut stroked on Apollo 11. The model's struts are rigid, its pad force stands for the primary and both secondary struts together, and the horizontal-velocity loop leaves the LM tilted 4.5 deg at contact, so it rocks from an aft pad onto the forward one. The check therefore holds the pad loads only against the 9,500 lb second cartridge.

The ascent engine is cut when the downrange velocity plus the velocity the 0.2 s thrust tail-off still adds (`T t_tail / m`) reaches the target, as the guidance computer anticipated the tail-off; without it the apolune would come out 4.7 km high.

## Limitations

- The Moon is a non-rotating sphere of the mean radius (1,737.4 km); the landing site lies 1.8 km below it, so the altitudes are above the sphere, as the guidance's are.
- The centre of mass stays at the body origin (its 27 in shift up the X axis during the descent is not modelled); the products of inertia are omitted.
- The RCS is an ideal saturated attitude loop: no jet logic, no RCS propellant (95 lb in the descent), no gimbal trim of the descent engine.
- No propellant slosh; the 45 s of hover time Eagle had left (SP-2000-4029) reflects a tank imbalance that the model does not have.
- The P66 pilot model holds Aldrin's called rates; the 2.1 ft/s lateral drift at touchdown and the pitch excursions to clear the boulder field are not modelled.
- The landing gear is four compliant Hunt-Crossley pads on rigid struts, not the struts' honeycomb crush; the probes are drawn but do not sense (the engine stops when a pad touches; on Apollo 11 it was shut down at 102:45:43, about 3 s after the contact light).
- The ascent starts from the descent stage's deck as a free body (no separation dynamics).

## Files

- `models/*.bgmodel.json`, `scenes/*.sdf`, `expected.json` and `bgsim.project.json` are generated by `design/build_model.py` from `design/data.py` and `design/design.json`.
- `design/reference.py` is the scipy reference; `design/design.py` fits the descent targets and writes `design/design.json` (`--refit` to fit again).
- `design/run_model.jl` and `design/readrun.py` run a model through BGSim directly and read the run, for design iterations.
