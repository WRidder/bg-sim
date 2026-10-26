@block Recorder begin
    @constants N::Int = 1
    @inputs u::Vec{N}
    @parameters decimation::Int = 1, [min = 1, description = "Record every Nth sample; ignored, because every signal is always recorded (D15)"]
    @variables sink::Vec{N}
    @equations begin
        for i in 1:N
            sink[i] ~ u[i] + 0.0 * decimation
        end
    end
end
