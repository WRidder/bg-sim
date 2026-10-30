/* bg-sim C runtime: the mechanics functions (plan/EXPORT_PLAN.md, work package J-EX5).

   Each function is the C twin of one opaque `bg_*` function in src/lower/fnmap.jl, with the
   same branches and the same operation order as its Julia body (src/mech/). The Julia
   functions return one component per call (a selector argument `k`); the C functions
   return all components at once into `out`, and the generated code calls each distinct
   argument tuple once and reads the components from a local array (see emit_intrinsics.jl).

   No allocation, no I/O, no error exits. Where the Julia function throws (the zero
   quaternion, a matrix that is not a rotation), the C function computes on: the result is
   NaN or meaningless, and a NaN that reaches a state stops the step with an error.

   The inertia entries are pure polynomials of a selected entry, so they keep the scalar
   form `(..., i, j)` of Julia (1-based selectors, as in the Julia call). */
#ifndef BG_MECH_H
#define BG_MECH_H

/* exp of a planar twist [w, vx, vy] -> the pose chart (theta, px, py). */
void bg_exp2(double w, double vx, double vy, double out[3]);
/* log of a planar pose chart (theta, px, py) -> the twist [w, vx, vy]; theta is folded into
   the principal range (-pi, pi] first. */
void bg_log2(double th, double px, double py, double out[3]);
/* exp of a spatial twist [w; v] -> the pose chart (qw, qx, qy, qz, px, py, pz), q_w >= 0. */
void bg_exp3(double wx, double wy, double wz, double vx, double vy, double vz, double out[7]);
/* log of a pose chart (q, p) -> the principal twist [w; v], |w| <= pi. */
void bg_log3(double qw, double qx, double qy, double qz, double px, double py, double pz,
             double out[6]);
/* The quaternion of a rotation vector (not canonicalised). */
void bg_quat_exp(double wx, double wy, double wz, double out[4]);
/* The principal rotation vector of a quaternion (normalised and canonicalised first). */
void bg_quat_log(double q0, double q1, double q2, double q3, double out[3]);
/* The quaternion of a rotation matrix (row-major arguments), Shepperd's branches, q_w >= 0. */
void bg_quat_from_rotation(double r11, double r12, double r13, double r21, double r22,
                           double r23, double r31, double r32, double r33, double out[4]);
/* Entry (i, j), 1-based, of the planar inertia planar_inertia(m, J, [cx, cy]). */
double bg_inertia2(double m, double J, double cx, double cy, int i, int j);
/* Entry (i, j), 1-based, of spatial_inertia(m, diag(J1, J2, J3), [c1, c2, c3]). */
double bg_inertia3(double m, double J1, double J2, double J3, double c1, double c2, double c3,
                   int i, int j);

#endif
