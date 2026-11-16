# Model and parameter reference

The calculation is a planar kinematic and axial-compliance screening model. It does not use a commercial multibody solver. Python computes all quantities; the browser draws the mechanism and time histories.

## Geometry and coordinates

World x points right and z points upward. The foot F is fixed at (0, 0). The hip/input axis O remains vertically above F; K is the knee/output axis. The motor housing is attached to the thigh. A separate hip-to-motor offset or torso-mounted motor is outside this model.

Knee angle q is zero with the thigh and shank aligned. Opposite signs describe opposite knee bends. The output crank angle in the thigh frame is β = q + δ, where δ is the output clocking. Rod phases are 0, α, 2α as applicable. α specifies crank attachment phases, not the angle between long rods.

For n ≥ 2, all paths are compatible parallelograms: equal input/output radii, coupler length equal to the axis distance, and the same phases on both discs. The ideal input/output angular ratio and torque ratio are 1:1. With n = 1, unequal radii/lengths and open/crossed assembly branches can be explored.

## Parameters

Configuration JSON uses millimetres and degrees. The solver internally uses metres, radians, newtons and seconds.

| JSON field | Meaning | Default |
|---|---|---|
| `n` | Number of rod paths | 2 |
| `spacing_deg` | Crank phase spacing α; three-rod range 60°–120° | 90° |
| `center_mm` | Input-to-knee axis distance d, also thigh length | 300 mm |
| `input_radius_mm` | Input crank radius | 60 mm |
| `output_radius_mm` | Output crank radius; linked to input radius for n ≥ 2 | 60 mm |
| `rod_mm` | Coupler length; linked to d for n ≥ 2 | 300 mm |
| `shank_mm` | Knee-to-foot length | 340 mm |
| `clocking_deg` | Output crank clocking δ | 120° |
| `q_start_deg`, `q_end_deg` | Signed knee angle endpoints | −120°, −15° |
| `half_cycle_s` | Time for one direction; full cycle takes twice this | 2 s |
| `dead_center_tol_deg` | Minimum acute crank-to-rod angle at either pin, single rod only | 5° |
| `mass_kg` | Total equivalent robot mass including payload | 80 kg |
| `share` | Prescribed fraction carried by this leg | 0.5 |
| `load_mode` | `constant` or `trajectory` | `constant` |
| `load_factor` | Constant vertical load multiplier κ | 1 |
| `stiffness_n_mm` | Rod 1 axial stiffness, illustrative rather than measured | 10,000 N/mm |
| `k2_ratio`, `k3_ratio` | Other rod stiffnesses relative to rod 1 | 1, 1 |
| `branch` | Single-rod `open` / `crossed` assembly | `open` |
| `samples` | Number of full-cycle samples | 241 |

The ±175° UI bounds are input limits, not verified mechanical joint limits.

## Motion and load

The knee follows a quintic interpolation from start to end and back, with zero velocity and acceleration at the endpoints. Hip height is determined by the fixed-foot geometry:

```text
h(q) = sqrt(d² + s² + 2 d s cos(q))
```

In `constant` mode, Fz = share × mass × g × κ. Changing playback duration changes speed but not this prescribed force. In `trajectory` mode, all equivalent mass is concentrated at the hip and Fz = share × mass × (g + ḧ). Link masses and rotational inertia are omitted. Nonpositive Fz is flagged as incompatible with continuous unilateral ground support; it is not silently clamped.

Single-rod motion near a dead point is excluded using the angular margin. A guarded preview uses the first continuous admissible interval in the requested direction and rebuilds the smooth motion inside that interval. A shortened preview cannot pass the original task in Scan. Finite sampling alone does not prove arbitrary four-bar branch continuity or clearance.

## Rod-force allocation

Several rigid parallel load paths are statically indeterminate. This implementation adds small axial compliance with assigned rod stiffnesses, rigid discs/supports, zero preload and zero clearance. If bᵢ is the signed output moment arm and τ the required output torque:

```text
Nᵢ = kᵢ bᵢ τ / Σ(kⱼ bⱼ²)
Δθ = τ / Σ(kⱼ bⱼ²)
```

This is the minimum axial strain-energy distribution under moment equilibrium, equivalent to fixing the input and allowing a small output twist. Forces are not divided equally by rod count. A common stiffness multiplier changes predicted twist but not force allocation. Large twist needs a nonlinear follow-up; the displayed geometry remains the nominal rigid geometry.

## Output definitions

| Quantity | Definition |
|---|---|
| `forces[i]` | Signed axial rod force: positive tension, negative compression |
| `rod_end_forces[i].A/B` | External force on the rod at its two pins, world [x, z]; equal and opposite |
| `tau_out` | Required output-disc torque opposing the ground-force moment about K |
| `tau_in` | Ideal input-disc drive torque; gearbox losses and motor limits are not applied |
| `reaction_input` | Net support force on the input disc at its axis, world [x, z] |
| `reaction_knee` | Net support force on the output-disc/shank assembly at K, world [x, z] |
| `twist_deg` | Small elastic output twist from the axial-compliance model |
| `gain` | Ideal output/input torque ratio, equal to the input/output angular speed ratio |

Scan's `Rod peak` is the maximum absolute force over rods and valid samples. `Knee support` is the maximum vector magnitude of `reaction_knee`, in N. It is not knee torque, individual bearing load, stress or fatigue life.

The force-range table uses valid nonzero samples: Min + / Max + are positive extrema, Min − is the most negative value (strongest compression), and Max − is the negative sample closest to zero. A missing sign is shown as —. Near-zero minima depend on sampling and are not strict bounds for a continuous curve.

## Screening and Pareto labels

Scan compares compatible parallelogram configurations and rejects failed motion/contact checks and enabled user limits. Limits set to zero are disabled. Candidates are sorted by peak rod force. A Pareto label considers only peak absolute rod force and crank radius within the scanned feasible grid. It does not include rod count, mass, compression demand or knee-axis reaction as objectives.

Compare configurations under a consistent task. Changing limb dimensions also changes hip height and, in trajectory mode, acceleration and ground force. The top/low hip-height limits help keep candidates relevant, but do not establish whole-robot task feasibility.

## Verification and limits

The included tests cover force and moment balance, virtual work, known load distributions, kinematic differentiation, load/stiffness scaling, singularities, guarding, signed statistics and export consistency. The benchmark also checks the equal-stiffness 60°/120° phase identity and sampling refinement.

No physical experiment or independent multibody solver has validated these predictions. Three-dimensional geometry, collisions, buckling, pin bending, bearing pairs, friction, backlash, preload, component masses, thermal limits and whole-robot balance require additional models or measurements.

Implementation: `kneelab/model.py` contains geometry, loading and cycle calculations; `scan.py` handles finite-grid screening; `statistics.py` handles signed extrema; `export.py` writes CSV. `server.py` serves the local interface, and `static/app.js` renders controls and plots.

## Display analysis and chain module (v0.9)

One-way and round-trip plots share the same full-cycle calculations. The one-way cursor retraces on return. The optional linkage torque overlay compares the input-disc requirement against rated module torque times extra reduction and assumed efficiency. Coverage measures the requested knee-angle range, requires both directions, and retains invalid angles in the denominator. It is not a thermal, speed or strength check.

The independent Chain module adds catalog dimensions, integer tooth selection, a fixed ratio range of 1 to a user maximum no greater than 2, and even chain-link ranges. Single or mirrored outside idlers press inward. A tangent-and-arc route solver searches longitudinal positions and inward travel, then reports chain tensions and individual wheel-axis resultants. See the [Chain guide](../static/chain-guide.html) for assumptions, formulas and manufacturer sources.

Chain forces use a mean-radius model with prescribed slack tension. Discrete tooth engagement, spring tensioner dynamics and wear life are outside scope. Current screening does not enforce the manufacturer's suggested minimum idler tooth engagement or free-span length. A passing route is only a preliminary candidate.
