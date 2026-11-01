@block PoseError begin
    # Distance between two poses on the D-MB6 chart (qw, qx, qy, qz, x, y, z): the position
    # error |p - pr| in mm and the rotation angle between the orientations in degrees,
    # 2 atan2(|v|, |w|) of q_r^-1 (x) q (the shorter way round). Observed only (no feedback).
    @inputs begin
        g::Vec{7}
        gr::Vec{7}
    end
    @outputs begin
        e_mm::Real, [description = "Position error [mm]"]
        e_deg::Real, [description = "Rotation angle [deg]"]
    end
    @variables begin
        w::Real = 1.0, [unit = "1", description = "Scalar part of q_r^-1 (x) q"]
        vx::Real = 0.0, [unit = "1"]
        vy::Real = 0.0, [unit = "1"]
        vz::Real = 0.0, [unit = "1"]
    end
    @equations begin
        w ~ gr[1] * g[1] + gr[2] * g[2] + gr[3] * g[3] + gr[4] * g[4]
        vx ~ gr[1] * g[2] - gr[2] * g[1] - gr[3] * g[4] + gr[4] * g[3]
        vy ~ gr[1] * g[3] + gr[2] * g[4] - gr[3] * g[1] - gr[4] * g[2]
        vz ~ gr[1] * g[4] - gr[2] * g[3] + gr[3] * g[2] - gr[4] * g[1]
        e_mm ~ 1000.0 * sqrt((g[5] - gr[5])^2 + (g[6] - gr[6])^2 + (g[7] - gr[7])^2 + 1.0e-30)
        e_deg ~ 2.0 * atan(sqrt(vx * vx + vy * vy + vz * vz + 1.0e-30), abs(w)) / deg
    end
end
