# DocTrust

**An open-weight reviewer agent that cross-examines a person's whole document set — and shows the human reviewer the evidence.**

*Do these documents tell a coherent story, and what evidence is missing before you can trust it?*

Built for the **Meta Global AI Developer Hackathon 2026** (Indie Developer track, "Build for Your World"). All code in this repository was written during the hackathon building period, 27 Oct – 4 Nov 2026.

## The problem

KYC and onboarding systems built around Latin names and clean scans fail people in non-Latin-script markets. In Bangladesh, the same person appears as Mohammad, Md. or Muhammed across documents; Bangla digits (০১২৩) sit next to 0123; dates change format from one document to the next; and applicants submit folded, glare-lit photos from low-end phones. Exact-match pipelines silently reject genuine customers, and tired human reviewers miss the subtle inconsistencies — a one-digit date-of-birth difference — that actually matter.

## What DocTrust does

DocTrust reviews a document set (national ID, birth certificate, bank form) the way a careful senior reviewer would:

1. **Locates the stamp** with SAM 3.1, called as a tool by the agent: SAM finds the stamp region, which the `stamp_masked` investigation view (step 4) then masks out before a re-read.
2. **Reads** each named field from the document views with Muse Spark — print, handwriting, Bangla and English, both digit systems.
3. **Estimates uncertainty by perturbation** — each field is read several times under changes (zoom, contrast, an occluding stamp masked out). Disagreement between reads marks a field as uncertain.
4. **Investigates** uncertain fields — and the model chooses how. Before each step, the reviewing model is consulted as a planner: shown the document image, the field and the reads so far, it picks the next step — mask the stamp and re-read, re-read a tighter zoomed crop, or stop and request a recapture — and its reason is recorded with the field's evidence trail. The planner only chooses where to look, never the answer: the field's value still comes from the reads, and every verdict from the deterministic comparator (step 5). If the planner cannot be reached or returns nothing usable, a fixed mask-then-zoom sequence runs instead, so a review never fails because the planner did.
5. **Normalizes and cross-examines** with deterministic code — digits, dates and name variants are canonicalized, then every shared fact is compared across documents.
6. **Reports a verdict with evidence** — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture* — every flag linked to the exact regions on the exact documents.

DocTrust never auto-approves or auto-rejects. It is decision support for a human reviewer. All documents used in development and evaluation are synthetic and watermarked SPECIMEN.

## Live demo

**https://rafiimam.github.io/DocTrust/demo/** — a self-contained replay of cached agent runs on synthetic document sets (a discrepancy hidden under a stamp, a genuine name/digit variation, a degraded capture), served from [`docs/demo/`](docs/demo/) by GitHub Pages. It calls no model and needs no API keys; live mode is the backend described below. Pages is enabled once by the repository owner: **Settings → Pages → Deploy from a branch → `main` → `/docs`**.

DocTrust is designed so sensitive documents never have to leave the institution: the reader can run on open weights (Muse Spark Open) and a self-hosted SAM 3.1 app is provided, so a deployment can run entirely inside the institution's own infrastructure. The current deployment instead uses Meta-hosted models for both reading (`muse-spark-1.3`) and SAM 3.1 segmentation. Both reader routes are verified live — the hosted Meta Model API route end-to-end in judge mode, and the open-weight Baseten route across the full evaluation (see Results) — see "Reader provider" under Judge mode.

## Judge mode — run it yourself, live

The demo page has an **Upload (judge mode)** tab. Instead of watching a replay, a judge runs the real pipeline on a fresh synthetic set:

1. **Download a case pack** from the backend (Clean / Variation / Discrepancy / Degraded) — a ZIP with `nid.png`, `birth_certificate.png`, `bank_form.png` and the `ground_truth.json` the run should agree with. Packs are generated on the fly; no binaries live in this repo.
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

## Status

Day 1 (27 Oct 2026): repository scaffold and plan; deterministic normalization and comparator with tests; synthetic SPECIMEN generator v1; agent loop with perturbation-based uncertainty and investigation reads; SAM 3.1 segmenter layer (Modal + Pillow fallback); GitHub Pages demo with cached cases; judge mode — live upload API with SSE trace, on-the-fly case packs, a Modal deployment wrapper, and an Upload tab in the demo. See [docs/PLAN.md](docs/PLAN.md) for the full plan, evaluation design, and schedule.

The **Bangla gate test has passed** on the Meta Model API route: `muse-spark-1.3` read all four fields of a clean synthetic NID exactly (4/4) — including the Bangla-digit ID number, preserved digit-for-digit. One calibration mattered: Muse Spark is a reasoning model, so the reader needs completion headroom (`max_tokens` 1024, `reasoning_effort` "minimal"); at a 128-token budget every call returned null content, the budget entirely consumed by reasoning. The judge-mode pipeline has also been verified publicly end-to-end on this route against the Modal deployment (fresh case pack downloaded, uploaded back, streamed investigation trace, correct *Discrepancy* verdict). The Baseten (Muse Spark Open) route has since been verified across the full evaluation (2026-10-29/30; see Results and [`eval/EVALUATION.md`](eval/EVALUATION.md)).

## Results

**The full evaluation has run** (2026-10-29/30, both reader routes, protocol and complete tables in [`eval/EVALUATION.md`](eval/EVALUATION.md)). 40 synthetic Bangla sets (12 clean, 10 genuine variation, 10 injected discrepancy, 8 degraded) plus 10 Hindi-script sets reported separately, three configurations (exact-match baseline, single-pass + normalization, full agent), all results as counts (x/n), never bare percentages. Headline, full agent, post-fix system:

- **Meta route** (muse-spark-1.3, 50/50 sets completed): false flags on genuine sets **0/22**, injected discrepancies caught **10/10**, degraded recovered **8/8**, **silent errors 0**. Hindi sets: false flags 0/7, caught 2/2, silent errors 0.
- **Baseten route** (Muse Spark Open, 42/50 completed — 8 sets exceeded the completion budget, 7 of them Hindi): false flags on genuine sets **0/21**, caught **8/10**, **silent errors 0**.

The first run exposed a systematic failure worth naming: the hosted reader transliterated the Bangla father's name on the birth certificate as "Abdul Karami", never "Abdul Karim", false-flagging 18/21 genuine sets. A deterministic consonant-skeleton equivalence in the name comparator fixed it — caught counts did not fall on either route (Meta 9/10 → 10/10). The physically-captured specimen batch is still pending, so every number above is synthetic-only, and no real-world accuracy claim is made. The fixed SAM-vs-heuristic stamp comparison protocol is in [`eval/SAM_TEST.md`](eval/SAM_TEST.md); its box-IoU stage has been run and is reported under "SAM 3.1 segmentation" below — a localization measurement, not an evaluation result.

## SAM 3.1 segmentation

SAM 3.1 is wired into the agent as a tool, not a preprocessing step:

- `backend/app/segmenter.py` defines the `Segmenter` interface the agent loop uses. When a field's perturbation reads disagree, the `stamp_masked` investigation view re-reads the field from a copy of the image with the stamp region masked by the injected segmenter. If no segmenter is configured — or segmentation fails — the view is read from the original image and the review proceeds unchanged.
- `MetaSAMSegmenter` calls SAM 3.1 hosted on the Meta Model API (the Responses endpoint, model `sam-3.1`, the same server-side `MODEL_API_KEY` as the reader). It parses the returned boxes in source-image pixels — the wire format carries no confidence score — and, when the optional `meta-sam-parser` package is installed, decodes the returned masks; otherwise the agent masks by box. Segmenter selection is by environment: `SEGMENTER=meta` (or a `MODEL_API_KEY` present with `SEGMENTER` unset) chooses this route, and the deployed backend sets `SEGMENTER=meta`.
- `ModalSegmenter` calls a self-hosted SAM 3.1 endpoint (`modal_sam/sam_app.py`: one scale-to-zero L4 GPU function on Modal, weights from the gated `facebook/sam3.1` Hugging Face repo, cached in a Modal Volume). Set `SEGMENTER=modal` and `SAM_MODAL_ENDPOINT` to enable it. That app is implemented but not currently deployed: the owner's Modal workspace cannot add the payment method its GPU functions require.
- `PillowFallbackSegmenter` is the deterministic offline path: a colour heuristic finds stamp-like (saturated blue/purple ink) regions and Pillow masks them. It needs no GPU, network or credits, and is what the offline test suite exercises.

**Evidence status** (27 Oct 2026):

- **Verified live:** the judge-mode pipeline runs publicly end-to-end. A fresh synthetic case pack was downloaded from the deployed (Modal) backend, uploaded back, and processed with a streamed investigation trace — including `stamp_masked` re-read views — returning the correct *Discrepancy* verdict.
- **Measured segmentation:** in the box-IoU stage of the fixed comparison in [eval/SAM_TEST.md](eval/SAM_TEST.md) (one clean synthetic set per stamp style, scored against the ground-truth stamp box), SAM 3.1 scored box IoU 0.99 on all four stamp styles (purple, black, red-orange, faded grey) under the pre-registered prompts "stamp" and "circular ink stamp"; the Pillow colour heuristic scored 0.98 on purple and found nothing (0.00) on the other three; the third pre-registered prompt, "rubber stamp", returned no boxes for SAM in any style. In a later spot check on the stamp-over-DOB placement, SAM's box matched ground truth exactly (IoU 1.00). Box IoU measures localization agreement only — it does not by itself establish better document-verification accuracy.
- **Still unproven:** whether SAM's localization improves recovered field readings and final verdicts across a broader test set. The full three-configuration evaluation ([eval/EVALUATION.md](eval/EVALUATION.md)) has now run with SAM 3.1 (hosted) as the segmenter in every run, but a controlled SAM-vs-heuristic comparison of final verdicts — the recovered-read stage of the SAM protocol — has not been run, so no verdict-level claim is made for SAM.

All development documents are synthetic and watermarked SPECIMEN.

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
