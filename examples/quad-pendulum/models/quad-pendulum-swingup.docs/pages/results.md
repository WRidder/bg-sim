# Results and checks

Real worker, Rodas5P, reltol 1e-7:

| quantity | bond graph | design closed loop (twin) |
| --- | --- | --- |
| at rest before 1 s | exactly | |
| all links within 5° | 3.97 s | 3.97 s |
| catch (BALANCING) | 5.50 s | 5.50 s |
| largest link deviation from 7.5 s | 0.00057° | 0.00057° |
| peak force | 14.13 N of 40 N | 14.13 N |
| peak cart travel | 0.581 m of ±1.5 m | 0.581 m |
| stacked energy at 10 s | 4.3164 J = UPRIGHT | |
| actuator work, friction losses | 6.99 J, 2.68 J | |
| free swing vs twin (cart, largest angle) | 1.0e-7 m, 7.0e-4° | |
| balance scenario: push peak, recovery inside 0.5° | 9.36°, 1.79 s | 9.36° |

The plant agrees with the twin so closely that the closed loops agree to the printed digits. In the design
closed loop the swing-up also survives ±5 % link masses, +1 % lengths, three times the joint friction, twice
the rail friction, +10 % cart mass, 1 or 2 ms of actuator delay and quantised encoders.

`expected.json` checks the swing-up (catch, the angles against the design closed loop at two instants,
the 0.5° band from 7.5 s, the force limit, the rail, the final stacked energy and the ledger), the balance
scenario and the free swing against the twin. The tolerances are named in every check's note.

Continue with [the short-travel controller](page:short).
