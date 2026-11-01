# One cup over the edge: common manifold

Cup 1 sits partly over the carton edge, which adds 20 mm² of leak area (`A_edge`). All six lines join one manifold.

![Cup vacuum and lost cups|900](assets/de704899810f.png)

Cup 1 cannot build vacuum ([1.9 kPa](signal:Cup1/dp)). Its open leak also draws the manifold down, so through the lines every other cup sits at [16.7 kPa](signal:Cup3/dp). That is the analytic operating point of `sizing.operating_vacuum` with the extra leak. Five cups at 16.7 kPa cannot lift 10 kg, so all cups are lost at the lift and the carton stays on the conveyor.

Compare `edge-leak-valves` (flow valves) and `separate-generators` (a generator per cup).
