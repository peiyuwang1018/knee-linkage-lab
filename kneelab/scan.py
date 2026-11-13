"""Finite-grid screening with explicit limits; no claim of global optimum."""
from __future__ import annotations
from itertools import product
from collections import Counter
from .model import Config, cycle

DEFAULT_GRID = dict(n=[1, 2, 3], input_radius_mm=[40, 60, 80],
                    spacing_deg=[60, 90, 120], center_mm=[300],
                    shank_mm=[340], clocking_deg=[90, 120, 150])
DEFAULT_LIMITS = dict(max_rod_n=5000, max_input_nm=0, max_speed_rad_s=0,
                      max_twist_deg=1, min_top_height_mm=550, max_bottom_height_mm=400)


def scan(base, grid=None, limits=None):
    base = Config.from_dict(base if isinstance(base, dict) else base.to_dict())
    grid = DEFAULT_GRID.copy() if grid is None else grid
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    if set(grid)-set(DEFAULT_GRID):
        raise ValueError("Unsupported scan axis.")
    if set(limits)-set(DEFAULT_LIMITS):
        raise ValueError("Unsupported scan limit.")
    import math
    for value in limits.values():
        if not isinstance(value,(float,int)) or not math.isfinite(value) or value < 0:
            raise ValueError("Limits must be finite and nonnegative; zero disables a limit.")
    grid = {k: grid.get(k, [getattr(base,k)]) for k in DEFAULT_GRID}
    count = 1
    for values in grid.values():
        if not isinstance(values,list) or not values or len(values)>30:
            raise ValueError("Each grid axis needs 1–30 values.")
        count *= len(values)
    if count>5000:
        raise ValueError("Grid too large: use at most 5,000 raw combinations.")
    candidates, rejected, seen = [], Counter(), set()
    for values in product(*grid.values()):
        data = {**base.to_dict(), **dict(zip(grid,values))}
        # Grid comparison intentionally stays inside the compatible family,
        # including n=1, so geometry changes are meaningful and comparable.
        data.update(output_radius_mm=data["input_radius_mm"], rod_mm=data["center_mm"], branch="open")
        if data["n"] == 1: data["spacing_deg"] = 90
        if data['n'] == 3 and not 60 <= data['spacing_deg'] <= 120:
            key=tuple(data.values())
            if key not in seen:
                seen.add(key)
                rejected['three_rod_phase_spacing'] += 1
            continue
        c = Config.from_dict(data)
        key=tuple(c.to_dict().values())
        if key in seen: continue
        seen.add(key)
        result=cycle(c); s=result["summary"]
        failures=[]
        if not s["complete"]:
            failures.extend(result["errors"] or ["incomplete_cycle"])
        if s["complete"]:
            # Parallel n=1 may pass directly through a dead point between
            # samples. Detect all such angles analytically.
            if c.n==1:
                lo,hi=sorted([c.q_start_deg+c.clocking_deg,c.q_end_deg+c.clocking_deg])
                if math.ceil(lo/180-1e-12)<=math.floor(hi/180+1e-12):
                    failures.append("dead_center_between_samples")
            for limit,metric in [("max_rod_n","peak_rod_n"),("max_input_nm","peak_input_nm"),
                                 ("max_speed_rad_s","peak_input_rad_s"),("max_twist_deg","peak_twist_deg")]:
                if limits[limit] and s[metric]>limits[limit]: failures.append(limit)
            if limits["min_top_height_mm"] and s["max_hip_m"]*1000<limits["min_top_height_mm"]:
                failures.append("top_height")
            if limits["max_bottom_height_mm"] and s["min_hip_m"]*1000>limits["max_bottom_height_mm"]:
                failures.append("bottom_height")
        if failures:
            rejected.update(set(failures)); continue
        candidates.append(dict(config=c.to_dict(), **s))
    candidates.sort(key=lambda r:(r["peak_rod_n"],r["config"]["input_radius_mm"]))
    # Pareto only within this finite grid: low rod load vs small crank radius.
    for a in candidates:
        a["pareto"] = not any(
            b["peak_rod_n"] <= a["peak_rod_n"] and
            b["config"]["input_radius_mm"] <= a["config"]["input_radius_mm"] and
            (b["peak_rod_n"] < a["peak_rod_n"]-1e-8 or
             b["config"]["input_radius_mm"] < a["config"]["input_radius_mm"])
            for b in candidates)
    return dict(grid=grid,limits=limits,evaluated=len(seen),feasible=len(candidates),
                rejected=dict(rejected),candidates=candidates,
                note="Sampled screening only. Same angle/time/load settings; limb changes also change hip height. No collision, strength, or actuator thermal verification.")
