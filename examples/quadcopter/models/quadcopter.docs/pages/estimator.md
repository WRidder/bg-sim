# Sensors and navigation filter

- [Imu](block:Imu) (`ImuSensor`, 500 Hz): gyro and accelerometer with constant biases (0.2 deg/s, 0.05 m/s²), white noise (0.01 deg/s/$\sqrt{\mathrm{Hz}}$, 300 µg/$\sqrt{\mathrm{Hz}}$) and 2nd-order Butterworth low-passes (gyro 80 Hz, accelerometer 30 Hz, bilinear coefficients from `design.py`).
- [Gps](block:Gps) (`GpsSensor`, 50 Hz): an RTK-quality fix of position (2 cm), velocity (5 cm/s) and heading (1 deg), held for 20 ms.
- Both read the true state ([Truth](block:Truth) and `RotorWrench.fs`); the controller never does.
- [Nav](block:Nav) (`NavFilter`, 500 Hz): a fixed-gain observer for attitude (quaternion), velocity, position and gyro bias. A multirotor's accelerometer measures thrust, not gravity, so the tilt is observed through the velocity: the specific force rotated by the estimated attitude propagates the velocity, the fix corrects it, and the cross product of the specific force with the velocity innovation corrects the attitude and the gyro bias (error dynamics in `design.py`, poles $-6.3 \pm 3.3\mathrm{j}$ and $-0.66 \pm 0.83\mathrm{j}$). The compass corrects the yaw.
- [Err](block:Err) (`EstError`) compares the estimate with the truth: `Err/pos`, `Err/vel`, `Err/att`, and the tracking distance `Err/track`.

## Why hash noise instead of the stdlib `Noise`

The stdlib block is a function of $t$ through `floor`; every step of its staircase is a solver event, and at some step times (6.5 s with a 0.5 s staircase, measured here) the root is not representable and the solver chatters until the event limit (W206). The sensors therefore use the same sine-hash Box-Muller sequence inside the discrete scope, indexed by the tick counter: deterministic, event-free, selectable by `seed`.
