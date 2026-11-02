# DocTrust evaluation — run summary

- Date: 2026-10-30T03:45:16.053474+00:00
- Reader: BasetenReader
- Segmenter: MetaSAMSegmenter
- Seed base: 7 (per-set seed = base + set index)
- Sets completed: 39 (errors: 1)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 22/22 | 10/22 | 6/22 |
| Injected discrepancies caught (x/n) | 5/9 | 7/9 | 8/9 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/8 / 0/8 | 8/8 / 0/8 | 6/8 / 0/8 |
| Reads per set (mean) | 11.0 | 11.0 | 35.41 |
| Latency per set (mean, s) | 62.38 | 62.38 | 213.28 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 0/12 | — | 0 | — / — |
| variation | 6/10 | — | 0 | — / — |
| discrepancy | — | 8/9 | 0 | — / — |
| degraded | 2/8 | — | 0 | 6/8 / 0/8 |

## Failure analysis

- Set clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-02 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-03 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-04 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-05 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-06 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY
- Set clean-07 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-08 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set clean-09 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-10 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-11 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-12 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-01 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-02 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-03 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-04 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-05 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-06 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-07 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-08 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-02 (discrepancy, stamp red_orange/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-03 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-09 (discrepancy, stamp purple/margin): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-10 (discrepancy, stamp red_orange/margin): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set variation-01 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-02 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-03 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-04 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-05 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-06 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-07 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-08 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-09 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-10 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-07 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
