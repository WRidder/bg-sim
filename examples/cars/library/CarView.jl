@block CarView begin
    # Scene helper (no physics): the 3D view keeps the car near the origin by moving the world
    # instead of the camera, so the orbit camera never has to chase a car that covers
    # kilometres. Every pose is shifted by the chassis' horizontal position (x, y); heights
    # stay. The wheels are the carrier poses turned by their spin angle about the axle (the
    # carrier z axis): q_wheel = q_carrier (x) (cos(th/2), 0, 0, sin(th/2)).
    @inputs begin
        gc::Vec{7}, [description = "Chassis pose"]
        g1::Vec{7}, [description = "Carrier pose FL"]
        g2::Vec{7}, [description = "Carrier pose FR"]
        g3::Vec{7}, [description = "Carrier pose RL"]
        g4::Vec{7}, [description = "Carrier pose RR"]
        th1::Real, [unit = "rad", description = "Spin angle FL"]
        th2::Real, [unit = "rad", description = "Spin angle FR"]
        th3::Real, [unit = "rad", description = "Spin angle RL"]
        th4::Real, [unit = "rad", description = "Spin angle RR"]
    end
    @outputs begin
        body::Vec{7}, [description = "Chassis pose in the view"]
        w1::Vec{7}, [description = "Wheel FL in the view"]
        w2::Vec{7}, [description = "Wheel FR in the view"]
        w3::Vec{7}, [description = "Wheel RL in the view"]
        w4::Vec{7}, [description = "Wheel RR in the view"]
        c1::Vec{7}, [description = "Carrier FL in the view (no spin)"]
        c2::Vec{7}, [description = "Carrier FR in the view"]
        c3::Vec{7}, [description = "Carrier RL in the view"]
        c4::Vec{7}, [description = "Carrier RR in the view"]
        ground::Vec{7}, [description = "World (track, terrain) in the view"]
    end
    @variables begin
        ch::Vec{4}, [unit = "1", description = "cos(th/2) of each wheel"]
        sh::Vec{4}, [unit = "1", description = "sin(th/2) of each wheel"]
    end
    @equations begin
        ch[1] ~ cos(0.5 * th1)
        sh[1] ~ sin(0.5 * th1)
        ch[2] ~ cos(0.5 * th2)
        sh[2] ~ sin(0.5 * th2)
        ch[3] ~ cos(0.5 * th3)
        sh[3] ~ sin(0.5 * th3)
        ch[4] ~ cos(0.5 * th4)
        sh[4] ~ sin(0.5 * th4)
        for k in 1:4
            body[k] ~ gc[k]
            c1[k] ~ g1[k]
            c2[k] ~ g2[k]
            c3[k] ~ g3[k]
            c4[k] ~ g4[k]
        end
        body[5] ~ 0.0
        body[6] ~ 0.0
        body[7] ~ gc[7]
        ground[1] ~ 1.0
        ground[2] ~ 0.0
        ground[3] ~ 0.0
        ground[4] ~ 0.0
        ground[5] ~ -gc[5]
        ground[6] ~ -gc[6]
        ground[7] ~ 0.0
        # q (x) (c, 0, 0, s) = (qw c - qz s, qx c + qy s, qy c - qx s, qz c + qw s)
        w1[1] ~ g1[1] * ch[1] - g1[4] * sh[1]
        w1[2] ~ g1[2] * ch[1] + g1[3] * sh[1]
        w1[3] ~ g1[3] * ch[1] - g1[2] * sh[1]
        w1[4] ~ g1[4] * ch[1] + g1[1] * sh[1]
        w2[1] ~ g2[1] * ch[2] - g2[4] * sh[2]
        w2[2] ~ g2[2] * ch[2] + g2[3] * sh[2]
        w2[3] ~ g2[3] * ch[2] - g2[2] * sh[2]
        w2[4] ~ g2[4] * ch[2] + g2[1] * sh[2]
        w3[1] ~ g3[1] * ch[3] - g3[4] * sh[3]
        w3[2] ~ g3[2] * ch[3] + g3[3] * sh[3]
        w3[3] ~ g3[3] * ch[3] - g3[2] * sh[3]
        w3[4] ~ g3[4] * ch[3] + g3[1] * sh[3]
        w4[1] ~ g4[1] * ch[4] - g4[4] * sh[4]
        w4[2] ~ g4[2] * ch[4] + g4[3] * sh[4]
        w4[3] ~ g4[3] * ch[4] - g4[2] * sh[4]
        w4[4] ~ g4[4] * ch[4] + g4[1] * sh[4]
        w1[5] ~ g1[5] - gc[5]
        w1[6] ~ g1[6] - gc[6]
        w1[7] ~ g1[7]
        w2[5] ~ g2[5] - gc[5]
        w2[6] ~ g2[6] - gc[6]
        w2[7] ~ g2[7]
        w3[5] ~ g3[5] - gc[5]
        w3[6] ~ g3[6] - gc[6]
        w3[7] ~ g3[7]
        w4[5] ~ g4[5] - gc[5]
        w4[6] ~ g4[6] - gc[6]
        w4[7] ~ g4[7]
        for k in 5:7
            c1[k] ~ w1[k]
            c2[k] ~ w2[k]
            c3[k] ~ w3[k]
            c4[k] ~ w4[k]
        end
    end
end
