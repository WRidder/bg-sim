# Results

![Flight: altitude, speed and mass|900](assets/1177f7831d86.png)

The thrust climbs from 25 t to 29 t as the air thins. The drag peaks near Mach 1.2, where the dynamic pressure is still high:

![Ascent: thrust and drag, Mach, dynamic pressure, acceleration|900](assets/f4b11e3c835e.png)

In vacuum, without gravity and drag, the speed is Tsiolkovsky's ideal velocity gain. At 80 s it is 2380.557 m/s, $c \ln(m_0/m_f)$ to 1e-6:

![Vacuum: speed and Tsiolkovsky|900](assets/592e19252a23.png)

## Against the published data

| | published | model |
| --- | --- | --- |
| burnout speed | about 1,500 m/s | 1,422 m/s (−5 %) |
| apogee, vertical | about 160 km (design); 174.6 km and 206 km were flown | 141.7 km (−11 %) |

The model is low on both counts. The published figures are "about" values from flights with different payloads and burn times. The drag table is an estimate: no digitised V-2 drag curve is online. The checks compare loosely with the published figures (10 % and 15 %) and tightly (1e-4) with an independent scipy model of the same equations (`design/reference.py`).
