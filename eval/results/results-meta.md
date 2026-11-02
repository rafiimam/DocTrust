# DocTrust evaluation — run summary

- Date: 2026-10-29T17:09:33.320063+00:00
- Reader: MetaReader
- Segmenter: MetaSAMSegmenter
- Seed base: 7 (per-set seed = base + set index)
- Sets completed: 39 (errors: 1)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 21/21 | 21/21 | 18/21 |
| Injected discrepancies caught (x/n) | 9/10 | 9/10 | 9/10 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/8 / 0/8 | 0/8 / 0/8 | 0/8 / 0/8 |
| Reads per set (mean) | 11.0 | 11.0 | 33.92 |
| Latency per set (mean, s) | 28.81 | 28.81 | 72.34 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 11/12 | — | 0 | — / — |
| variation | 7/9 | — | 0 | — / — |
| discrepancy | — | 9/10 | 0 | — / — |
| degraded | 8/8 | — | 0 | 0/8 / 0/8 |

## Failure analysis

- Set clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-02 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-03 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-04 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-05 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set clean-06 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-07 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-08 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-09 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-10 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-11 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set clean-12 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-01 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-02 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-03 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-04 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-05 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-06 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-07 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set degraded-08 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-03 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set variation-01 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-02 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-03 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-05 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-06 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-07 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-08 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-09 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-10 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set variation-04 (variation): run error — RuntimeError: Meta Model API request failed: _ssl.c:1015: The handshake operation timed out
