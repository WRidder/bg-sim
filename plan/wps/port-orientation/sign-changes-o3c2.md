# Sign changes of WP-O3c2 (O18)

Examples migrated with `tools/migrate_bond_orientation.py`: cube-pyramid-3d, multibond-pendulum-2d, planar-links,
reaction-wheel-2d, reaction-wheel-3d, robot-arm-2d. Only port variables (and the integral of a port variable, `I/P`)
change sign. No signal on this list is named by an `expected.json` check, a plot, a binding, a dashboard card, a
docs source or a test, so no recorded value was negated. No expected value or tolerance changed.

"Joint child", "contact", "gravity" refer to the WP-O3a block rows of `sign-changes.md`; a mount or link
(`FixedTransform3DNeutral`, `FixedJoint2D`) carries the sign of the chain it sits on.

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `cube-pyramid-3d/edge-contact`, `sequence-contact` | tool: `WMount1..4.b -> Cube` reversed into `Cube.p -> WMount*.b` (the body face is renamed, every O7 law change cancels) | `C1..C4/p.e`, `p.f`; `Mount1..4/a.*`, `b.*`; `WJoint1..4/child.e`, `child.f`; `WLink1..4/a.*`, `b.*`; `Cube/gravity/p.*`, `Wheel1..4/gravity/p.*` |
| `cube-pyramid-3d/edge-switched` | tool: as above (no contacts; `SwitchedPivot3D` joint) | `Joint/child.*`, `Link/a.*`, `Link/b.*`; `WJoint1..4/child.*`; `WLink1..4/a.*`, `b.*`; `Cube/gravity/p.*`, `Wheel1..4/gravity/p.*` |
| `multibond-pendulum-2d/pendulum` | tool: `De`, `Joint.parent` reversed on the 0-junction `Pivot` (neutral); `Body` (IPlanar), `Coriolis`, `Df` reversed on `J1`, which is renamed, so `Body/P`, `Df/y`, `De/y` keep their sign | `Gravity/p.e`, `Gravity/p.f`, `Joint/child.*`, `Link/a.*`, `Link/b.*` |
| `reaction-wheel-2d/balancer`, `balancer-free` | tool: `WheelJ.parent` reversed on `BodyJ` | `Pivot/child.*`, `WheelJ/child.*`, `LinkB/parent.*`, `LinkB/child.*`, `Body/gravity/p.*`, `Wheel/gravity/p.*` |
| `reaction-wheel-3d/gravity-on`, `gravity-off` | tool: `WMount1..4.b -> Body` reversed | `Pivot/child.*`, `Link/a.*`, `b.*`; `WJoint1..4/child.*`; `WLink1..4/a.*`, `b.*`; `Body/gravity/p.*`, `Wheel1..4/gravity/p.*` |
| `robot-arm-2d/arm`, `arm-free` | tool: `Joint2.parent` reversed on `BodyJ1` | `Joint1/child.*`, `Joint2/child.*`, `Link1/parent.*`, `child.*`, `Link2/parent.*`, `child.*`, `Body1/gravity/p.*`, `Body2/gravity/p.*` |
| `planar-links/planar-links-fwd` | tool: elbow `Joint.parent` reversed on the body junction `N`; gear `a` reversed on the motor junction `Motor`, which is renamed (its flow is now `+n qdot`, the motor speed in the joint's sense) | per arm `A<n>_`: `Joint<j>/child.*`, `Link<j>/parent.*`, `child.*`, `Body<j>/gravity/p.*`, `Jm<j>/p.e`, `Jm<j>/p.f`, `Jm<j>/P`, `Bm<j>/p.e`, `Bm<j>/p.f` |
| `planar-links/planar-links`, `planar-links-payload` | as `-fwd`, plus: `Torque.a -> Drive` reversed, the sensor's terminals exchanged (`Speed.p -> Torque.a`, `Drive -> Torque.b`) and the `MSf` gain negated (`-1.0 -> 1.0`, back to the generator's value); `Torque/y` keeps its sign | as `-fwd`, plus `Speed<j>/p.e`, `Speed<j>/p.f`, `Torque<j>/a.f`, `Torque<j>/b.f` (`Torque<j>/a.e`, `b.e`, `y` unchanged) |

`.*` stands for `.e` and `.f`. The tool's per-model list (the exact names) is in its report; every name above is a
port variable of a block whose convention changed (joint child, contact, gravity, a mount on such a chain) or of an
element on a renamed or reversed chain (`Jm`, `Bm`, `Speed`, `Torque`), plus `Jm/P`, the integral of `Jm/p.e`.

Deviation: none. No state, position, twist or sensed output changes sign.
