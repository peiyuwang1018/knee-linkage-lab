"""Signed extrema of valid sampled rod forces; never continuous extrema."""
import math

ZERO_FORCE_N = 1e-6


def sampled_force_extrema(rows, rod, zero_tol_n=ZERO_FORCE_N):
    """Keep source frame/time/angle so a reported extremum is inspectable.

    Negative minimum is strongest compression; negative maximum is closest
    to zero. A missing sign has None, rather than a fabricated zero sample.
    Near-zero numerical noise is excluded. Ties retain the first sample.
    """
    result = dict(min_positive=None, max_positive=None,
                  min_negative=None, max_negative=None)
    for index, row in enumerate(rows):
        forces = row.get('forces')
        if not row.get('valid') or forces is None or rod >= len(forces):
            continue
        value = forces[rod]
        if value is None or not math.isfinite(value) or abs(value) <= zero_tol_n:
            continue
        sign = 'positive' if value > 0 else 'negative'
        event = dict(force_n=value, frame=index, t_s=row['t'], q_deg=row['q_deg'])
        for kind, better in (('min', lambda a,b:a<b), ('max', lambda a,b:a>b)):
            key = f'{kind}_{sign}'
            if result[key] is None or better(value, result[key]['force_n']):
                result[key] = event
    return result
