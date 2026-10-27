# Reviewer UI

Purpose-built reviewer interface: the document set on the left, the agent's
live cross-examination trace with evidence links on the right. Not a dashboard.

## Live demo (GitHub Pages)

A self-contained demo of this interface lives in
[../docs/demo/](../docs/demo/) and is served by GitHub Pages from the
`main` branch `/docs` folder:

**https://rafiimam.github.io/DocTrust/demo/**

It replays cached agent runs on synthetic, SPECIMEN-marked document sets —
a discrepancy hidden under a stamp, a genuine transliteration/digit
variation, and a degraded capture that ends in "Unreadable, request
recapture". No model is called from the page; the banner on the page says
so. The live system it mirrors is the FastAPI backend in `../backend/`
(documents left, agent trace right, verdicts with evidence), driven by
Muse Spark Open via Baseten and SAM 3.1 on Modal.
