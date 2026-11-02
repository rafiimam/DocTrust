# DocTrust evaluation — run summary

- Date: 2026-10-31T13:11:48.190210+00:00
- Reader: MetaReader
- Segmenter: MetaSAMSegmenter
- Seed base: 303 (per-set seed = base + set index)
- Sets completed: 30 (errors: 0)
- Multi-persona sets: 30 (discrepancy sets planted across a pool of ten Bangla personas, not just the base person; scored in the headline tables as discrepancy sets)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | — | — | — |
| Injected discrepancies caught (x/n) | 24/30 | 26/30 | 26/30 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | — / — | — / — | — / — |
| Reads per set (mean) | 11.0 | 11.0 | 34.6 |
| Latency per set (mean, s) | 19.6 | 19.6 | 61.44 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | — | — | 0 | — / — |
| variation | — | — | 0 | — / — |
| discrepancy | — | 26/30 | 0 | — / — |
| degraded | — | — | 0 | — / — |

### Investigation planner activity (full agent)

- Fields investigated: 19
- Steps by action: recapture ×6, stamp_masked ×8, zoom_tight ×13
- Steps by source: planner ×27

## Failure analysis

- Set persona-disc-01 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-03 (discrepancy, stamp purple/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-05 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-07 (discrepancy, stamp purple/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-08 (discrepancy, stamp red_orange/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-09 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set persona-disc-25 (discrepancy, stamp black/margin): 3. Full agent: expected DISCREPANCY, got UNREADABLE
