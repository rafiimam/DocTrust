# DocTrust — Revised Plan (v2)

Meta Global AI Developer Hackathon · Indie Developer track · "Build for Your World"
Written 27 Oct 2026 by Rafi. Supersedes the earlier plan (DocTrust-Updated-Plan-2026-10-27.md).

## One line
DocTrust is an open-weight reviewer agent that cross-examines a person's whole document set (NID, birth certificate, bank form), re-reads anything it is unsure about, and shows the human reviewer the exact regions that agree or disagree. It never auto-rejects.

## Status note (27 Oct 2026) — what is verified, what is pending
- **Verified live:** the reader running on the hosted Meta Model API (`muse-spark-1.3`) — the Bangla gate test passed 4/4, and the judge-mode pipeline was verified publicly end-to-end against the Modal deployment (fresh case pack downloaded, uploaded back, streamed investigation trace including `stamp_masked` re-read views, correct DISCREPANCY verdict; 27 Oct 2026). Billing resolved via the $150 credit.
- **Implemented, verification pending:** the open-weight route — Muse Spark Open (`meta-models/muse-spark-open-1026`) via Baseten. The reader is implemented and selectable by environment variable, but no result in this repo comes from it yet; verification waits on a Baseten key. Below, "Muse Spark Open" names that route; where the current build's live behaviour is described, it is the Meta Model API route.
- **Segmentation route:** SAM 3.1 is called through the Meta Model API (Meta-hosted, same weights), and that is the segmenter the deployed backend uses. The self-hosted Modal SAM app is implemented but not deployed — the owner's Modal workspace cannot add the payment method its GPU functions require. Measured so far: the box-IoU stage of the stamp comparison (`eval/SAM_TEST.md`) — SAM box IoU 0.99 on all four stamp styles under two pre-registered prompts, the Pillow heuristic 0.98 on purple and nothing on the other three. Still unproven: whether that localization improves recovered reads and verdicts — the recovered-read stage and the full evaluation run remain pending (protocol in `eval/EVALUATION.md`).
- The open-weights point throughout this plan is a **design property** — a deployment *can* run entirely inside the institution — not a claim about which route the current demo runs.
- **Update (29 Oct 2026):** investigation is now model-directed — when a field is uncertain, the reader is consulted as a planner (max 2 consultations per field) to choose the next step (mask the stamp / tighter zoom / stop for recapture) with its reason logged per field; any planner failure falls back to the previous fixed mask-then-zoom sequence, and the comparator keeps sole verdict authority. Implemented and covered by offline tests; the full evaluation now runs against this agent.

## What changed from v1, and why
- Re-reads are triggered by perturbation disagreement, not model self-confidence — principled uncertainty, and it puts the noise-robustness research at the core.
- SAM 3.1 becomes a tool the agent calls (e.g. mask a stamp, then re-read) — rubric asks for use of Meta tooling beyond a basic integration.
- Open weights are a design argument, not a workaround — documents can stay inside the institution; fits the open-weight bonus.
- Small evaluation with an exact-match baseline — technical depth; proves the claims instead of asserting them.
- "Likely-fraud" replaced by "Discrepancy, needs human review" and a new "Unreadable, request recapture" verdict — ethics, accuracy, and it serves applicants with poor cameras.
- Scope cut to 3 document types and 3 discrepancy classes; no face matching — realistic for a solo, part-time build.
- Synthetic generator moved to Wednesday — nothing can be tested or evaluated without it.

## The problem (Impact, 30%)
KYC systems built around Latin names and clean scans fail people in non-Latin-script markets. Bangladesh is the proving ground:
- Name variation across scripts. The same person appears as Mohammad, Md. or Muhammed, and Bangla names transliterate several ways. Exact matching rejects genuine customers.
- Mixed digits and date formats. Bangla digits (০১২৩) appear next to 0123, and dates differ between documents. Generic OCR can mishandle these silently.
- Poor captures. Folded, glared, low-end-phone photos fail exactly where inclusion matters most.
- Subtle inconsistencies. A one-digit DOB difference or a nearly matching name is easy for a tired reviewer to miss.

Framing for judges: this is a pattern shared by many markets; Bangladesh is where it is built and tested. Use only statistics that can be cited; do not invent scale numbers.

## How it works (the agent loop)
1. Segment. SAM 3.1 finds each document and field region using text concept prompts ("stamp", "signature", "handwritten date", "photo").
2. Read. Muse Spark reads each region (print, handwriting, Bangla, English, both digit systems).
3. Estimate uncertainty. Each field is read several times under perturbations (zoom, contrast, stamp masked out). Disagreement across reads marks the field uncertain.
4. Investigate. For uncertain fields the agent acts: zoom, mask an occluding stamp via SAM, re-read, and record what changed.
5. Normalize. Deterministic code converts digits, dates and name variants to canonical forms (transliteration-aware matching, not string equality).
6. Cross-examine. Deterministic comparison of every shared fact across documents: name, DOB, ID number, father's name, address.
7. Verdict with evidence. Consistent / Discrepancy, needs human review / Unreadable, request recapture. Every flag links to the exact regions on the exact documents.

## Design rules
- The model reads and handles ambiguous calls. Normalization and comparison are deterministic code, so every flag is traceable.
- If tool calling on Muse Spark Open proves unreliable, use a fixed step sequence where the model decides at each step. The UI looks the same.
- Nothing auto-approves or auto-rejects. The output is decision support.

## Rubric mapping
- Impact (30%): genuine customer falsely rejected by exact match; recapture verdict for bad photos; open weights so documents need not leave the institution.
- Meta AI tooling (25%): SAM 3.1 as an in-loop tool with open-vocabulary prompts and masks as evidence; Muse Spark reading mixed Bangla/English and both digit systems (verified live via the Meta Model API; the open-weight Baseten route is implemented, verification pending its key).
- Technical depth (20%): perturbation-based uncertainty, deterministic comparator with tests, ablation results.
- Demo (25%): live agent trace, evidence overlays across documents, pre-warmed endpoints, recorded fallback.

Bonus fits: Best Build on Meta Open Weight Models ($10K, via Baseten/Modal), Best Agentic Use-Case ($5K). Optional after submission: post the demo on X for the Most Viral bonus.

## Evaluation (small, synthetic, honest)
About 40 synthetic document sets with known ground truth:
- ~12 clean genuine sets
- ~10 genuine sets with legitimate variation (name transliterations, Bangla vs English digits, different date formats)
- ~10 sets with injected discrepancies (swapped DOB digit, swapped ID digit, mismatched father's name)
- ~8 degraded captures (blur, glare, fold, stamp over text)

Three configurations compared:
1. Exact-match baseline
2. Single-pass extraction plus normalization
3. Full agent (perturbation uncertainty plus investigation)

Metrics: false-flag rate on genuine sets, detection rate on injected discrepancies, how often degraded captures are correctly marked unreadable or recovered by re-reading.
Report as a small synthetic-set result. Do not claim real-world accuracy.

## Stack
- Reasoning and reading: Muse Spark, provider chosen by environment variable. Verified live: Meta Model API (`muse-spark-1.3`, hosted). Implemented, verification pending a Baseten key: Muse Spark Open (meta-models/muse-spark-open-1026) via Baseten — the open-weight route a deployment inside an institution would use.
- Segmentation: SAM 3.1 hosted on the Meta Model API (`sam-3.1` via the Responses endpoint; MetaSAMSegmenter, selected with `SEGMENTER=meta`). A self-hosted Modal app (`modal_sam/`) is implemented but not deployed — the workspace cannot add the payment method its GPU functions require. Fallback: the deterministic Pillow heuristic segmenter (offline).
- Backend: FastAPI. Frontend: purpose-built reviewer UI (documents on the left, live agent trace with evidence links on the right), using whatever you can build fastest. No dashboard-as-product.
- Repo: fresh public repo with clean history from 27 Oct. README states exactly what was built during the hackathon.

## Scope
In: three document types (NID, bank form, birth certificate); three discrepancy classes (name variants, Bangla/English digits and dates, swapped digits); one reviewer UI; one evaluation chart.
Out: face or photo matching, real NID formats, any real data, auth, database, anything beyond the demo path.

## Ethics and rules checklist
- Synthetic data only. Watermark every generated document SPECIMEN and do not imitate real security features.
- No bank code, data, templates or internal material. Build from scratch for the "new work only" rule. Confirm you are comfortable with your employer on this.
- Public repo; demo and README identify only what was built during the event.
- Output is decision support for a human reviewer, never an automated accusation or decision.
- Transliteration-aware matching aims to reduce false rejections, but is only validated on the synthetic set. Say so.

## Risks and mitigations
- SAM 3.1 access refused or Modal credits missed → request all access tonight; ask in #questions; fall back to Meta Model API if billing works.
- Baseten credits/key not granted (reviewed, not guaranteed) → no longer on the critical path: the Meta Model API route is verified live and carries the demo and evaluation. The open-weight route's verification, and any open-weight-bonus claim, wait on the key; do not claim Baseten results before it lands.
- Tool calling flaky on Muse Spark Open → fixed step sequence with model decisions.
- Cold starts break the live demo → pre-warm endpoints; cache a full run; keep a recorded fallback.
- Scope creep → feature freeze Monday noon.
- Evaluation not finished → generator first (Wednesday); eval run Saturday; ablations Sunday.

## Schedule (Dhaka time)
US clocks change on 1 Nov: after that, 9 PM ET is 08:00 Dhaka on 5 Nov. Aim to submit well before.
- Tue 27 (evening): claim Meta $150 credit form (claim regardless of the card issue); request Baseten, Modal and Hugging Face SAM 3.1 access; create repo; first API calls; ask in #questions about SAM self-hosting and tool calling; post in #intros.
- Wed 28: synthetic generator v1 (three templates, watermark, Bangla/English text, degradations); SAM concept segmentation on samples; Muse Spark Open reading regions. Optional: Agents 102 session at 10 PM.
- Thu 29: normalization layer (digits, dates, name variants) and deterministic comparator with tests; perturbation-based uncertainty v1.
- Fri 30 (full day): agent loop with zoom and mask-and-reread tools; streaming trace; UI skeleton.
- Sat 31 (full day): UI evidence view with cross-document links; finish all synthetic sets; first evaluation run.
- Sun 1 Nov: ablations, fixes, buffer, office-hours questions.
- Mon 2 Nov: feature freeze at noon; pre-warm and cache; final demo script; record several takes; README.
- Tue 3 Nov: submission package; submit this evening if possible; check repo is public, video link works, team listed.
- Wed 4 Nov: spare day only.

Meta office hours run daily 10–11 AM ET (evening in Dhaka); use them for any blocker.

## Three-minute demo script
- 0:00–0:15 A genuine applicant rejected because her name is spelled differently on two documents.
- 0:15–0:35 What DocTrust is; open weights mean documents can stay inside the institution.
- 0:35–1:50 Live fraud set: SAM segments regions, the agent reads, finds an uncertain field under a stamp, masks the stamp, re-reads, and flags a one-digit DOB discrepancy and a mismatched name with evidence pinned on both documents.
- 1:50–2:20 A genuine set with name and digit variants passes in seconds.
- 2:20–2:45 Evaluation chart: exact-match baseline vs full agent on the synthetic set, stated as small-sample.
- 2:45–3:00 What was built during the hackathon, and who benefits.

## Claims discipline
- Say: "on a small synthetic set," "reduces false flags in our tests," "decision support for reviewers."
- Avoid: "detects fraud," "solves KYC," real-world accuracy claims, or unsourced scale statistics.

## Submission checklist
- Public repo with README describing what was built during the hackathon
- Three-minute demo video, link tested
- Evaluation results and limitations stated
- All contributors listed on the submission page
- Submitted before the deadline, not on it
