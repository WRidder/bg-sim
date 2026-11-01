# FEM bracket on a turntable

An aluminium L-bracket carries a 0.5 kg payload (a 40 mm steel cube) on a turntable. The table indexes +90° at t = 0.2 s and back at t = 1.6 s. The tangential acceleration bends the bracket's upright in its thin direction, and the payload rings after each move.

## The bracket as a reduced FEM model

[Bracket](block:Bracket) is a `ModalBody3D`. Its part spec, `design/bracket.fem.json`, builds the L from two boxes: a base plate 120 × 40 × 5 mm and an upright 40 × 4 × 150 mm (4 mm thick along the table's tangential direction). The offline tool `julia/BGSimFEM` meshes it with quadratic tetrahedra (39 348 DOFs) and reduces it by Craig–Bampton with two interfaces:

- **A**: the bolted area of the base plate (its bottom face up to x = 40 mm), at the bolt axis. It is the body's reference frame and sits on the hub.
- **B**: the top face of the upright, where the payload clamp sits.

4 fixed-interface modes plus the 6 constraint modes of B give 10 modal coordinates. The model reads `data/bracket.modal.json`; the 3D view deforms `meshes/bracket.glb` with `Bracket/eta[1..10]`.

## The mechanism

- [Table](block:Table) is a `Revolute3D` about the world z axis. A speed servo drives it: [Servo](block:Servo), a speed source fed by the sum of two jerk-limited [MoveOut](block:MoveOut) / [MoveBack](block:MoveBack) velocity profiles, acts through a stiff [ServoSpring](block:ServoSpring) and [ServoDamper](block:ServoDamper) (about 60 Hz, ζ = 0.7).
- [Hub](block:Hub) is the turntable disk (a `RigidBody3D`). [Seat](block:Seat) places interface A on its top face, behind the weld: an offset between the hub and the weld would leave algebraic equations (see the manual, Flexible bodies, Simulation and export).
- [WeldA](block:WeldA) and [WeldB](block:WeldB) are the bolted joints, hub to bracket and bracket to payload. Two bodies that each carry their own momentum cannot be joined rigidly (that would be derivative causality), so each joint is a stiff `Revolute3D` whose rotation about its axis is held by a stiff torsion spring ([WeldASpring](block:WeldASpring), [WeldBSpring](block:WeldBSpring)), 100 to 1000 times stiffer than the bracket at that interface.
- [Offset](block:Offset) puts the [Payload](block:Payload) centre 20 mm above interface B. The payload's pose is composed from `Bracket/poseB`, the deformed interface.
- Gravity acts on all bodies; the payload's weight is a compressive interface force on the upright, which the geometric stiffening of the reduced model includes.

## What to look at

- [Payload/flow/y[1]](signal:Payload/flow/y[1]) and [Payload/flow/y[5]](signal:Payload/flow/y[5]) (components of the payload twist [ω; v] in its own frame): the payload rocks about its x axis and moves sideways at the first bracket mode (about 18.6 Hz with the payload) after each move.
- [Bracket/eta[1]](signal:Bracket/eta[1]): the first modal coordinate, the upright bending in its thin direction.
- [Bracket/Ee](signal:Bracket/Ee): the strain energy in the bracket.

The companion model **bracket-ringdown** clamps the same bracket and checks its frequencies with the payload against the full finite element model.
