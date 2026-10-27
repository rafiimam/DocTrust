"""DocTrust judge-mode backend, hosted on Modal.

Wraps the FastAPI app in backend/app/main.py as a scale-to-zero Modal
web endpoint, so the GitHub Pages demo's Upload (judge) mode has a live
backend a judge can run against:

    GET  /health
    POST /api/review                      upload 3 synthetic documents
    GET  /api/review/{job_id}/events      SSE trace stream
    GET  /api/review/{job_id}             final result JSON
    GET  /api/case-pack/{variant}         downloadable synthetic set (ZIP)

Configuration (all server-side; nothing secret lives in this repo):
- The reader API key comes from a Modal secret attached below. The
  default is the Meta Model API: secret "meta-secret" (key
  MODEL_API_KEY), with JUDGE_READER defaulting to "meta" (model from
  META_MODEL, default muse-spark-1.3 — see backend/app/providers.py).
- IMPORTANT: Modal fails the deploy/function if a listed secret does
  not exist, so exactly ONE secret is listed here. Create the secret
  before deploying (see README), or remove the `secrets=[...]` line to
  deploy without a reader — the app still serves, but review jobs end
  in the honest "reader_not_configured" state (backend/app/judge.py).
- Baseten instead of Meta: two one-line changes — point the secrets
  line at "baseten-secret" (key BASETEN_API_KEY) and change the
  JUDGE_READER default below to "baseten".
- To also use SAM 3.1 on Modal for the masked investigation view, set
  SAM_MODAL_ENDPOINT to the doctrust-sam31 endpoint URL (see
  modal_sam/). Until then the deterministic Pillow fallback segmenter
  is used, exactly as in local runs.

Deploy and smoke-test steps: modal_backend/README.md.
"""

from __future__ import annotations

import os

import modal

APP_NAME = "doctrust-backend"

app = modal.App(APP_NAME)

# The container mirrors the repository layout (/root/repo/backend,
# /root/repo/generator) because backend/app/main.py locates the
# generator relative to the repo root, and tests/imports assume the
# same shape.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements("backend/requirements.txt")
    .add_local_dir("backend", remote_path="/root/repo/backend")
    .add_local_dir("generator", remote_path="/root/repo/generator")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("meta-secret")],
    scaledown_window=300,   # scale to zero after ~5 idle minutes
    timeout=900,            # a review job may run several minutes
)
@modal.asgi_app()
def fastapi_app():
    # Env must be set before the app resolves its reader (resolution is
    # per request in backend/app/judge.py, but set defaults up front so
    # the intent is in exactly one place).
    os.environ.setdefault("JUDGE_READER", "meta")
    os.environ.setdefault("PYTHONPATH", "/root/repo:/root/repo/backend")

    import sys

    for path in ("/root/repo/backend", "/root/repo"):
        if path not in sys.path:
            sys.path.insert(0, path)

    from app.main import app as web_app

    return web_app
