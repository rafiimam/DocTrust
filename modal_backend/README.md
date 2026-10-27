# DocTrust backend on Modal — deploy steps (owner only)

`backend_app.py` wraps the FastAPI backend (`backend/app/main.py`) as a
scale-to-zero Modal web endpoint, giving the GitHub Pages demo's
**Upload (judge mode)** a live backend. Costs nothing while idle.

Run every command below **from the repository root** (the image build
references `backend/` and `generator/` by relative path).

## 1. Install and log in (once)

```bash
pip install modal
modal setup            # log in; workspace: rafiimam96
```

## 2. Create the Baseten secret (once the Baseten key exists)

The app reads the key from a Modal secret named `baseten-secret`. Do
not put the key in the repo, in chat, or in the demo page.

```bash
modal secret create baseten-secret BASETEN_API_KEY=<your-baseten-key>
```

Until this secret exists, **remove the `secrets=[...]` line** in
`backend_app.py` before deploying — the backend will run fine, but
review jobs will end in the honest `reader_not_configured` state (no
reads are faked) until the secret is created and the app redeployed.

## 3. Deploy

```bash
modal deploy modal_backend/backend_app.py
```

Modal prints the web endpoint URL, shaped like
`https://rafiimam96--doctrust-backend-fastapi-app.modal.run`.
That URL is the backend for judge mode.

## 4. Smoke test

```bash
BASE=<paste the endpoint URL>

curl $BASE/health
# -> {"status":"ok","service":"doctrust"}

curl $BASE/api/case-pack/discrepancy -o /tmp/pack.zip
unzip -o /tmp/pack.zip -d /tmp/pack

curl -X POST $BASE/api/review \
  -F nid=@/tmp/pack/nid.png \
  -F birth_certificate=@/tmp/pack/birth_certificate.png \
  -F bank_form=@/tmp/pack/bank_form.png
# -> {"job_id": "...", "state": "queued", "reader_configured": true, ...}

curl $BASE/api/review/<job_id>          # poll until state = done
curl -N $BASE/api/review/<job_id>/events   # the live SSE trace
```

Expected with the Baseten secret in place: `reader_configured: true`
and a final verdict (`DISCREPANCY` for the discrepancy pack). Without
the secret: jobs end as `reader_not_configured` with preprocessing and
segmentation evidence only — that is the designed behaviour, not an
error.

## 5. Point the demo at it

Open https://rafiimam.github.io/DocTrust/demo/, switch to **Upload
(judge mode)**, paste the endpoint URL into **Backend URL**, and it is
remembered (localStorage) on that browser.

## Optional: SAM 3.1 segmenter

Judge mode uses the Pillow fallback segmenter by default. To use the
self-hosted SAM 3.1 endpoint instead (see `modal_sam/`), set the
`SAM_MODAL_ENDPOINT` environment variable for this Modal app to the
`doctrust-sam31` endpoint URL and redeploy.
