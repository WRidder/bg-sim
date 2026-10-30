# The multibond structure

```
Ground -- Rail(Prismatic2D) -- CartJ(1) -- Cart(RigidBody2D)
                |                 `-- Joint1 -- Link1 -- N1(1) -- Body1(RigidBody2D)
           drive (Translation)                      `-- Joint2 -- Link2 -- N2(1) -- Body2 ...
Motor(ElectricDrive) -- Gear -- Pulley(RackAndPinion) -- Belt(SpringDamper) -- Rail.drive
```

Every bond between planar ports is a two-stroke multibond carrying a 3-component twist and wrench $(\omega, v_x, v_y)$ and $(\tau, f_x, f_y)$.

| block | element | role |
| --- | --- | --- |
| [Ground](block:Ground) | `GroundPlanar` | world, zero twist |
| [Rail](block:Rail) | `Prismatic2D` | the cart's prismatic joint along $x$; exact translation, compliant in rotation and the perpendicular direction (the rigid limit is $k \to \infty$); its drive port is a force/velocity (Translation) |
| [CartJ](block:CartJ) | 1-junction | the cart's twist, shared by the rail's child, the cart body and the first pivot |
| [Cart](block:Cart) | `RigidBody2D` | 0.8 kg, $J = 0.0015$ kg m²; inertia, Coriolis and gravity wrench in one composite |
| [Joint1](block:Joint1), [Joint2](block:Joint2), [Joint3](block:Joint3) | `Revolute2DCompliant` | the pendulum joints; exact angle $q$, pivot translations stiff springs ($k_t = 10^8$ N/m, $b_t = 10^3$ N s/m), viscous friction $b$ on the joint |
| Link1 to Link3 | `FixedJoint2D` | the constant offset from the pivot to the link's centre of mass |
| N1 to N3 | 1-junctions | each link's twist, shared by the link body, its fixed joint and the next joint's parent |
| [Body1](block:Body1), [Body2](block:Body2), [Body3](block:Body3) | `RigidBody2D` | the rods: mass, inertia about the centre of mass, gravity |
| Passive1 to Passive3 | `Se` with $e = 0$ | closes the joint drive ports: the joints are not actuated |
| [Push](block:Push) | `ExternalWrenchPlanar` | the disturbance force perpendicular to the tip link and its moment about the centre of mass |

**Why compliant pivots.** A rigid revolute joint on a rigid 3-DOF body is an index-3 constraint problem. `Revolute2DCompliant` keeps the joint angle exact and replaces the two pivot translation constraints by a very stiff spring-damper, so every state stays integral and the model is a plain ODE with a $\sqrt{k_t/m} \approx 10^4$ rad/s pivot mode that the implicit solver (Rodas5P) handles. The trajectory error is of order $1/k_t$ (measured in [the results](page:results)). The cart's rotation and perpendicular motion are held the same way ($k_r = 100000$ N m/rad, $k_d = 1e+08$ N/m).

**Bond directions matter.** A bond's half arrow sets the sign of the junction equations, so every joint's `parent` port is bonded *towards* the junction of the body it hangs from (`Joint.parent → N`), like every other element port. The opposite direction produces a plant whose reaction forces on the cart have the wrong sign.

**Poses.** The poses are composed, never integrated: [Rail](block:Rail) outputs the cart pose, every joint outputs $(q, r_x, r_y)$, `ComposePose2D` chains them and `LocalPose2D` adds the centre-of-mass offsets. The body gravity reads its composed world pose, and the scene bindings of the 3D view read the same joint signals.

**Drive train.** The electrical side is [Motor](block:Motor) (`ElectricDrive`: voltage source, winding resistance and inductance, back-EMF gyrator, rotor inertia, bearing loss), then [Gear](block:Gear) (ideal ratio 3), [Pulley](block:Pulley) (`RackAndPinion`, radius 16 mm: torque to belt force) and [Belt](block:Belt) (a spring-damper, so the rotor inertia is not a derivative-causal store). The domain-concrete ports of the drive train are joined by wires, the junctions by bonds.

**Firmware.** [Traj](block:Traj) is a continuous block: `interp1` is an equation-scope intrinsic, so the 10 ms tables of the nominal state, the feed-forward voltage and the TVLQR gains are looked up there. [Ctrl](block:Ctrl) is the `@discrete Ts = 1e-3` block: it samples the encoders ($x$, $v$, $q_i$, $\dot q_i$) and the lookup outputs, forms the absolute angles, and sets the voltage of [Motor](block:Motor).
