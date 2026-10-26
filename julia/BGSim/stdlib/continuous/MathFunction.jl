@block MathFunction begin
    @constants fn::Int = 0
    @inputs u::Real
    @outputs y::Real
    @equations begin
        y ~ ifelse(
            fn == 0,
            sin(u),
            ifelse(
                fn == 1,
                cos(u),
                ifelse(
                    fn == 2,
                    tan(u),
                    ifelse(
                        fn == 3,
                        asin(u),
                        ifelse(
                            fn == 4,
                            acos(u),
                            ifelse(
                                fn == 5,
                                atan(u),
                                ifelse(
                                    fn == 6,
                                    sinh(u),
                                    ifelse(
                                        fn == 7,
                                        cosh(u),
                                        ifelse(
                                            fn == 8,
                                            tanh(u),
                                            ifelse(
                                                fn == 9,
                                                exp(u),
                                                ifelse(
                                                    fn == 10,
                                                    log(u),
                                                    ifelse(
                                                        fn == 11,
                                                        log10(u),
                                                        ifelse(
                                                            fn == 12,
                                                            sqrt(u),
                                                            ifelse(
                                                                fn == 13,
                                                                abs(u),
                                                                ifelse(
                                                                    fn == 14,
                                                                    sign(u),
                                                                    ifelse(
                                                                        fn == 15,
                                                                        floor(u),
                                                                        ceil(u),
                                                                    ),
                                                                ),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    end
end
