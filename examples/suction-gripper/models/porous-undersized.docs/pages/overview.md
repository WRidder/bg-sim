# Porous parcel on an undersized generator

The carton material leaks 2e-6 m/(s·Pa) per cup area (`perm`), and the generator delivers only 36 l/min (`Q_max` = 6e-4). Air through the material sets the operating point. The cups reach only [21.6 kPa](signal:Cup1/dp), and the generator runs at 64 % of its free flow just to feed the leaks.

![Vacuum, flow and lost cups|900](assets/c25597484108.png)

The carton survives the lift and the acceleration of a 1.2 s S-curve and is lost in the deceleration. With 60 l/min (29.0 kPa) the same move holds with a max U of 1.13. A safe move (U ≤ 0.5) needs 3.3 s as an S-curve, or a much larger generator (see the sizing page of the `transfer` model).
