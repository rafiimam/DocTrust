# DocTrust evaluation — run summary

- Date: 2026-10-30T12:12:01.150039+00:00
- Reader: BasetenReader
- Segmenter: MetaSAMSegmenter
- Seed base: 7 (per-set seed = base + set index)
- Sets completed: 42 (errors: 8)
- Hindi-script sets: 10 (secondary script, reported separately below; not in the headline tables)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 19/21 | 1/21 | 0/21 |
| Injected discrepancies caught (x/n) | 7/10 | 8/10 | 8/10 |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | 0/8 / 2/8 | 4/8 / 2/8 | 5/8 / 3/8 |
| Reads per set (mean) | 11.0 | 11.0 | 35.28 |
| Latency per set (mean, s) | 57.23 | 57.23 | 194.55 |
| Cost per set (USD, at route prices) | — | — | — |

### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 0/12 | — | 0 | — / — |
| variation | 0/9 | — | 0 | — / — |
| discrepancy | — | 8/10 | 0 | — / — |
| degraded | 0/8 | — | 0 | 5/8 / 3/8 |

### Hindi-script sets (secondary, small n)

_The same three configurations over the Hindi-script (Devanagari) sets only. These sets are NOT included in the headline tables above — the headline comparison is the Bangla sets. Claims stay narrow: Bangla primary, Hindi secondary, small n._

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 0/3 | 0/3 | 1/3 |
| Injected discrepancies caught (x/n) | — | — | — |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | — / — | — / — | — / — |
| Reads per set (mean) | 11.0 | 11.0 | 48.33 |
| Latency per set (mean, s) | 79.27 | 79.27 | 400.51 |
| Cost per set (USD, at route prices) | — | — | — |

#### By category — full agent (configuration 3)

| Category | False flags (x/n) | Discrepancies caught (x/n) | Silent errors | Recovered / recapture (x/n) |
|---|---|---|---|---|
| clean | 1/2 | — | 0 | — / — |
| variation | 0/1 | — | 0 | — / — |
| discrepancy | — | — | 0 | — / — |
| degraded | — | — | 0 | — / — |

## Failure analysis

- Set clean-01 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-02 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY
- Set clean-03 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-04 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-05 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-06 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-07 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE
- Set clean-08 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-09 (clean, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-10 (clean, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-11 (clean, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set clean-12 (clean, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE
- Set degraded-01 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE
- Set degraded-02 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set degraded-03 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY
- Set degraded-04 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 2. Single-pass + norm.: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set degraded-05 (degraded, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set degraded-06 (degraded, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE
- Set degraded-07 (degraded, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set degraded-08 (degraded, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set discrepancy-02 (discrepancy, stamp red_orange/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-03 (discrepancy, stamp black/over_dob): 1. Exact-match: expected DISCREPANCY, got UNREADABLE; 2. Single-pass + norm.: expected DISCREPANCY, got UNREADABLE; 3. Full agent: expected DISCREPANCY, got UNREADABLE
- Set discrepancy-09 (discrepancy, stamp purple/margin): 1. Exact-match: expected DISCREPANCY, got UNREADABLE
- Set hindi-clean-01 (clean, script hindi, stamp black/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE; 3. Full agent: expected CONSISTENT, got DISCREPANCY
- Set hindi-clean-04 (clean, script hindi, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set hindi-variation-01 (variation, script hindi, stamp black/margin): 1. Exact-match: expected CONSISTENT, got UNREADABLE; 2. Single-pass + norm.: expected CONSISTENT, got UNREADABLE; 3. Full agent: expected CONSISTENT, got UNREADABLE
- Set variation-01 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-02 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-03 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-04 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-06 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-07 (variation, stamp purple/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-08 (variation, stamp red_orange/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-09 (variation, stamp black/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set variation-10 (variation, stamp faded_grey/margin): 1. Exact-match: expected CONSISTENT, got DISCREPANCY
- Set hindi-clean-02 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-clean-03 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-degraded-01 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-discrepancy-01 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-discrepancy-02 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-variation-02 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set hindi-variation-03 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-05 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
