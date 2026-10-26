@block Scope begin
    @constants N::Int = 1
    @inputs u::Vec{N}
    @variables sink::Vec{N}
    @equations begin
        for i in 1:N
            sink[i] ~ u[i]
        end
    end
end
