# DocTrust

**An open-weight reviewer agent that cross-examines a person's whole document set — and shows the human reviewer the evidence.**

Built for the **Meta Global AI Developer Hackathon 2026** (Indie Developer track, "Build for Your World"). All code in this repository was written during the hackathon building period, 27 Oct – 4 Nov 2026.

## The problem

KYC and onboarding systems built around Latin names and clean scans fail people in non-Latin-script markets. In Bangladesh, the same person appears as Mohammad, Md. or Muhammed across documents; Bangla digits (০১২৩) sit next to 0123; dates change format from one document to the next; and applicants submit folded, glare-lit photos from low-end phones. Exact-match pipelines silently reject genuine customers, and tired human reviewers miss the subtle inconsistencies — a one-digit date-of-birth difference — that actually matter.

## What DocTrust does

DocTrust reviews a document set (national ID, birth certificate, bank form) the way a careful senior reviewer would:

1. **Segments** each document and field region with SAM 3.1, called as a tool by the agent.
2. **Reads** each region with Muse Spark Open — print, handwriting, Bangla and English, both digit systems.
3. **Estimates uncertainty by perturbation** — each field is read several times under changes (zoom, contrast, an occluding stamp masked out). Disagreement between reads marks a field as uncertain.
4. **Investigates** uncertain fields: zooms in, masks the stamp, re-reads, and records what changed.
5. **Normalizes and cross-examines** with deterministic code — digits, dates and name variants are canonicalized, then every shared fact is compared across documents.
6. **Reports a verdict with evidence** — *Consistent* / *Discrepancy, needs human review* / *Unreadable, request recapture* — every flag linked to the exact regions on the exact documents.

DocTrust never auto-approves or auto-rejects. It is decision support for a human reviewer. All documents used in development and evaluation are synthetic and watermarked SPECIMEN.

## Live demo

**https://rafiimam.github.io/DocTrust/demo/** — a self-contained replay of cached agent runs on synthetic document sets (a discrepancy hidden under a stamp, a genuine name/digit variation, a degraded capture), served from [`docs/demo/`](docs/demo/) by GitHub Pages. It calls no model and needs no API keys; live mode is the backend described below. Pages is enabled once by the repository owner: **Settings → Pages → Deploy from a branch → `main` → `/docs`**.

Because it runs on open-weight models (Muse Spark Open via Baseten, SAM 3.1 self-hosted on Modal), sensitive documents can stay inside the institution's own infrastructure.

## Status

Day 1 (27 Oct 2026): repository scaffold and plan; deterministic normalization and comparator with tests; synthetic SPECIMEN generator v1; agent loop with perturbation-based uncertainty and investigation reads. See [docs/PLAN.md](docs/PLAN.md) for the full plan, evaluation design, and schedule.

## SAM 3.1 segmentation (on Modal)

SAM 3.1 is wired into the agent as a tool, not a preprocessing step:

- `backend/app/segmenter.py` defines the `Segmenter` interface the agent loop uses. When a field's perturbation reads disagree, the `stamp_masked` investigation view re-reads the field from a copy of the image with the stamp region masked by the injected segmenter. If no segmenter is configured — or segmentation fails — the view is read from the original image and the review proceeds unchanged.
- `ModalSegmenter` calls the self-hosted SAM 3.1 endpoint (`modal_sam/sam_app.py`: one scale-to-zero L4 GPU function on Modal, weights from the gated `facebook/sam3.1` Hugging Face repo, cached in a Modal Volume). Set `SAM_MODAL_ENDPOINT` to enable it.
- `PillowFallbackSegmenter` is the deterministic offline path: a colour heuristic finds stamp-like (saturated blue/purple ink) regions and Pillow masks them. It needs no GPU, network or credits, and is what the test suite exercises.

**Status: implemented and covered by offline tests; the live Modal smoke test is pending** — it needs the project owner's Hugging Face read token and Modal login, plus the endpoint's first (slow) weights download. Exact steps are in [modal_sam/README.md](modal_sam/README.md). No accuracy claim is made for segmentation at this stage; all development documents are synthetic and watermarked SPECIMEN.

## Layout

- `backend/` — FastAPI service: agent loop, tools, deterministic comparator
- `modal_sam/` — SAM 3.1 image segmentation as a Modal app (deployment + smoke-test steps inside)
- `frontend/` — reviewer UI (documents left, live agent trace with evidence links right)
- `generator/` — synthetic document set generator (SPECIMEN-watermarked)
- `eval/` — synthetic evaluation sets and baseline/agent comparisons
- `docs/` — plan and notes; `docs/demo/` is the GitHub Pages reviewer-UI demo

## License

MIT
