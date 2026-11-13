# The microduck on a stand

The robot hangs by its trunk, the way a real robot is brought up. Its 15 bodies come from the microduck_rl MJCF, with 14 `Revolute3D` joints. Each jointed body is an instance of the library subsystem `Link` ([left_knee_link](block:left_knee_link): the body, its two frames and its pose band), with its joint beside it. One [XL330](block:left_knee) instance per joint is named after the joint. Every `vbus` port sits on one battery bus: a [battery](block:Battery) behind a [resistance](block:Rbat), and a [bus capacitor](block:Cbus).

At 0.2 s the hip-pitch, knee and ankle goals step from HOME to a pose that would lower a standing trunk by 15 mm (inverse kinematics in `design/robot.py`). The other joints hold HOME.

What to watch:

- the firmware **latency**: [left_knee/Latency/y](signal:left_knee/Latency/y) steps 20 ms after the goal;
- the **P gain**: the knee draws at most 0.87 A, so at kp 200 the gain, not the 1.75 A limit, sets the speed of the move;
- the **backlash**: [left_knee/Backlash/phi](signal:left_knee/Backlash/phi) sits on one flank (+1°) under the weight of the shank;
- the **gravity sag**: every joint ends short of its goal.

Raise `kp_fw` and the move gets faster; lower `i_limit` to 1.0 A and the limit starts to matter.
