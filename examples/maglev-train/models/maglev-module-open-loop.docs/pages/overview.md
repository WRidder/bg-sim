# Open-loop module

The module of [maglev-module](model:maglev-module) with **all feedback gains set to zero**: the chopper only holds the trim voltage $R\,i_\mathrm{trim}$. It starts exactly at its trim state with the gap **10 nm** too large. Because the magnet attracts more when the gap shrinks, the deviation grows exponentially, $\delta h \propto \mathrm{e}^{p t}$, with the unstable pole $p$ of the linearisation. The block [Growth](block:Growth) computes $\dot h / (h - h_0)$, which tends to $p$.

![The model canvas|900](assets/a3a82ed49a2f.png)

![Open-loop growth|900](assets/3de36791d9a4.png)

- The growth rate is 52.64 1/s at 0.15 s, against the unstable eigenvalue 52.68 1/s of the five-state linearisation (module, secondary suspension and coil), computed with scipy in `design/design.py`. It starts higher (the coil current responds first) and settles on the pole, until the deviation (about 0.06 mm at 0.2 s) leaves the linear range.
- This is the instability the gap controller has to remove: at 8.4 Hz the deviation doubles in 13 ms, so the control loop has to be fast, with a gap sensor and a chopper that react within about a millisecond.
