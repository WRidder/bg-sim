# The AIM-9X example

Four views of one missile:

| model | what it shows |
| --- | --- |
| `aim9x-airframe` | open-loop 6-DOF plant: cubic lift, Mach tables, canards, variable mass and the short-period mode |
| `aim9x-control` | the rate-command autopilot, roll hold, gain schedule and two-axis TVC |
| `aim9x-intercept` | imaging seeker, proportional navigation, proximity fuze and a target |
| `aim9x-fmu` | the host-interface variant for `apps/f16-sim`: target inputs, missile outputs, no fuze stop |

The airframe is a slender cruciform missile with **cubic lift** `CN = cna alpha + CN3 alpha^3`, a small static margin (`Cm = -0.8 CN`), Mach-dependent drag and canard control. The motor is a Mk. 36-class boost: 21 kg of propellant in 2.4 s, 235 s vacuum Isp, with the ambient-pressure correction on the nozzle. The body is a `Free3D` joint, a modulated spatial inertia and six outflow `MR` elements, so the mass loss carries its momentum away with it.

The autopilot is deliberately a **rate-command** law: it is robust over the launch envelope, and the guidance limit `a_frac qbar S CN_MAX / m` keeps the demand inside what the airframe can actually deliver. The checks are analytic (thrust, mass, lift, drag, atmosphere, seeker range and irradiance, the PN gain) and a fitted short-period mode, not numbers copied from a run.
