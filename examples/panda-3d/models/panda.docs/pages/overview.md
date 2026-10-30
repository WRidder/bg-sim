# Franka Emika Panda: Cartesian tour on bond-graph joint drives

The seven-axis Franka Emika Panda follows a Cartesian tour of its flange through four waypoints and back home. Two layers:

- **[Robot](block:Robot)**, a subsystem with the plant: the spatial multibond arm (`Revolute3D`, `RigidBody3D`, `FixedTransform3DNeutral`, the physically feasible dynamics of Gaz et al. 2019), one bond-graph drive per joint (torque limit, motor, rotor inertia, gear, elastic gear, Gaz friction) and the sensors (20-bit link-side encoders sampled at 1 kHz, joint rates, joint-torque sensors). Its ports: inputs `tau1..tau7` [N·m], outputs `q1..q7`, `dq1..dq7`, `tauJ1..tauJ7`.
- **The 1 kHz outer layer**, three discrete code blocks wired by signals: [Traj](block:Traj) (quintic rest-to-rest segments between the waypoints, yaw slerped), [IK](block:IK) (the analytical IK of He and Liu 2021 with q7 held) and [PD](block:PD) (PD with gravity and friction feedforward from the Gaz model).

![The model canvas|900](assets/aa1b638e19fb.png)

```
Clock -> Traj -> g -> IK -> qr1..7 -> PD -> u1..7 -> Robot.tau1..7
                      ^               ^  ^
                      q1..6           q  dq       <- Robot.q1..7, Robot.dq1..7 (sensors)
```

The run: 5.15 s with `Rodas5P`, `reltol` 1e-6, `abstol` 1e-8, 1031 output points; about 3 s of compile and 19 s of solve time on the reference machine.

## What to look at

- the flange [Robot/TCP/g[5]](signal:Robot/TCP/g[5]) against the target [Traj/px](signal:Traj/px) (and `g[6]`, `g[7]` against `Traj/py`, `Traj/pz`);
- the joint-torque sensors [Robot/TauSense4/y](signal:Robot/TauSense4/y) (18.57 N·m at rest: the elbow carries the forearm);
- the IK status [IK/flag](signal:IK/flag), zero all the way (solved every tick).

## 3D view

`scenes/panda.sdf` is the URDF tree of `franka_description` with the official visual meshes (`meshes/link0..7.glb`); the seven joints are bound to `Robot/J<i>/qout`, so the viewer composes the arm itself. The RGB triad is the target pose `Traj/g`, the orange ball the simulated flange `Robot/TCP/g`.

![3D view at t = 1.75 s: the flange trails the target in the move from waypoint 1 to 2|500](assets/dc6d2694de2d.png)

Continue with [the Robot subsystem](page:robot), [the outer layer](page:control), [the results](page:results) and [the notes](page:notes).
