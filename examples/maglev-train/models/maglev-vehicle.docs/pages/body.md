# The 3D car body

| part | element |
| --- | --- |
| [World](block:World) | `multibond/GroundSpatial` |
| [Free](block:Free) | `spatial/Free3D`: a floating base. Its pose is seven states (unit quaternion and the position of the body origin); its six **drive ports** carry the relative twist in the body frame: $\omega_x, \omega_y, \omega_z$ (rotation) and $v_x, v_y, v_z$ (translation). |
| [Body](block:Body) | `spatial/RigidBody3D`: spatial inertia, the Coriolis (Eulerian) term and gravity from the pose $g$. 47 t, $J = (1.2\cdot10^5,\ 2.9\cdot10^6,\ 2.9\cdot10^6)$ kg·m² (a homogeneous box of 27 × 3.7 × 4.2 m). |
| along the track | [Jx](block:Jx) on `drive4`: LSM thrust [Lsm](block:Lsm) (`MSe`, after a 50 ms lag), aerodynamic drag [Drag](block:Drag) (`MR` with $r = k_\mathrm{aero}\,\lvert v \rvert$, $k_\mathrm{aero} = \tfrac12\rho C_d A = 2.496$ N·s²/m²) and the speed detector [Speed](block:Speed) |
| heave and pitch | [Jz](block:Jz) on `drive6` and [Jt](block:Jt) on `drive2`; the levers below |
| guidance | [JLat](block:JLat), [JRoll](block:JRoll), [JYaw](block:JYaw) on `drive5`, `drive1`, `drive3`: stiff spring-dampers (guidance magnets) that hold the lateral, roll and yaw degrees of freedom |
| modules | [ModF](block:ModF) and [ModR](block:ModR) (front and rear, 9.5 m from the centre of mass), two instances of the library subsystem `LevitationModule` (`library/LevitationModule.bgsub.json`) |

**Levers.** The velocity of the module point at $x = \pm 9.5$ m, in the world's vertical direction, is
$$ v_\mathrm{pt} = v_z - x\,\omega_y + R_{31}\, v_x, \qquad R_{31} = -2\,q_y, $$
the heave, the pitch lever and the forward speed's vertical component when the car is pitched. Bond graph: a 0-junction ([ZF](block:ZF), [ZR](block:ZR)) adds the heave flow from [Jz](block:Jz), the pinion flow of the `RackAndPinion` [LeverF](block:LeverF) (radius 9.5 m, from the pitch rate) and the flow of the modulated transformer [ClimbF](block:ClimbF) (modulus $R_{31}$ from [R31](block:R31), on [Jx](block:Jx)). The same elements carry the forces back: the module force acts on heave, on pitch through the lever and, through $R_{31}$, on the along-track motion (a component of $-\theta F$). The $R_{31} v_x$ term matters at 430 km/h: a pitch of 0.1 mrad makes 12 mm/s of vertical velocity, as large as the heave velocity from a 3 mm sag. Without it the body heave drifts away from the integral of the gap loops.

## Why the module is a scalar graph

A levitation module is one-dimensional: the force acts along the guideway normal, the gap is a single coordinate. It is therefore the scalar module of [maglev-module](model:maglev-module) (one coil, one gap, one chassis), and only the car body, the part that heaves, pitches and travels, is a spatial body. The stdlib has no element that converts a spatial port to a scalar one, so the drive ports of `Free3D` are the interface.

Continue with [the guideway](page:track).
