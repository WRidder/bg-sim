# The aircraft

## Airframe and forces

The airframe is the stdlib `RigidBody3D` on a `Free3D` joint, with a mass of 1088.6 kg (2400 lb). Its inertia is c172p's empty tensor plus its point masses. Two kinds of force enter it as `ExternalWrenchSpatial` modulated sources:

- `C172Aero`: the aerodynamic wrench, the c172p build-up of lift, drag, side force and the three moments;
- `Propeller`: the thrust and torque at the hub.

The aerodynamic build-up includes:

- the flap and ground-effect tables;
- the rate and alpha-dot terms;
- a stall hysteresis on the lift.

`C172AirData` computes the inputs of the build-up from the body pose and twist:

$$\alpha = \arctan\frac{w}{\sqrt{u^2 + V_f^2}}, \qquad \beta = \arctan\frac{v}{\sqrt{u^2 + w^2 + V_f^2}}, \qquad \bar q = \tfrac12 \rho V^2$$

Here $V_f = 1$ m/s keeps both angles finite at standstill.

## Engine and propeller

The engine and propeller form a rotational bond graph. Its one inertia is a `Rotor3D` (the crankshaft and the propeller, 2.26 kg m²), mounted on the airframe, so its gyroscopic moment and torque reaction act on the body. On its 1-junction sit two elements.

The first is `PistonEngine`, a modulated effort source: JSBSim's FGPiston model of the 160 hp Lycoming O-320. Its torque comes from the manifold pressure (a lagged state), the air mass flow and the mixture efficiency, minus the pumping and friction losses.

The second is `Propeller`, a resistance whose torque and thrust are

$$\tau = C_P(J)\,\frac{\rho n^2 D^5}{2\pi}, \qquad T = C_T(J)\,\rho n^2 D^4, \qquad J = \frac{u}{n D}$$

with the 75-inch fixed-pitch propeller's tables.

## Validation source

`design/c172_ref.py` is an independent numpy implementation of the same physics. `design/c172_lin.py` trims and linearises it. Its modes are the expected values of the next page.
