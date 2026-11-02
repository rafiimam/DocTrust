# DocTrust evaluation — run summary

- Date: 2026-10-29T17:44:49.993136+00:00
- Reader: BasetenReader
- Segmenter: MetaSAMSegmenter
- Seed base: 7 (per-set seed = base + set index)
- Sets completed: 1 (errors: 0)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 1/1 | 0/1 | 0/1 |
| Injected discrepancies caught (x/n) | — | — | — |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | — / — | — / — | — / — |
| Reads per set (mean) | 11.0 | 11.0 | 33.0 |
| Latency per set (mean, s) | 71.17 | 71.17 | 275.82 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 0/1 | — | 0 | — / — |
| variation | — | — | 0 | — / — |
| discrepancy | — | — | 0 | — / — |
| degraded | — | — | 0 | — / — |

## Failure analysis

- Set clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
