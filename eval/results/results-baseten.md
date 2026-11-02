# DocTrust evaluation — run summary

- Date: 2026-10-29T17:09:38.431657+00:00
- Reader: BasetenReader
- Segmenter: PillowFallbackSegmenter
- Seed base: 7 (per-set seed = base + set index)
- Sets completed: 1 (errors: 39)

**Counts (x/n) throughout — never bare percentages.**

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 1/1 | 0/1 | 0/1 |
| Injected discrepancies caught (x/n) | — | — | — |
| **Silent errors — verdict "Consistent" while a discrepancy exists (count)** | **0** | **0** | **0** |
| Degraded sets: recovered / recapture requested (x/n) | — / — | — / — | — / — |
| Reads per set (mean) | 11.0 | 11.0 | 33.0 |
| Latency per set (mean, s) | 117.81 | 117.81 | 209.58 |
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
- Set clean-02 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set clean-03 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set clean-04 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set clean-05 (clean): run error — RuntimeError: Baseten request failed: _ssl.c:1015: The handshake operation timed out
- Set clean-06 (clean): run error — RuntimeError: Baseten request failed: The read operation timed out
- Set clean-07 (clean): run error — RuntimeError: Baseten request failed: The read operation timed out
- Set clean-08 (clean): run error — RuntimeError: Baseten request failed: [Errno 54] Connection reset by peer
- Set clean-09 (clean): run error — RuntimeError: Baseten request failed: Server disconnected without sending a response.
- Set clean-10 (clean): run error — RuntimeError: Baseten request failed: The read operation timed out
- Set clean-11 (clean): run error — RuntimeError: Baseten request failed: _ssl.c:1015: The handshake operation timed out
- Set clean-12 (clean): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-01 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-02 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-03 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-04 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-05 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-06 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-07 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set degraded-08 (degraded): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-01 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-02 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-03 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-04 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-05 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-06 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-07 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-08 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-09 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set discrepancy-10 (discrepancy): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-01 (variation): run error — RuntimeError: Baseten request failed: _ssl.c:1015: The handshake operation timed out
- Set variation-02 (variation): run error — RuntimeError: Baseten request failed: The read operation timed out
- Set variation-03 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-04 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-05 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-06 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-07 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-08 (variation): run error — RuntimeError: Baseten request failed: The read operation timed out
- Set variation-09 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
- Set variation-10 (variation): run error — RuntimeError: Baseten returned no content (finish_reason='length'); Muse Spark Open always reasons, so the completion budget was likely consumed by reasoning — raise BASETEN_MAX_TOKENS — or the response shape was unexpected.
