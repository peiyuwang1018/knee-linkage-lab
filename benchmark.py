#!/usr/bin/env python3
"""Reproduce the controlled comparisons in docs/Initial-findings.en.md."""
import argparse
import csv
import json
import math
from dataclasses import replace
from pathlib import Path

from kneelab.model import Config, cycle
from kneelab.scan import scan


def metrics(result):
    c, s = result['config'], result['summary']
    return dict(n=c['n'], phase_deg=c['spacing_deg'], radius_mm=c['input_radius_mm'],
                clocking_deg=c['clocking_deg'], k3_ratio=c['k3_ratio'],
                samples=c['samples'], complete=s['complete'],
                peak_rod_n=s['peak_rod_n'],
                peak_compression_n=max(r['compression_n'] for r in s['rods']),
                peak_knee_reaction_n=s['peak_knee_reaction_n'],
                peak_input_reaction_n=s['peak_input_reaction_n'],
                peak_input_nm=s['peak_input_nm'])


def save_csv(path, records):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('output/phase-benchmark'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = Config()
    cases = [(2, 90, 60), (3, 60, 60), (3, 90, 60), (3, 120, 60),
             (3, 120, 40), (3, 120, 80)]
    results = [cycle(replace(base, n=n, spacing_deg=a, input_radius_mm=r))
               for n, a, r in cases]
    comparisons = [metrics(r) for r in results]
    sixty, one_twenty = results[1], results[3]
    # Independent symmetry identity: a phase shift by 180° reverses a rod force.
    residual = max(abs(a['forces'][i] - sign*b['forces'][j])
                   for a, b in zip(sixty['rows'], one_twenty['rows'])
                   for i, j, sign in [(0, 0, 1), (1, 2, -1), (2, 1, 1)])
    assert residual < 1e-8
    assert max(math.hypot(*r['reaction_input']) for r in one_twenty['rows']) < 1e-8
    assert all(r['summary']['complete'] for r in results)
    sensitivity = [metrics(cycle(replace(base, n=3, spacing_deg=120, k3_ratio=k)))
                   for k in (.8, 1.0, 1.2)]
    dense = [metrics(cycle(replace(base, n=n, spacing_deg=a, samples=1001)))
             for n, a in [(2, 90), (3, 60), (3, 120)]]
    scan_result = scan(base)
    front = [metrics({'config':r['config'], 'summary':r})
             for r in scan_result['candidates'] if r['pareto']]
    report = dict(baseline=base.to_dict(), comparisons=comparisons,
                  stiffness_sensitivity=sensitivity, dense_sampling=dense,
                  phase_identity_residual_n=residual,
                  scan_evaluated=scan_result['evaluated'],
                  scan_feasible=scan_result['feasible'], pareto=front,
                  scope='Analytical model predictions; no experimental validation.')
    (args.out/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    save_csv(args.out/'comparisons.csv', comparisons)
    save_csv(args.out/'stiffness-sensitivity.csv', sensitivity)
    save_csv(args.out/'pareto.csv', front)
    print(f'Results: {args.out.resolve()}')
    print(f'Phase symmetry residual: {residual:.3g} N; {len(front)} Pareto candidates.')


if __name__ == '__main__':
    main()
