# Results

![Rotor speed and winding current after the step at 0.01 s|900](assets/ee4d50cae9a5.png)

At the start the winding current jumps to nearly $V/R = 6$ A (the back-EMF is still zero) and decays to the load current while the speed builds up.

## Acceptance checks (`expected.json`)

| check | expected | tolerance |
| --- | --- | --- |
| `Motor1/shaft.f` at $t = 1$ s | 239.80815347721824 rad/s | relative 1e-4 |
| `Motor1/shaft.f` at $t = 0.2$ s (the number the Playwright test reads) | 239.8 rad/s | 0.1 |
| `Motor1/i` at $t = 1$ s | 0.004796163069544365 A | relative 1e-4 |
| iconic vs bond graph, `Motor1/shaft.f` against `IJ/p.f`, from $t = 0.5$ s | difference | below 1e-6 rad/s |
| 3D bindings | scene file matches the bindings | |

The legend shows rotation speed in `1/s`; radians are dimensionless in the unit system, the plan quotes the same quantity as rad/s.

See also the [physics page](page:physics).
