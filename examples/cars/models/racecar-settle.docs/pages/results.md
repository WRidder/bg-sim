# Results

![CG height and tyre loads|900](assets/7b00ea45aaf6.png)

The reference is a 7-DOF ride model (heave, roll, pitch and four wheel hops with the same springs, asymmetric dampers, bump stops and tyre springs) integrated with scipy in `design/reference.py`. The CG height [Pose/pz](signal:Pose/pz) agrees to 0.02 mm at every sample from 0.05 to 3 s, the tyre loads to 0.5 % from 0.3 s on and the static loads (1527 N front, 2024 N rear per wheel) to 0.1 %.
