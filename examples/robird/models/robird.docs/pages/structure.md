# The multibond structure

```
 World (GroundSpatial) -- Free (Free3D, 6 DOF) -- Body (RigidBody3D: fuselage, 0.55 kg)
     Body.p -- MountL1 -- JL1 (WingJoint, flap) -- LinkL1 -- BL1 (inner wing segment) -- MountL2 -- JL2 (WingJoint, bend) -- LinkL2 -- BL2 (outer segment)
     Body.p -- MountR1 ... (right wing, mirrored)
     Body.p -- MountTL -- JTL (Revolute3DCompliant) -- BTL (left elevon)   (right elevon, rudder alike)
 every body: ExternalWrenchSpatial <-- StripAero (wings, tail) / FuselageAero
 pose chain: Free.pose o LocalPose o joint.pose o LocalPose ... -> the world pose of every body (gravity, aerodynamics, scene)
```

* **Fuselage.** [World](block:World) -> [Free](block:Free) -> [Body](block:Body): `GroundSpatial -> Free3D -> RigidBody3D`, 13 states
  (quaternion, position, six momenta), gravity inside the body, six zero-effort `Se` on the unused drive ports. Body frame: $x$ forward, $y$ left, $z$ up, origin at the centre of mass.
  The load of the air on the fuselage ([FusAero](block:FusAero)) enters through an `ExternalWrenchSpatial` ([FusWrench](block:FusWrench)).
* **Wing segments** (4 bodies: inner "arm" and outer "hand" of each wing). Each is a `RigidBody3D` with its own gravity and its own `ExternalWrenchSpatial`:
  [BL1](block:BL1), [BL2](block:BL2) and the mirrored [BR1](block:BR1), [BR2](block:BR2). The joint frames are mounted with `FixedTransform3DNeutral` ([MountL1](block:MountL1), [LinkL1](block:LinkL1)).
  The 4-body class of the thesis (Figure 7) is reduced here to two spanwise segments per wing; the chordwise division is replaced by the torsion degree of freedom of the root joints (see [the aeroelastic wing](page:wing)).
* **Joints.** [JL1](block:JL1) (the flap joint, about the forward axis, up positive) and [JL2](block:JL2) (the bend of the outer segment against the inner one, about the same axis direction) are
  `WingJoint`, an example-local copy of the stdlib `Revolute3DCompliant` whose held rotation about the span axis is a soft torsion spring; all other held directions (sweep, three pivot translations) are stiff spring-dampers, so every state is integral and there is no W201.
* **Tail.** Two all-moving elevon halves ([BTL](block:BTL), [BTR](block:BTR)) and a rudder ([BTV](block:BTV)), each on a `Revolute3DCompliant` hinge driven by a first-order position servo
  ([ServoTL](block:ServoTL)) through an effort source. The weight of the fixed tail frame is part of the fuselage.
* **Power balance.** The aerodynamic wrench enters as an external wrench on each body, so the power given to the air is exactly $-\sum F_i\cdot v_i$ ([PaSum](block:PaSum), taps `Pa` of every aerodynamic block); with the
  flapping drive it closes the energy budget: the aerodynamic power averages 16.2 W against 23.0 W electrical.

The bonds follow the declared port orientations: the parent body bonds into its mount (`Body.p -> Mount.b`, `Mount.a -> Joint.parent`) and the joint child through a link into the child body (`Joint.child -> Link.a`, `Link.b -> Body.p`).

States: about 107 continuous states by count (fuselage 13, each wing segment 12, each tail flap 12, motor current and speed, crank angle, two shaft twists, three servo filters, power average, motor-controller integrator), solved by the `auto` stiff solver at `reltol` 1e-4; 44 s of wall time for the 60 s run.
