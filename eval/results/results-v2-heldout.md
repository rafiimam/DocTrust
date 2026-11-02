# DocTrust evaluation — run summary

- Date: 2026-11-02T12:10:14.375068+00:00
- Reader: MetaReader
- Segmenter: MetaSAMSegmenter
- Seed base: 101 (per-set seed = base + set index)
- Sets completed: 50 (errors: 0)
- Hindi-script sets: 10 (secondary script, reported separately below; not in the headline tables)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 22/22 | 0/22 | 0/22 |
| Injected discrepancies caught (x/n) | 9/10 | 9/10 | 8/10 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/8 / 0/8 | 8/8 / 0/8 | 8/8 / 0/8 |
| Reads per set (mean) | 11.0 | 11.0 | 34.8 |
| Latency per set (mean, s) | 19.8 | 19.8 | 64.56 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 0/12 | — | 0 | — / — |
| variation | 0/10 | — | 0 | — / — |
| discrepancy | — | 8/10 | 0 | — / — |
| degraded | 0/8 | — | 0 | 8/8 / 0/8 |

### Investigation planner activity (full agent)

- Fields investigated: 14
- Steps by action: recapture ×6, stamp_removed ×3, zoom_tight ×11
- Steps by source: planner ×20

### Advisory visual cross-examination (full agent)

- Sets with a visual pass: 50
- Discrepancy sets with ≥1 visual concern: 4/12 (4 concerns in total)
- Genuine sets with ≥1 visual concern: 0/29 (0 concerns in total)
- Advisory only: the pass never feeds a verdict; these counts measure how often it fires, nothing more.

### Hindi-script sets (secondary, small n)

_The same three configurations over the Hindi-script (Devanagari) sets only. These sets are NOT included in the headline tables above — the headline comparison is the Bangla sets. Claims stay narrow: Bangla primary, Hindi secondary, small n._

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 7/7 | 0/7 | 0/7 |
| Injected discrepancies caught (x/n) | 2/2 | 2/2 | 2/2 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/1 / 0/1 | 1/1 / 0/1 | 1/1 / 0/1 |
| Reads per set (mean) | 11.0 | 11.0 | 34.2 |
| Latency per set (mean, s) | 23.82 | 23.82 | 75.89 |
| Cost per set (USD, at route prices) | — | — | — |

#### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 0/4 | — | 0 | — / — |
| variation | 0/3 | — | 0 | — / — |
| discrepancy | — | 2/2 | 0 | — / — |
| degraded | 0/1 | — | 0 | 1/1 / 0/1 |

## Failure analysis

- Set clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-02 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-03 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-04 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-05 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-06 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-07 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-08 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-09 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-10 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-11 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set clean-12 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-01 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-02 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-03 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-04 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-05 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-06 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-07 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-08 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-01 (discrepancy, stamp purple/over_dob): 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-03 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set hindi-clean-01 (clean, script hindi, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-clean-02 (clean, script hindi, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-clean-03 (clean, script hindi, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-clean-04 (clean, script hindi, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-degraded-01 (degraded, script hindi, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-variation-01 (variation, script hindi, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-variation-02 (variation, script hindi, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-variation-03 (variation, script hindi, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-01 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-02 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-03 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-04 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-05 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-06 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-07 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-08 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-09 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-10 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
