"""Run from the project root: python3 examples/walkthrough.py.

Compare the same task with two vs three rods, then change the duration.
No GUI or third-party packages are needed.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kneelab.model import Config, cycle

for rod_count in (2, 3):
    config = Config.from_dict({"n": rod_count, "mass_kg": 80, "share": 0.5})
    summary = cycle(config)["summary"]
    print(f"n={rod_count}: rod peak {summary['peak_rod_n']:.1f} N, "
          f"input peak {summary['peak_input_nm']:.2f} Nm, "
          f"knee support {summary['peak_knee_reaction_n']:.1f} N")

for duration in (2, 1, 0.5):
    config = Config.from_dict({"load_mode": "trajectory", "half_cycle_s": duration})
    summary = cycle(config)["summary"]
    print(f"One-way {duration} s: force factor "
          f"{summary['min_load_factor']:.3f}–{summary['max_load_factor']:.3f}, "
          f"contact-compatible sampled cycle: {summary['complete']}")

# Positive N is tension, negative N is compression.
frame = cycle(Config())["rows"][60]
print("At t=", frame["t"], "s, rod forces are", frame["forces"], "N")
