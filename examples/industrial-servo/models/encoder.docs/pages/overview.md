# Servo with a 24-bit encoder and estimated speed

The `baseline` drive, but the loops no longer see the ideal angle and speed: the angle goes through a 24-bit absolute encoder and the speed is estimated by differencing it. The plant, inverter (averaged) and mechanics are unchanged (see `baseline`).

![The encoder model canvas|900](assets/e5b72d08ee2f.png)

- [Enc](block:Enc): a `Quantizer` at 8 kHz with resolution $2\pi/2^{24} = 3.745\cdot10^{-7}$ rad on the angle [Theta](block:Theta);
- [SpeedEst](block:SpeedEst): a 1 kHz backward difference of the quantised angle plus a first-order low-pass with $\alpha = 0.8$; its output `SpeedEst/w` replaces the measured speed in the speed loop and in the current loop's decoupling; `Enc/y` replaces the angle in the position loop;
- [EncMon](block:EncMon): records the quantisation error at the encoder tick (the half-LSB error is $1.872\cdot10^{-7}$ rad).

## Results

![True and estimated speed during the speed step|900](assets/7c0fcc0c0be4.png)

The speed-loop overshoot is larger (10.5 %, against 3.4 % for the baseline) because the 1 kHz differenced estimate lags the true speed by up to one sample plus the low-pass; rise 5.1 ms, settle 11 ms. The estimate still tracks the steady speed: its RMS error is 0.0038 rad/s over $[1.0, 1.15]$ s. Position step 108 ms / 0 % / 386 ms, peak $i_q$ 15.78 A / 7.574 N·m, position at 1.15 s -6.8e-4 rad.
