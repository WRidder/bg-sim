# Multimodal aerial manipulator with a contact controller

A hexarotor flies up to a wall, pushes an end-effector on it with a tilted thrust vector, and drives the end-effector's three omnidirectional wheels so that it climbs and descends the wall while the multirotor follows it. This is the system of Wopereis, van de Ridder, Lankhorst, Klooster, Bukai, Wuthier, Nikolakopoulos, Stramigioli, Engelen and Fumagalli, *Multimodal Aerial Locomotion: An Approach to Active Tool Handling*, IEEE Robotics & Automation Magazine, December 2018 (X5.8).

The model contains

- a 2.1 kg hexarotor (80 cm across, 950 Kv motors, 10x4.5 in propellers, 16 V tether, 78 N maximum thrust) as a multibond floating body, every rotor a chain [Esc1](block:Esc1) - [Drv1](block:Drv1) - [Prop1](block:Prop1) (six of them), the air and rotor wrench in [RW](block:RW);
- a one-DoF manipulator: a position servo [Servo](block:Servo) about the body y axis, driven by [ServoCtl](block:ServoCtl), and a 0.6 m carbon tube [Arm](block:Arm) (0.23 kg, rigid);
- the rubber shock mount [Rub](block:Rub), a compliant spherical joint with the spring-damper [RubK](block:RubK), and the 0.15 kg end-effector [EE](block:EE);
- three omnidirectional wheels at 120 degrees, each an anisotropic contact [Wheel1](block:Wheel1), [Wheel2](block:Wheel2), [Wheel3](block:Wheel3) against the wall [Wall](block:Wall), driven open loop by [Omni](block:Omni);
- the firmware: sensors ([Imu](block:Imu), [Gps](block:Gps)) and the navigation filter [Nav](block:Nav), the phase machine [Sup](block:Sup), and three controllers: the free-flight cascade ([Pos](block:Pos), [Att](block:Att), [Rate](block:Rate)), the engage controller [Eng](block:Eng) and the gain-scheduled LQR contact controller [Con](block:Con), selected by [Sel](block:Sel) and allocated to the rotors by [Mix](block:Mix).

The run lasts 34 s and starts in hover (there is no take-off; the landing legs of the quadcopter example are not part of this model). It approaches the wall in free flight, engages with the pitch reference $\theta_{sp}$ ramping from 12 to 20 degrees, holds contact while $\theta_{sp}$ ramps to 27 degrees, climbs 0.30 m and descends again by an open-loop wheel velocity command, disengages by $C = 0.75$ m and hovers.

![The run|720](assets/330d3ca62ecb.png)

## Run it

Press **Run** (about 25 s of wall time; every 4 ms discrete tick is recorded as a left/right event pair, so the run holds 17 001 rows of about 2 560 signals, 350 MB). Then plot [WallForce/N](signal:WallForce/N) against [WallForce/Npred](signal:WallForce/Npred): the measured normal force follows the quasi-static prediction $m g \tan\theta_{sp}$ of the paper. Open the 3D view: the arm joint turns with [Servo/qout](signal:Servo/qout), the wheels with [Omni/phi1](signal:Omni/phi1).

Continue with [the system](page:system), [the phase machine](page:phases), [the free-flight controller](page:flight), [the contact controller](page:contact), [the manipulator and the end-effector](page:manipulator) or [the results](page:results).
