# DocTrust evaluation — run summary

- Date: 2026-10-31T12:40:21.572799+00:00
- Reader: MetaReader
- Segmenter: MetaSAMSegmenter
- Seed base: 202 (per-set seed = base + set index)
- Sets completed: 18 (errors: 0)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | — | — | — |
| Injected discrepancies caught (x/n) | 7/10 | 7/10 | 7/10 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/8 / 0/8 | 8/8 / 0/8 | 8/8 / 0/8 |
| Reads per set (mean) | 11.0 | 11.0 | 34.67 |
| Latency per set (mean, s) | 22.05 | 22.05 | 73.66 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | — | — | 0 | — / — |
| variation | — | — | 0 | — / — |
| discrepancy | — | 7/10 | 0 | — / — |
| degraded | 0/8 | — | 0 | 8/8 / 0/8 |

### Investigation planner activity (full agent)

- Fields investigated: 11
- Steps by action: recapture ×2, stamp_masked ×9, zoom_tight ×5
- Steps by source: planner ×16

## Failure analysis

- Set degraded-01 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-02 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-03 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-04 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-05 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-06 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-07 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-08 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-01 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-05 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-09 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
