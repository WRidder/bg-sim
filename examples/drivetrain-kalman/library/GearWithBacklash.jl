@block GearWithBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @components begin
        gear = LossyGear(n = 10.0, eta = 1.0)
        play = GearBacklash(k = 1e4, d = 5.0, gap = 0.02)
    end
    @connections begin
        connect(a, gear.a)
        connect(gear.b, play.a)
        connect(play.b, b)
    end
end
