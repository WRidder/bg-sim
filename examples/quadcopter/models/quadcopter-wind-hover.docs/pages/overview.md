# Hover in a steady wind

The `quadcopter` model climbs to 1 m at 1 s and then hovers for 12 s in a steady 4 m/s wind along +x, with no turbulence and the gust off. The mission table holds only the climb. At rest, the thrust along the body z axis, the drag and the weight balance. With the body pitched by $\theta$ into the wind, the air speed in the body frame is $(-w\cos\theta, 0, w\sin\theta)$, and in world axes the balance reads

$$-T\sin\theta + w\,(c_x\cos^2\theta + c_z\sin^2\theta) = 0,\qquad T\cos\theta + w\,(c_x - c_z)\sin\theta\cos\theta - m g = 0.$$

`design.wind_tilt` solves it: $\theta = 0.075366$ rad for $w = 4$ m/s ($c_x w/(m g) = 0.0755$ in the small-angle limit). The noisy sensors make the attitude jitter, so `PitchAvg`, a 2 s low-pass, gives the mean. It reads $-0.0743$ to $-0.0745$ rad, within 1.3 % of the balance (the check allows 2 %). The quadcopter holds its place within 2.4 cm.

![Pitch, its mean and the tracking error|900](assets/e55524c9250b.png)

![Hovering in the wind; the vane points downwind|700](assets/74f6d57f201f.png)
