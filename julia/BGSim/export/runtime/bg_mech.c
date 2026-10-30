/* bg-sim C runtime: the mechanics functions (see bg_mech.h).

   Every function follows its Julia body in src/mech/ (se2.jl, se3.jl, quat.jl, lie.jl)
   branch for branch and in the same operation order, so the results agree with Julia to a
   few ulp (the golden tests in test/test_export_intrinsics.jl measure it). Two sources of
   difference remain: libm against Julia's own sin/cos/tan/atan (about 1 ulp), and the
   matrix-vector products, which StaticArrays writes as `muladd` chains that Julia may fuse
   into FMA instructions while this file uses a plain multiply and add (ISO C, no
   contraction). */
#include <math.h>
#include "bg_mech.h"

/* ---- small helpers, written as in the Julia sources ---- */

/* A 3x3 row-major matrix times a 3-vector, accumulated left to right as StaticArrays does. */
static void bg_mv3(const double W[9], const double v[3], double out[3]) {
    int k;
    for (k = 0; k < 3; ++k) {
        out[k] = (W[3 * k] * v[0] + W[3 * k + 1] * v[1]) + W[3 * k + 2] * v[2];
    }
}

/* skew(w): the cross-product matrix, row-major. */
static void bg_skew(const double w[3], double W[9]) {
    W[0] = 0.0;   W[1] = -w[2]; W[2] = w[1];
    W[3] = w[2];  W[4] = 0.0;   W[5] = -w[0];
    W[6] = -w[1]; W[7] = w[0];  W[8] = 0.0;
}

/* normalise(q): q / |q| with |q| = sqrt(w^2 + x^2 + y^2 + z^2). */
static void bg_quat_normalise(const double q[4], double u[4]) {
    double n = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
    u[0] = q[0] / n; u[1] = q[1] / n; u[2] = q[2] / n; u[3] = q[3] / n;
}

/* The canonical branch q_w >= 0 (quat.jl `_canonical`). */
static void bg_quat_canonical(double q[4]) {
    if (q[0] < 0.0) {
        q[0] = -q[0]; q[1] = -q[1]; q[2] = -q[2]; q[3] = -q[3];
    }
}

/* quat_to_matrix(q): the rotation matrix of normalise(q), row-major. */
static void bg_quat_matrix(const double q[4], double R[9]) {
    double u[4], w, x, y, z;
    bg_quat_normalise(q, u);
    w = u[0]; x = u[1]; y = u[2]; z = u[3];
    R[0] = 1.0 - 2.0 * (y * y + z * z);
    R[1] = 2.0 * (x * y - w * z);
    R[2] = 2.0 * (x * z + w * y);
    R[3] = 2.0 * (x * y + w * z);
    R[4] = 1.0 - 2.0 * (x * x + z * z);
    R[5] = 2.0 * (y * z - w * x);
    R[6] = 2.0 * (x * z - w * y);
    R[7] = 2.0 * (y * z + w * x);
    R[8] = 1.0 - 2.0 * (x * x + y * y);
}

/* quat_from_rotation(M) for a row-major M: Shepperd's branch on the largest of the trace
   and the diagonal, then normalise and canonicalise. */
static void bg_quat_of_matrix(const double M[9], double out[4]) {
    double q[4], s;
    double tr = M[0] + M[4] + M[8];
    if (tr > 0.0) {
        s = 2.0 * sqrt(tr + 1.0);
        q[0] = 0.25 * s;
        q[1] = (M[7] - M[5]) / s;
        q[2] = (M[2] - M[6]) / s;
        q[3] = (M[3] - M[1]) / s;
    } else if (M[0] > M[4] && M[0] > M[8]) {
        s = 2.0 * sqrt(1.0 + M[0] - M[4] - M[8]);
        q[0] = (M[7] - M[5]) / s;
        q[1] = 0.25 * s;
        q[2] = (M[1] + M[3]) / s;
        q[3] = (M[2] + M[6]) / s;
    } else if (M[4] > M[8]) {
        s = 2.0 * sqrt(1.0 + M[4] - M[0] - M[8]);
        q[0] = (M[2] - M[6]) / s;
        q[1] = (M[1] + M[3]) / s;
        q[2] = 0.25 * s;
        q[3] = (M[5] + M[7]) / s;
    } else {
        s = 2.0 * sqrt(1.0 + M[8] - M[0] - M[4]);
        q[0] = (M[3] - M[1]) / s;
        q[1] = (M[2] + M[6]) / s;
        q[2] = (M[5] + M[7]) / s;
        q[3] = 0.25 * s;
    }
    bg_quat_normalise(q, out);
    bg_quat_canonical(out);
}

static void bg_quat_exp_v(const double v[3], double out[4]) {
    double th = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    double half = th / 2.0;
    double s;
    if (fabs(half) < 1e-8) {
        double h2 = half * half;
        s = 1.0 - h2 / 6.0 + (h2 * h2) / 120.0;
    } else {
        s = sin(half) / half;
    }
    out[0] = cos(half);
    out[1] = s * v[0] / 2.0;
    out[2] = s * v[1] / 2.0;
    out[3] = s * v[2] / 2.0;
}

static void bg_quat_log_q(const double q[4], double out[3]) {
    double u[4], nv, s;
    bg_quat_normalise(q, u);
    bg_quat_canonical(u);
    nv = sqrt(u[1] * u[1] + u[2] * u[2] + u[3] * u[3]);
    if (nv < 1e-12) {
        s = nv == 0.0 ? 0.0 : 2.0 / u[0];
    } else {
        s = 2.0 * atan2(nv, u[0]) / nv;
    }
    out[0] = s * u[1];
    out[1] = s * u[2];
    out[2] = s * u[3];
}

/* ---- SE(2): se2.jl ---- */

static double bg_se2_sinc(double th) {
    if (fabs(th) < 1e-2) {
        double t2 = th * th;
        return 1.0 - t2 / 6.0 + (t2 * t2) / 120.0 - (t2 * t2 * t2) / 5040.0;
    }
    return sin(th) / th;
}

static double bg_se2_c1(double th) {
    if (fabs(th) < 1e-2) {
        double t2 = th * th;
        return th / 2.0 - th * t2 / 24.0 + th * (t2 * t2) / 720.0;
    }
    return (1.0 - cos(th)) / th;
}

void bg_exp2(double w, double vx, double vy, double out[3]) {
    double s = bg_se2_sinc(w);
    double c = bg_se2_c1(w);
    out[0] = w;
    out[1] = s * vx - c * vy;
    out[2] = c * vx + s * vy;
}

void bg_log2(double th, double px, double py, double out[3]) {
    double t = atan2(sin(th), cos(th));  /* principal value in (-pi, pi] */
    double a, b;
    if (fabs(t) < 1e-2) {
        double t2 = t * t;
        a = 1.0 - t2 / 12.0 - (t2 * t2) / 720.0;
    } else {
        a = (t / 2.0) / tan(t / 2.0);
    }
    b = t / 2.0;
    out[0] = t;
    out[1] = a * px + b * py;
    out[2] = -b * px + a * py;
}

/* ---- SE(3): se3.jl ---- */

static double bg_se3_c1(double th) {
    if (fabs(th) < 1e-2) {
        double t2 = th * th;
        return 0.5 - t2 / 24.0 + (t2 * t2) / 720.0;
    }
    return (1.0 - cos(th)) / (th * th);
}

static double bg_se3_c2(double th) {
    if (fabs(th) < 1e-2) {
        double t2 = th * th;
        return 1.0 / 6.0 - t2 / 120.0 + (t2 * t2) / 5040.0;
    }
    return (th - sin(th)) / (th * th * th);
}

static double bg_se3_c3(double th) {
    if (fabs(th) < 1e-2) {
        double t2 = th * th;
        return 1.0 / 12.0 + t2 / 720.0 + (t2 * t2) / 30240.0;
    }
    return (1.0 - (th / 2.0) / tan(th / 2.0)) / (th * th);
}

void bg_exp3(double wx, double wy, double wz, double vx, double vy, double vz, double out[7]) {
    double w[3], v[3], W[9], Wv[3], WWv[3], q[4], R[9], c1, c2, th;
    int k;
    w[0] = wx; w[1] = wy; w[2] = wz;
    v[0] = vx; v[1] = vy; v[2] = vz;
    th = sqrt(wx * wx + wy * wy + wz * wz);
    bg_skew(w, W);
    c1 = bg_se3_c1(th);
    c2 = bg_se3_c2(th);
    bg_mv3(W, v, Wv);
    bg_mv3(W, Wv, WWv);
    /* exp(W) as a matrix, then its chart quaternion: the same round trip as Julia's
       chart(exp(V)), so the branch and the sign of q match. */
    bg_quat_exp_v(w, q);
    bg_quat_matrix(q, R);
    bg_quat_of_matrix(R, out);
    for (k = 0; k < 3; ++k) {
        out[4 + k] = v[k] + c1 * Wv[k] + c2 * WWv[k];
    }
}

void bg_log3(double qw, double qx, double qy, double qz, double px, double py, double pz,
             double out[6]) {
    double q0[4], R[9], q[4], w[3], W[9], p[3], Wp[3], WWp[3], c3, th;
    int k;
    q0[0] = qw; q0[1] = qx; q0[2] = qy; q0[3] = qz;
    p[0] = px; p[1] = py; p[2] = pz;
    bg_quat_matrix(q0, R);  /* pose(SE3, chart) */
    bg_quat_of_matrix(R, q);
    bg_quat_log_q(q, w);
    th = sqrt(w[0] * w[0] + w[1] * w[1] + w[2] * w[2]);
    bg_skew(w, W);
    c3 = bg_se3_c3(th);
    bg_mv3(W, p, Wp);
    bg_mv3(W, Wp, WWp);
    for (k = 0; k < 3; ++k) {
        out[k] = w[k];
        out[3 + k] = p[k] - 0.5 * Wp[k] + c3 * WWp[k];
    }
}

/* ---- quaternions: quat.jl ---- */

void bg_quat_exp(double wx, double wy, double wz, double out[4]) {
    double v[3];
    v[0] = wx; v[1] = wy; v[2] = wz;
    bg_quat_exp_v(v, out);
}

void bg_quat_log(double q0, double q1, double q2, double q3, double out[3]) {
    double q[4];
    q[0] = q0; q[1] = q1; q[2] = q2; q[3] = q3;
    bg_quat_log_q(q, out);
}

void bg_quat_from_rotation(double r11, double r12, double r13, double r21, double r22,
                           double r23, double r31, double r32, double r33, double out[4]) {
    double M[9];
    M[0] = r11; M[1] = r12; M[2] = r13;
    M[3] = r21; M[4] = r22; M[5] = r23;
    M[6] = r31; M[7] = r32; M[8] = r33;
    bg_quat_of_matrix(M, out);
}

/* ---- inertia: fnmap.jl `bg_inertia2`, lie.jl `inertia_entry` ---- */

double bg_inertia2(double m, double J, double cx, double cy, int i, int j) {
    if (i < 1 || i > 3 || j < 1 || j > 3) return NAN;
    if (i == 1 && j == 1) return J + m * (cx * cx + cy * cy);
    if ((i == 1 && j == 2) || (i == 2 && j == 1)) return -m * cy;
    if ((i == 1 && j == 3) || (i == 3 && j == 1)) return m * cx;
    if (i == j) return m;
    return 0.0;
}

/* The (a, b) entry, 1-based, of skew(c). */
static double bg_skew_entry(const double c[3], int a, int b) {
    double W[9];
    bg_skew(c, W);
    return W[3 * (a - 1) + (b - 1)];
}

double bg_inertia3(double m, double J1, double J2, double J3, double c1, double c2, double c3,
                   int i, int j) {
    double c[3], J[3];
    if (i < 1 || i > 6 || j < 1 || j > 6) return NAN;
    c[0] = c1; c[1] = c2; c[2] = c3;
    J[0] = J1; J[1] = J2; J[2] = J3;
    if (i <= 3 && j <= 3) {
        double n2 = c1 * c1 + c2 * c2 + c3 * c3;
        return (i == j ? J[i - 1] : 0.0) + m * ((i == j ? n2 : 0.0) - c[i - 1] * c[j - 1]);
    } else if (i <= 3) {
        return m * bg_skew_entry(c, i, j - 3);
    } else if (j <= 3) {
        return m * bg_skew_entry(c, j, i - 3);
    }
    return i == j ? m : 0.0;
}
