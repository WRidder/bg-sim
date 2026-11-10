# Parameters and sources

| quantity | value | status |
| --- | --- | --- |
| nominal gap $h_0$ | 10 mm | **published**: constant gap of about 10 mm (Transrapid; Wikipedia "Transrapid", Meisinger "40 years of Maglev") |
| cruise speed | 430 km/h | **published**: Shanghai Transrapid operating speed (not re-checked in this session) |
| acceleration | 1 m/s² | **published**: about 1 m/s² (Wikipedia "Transrapid") |
| drag | Cd 0.26, frontal area 16 m² | **published**: Wikipedia "Transrapid" (the area is marked "citation needed" there). The model's drag power at 400 km/h is 3.42 MW against the 3.53 MW quoted there. |
| car section | 27.0 m long, 3.7 m wide, 4.2 m high, 53 t empty | **published**: Transrapid vehicle brochure (end section; the 53 t is the passenger section, TR generation not named) |
| levitation chassis | four per section, 12-pole magnets | **published**: Schneider et al. 2022, coupled vehicle-guideway simulations of the TR08 (read through a search summary only) |
| span of the guideway | 24.768 m (double-span beam) | **recalled** from Transrapid guideway literature, not checked |
| chassis mass $m_b$ | 1.5 t per quarter | estimate (4 × 1.5 t = 6 t of the 53 t) |
| body mass $m_c$ | 11.75 t per quarter (47 t) | estimate (53 t minus the chassis) |
| magnet constant $\alpha$ | 5.777·10⁻⁴ H·m | estimate: $\alpha i_0^2/h_0^2 = (m_b + m_c) g$ at $i_0 = 150$ A (an equivalent magnet of N = 100 turns, 0.18 m² pole area, B = 0.94 T) |
| coil $R$, $L_\infty$ | 0.55 Ω, 30 mH | estimate ($R i_0^2$ = 12.4 kW per quarter = 0.93 kW/t, below the published 1.7 kW/t for levitation and guidance including the electronics) |
| chopper rail | ±800 V | estimate |
| secondary suspension | 1 Hz heave, ζ = 0.3 | estimate (typical air-spring ride) |
| skid gap, stop | 16 mm, 4 mm | estimate |
| guideway | sag 3 mm per span, one 2 mm × 12 m bump | estimate |
| LSM | 150 kN limit, 50 ms lag | estimate |
| guidance (lateral, roll, yaw) | stiff spring-dampers | estimate (the symmetric run never excites them) |

**Published validation data.** FRA/VNTSC measured TR08 vibrations at the Emsland test facility in 2001 (report DOT/FRA/ORD-02/06), but those are ground-vibration spectra and the report's data tables could not be read here. No levitation-gap, current or body-acceleration time series was found. The only published numbers used as a check are the cruise speed, the 1 m/s² acceleration and the drag power at 400 km/h.
