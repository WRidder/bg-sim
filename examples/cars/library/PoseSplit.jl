@block PoseSplit begin
    # A pose (D-MB6 chart: q_w, q_x, q_y, q_z, x, y, z) split into scalars, for the FMU
    # outputs of the sim models (an export output is one scalar).
    @inputs g::Vec{7}, [description = "Pose"]
    @outputs begin
        px::Real, [unit = "m", description = "Position x"]
        py::Real, [unit = "m", description = "Position y"]
        pz::Real, [unit = "m", description = "Position z"]
        qw::Real, [unit = "1", description = "Quaternion w"]
        qx::Real, [unit = "1", description = "Quaternion x"]
        qy::Real, [unit = "1", description = "Quaternion y"]
        qz::Real, [unit = "1", description = "Quaternion z"]
    end
    @equations begin
        qw ~ g[1]
        qx ~ g[2]
        qy ~ g[3]
        qz ~ g[4]
        px ~ g[5]
        py ~ g[6]
        pz ~ g[7]
    end
end
