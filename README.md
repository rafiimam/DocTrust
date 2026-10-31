# DocTrust

**A reviewer agent that cross-examines a person's whole document set — and shows the human reviewer the evidence. It runs on hosted Muse Spark or Muse Spark Open (open weights).**

*Do these documents tell a coherent story, and what evidence is missing before you can trust it?*

Built for the **Meta Global AI Developer Hackathon 2026** (Indie Developer track, "Build for Your World"). All code in this repository was written during the hackathon building period, 27 Oct – 4 Nov 2026.

## The problem

KYC and onboarding systems built around Latin names and clean scans fail people in non-Latin-script markets. In Bangladesh, the same person appears as Mohammad, Md. or Muhammed across documents; Bangla digits (০১২৩) sit next to 0123; dates change format from one document to the next; and applicants submit folded, glare-lit photos from low-end phones. Exact-match pipelines silently reject genuine customers, and tired human reviewers miss the subtle inconsistencies — a one-digit date-of-birth difference — that actually matter.

The scale is not hypothetical. Bangladesh's Election Commission has received **6,570,842 applications to correct NID records** — 6,442,832 settled, 1,355,157 rejected after scrutiny, 128,010 still pending, and a further 80,000–90,000 arriving every month (National Identity Registration Wing figures to 18 Oct 2026, reported by the [Daily Observer](https://observerbd.com/news/601634) and [Sarabangla](https://en.sarabangla.net/election/post-44610/ec-settles-6-44-million-nid-correction-applications/)). These are applications to correct the record itself, and many are screened out as unjustified — but the volume is the point: errors in identity records are common enough that fixing them is a mass-scale public service, and the same errors plausibly surface downstream as mismatches whenever a person's documents are cross-checked against each other.

## Results at a glance

Full agent vs the baselines it has to beat — Meta route (muse-spark-1.3), 40 synthetic Bangla sets, post-fix system, 2026-10-30. Full tables, the second reader route, the Hindi sets, and every failure: [Results](#results) and [`eval/EVALUATION.md`](eval/EVALUATION.md).

| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |
|---|---|---|---|
| False flags on genuine sets (x/n) | 22/22 | 0/22 | 0/22 |
| Genuine sets cleared as Consistent (x/n) | 0/22 | 22/22 | 20/22 |
| Injected discrepancies caught (x/n) | 9/10 | 9/10 | 10/10 |
| Silent errors (count) | 0 | 0 | 0 |
| Degraded sets recovered (x/n) | 0/8 | 8/8 | 8/8 |
| Reads per set (mean) / latency per set (mean, s) | 11.0 / 19.6 | 11.0 / 19.6 | 34.2 / 60.7 |

Read this table honestly: the deterministic normalization is what removes the false flags — single-pass + normalization matches the full agent on almost every row, clears two more genuine sets, and costs a third of the reads. The agent layer's measured value is narrower and specific: it is an evidence-gathering and safe-escalation layer. It caught the one development discrepancy single-pass missed (a one-digit DOB difference under a stamp), it recovers degraded captures by re-reading instead of guessing, and across every batch its failures end as *Unreadable, request recapture* — never as a silent pass. Whether that is worth ~3× the reads is a deployment judgement; the numbers to make it are all here.

## What DocTrust does

DocTrust reviews a document set (national ID, birth certificate, bank form) the way a careful senior reviewer would:

1. **Locates the stamp** with SAM 3.1, called as a tool by the agent: SAM finds the stamp region, which the `stamp_masked` investigation view (step 4) then masks out before a re-read.
2. **Reads** each named field from the document views with Muse Spark — print, handwriting, Bangla and English, both digit systems.
3. **Estimates uncertainty by perturbation** — each field is read several times under changes (zoom, contrast, an occluding stamp masked out). Disagreement between reads marks a field as uncertain.
4. **Investigates** uncertain fields — and the model chooses how. Before each step, the reviewing model is consulted as a planner: shown the document image, the field and the reads so far, it picks the next step — mask the stamp and re-read, re-read a tighter zoomed crop, or stop and request a recapture — and its reason is recorded with the field's evidence trail. The planner only chooses where to look, never the answer: the field's value still comes from the reads, and every verdict from the deterministic comparator (step 5). If the planner cannot be reached or returns nothing usable, a fixed mask-then-zoom sequence runs instead, so a review never fails because the planner did.
5. **Normalizes and cross-examines** with deterministic code — digits, dates and name variants are canonicalized, then every shared fact is compared across documents.
6. **Reports a verdict with evidence** — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture* — every flag linked to the exact regions on the exact documents.

DocTrust never auto-approves or auto-rejects. It is decision support for a human reviewer. All documents used in development and evaluation are synthetic and watermarked SPECIMEN.

## Quick start

- **See it (30 seconds):** open the [live demo](https://rafiimam.github.io/DocTrust/demo/) and press Play. Cases A–D replay real review traces — a discrepancy caught under a stamp, a degraded set asking for recapture, and a Hindi (Devanagari) set. Nothing to install, nothing uploaded.
- **Run it live:** in the same page, switch to Judge mode and upload your own documents (synthetic only, please), or download a specimen case pack — including the Hindi pack — and run it through.
- **Run it locally:** `pip install -r backend/requirements.txt`, set `MODEL_API_KEY` and `JUDGE_READER=meta`, then serve `backend/app/main.py` — full steps under [Judge mode](#judge-mode--run-it-yourself-live) below. The test suite is 152 tests: `python -m pytest backend/tests -q`.

## Live demo

**https://rafiimam.github.io/DocTrust/demo/** — a self-contained replay of cached agent runs on synthetic document sets (Case A: a discrepancy hidden under a stamp; Case B: a genuine name/digit variation; Case C: a degraded capture that ends in a recapture request; Case D: a Hindi (Devanagari) set), served from [`docs/demo/`](docs/demo/) by GitHub Pages. It calls no model and needs no API keys; live mode is the backend described below.

DocTrust is designed so sensitive documents never have to leave the institution: the reader can run on open weights (Muse Spark Open) and a self-hosted SAM 3.1 app is provided, so a deployment can run entirely inside the institution's own infrastructure. The current deployment instead uses Meta-hosted models for both reading (`muse-spark-1.3`) and SAM 3.1 segmentation. Both reader routes are verified live — the hosted Meta Model API route end-to-end in judge mode, and the open-weight Baseten route across the full evaluation (see Results) — see "Reader provider" under Judge mode.

## Judge mode — run it yourself, live

The demo page has an **Upload (judge mode)** tab. Instead of watching a replay, a judge runs the real pipeline on a fresh synthetic set:

1. **Download a case pack** from the backend (Clean / Variation / Discrepancy / Degraded / Hindi) — a ZIP with `nid.png`, `birth_certificate.png`, `bank_form.png` and the `ground_truth.json` the run should agree with. The Hindi pack is a clean set from the Hindi persona (Devanagari script). Packs are generated on the fly; no binaries live in this repo.
2. **Upload the images.** All three documents are expected, but any subset is accepted — an expected document left out is reported as an evidence gap (step 3), not an error. The backend runs the agent loop as a job: reads under real perturbed views (zoom, contrast), model-chosen investigation steps when reads disagree (each decision and its reason appear in the streamed trace and in the result's per-field `investigation` log), then the deterministic cross-examination.
3. **Watch it happen.** The agent trace streams live (Server-Sent Events), and the result shows every field's read value, canonical form and per-view readings, the comparator findings, the evidence views the agent actually read, and the verdict — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture*. The result also carries an **Evidence gaps & next steps** section (`evidence_gaps` in the JSON), derived deterministically from the recorded run: a document the case profile expects but that was not uploaded, a field that stayed unreadable after investigation, or a field the readable documents disagree on — each with the next step it calls for. The three states are kept distinct: a missing document is not a contradiction, and an unreadable field is not a mismatch.

API: `POST /api/review` (multipart: `nid`, `birth_certificate`, `bank_form` — each field optional, at least one required; PNG/JPG, 8 MB per file) → `GET /api/review/{job_id}/events` (SSE) → `GET /api/review/{job_id}` (result JSON). Plus `GET /api/case-pack/{variant}` and `GET /health`. Jobs are in-memory only (capped, TTL-evicted); uploaded files are deleted with the job's temp directory.

**Run it locally:**

```bash
cd backend && uvicorn app.main:app --port 8000   # after: pip install -r requirements.txt
```

Then open the demo, switch to Upload mode — the demo's default backend URL is the hosted Modal backend (`https://rafiimam96--doctrust-backend-fastapi-app.us-east.modal.run`, editable on the page, remembered per browser); use `http://localhost:8000` instead when running this backend locally. **Deploy it:** [`modal_backend/README.md`](modal_backend/README.md) (scale-to-zero Modal app; paste its URL into the demo's Backend URL field).

**Honest limits.** Live field reading needs a reader API key configured **server-side**. Without one, the backend still accepts uploads and runs preprocessing and stamp segmentation — then ends the job in a plainly labelled `reader_not_configured` state. It never fakes a read or a verdict. Judge mode is for **synthetic documents only** — please do not upload real identity documents.

**Reader provider is configuration, not code.** The vision reader can be the **Meta Model API** (`MODEL_API_KEY`, model `muse-spark-1.3` by default) or **Baseten** hosting Muse Spark Open (`BASETEN_API_KEY`). Which one is used is chosen purely by environment — `JUDGE_READER=meta` or `JUDGE_READER=baseten` — and the Modal deployment stores the key as a secret (`meta-secret` or `baseten-secret`); see [`modal_backend/README.md`](modal_backend/README.md). Verification status, stated plainly: the **Meta Model API route is verified live** (Bangla gate test and a full judge-mode run, 27 Oct 2026, plus the full evaluation). The **Baseten / Muse Spark Open route is also verified** — it ran the complete evaluation on 2026-10-29/30 (see Results); its known quirk is completion budget: Spark Open always reasons at full depth, so it needs a much larger `max_tokens` budget than the hosted route, and on most Devanagari sets its reasoning exceeded even a 16384-token budget. A public backend also has a daily cap on live runs (`JUDGE_DAILY_RUN_CAP`, default 100) so the endpoint cannot spend the reader budget unbounded.

## How a reviewer team would use it

DocTrust sits in front of the human queue, not instead of it. Each application arrives as a job, and the verdict routes it: *Consistent* sets pass to a fast human confirm with the evidence attached; *Discrepancy* sets reach the reviewer with the disagreeing fields and regions already marked; *Unreadable* sets go back for recapture before a human spends time on them. The reviewer always makes the call — the agent's job is to make sure the call is made on evidence, not on a first glance. In a regulated deployment, the open-weights route (Muse Spark Open plus the self-hosted SAM app) keeps every document inside the institution's own infrastructure; in this hosted demo, jobs are in-memory only and uploaded files are deleted with the job's temporary directory.

## Status

Feature-complete; final evaluation and submission polish (31 Oct 2026). The full three-configuration evaluation has run on both reader routes, a fresh-seed held-out batch replicated the post-fix results (50/50 after a same-day retry of the one timed-out set), and the demo (cached cases + live judge mode on Modal) is public. Completed 31 Oct: the stamp-over-field hard batch — SAM vs Pillow vs planner ablation, no verdict-level differences, failures all safe recaptures — and the multi-persona name-generalization batch (30 discrepancy sets, ten personas; agent 26/30 SAM, 27/30 Pillow, zero silent errors; pooled silent-error bound now ≈ 6%). Still pending: the physically-captured specimen batch. Reader calibration detail — the Bangla gate test and the reasoning-budget configuration it produced — lives in [`eval/EVALUATION.md`](eval/EVALUATION.md); the plan is in [docs/PLAN.md](docs/PLAN.md).

## Results

**The full evaluation has run** (2026-10-29/30, both reader routes, protocol and complete tables in [`eval/EVALUATION.md`](eval/EVALUATION.md)). 40 synthetic Bangla sets (12 clean, 10 genuine variation, 10 injected discrepancy, 8 degraded) plus 10 Hindi-script sets reported separately, three configurations (exact-match baseline, single-pass + normalization, full agent), all results as counts (x/n), never bare percentages. Headline, full agent, post-fix system:

- **Meta route** (muse-spark-1.3, 50/50 sets completed): false flags on genuine sets **0/22**, injected discrepancies caught **10/10**, degraded recovered **8/8**, **silent errors 0**. Hindi sets: false flags 0/7, caught 2/2, silent errors 0.
- **Baseten route** (Muse Spark Open, 42/50 completed — 8 sets exceeded the completion budget, 7 of them Hindi): false flags on genuine sets **0/21**, caught **8/10**, **silent errors 0**.

The first run exposed a systematic failure worth naming: the hosted reader transliterated the Bangla father's name on the birth certificate as "Abdul Karami", never "Abdul Karim", false-flagging 18/21 genuine sets. A deterministic consonant-skeleton equivalence in the name comparator fixed it — caught counts did not fall on either route (Meta 9/10 → 10/10). Because the fix was designed from those sets' failures, a fresh-seed **held-out batch** (seed base 101, Meta route, run once with no code changes) was run on 2026-10-31: the behaviour replicated — full agent false flags **0/22**, discrepancies caught **9/9** of completed sets, silent errors **0**, Hindi sets again clean (0/7 false flags, 2/2 caught). One held-out set did not complete on the first pass: discrepancy-03 — the stamp-over-DOB case — errored on a network timeout; retried the same day, it completed as Unreadable in all three configurations (final held-out: 50/50, caught 9/10). A separate **multi-persona batch** — 30 discrepancy sets across ten Bangla personas with near-miss name and digit injections — measures catch rates on names the fix was not tuned on: the full agent caught 26/30 (SAM) and 27/30 (Pillow), single-pass + normalization the same 26/30 and 27/30, zero silent errors, and the near-miss names were caught at the same rate as the digit swaps. Two sets were flagged only on a wrong field (father_name — a disagreement in the reads, not in the documents); the field-level analysis is in EVALUATION.md. The companion **genuine multi-persona run** (30 clean/variation sets across the same ten personas) is the sobering one: the agent cleared 23/30 (5 flagged, 2 sent to recapture) and single-pass 23/30 (7 flagged) — every flag on father_name, from consonant-level transliteration variance ("Rafiqul" read as "Rafikul") that the name equivalence does not fold. The base persona's clean false-flag record does not generalize across names, and we say so in the evaluation rather than finding out from a judge. The physically-captured specimen batch is still pending, so every number above is synthetic-only, and no real-world accuracy claim is made. The fixed SAM-vs-heuristic stamp comparison protocol is in [`eval/SAM_TEST.md`](eval/SAM_TEST.md); its box-IoU stage has been run and is reported under "SAM 3.1 segmentation" below — a localization measurement, not an evaluation result.

## SAM 3.1 segmentation

SAM 3.1 is wired into the agent as a tool, not a preprocessing step:

- `backend/app/segmenter.py` defines the `Segmenter` interface the agent loop uses. When a field's perturbation reads disagree, the `stamp_masked` investigation view re-reads the field from a copy of the image with the stamp region masked by the injected segmenter. If no segmenter is configured — or segmentation fails — the view is read from the original image and the review proceeds unchanged.
- `MetaSAMSegmenter` calls SAM 3.1 hosted on the Meta Model API (the Responses endpoint, model `sam-3.1`, the same server-side `MODEL_API_KEY` as the reader). It parses the returned boxes in source-image pixels — the wire format carries no confidence score — and, when the optional `meta-sam-parser` package is installed, decodes the returned masks; otherwise the agent masks by box. Segmenter selection is by environment: `SEGMENTER=meta` (or a `MODEL_API_KEY` present with `SEGMENTER` unset) chooses this route, and the deployed backend sets `SEGMENTER=meta`.
- `ModalSegmenter` calls a self-hosted SAM 3.1 endpoint (`modal_sam/sam_app.py`: one scale-to-zero L4 GPU function on Modal, weights from the gated `facebook/sam3.1` Hugging Face repo, cached in a Modal Volume). Set `SEGMENTER=modal` and `SAM_MODAL_ENDPOINT` to enable it. That app is implemented but not currently deployed: the owner's Modal workspace cannot add the payment method its GPU functions require.
- `PillowFallbackSegmenter` is the deterministic offline path: a colour heuristic finds stamp-like (saturated blue/purple ink) regions and Pillow masks them. It needs no GPU, network or credits, and is what the offline test suite exercises.

**Evidence status** (updated 31 Oct 2026):

- **Verified live:** the judge-mode pipeline runs publicly end-to-end. A fresh synthetic case pack was downloaded from the deployed (Modal) backend, uploaded back, and processed with a streamed investigation trace — including `stamp_masked` re-read views — returning the correct *Discrepancy* verdict.
- **Measured segmentation:** in the box-IoU stage of the fixed comparison in [eval/SAM_TEST.md](eval/SAM_TEST.md) (one clean synthetic set per stamp style, scored against the ground-truth stamp box), SAM 3.1 scored box IoU 0.99 on all four stamp styles (purple, black, red-orange, faded grey) under the pre-registered prompts "stamp" and "circular ink stamp"; the Pillow colour heuristic scored 0.98 on purple and found nothing (0.00) on the other three; the third pre-registered prompt, "rubber stamp", returned no boxes for SAM in any style. In a later spot check on the stamp-over-DOB placement, SAM's box matched ground truth exactly (IoU 1.00). Box IoU measures localization agreement only — it does not by itself establish better document-verification accuracy.
- **Measured, no verdict-level difference:** the controlled SAM-vs-heuristic comparison of final verdicts — the recovered-read stage of the SAM protocol — ran on 31 Oct over 18 stamp-over-field and degraded sets: SAM and the Pillow fallback produced identical verdicts (7/10 caught, the same three black-stamp sets unreadable to both, zero silent errors). On black-stamp occlusion the raw reads fail before masking matters, so localization is not the bottleneck there; no verdict-level claim is made for SAM. Detail in [eval/EVALUATION.md](eval/EVALUATION.md).

All development documents are synthetic and watermarked SPECIMEN.

## What we learned about Meta's models

Findings from building on the Meta Model API and Baseten's Muse Spark Open route — each one cost us a debugging session, and each one is the kind of thing we would want to know before starting:

- **Reasoning models eat small budgets silently.** At `max_tokens` 128, `muse-spark-1.3` returned null content on every call — the budget went entirely to reasoning. Field reads need real headroom (1024 + `reasoning_effort: "minimal"` on the hosted route). Muse Spark Open reasons at full depth with no effort control: a minority of sets returned no content at 4096 or 8192 tokens, and 7 of 50 sets — almost all Devanagari — returned none even at 16,384.
- **Reader bias is systematic, not noisy.** The hosted reader back-transliterated the Bangla করিম as "Abdul Karami" in 26 of 29 genuine sets and never once as "Abdul Karim"; the open-weights build read "Abdul Karim" on the identical images. One biased field produced 18/21 false flags. Lesson: evaluate vision readers per script and per field — an aggregate accuracy number would have hidden this completely.
- **SAM 3.1 is prompt-sensitive in a specific way.** "stamp" and "circular ink stamp" localized the stamp at box IoU 0.99 across all four ink styles; "rubber stamp" returned zero boxes in every style. The hosted route returns boxes and masks but no confidence score, so downstream code cannot threshold on certainty — plan for that.
- **The route is a variable, not a detail.** Same model family, two routes: the hosted API answered a full agent review in ~58 s per set; the open-weights route took ~195–213 s and completed 42 of 50 sets within the token budgets we could give it. Report the route with every number.

## Future work — directions, not capabilities

Two directions are recorded here as future research to build on the investigation engine above. **Neither is implemented, and nothing in this submission claims them.**

- **PaperTrail** — missing-link reasoning across property and inheritance records: rather than only checking whether fields agree, evaluate the relationships among claims, events and supporting evidence — what a packet asserts, what each assertion depends on, and which supporting evidence is absent.
- **WorkerShield** — cross-document employment-term verification for migrant workers: compare the terms across a job offer, an employment contract, a work permit and payment receipts, and surface where the documents a worker was shown and the documents they are asked to sign tell different stories.

## Layout

- `backend/` — FastAPI service: agent loop, tools, deterministic comparator
- `modal_sam/` — SAM 3.1 image segmentation as a Modal app (deployment + smoke-test steps inside)
- `modal_backend/` — the judge-mode backend as a scale-to-zero Modal app (deployment + smoke-test steps inside)
- `frontend/` — reviewer UI (documents left, live agent trace with evidence links right)
- `generator/` — synthetic document set generator (SPECIMEN-watermarked)
- `eval/` — synthetic evaluation sets and baseline/agent comparisons
- `docs/` — plan and notes; `docs/demo/` is the GitHub Pages reviewer-UI demo

## License

MIT
