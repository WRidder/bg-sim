# A Furuta pendulum with a bending rod

A horizontal arm turns about the vertical axis on [Motor](block:Motor), a `Revolute3D`. The pendulum hangs from [Pivot](block:Pivot) at the arm tip. [PivotFree](block:PivotFree) is a zero torque on the pivot's drive, so the pivot is free. The pendulum is [Rod](block:Rod), a `FlexibleBeam3D`:

- an aluminium rod, d = 5 mm, L = 0.5 m;
- two bending modes in each plane (`ny = nz = 2`) and no torsion modes (`nt = 0`);
- modal damping ζ = 0.01.

The rod is clamped at its end A, the pivot. Its own mass (26.5 g) and inertia are part of the beam. Its first bending frequencies are 14.25 Hz and 89.28 Hz ([Rod/f_y[1]](signal:Rod/f_y[1]), [Rod/f_y[2]](signal:Rod/f_y[2])).

## What happens

The rod is released from 90° with the motor free. It swings, and the arm turns back and forth in reaction. At t = 3 s, [Kick](block:Kick) applies a 0.4 N·m torque pulse of 0.05 s to the arm. The rod's root is then whipped sideways, and the rod bends:

- [Rod/eta_y[1]](signal:Rod/eta_y[1]) and [Rod/eta_y[2]](signal:Rod/eta_y[2]) are the bending coordinates in the beam's x–y plane;
- [Rod/eta_z[1]](signal:Rod/eta_z[1]) and [Rod/eta_z[2]](signal:Rod/eta_z[2]) are the bending coordinates in its x–z plane.

All four are in metres. The first mode peaks at about 0.6 mm. The tip deflection is Σ φ_n(L) η_n, with φ_n(L) = ±2. In the 3D view, these coordinates bend `rod_bar`; raise the deformation exaggeration to see it clearly.

## Geometric stiffening and energy

The swing loads the rod along its axis: gravity, and the centrifugal force of the swing. An axial tension makes a beam stiffer in bending. The beam includes this through its geometric-stiffness terms, which keep the model energy-consistent. [Rod/Ek](signal:Rod/Ek), [Rod/Ee](signal:Rod/Ee) and [Rod/Eg](signal:Rod/Eg) are the rod's kinetic, strain and gravity energies. The whole graph's power balance (`energy_ledger` check) closes to 3e-18 of the energy throughput.

## The rigid twin

`flex-rotary-pendulum-rigid` replaces the beam with a `RigidBody3D` that has the same mass and inertia. Over the first 1.5 s, the two pendulum angles ([Pivot/qout](signal:Pivot/qout)) differ by at most 0.02 rad. The rod is stiff compared with the swing (14 Hz against 0.6 Hz), so its flexibility shows up as a small, slow phase drift and as the vibration after the kick.
