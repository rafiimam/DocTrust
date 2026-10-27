# DocTrust

**An open-weight reviewer agent that cross-examines a person's whole document set — and shows the human reviewer the evidence.**

Built for the **Meta Global AI Developer Hackathon 2026** (Indie Developer track, "Build for Your World"). All code in this repository was written during the hackathon building period, 27 Oct – 4 Nov 2026.

## The problem

KYC and onboarding systems built around Latin names and clean scans fail people in non-Latin-script markets. In Bangladesh, the same person appears as Mohammad, Md. or Muhammed across documents; Bangla digits (০১২৩) sit next to 0123; dates change format from one document to the next; and applicants submit folded, glare-lit photos from low-end phones. Exact-match pipelines silently reject genuine customers, and tired human reviewers miss the subtle inconsistencies — a one-digit date-of-birth difference — that actually matter.

## What DocTrust does

DocTrust reviews a document set (national ID, birth certificate, bank form) the way a careful senior reviewer would:

1. **Segments** each document and field region with SAM 3.1, called as a tool by the agent.
2. **Reads** each region with Muse Spark — print, handwriting, Bangla and English, both digit systems.
3. **Estimates uncertainty by perturbation** — each field is read several times under changes (zoom, contrast, an occluding stamp masked out). Disagreement between reads marks a field as uncertain.
4. **Investigates** uncertain fields: zooms in, masks the stamp, re-reads, and records what changed.
5. **Normalizes and cross-examines** with deterministic code — digits, dates and name variants are canonicalized, then every shared fact is compared across documents.
6. **Reports a verdict with evidence** — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture* — every flag linked to the exact regions on the exact documents.

DocTrust never auto-approves or auto-rejects. It is decision support for a human reviewer. All documents used in development and evaluation are synthetic and watermarked SPECIMEN.

## Live demo

**https://rafiimam.github.io/DocTrust/demo/** — a self-contained replay of cached agent runs on synthetic document sets (a discrepancy hidden under a stamp, a genuine name/digit variation, a degraded capture), served from [`docs/demo/`](docs/demo/) by GitHub Pages. It calls no model and needs no API keys; live mode is the backend described below. Pages is enabled once by the repository owner: **Settings → Pages → Deploy from a branch → `main` → `/docs`**.

DocTrust is designed so sensitive documents never have to leave the institution: the reader can run on open weights (Muse Spark Open) and the segmenter is a self-hosted SAM 3.1, so a deployment can run entirely inside the institution's own infrastructure. What is verified live so far is the hosted Meta Model API route (`muse-spark-1.3`); the open-weight Baseten route is implemented and selectable by environment variable, with its verification pending a Baseten key — see "Reader provider" under Judge mode.

## Judge mode — run it yourself, live

The demo page has an **Upload (judge mode)** tab. Instead of watching a replay, a judge runs the real pipeline on a fresh synthetic set:

1. **Download a case pack** from the backend (Clean / Variation / Discrepancy / Degraded) — a ZIP with `nid.png`, `birth_certificate.png`, `bank_form.png` and the `ground_truth.json` the run should agree with. Packs are generated on the fly; no binaries live in this repo.
2. **Upload the three images.** The backend runs the agent loop as a job: reads under real perturbed views (zoom, contrast, tight zoom), investigation re-reads with the stamp masked when reads disagree, then the deterministic cross-examination.
3. **Watch it happen.** The agent trace streams live (Server-Sent Events), and the result shows every field's read value, canonical form and per-view readings, the comparator findings, the evidence views the agent actually read, and the verdict — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture*.

API: `POST /api/review` (multipart: `nid`, `birth_certificate`, `bank_form`; PNG/JPG, 8 MB per file) → `GET /api/review/{job_id}/events` (SSE) → `GET /api/review/{job_id}` (result JSON). Plus `GET /api/case-pack/{variant}` and `GET /health`. Jobs are in-memory only (capped, TTL-evicted); uploaded files are deleted with the job's temp directory.

**Run it locally:**

```bash
cd backend && uvicorn app.main:app --port 8000   # after: pip install -r requirements.txt
```

Then open the demo, switch to Upload mode — the default backend URL is `http://localhost:8000` (editable on the page, remembered per browser). **Deploy it:** [`modal_backend/README.md`](modal_backend/README.md) (scale-to-zero Modal app; paste its URL into the demo's Backend URL field).

**Honest limits.** Live field reading needs a reader API key configured **server-side**. Without one, the backend still accepts uploads and runs preprocessing and stamp segmentation — then ends the job in a plainly labelled `reader_not_configured` state. It never fakes a read or a verdict. Judge mode is for **synthetic documents only** — please do not upload real identity documents.

**Reader provider is configuration, not code.** The vision reader can be the **Meta Model API** (`MODEL_API_KEY`, model `muse-spark-1.3` by default) or **Baseten** hosting Muse Spark Open (`BASETEN_API_KEY`). Which one is used is chosen purely by environment — `JUDGE_READER=meta` or `JUDGE_READER=baseten` — and the Modal deployment stores the key as a secret (`meta-secret` or `baseten-secret`); see [`modal_backend/README.md`](modal_backend/README.md). Verification status, stated plainly: the **Meta Model API route is the one verified live** (Bangla gate test and a full judge-mode run, 27 Oct 2026). The **Baseten / Muse Spark Open route is implemented but not yet verified** — it awaits a Baseten API key, and nothing in this README claims results for it. A public backend also has a daily cap on live runs (`JUDGE_DAILY_RUN_CAP`, default 100) so the endpoint cannot spend the reader budget unbounded.

## Status

Day 1 (27 Oct 2026): repository scaffold and plan; deterministic normalization and comparator with tests; synthetic SPECIMEN generator v1; agent loop with perturbation-based uncertainty and investigation reads; SAM 3.1 segmenter layer (Modal + Pillow fallback); GitHub Pages demo with cached cases; judge mode — live upload API with SSE trace, on-the-fly case packs, a Modal deployment wrapper, and an Upload tab in the demo. See [docs/PLAN.md](docs/PLAN.md) for the full plan, evaluation design, and schedule.

The **Bangla gate test has passed** on the Meta Model API route: `muse-spark-1.3` read all four fields of a clean synthetic NID exactly (4/4) — including the Bangla-digit ID number, preserved digit-for-digit. One calibration mattered: Muse Spark is a reasoning model, so the reader needs completion headroom (`max_tokens` 1024, `reasoning_effort` "minimal"); at a 128-token budget every call returned null content, the budget entirely consumed by reasoning. A full judge-mode run with live reads has also completed end-to-end on this route (discrepancy set, correct verdict). The Baseten (Muse Spark Open) route remains implemented-but-unverified pending its key.

## Results

**Evaluation pending — no numbers are claimed yet.** The evaluation protocol and report template are in [`eval/EVALUATION.md`](eval/EVALUATION.md): about 40 synthetic sets (clean, genuine variation, injected discrepancy, degraded, plus physically captured specimen sets), three configurations (exact-match baseline, single-pass + normalization, full agent), all results reported as counts (x/n), never bare percentages. The fixed SAM-vs-heuristic stamp comparison protocol is in [`eval/SAM_TEST.md`](eval/SAM_TEST.md).

## SAM 3.1 segmentation (on Modal)

SAM 3.1 is wired into the agent as a tool, not a preprocessing step:

- `backend/app/segmenter.py` defines the `Segmenter` interface the agent loop uses. When a field's perturbation reads disagree, the `stamp_masked` investigation view re-reads the field from a copy of the image with the stamp region masked by the injected segmenter. If no segmenter is configured — or segmentation fails — the view is read from the original image and the review proceeds unchanged.
- `ModalSegmenter` calls the self-hosted SAM 3.1 endpoint (`modal_sam/sam_app.py`: one scale-to-zero L4 GPU function on Modal, weights from the gated `facebook/sam3.1` Hugging Face repo, cached in a Modal Volume). Set `SAM_MODAL_ENDPOINT` to enable it.
- `PillowFallbackSegmenter` is the deterministic offline path: a colour heuristic finds stamp-like (saturated blue/purple ink) regions and Pillow masks them. It needs no GPU, network or credits, and is what the test suite exercises.

**Status: implemented and covered by offline tests; the live Modal smoke test is pending** — it needs the project owner's Hugging Face read token and Modal login, plus the endpoint's first (slow) weights download. Exact steps are in [modal_sam/README.md](modal_sam/README.md). No accuracy claim is made for segmentation at this stage; all development documents are synthetic and watermarked SPECIMEN.

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
