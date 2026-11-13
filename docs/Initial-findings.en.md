# Initial findings: phase layout, rod load and support reactions

13 November 2026 · Peiyu Wang · Knee Linkage Lab, UI v0.6 / solver v0.4.0

These are analytical predictions for design screening. They establish useful comparisons within the stated model, not a validated robot design. Reproduce with `python3 benchmark.py` from the project root.

## Controlled baseline

Total equivalent mass 80 kg, leg share 0.5, constant load factor 1: vertical ground force **392.4 N**. Axis distance 300 mm, shank length 340 mm, equal input/output crank radii 60 mm, coupler length 300 mm, output clocking 120°. Knee angle −120° → −15° → −120°, two seconds per direction, 241 samples. Each rod has the same assigned axial stiffness, 10,000 N/mm.

This baseline is deliberately distinct from arbitrary settings in screenshots or saved browser configurations. Changing the motion or using COM-trajectory loading changes the results.

| Layout | Peak absolute rod force (N) | Peak compression magnitude (N) | Peak knee-axis reaction (N) | Peak input-disc torque (N·m) |
|---|---:|---:|---:|---:|
| 2 rods, 90° spacing | 1794.9 | 70.4 | 2303.2 | 107.7 |
| 3 rods, 60° spacing | 1065.7 | 180.0 | 2359.4 | 107.7 |
| 3 rods, 90° spacing | 1794.9 | 609.7 | 1986.0 | 107.7 |
| 3 rods, 120° spacing | 1065.7 | 1065.7 | 392.4 | 107.7 |

Each column is a separate cycle peak; peaks need not occur at the same time.

## What this establishes

1. **More rods alone do not guarantee a lower peak load.** The 60° and 120° three-rod layouts reduce the peak rod force by about 41% relative to the two-rod example. The three-rod 90° layout does not reduce that peak in this task.
2. **Rod load and axis reaction are different design objectives.** The three-rod 60° and 120° layouts have equal peak absolute rod force but sharply different reaction forces.
3. **Low reaction can trade against compression.** The 120° layout has a much higher peak compressive rod force in this motion. Buckling therefore remains a separate check, requiring section properties, unsupported length and end conditions.
4. **Crank radius reduces internal force, not required output torque.** For this equal-radius compatible family and otherwise fixed settings, rod force scales as 1/r. Three rods at 120° give peak rod forces 1598.5, 1065.7 and 799.3 N at radii 40, 60 and 80 mm, respectively. Input torque remains 107.7 N·m. More rod paths do not create additional reduction.

## Why 60° and 120° differ

For parallel rods, let β be the first output crank angle relative to the thigh, φᵢ the phase, r the crank radius, kᵢ axial stiffness and τ the required output torque. The tensile-force moment arm is bᵢ = r sin(β + φᵢ). The current compliance model gives:

```text
Nᵢ = kᵢ bᵢ τ / Σ(kⱼ bⱼ²)
```

For equal stiffness and phases [0°, 60°, 120°] or [0°, 120°, 240°], the denominator is 1.5 k r² at every angle. The force vectors by rod index are related by:

```text
N120 = [N60[0], N60[2], -N60[1]]
```

Their absolute force sets are equal, but their signed sums differ. At t = 1 s in the baseline:

- 60° layout: **[+612.0, +712.7, +100.7] N**.
- 120° layout: **[+612.0, +100.7, −712.7] N**.

The latter sums to zero. The parallel rod forces form a pure couple on each disc: torque remains, while the net rod force cancels. In this ideal equal-stiffness model, the input-axis net force is zero and the knee-axis force magnitude equals the ground force. This does not mean zero input torque or zero pin/individual-bearing load.

Symmetry matters. Changing only the third rod's stiffness to 0.8 times the others raises the 120° case's peak input-axis reaction from approximately zero to **242.5 N**, and its peak knee-axis reaction from **392.4 to 569.2 N**. Real clearances, preload, manufacturing differences and spatial offsets also require further modeling; this numerical sensitivity is not a manufacturing tolerance recommendation.

## Meaning of “Knee support”

The code reports the support's resultant force on the output-disc/shank assembly at the ideal knee axis K, resolved in world x/z coordinates. With uᵢ pointing from input rod pin A to output pin B, positive Nᵢ indicating tension, and ground force Fg:

```text
Rk = Σ(Nᵢ uᵢ) − Fg
Knee support in Scan = max over valid cycle samples of ||Rk||
```

It is a **force in newtons**, useful for comparing the ideal axis/support demand. It is not knee torque, a sum of absolute rod forces, stress, or the load on one bearing of a bearing pair. Those bearings may also have to resist moments caused by axial separation and overhang, which this planar model omits. `Rod peak` instead is max over rods and samples of |Nᵢ|.

## Why both configurations are Pareto

The current scan compares only two objectives: **lower peak absolute rod force** and **smaller crank radius**. A feasible candidate is Pareto if no other sampled feasible candidate is at least as good in both and strictly better in one (using the implementation's numerical tolerance).

The 60° and 120° cases can tie on both objectives and remain Pareto even though their knee-axis reactions differ. That is expected for this objective definition. Knee reaction, compression demand, rod count, mass and packaging are not current Pareto objectives. The label describes the finite grid and enabled constraints, not a global optimum.

The default scan currently evaluates 63 unique configurations, accepts 56 and returns six Pareto candidates: the two phase layouts at radii 40, 60 and 80 mm, with 120° output clocking. Compare their compression and reaction columns before choosing a candidate.

## Next design questions

- Evaluate peak compression against buckling capacity, and rod/pin loads against actual component limits.
- Use knee/input axis reaction as explicit screening limits or additional objectives alongside crank radius and rod force.
- Check equal-stiffness sensitivity, clearance/preload, and the assembly's out-of-plane stack and collisions.
- Define a task-consistent load and posture envelope. A successful sampled cycle is not proof of whole-robot balance, safe knee reversal or physical clearance.

The equal-stiffness phase identity was checked over the full sampled baseline cycle with residual below 10⁻⁸ N. Repeating the primary cases with 1001 samples changes the 60° peak knee reaction by about 0.016 N. These checks support implementation consistency and sampled numerical convergence; they do not replace physical validation.
