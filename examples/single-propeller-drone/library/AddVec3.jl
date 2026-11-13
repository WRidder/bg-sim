@block AddVec3 begin
    # y = a + b: the specific force the accelerometer feels is the sum of the aero wrench (thrust,
    # drag, contacts) and the fin wrench, each divided by the mass in its own block.
    @inputs begin
        a::Vec{3}
        b::Vec{3}
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ a[1] + b[1]
        y[2] ~ a[2] + b[2]
        y[3] ~ a[3] + b[3]
    end
end
