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

Because it runs on open-weight models (Muse Spark Open via Baseten, SAM 3.1 self-hosted on Modal), sensitive documents can stay inside the institution's own infrastructure.

## Status

Day 1 (27 Oct 2026): repository scaffold and plan. See [docs/PLAN.md](docs/PLAN.md) for the full plan, evaluation design, and schedule.

## Layout

- `backend/` — FastAPI service: agent loop, tools, deterministic comparator
- `frontend/` — reviewer UI (documents left, live agent trace with evidence links right)
- `generator/` — synthetic document set generator (SPECIMEN-watermarked)
- `eval/` — synthetic evaluation sets and baseline/agent comparisons
- `docs/` — plan and notes

## License

MIT
