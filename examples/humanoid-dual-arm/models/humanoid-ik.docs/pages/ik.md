# The IK and the redundancy

## Counting

A rigid grasp fixes the full pose of a hand (3 position + 3 orientation constraints), so two hands on one box give **12 constraints**. Two 7-DOF arms have **14 joints, 2 left over**: one **self-motion** per arm, where the elbow swings about the shoulder-wrist line while the hand stays put.

## The page's damped least squares

[IKL](block:IKL) runs once per 1 ms tick, warm-started from its last solution. Angles are in degrees and the Jacobian is per degree, which are the page's units, so the page's constants carry over:

$$e = \begin{bmatrix} p_t - p \\ \tfrac12\, r_w \sum_i c_i \times t_i \end{bmatrix},\quad y = (JJ^\top + 10^{-5} I)^{-1} e,\quad z = 0.1\,(q_{home} - q)$$

$$v = (JJ^\top + 10^{-9} I)^{-1} J z,\qquad d = z + J^\top (y - v),\qquad q \leftarrow \mathrm{clamp}(q + d)$$

$r_w = 0.3$ m/rad weighs orientation against position. The task step $J^\top y$ removes the hand error. The pull $z$ toward home is projected out of the task space ($z - J^\top v$ is its null-space part), so it moves only the self-motion: among all the postures that hold the box, it picks the one closest to home.

**Elbow bias.** The bias is added to the shoulder-yaw home angle, mirrored by the arm's side $s$. The null-space pull then swings the elbows to the new home while the hands stay on the box. With 30° of bias the left elbow moves 47 mm and the right elbow 52 mm, and the hand error stays below 0.006 mm. Because the yaw joint also turns by $s\,q$, both elbows swing to the same side of the robot.

![Left arm: joints, hand error, elbow position and the bias ramp|900](assets/945a5a22ab22.png)

## Differences from the page

- **Exact Jacobian.** Where the page takes a 1° finite difference, the block uses the exact derivative of the page's error. This is generated scalar code, checked against a central difference to 5e-11. The solutions differ by up to 0.2° (stacked) and 0.4° (ideal) per joint.
- **Rate limit.** The whole step is scaled down to at most 0.05° per joint and tick (50°/s), where the page clamps each joint to ±8°. Scaling keeps the direction of the step, so a fast self-motion stays in the null space. The fixed points are the page's.
- **Solves.** The two 6×6 systems are solved by generated Cholesky factorisations: the compiler rejects `A \ b` on arrays (see [the results](page:results)).
