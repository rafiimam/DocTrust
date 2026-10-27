# SAM 3.1 on Modal — deployment and smoke test

Status: **the hosted route is currently used; this app is the
self-host path.** The deployed backend segments with SAM 3.1 hosted
on the Meta Model API (`MetaSAMSegmenter`, `SEGMENTER=meta`), so this
Modal app is not deployed at present — the owner's Modal workspace
cannot add the payment method its GPU functions require. The code is
written and unit-tested offline, and the steps below remain the
deployment and smoke-test path for a workspace that can run GPUs;
they need Rafi's own Hugging Face token and Modal login — nobody
else can (or should) do these steps.

## What this is

`sam_app.py` is a Modal app (`doctrust-sam31`) serving SAM 3.1 image
segmentation: one GPU function (L4, scales to zero) with a POST
endpoint taking `{"image_base64", "prompt"}` and returning
`{"boxes", "scores", "mask_base64"}`. The backend reaches it through
`ModalSegmenter` in `backend/app/segmenter.py` when `SEGMENTER=modal`
and `SAM_MODAL_ENDPOINT` is set. While it is not deployed, the agent
uses the Meta-hosted SAM segmenter or the deterministic Pillow
fallback masker, and reviews work either way — segmentation failing
never fails a review.

## Steps (run on your Mac, from the repo root)

1. **Install the Modal CLI and log in** (workspace `rafiimam96`):
   ```bash
   pip install modal
   modal setup
   ```
2. **Create a Hugging Face read token.** Your account already has
   access to the gated SAM repos (granted 27 Oct 2026).
   Go to https://huggingface.co/settings/tokens and create a token
   with **Read** permission. Keep it out of chat, email and git.
3. **Store the token as a Modal secret** (the app expects exactly this
   secret name and variable):
   ```bash
   modal secret create huggingface-secret HF_TOKEN=hf_your_token_here
   ```
4. **Deploy:**
   ```bash
   modal deploy modal_sam/sam_app.py
   ```
   The first call downloads the gated `facebook/sam3.1` weights into a
   Modal Volume (`doctrust-sam31-weights`), so the first request is
   slow (minutes, not seconds). Copy the endpoint URL Modal prints.
5. **Point the backend at it:**
   ```bash
   export SAM_MODAL_ENDPOINT="<the URL Modal printed>"
   ```
6. **Smoke test — one cheap image.** Generate one synthetic set if you
   don't have one handy, then send just the NID page:
   ```bash
   cd ~/workspace/doctrust   # or wherever your local copy lives
   python -m generator.generate --out /tmp/doctrust_sample --variant clean
   python - <<'PY'
   import base64, json, urllib.request
   img = base64.b64encode(open("/tmp/doctrust_sample/nid.png", "rb").read()).decode()
   req = urllib.request.Request(
       "<the URL Modal printed>",
       data=json.dumps({"image_base64": img, "prompt": "stamp"}).encode(),
       headers={"Content-Type": "application/json"})
   print(urllib.request.urlopen(req, timeout=600).read().decode()[:500])
   PY
   ```
   A healthy reply is JSON with `boxes`, `scores`, and a `mask_base64`
   (possibly with empty boxes if no stamp is found on the clean sample —
   that is still a pass; an HTTP error or timeout is not).

## Things to check if the smoke test fails

- **403 / gated-repo error downloading weights** → the token in the
  `huggingface-secret` isn't a read token for the account that was
  granted SAM access. Recreate both.
- **Checkpoint load error in the Modal logs** (`modal app logs
  doctrust-sam31`) → the app already falls back to the SAM builder's
  default download path once; if it still fails, note the exact error —
  the 3.1 checkpoint plumbing in `_load_model` / `_find_checkpoint` in
  `sam_app.py` is the SMOKE-TEST-marked section written defensively
  for exactly this.
- **Cold start feels endless on the very first call** → weights
  download + model load; retry once before debugging, and keep the
  function warm during the demo (scaledown window is 120s).

## Cost discipline

- L4 GPU, image segmentation only (no video/multiplex tracking).
- Scale-to-zero: no calls, no GPU cost. Volume storage for the weights
  is the only standing charge, and it is small.
- Do not run the ~40-set evaluation through this endpoint until the
  hackathon credits have actually landed in the workspace.
