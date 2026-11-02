# DocTrust evaluation — run summary

- Date: 2026-11-02T13:42:42.970626+00:00
- Reader: MetaReader
- Segmenter: MetaSAMSegmenter
- Seed base: 404 (per-set seed = base + set index)
- Sets completed: 30 (errors: 0)
- Multi-persona genuine sets: 30 (clean and variation sets across the same pool of ten Bangla personas; scored in the headline tables as genuine sets)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 30/30 | 6/30 | 7/30 |
| Injected discrepancies caught (x/n) | — | — | — |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | — / — | — / — | — / — |
| Reads per set (mean) | 11.0 | 11.6 | 35.8 |
| Latency per set (mean, s) | 24.41 | 25.82 | 77.11 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 4/15 | — | 0 | — / — |
| variation | 3/15 | — | 0 | — / — |
| discrepancy | — | — | 0 | — / — |
| degraded | — | — | 0 | — / — |

### Investigation planner activity (full agent)

- Fields investigated: 14
- Steps by action: recapture ×3, zoom_tight ×15
- Steps by source: planner ×18

### Advisory visual cross-examination (full agent)

- Sets with a visual pass: 30
- Discrepancy sets with ≥1 visual concern: 0/0 (0 concerns in total)
- Genuine sets with ≥1 visual concern: 0/30 (0 concerns in total)
- Advisory only: the pass never feeds a verdict; these counts measure how often it fires, nothing more.

## Failure analysis

- Set persona-clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-02 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-03 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-04 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-05 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-06 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-07 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-08 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set persona-clean-09 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-10 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-11 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-12 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-13 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-14 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-clean-15 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-var-01 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-var-02 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-03 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set persona-var-04 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-05 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-var-06 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-07 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-08 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-09 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-10 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set persona-var-11 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set persona-var-12 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-13 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-14 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set persona-var-15 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
