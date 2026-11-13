# Averaged model

![The averaged model canvas|900](assets/86c7381f4072.png)

The power stage is a bond graph. [Supply](block:Supply) (`MSe`) applies [Vin](block:Vin); the power sensor [Pin](block:Pin) reads the input power and the 1-junction [IN](block:IN) carries the input-current detector [Iin](block:Iin). The switch [SW](block:SW) is an `MTF` whose modulus is the duty from [PWM](block:PWM) (`PWMAverage` here): it passes $d V_{in}$ to the 1-junction [LJ](block:LJ) with [L](block:L), [RL](block:RL) and the current detector [IL](block:IL), and $d\, i_L$ back to the input. The 0-junction [OUT](block:OUT) carries [C](block:C) and the voltage detector [Vout](block:Vout); the 1-junction [IO](block:IO) with [Iout](block:Iout) leads to the load node [LOAD](block:LOAD) with [Rload](block:Rload) and the load step [Iload](block:Iload) (an `MSf` with gain $-1$, so it draws the [LoadStep](block:LoadStep) current). [Pout](block:Pout) multiplies the output voltage and current.

The control path is [Vref](block:Vref) → [VrefFilt](block:VrefFilt) → the error [Err](block:Err) → [PID1](block:PID1). The feed-forward [FF](block:FF) divides the filtered reference by [Vin](block:Vin); [DutySum](block:DutySum) adds the two and [DutySat](block:DutySat) clamps the result to [0, 1].

![Averaged run|900](assets/1d757667c7b7.png)

The output reaches the 1 % band in 4.3 ms without overshoot. At 20 ms the 1 A load step dips the output to 4.823 V; the inductor current peaks at 2.093 A at 20.28 ms, and the loop recovers in 0.58 ms (2 % band) with a 5.012 V overshoot at 23.5 ms. At 30 ms the input steps to 15 V; the feed-forward drops the duty at once and the output moves by less than 10 mV. The largest inductor current, 2.351 A, is the startup inrush at 0.245 ms, not the load step. The duty jumps to 0.71 in the first 65 $\mu$s: the derivative acts on the error, and the 1 ms reference filter only bounds that kick.

At 15 V and 2 A the input current is $d\, i_L = 0.6933$ A and the input power 10.400 W against 10.000 W out: the 0.400 W difference is $R_L i^2$, and the efficiency is 96.15 %.
