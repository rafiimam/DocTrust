"""SAM 3.1 image segmentation, self-hosted on Modal.

One scale-to-zero GPU function exposing a single HTTP endpoint:

    POST {"image_base64": "...", "prompt": "stamp"}
      -> {"boxes": [[x1, y1, x2, y2], ...],   # pixel coords, xyxy
          "scores": [0.93, ...],
          "mask_base64": "<PNG, white = union of all instance masks>",
          "prompt": "stamp"}

The DocTrust backend calls this through backend/app/segmenter.py's
ModalSegmenter with SAM_MODAL_ENDPOINT set to this endpoint's URL.

Design notes
- Image segmentation only (no video / no multiplex tracking), so a
  modest GPU (L4) is enough and the function scales to zero when idle.
- Weights come from the gated Hugging Face repo facebook/sam3.1 and are
  downloaded once into a persistent Modal Volume using an HF_TOKEN
  secret; containers never re-download on a warm start.
- The SAM 3 calls below follow the public facebookresearch/sam3
  examples (sam3.model_builder.build_sam3_image_model +
  Sam3Processor.set_image / set_text_prompt). The two places where the
  3.1 checkpoint plumbing could not be verified offline are marked
  SMOKE TEST and coded with a fallback; see README.md.
"""

from __future__ import annotations

import base64
import io
import os

import modal

APP_NAME = "doctrust-sam31"
HF_REPO = "facebook/sam3.1"
MODEL_DIR = "/models/sam3.1"
GPU = "L4"  # modest: single-image segmentation, no video tracking

app = modal.App(APP_NAME)
weights_volume = modal.Volume.from_name("doctrust-sam31-weights",
                                        create_if_missing=True)

# ---------------------------------------------------------------------------
# Image: PyTorch with CUDA + the SAM 3 code from GitHub.
# ---------------------------------------------------------------------------
image = (
    modal.Image.from_registry("nvidia/cuda:12.6.0-devel-ubuntu22.04",
                              add_python="3.12")
    .apt_install("git")
    .run_commands(
        # Torch build matching the SAM 3 README (cu126 wheels).
        "pip install torch==2.7.0 torchvision --index-url "
        "https://download.pytorch.org/whl/cu126",
        "git clone https://github.com/facebookresearch/sam3.git /opt/sam3",
        "pip install -e /opt/sam3",
        "pip install fastapi huggingface_hub pillow",
    )
)

_model = None
_processor = None


def _find_checkpoint(model_dir: str) -> str | None:
    """Locate the SAM 3.1 checkpoint inside the downloaded repo snapshot."""
    candidates = []
    for root, _dirs, files in os.walk(model_dir):
        for name in files:
            if name.endswith((".pt", ".safetensors")):
                candidates.append(os.path.join(root, name))
    if not candidates:
        return None
    # SMOKE TEST: the 3.1 repo's documented checkpoint is the multiplex
    # .pt; prefer it. If the image builder rejects it (see fallback in
    # _load_model), this preference is the first thing to revisit.
    candidates.sort(key=lambda p: ("multiplex" not in p, len(p)))
    return candidates[0]


def _download_weights() -> str:
    """Download the gated weights into the Volume once; return the path."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    existing = _find_checkpoint(MODEL_DIR)
    if existing:
        return existing
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=HF_REPO, local_dir=MODEL_DIR,
                      token=os.environ["HF_TOKEN"])
    weights_volume.commit()
    ckpt = _find_checkpoint(MODEL_DIR)
    if ckpt is None:
        raise RuntimeError(f"No checkpoint file found under {MODEL_DIR}")
    return ckpt


def _load_model():
    """Load SAM 3.1 (image model) once per warm container."""
    global _model, _processor
    if _processor is not None:
        return _processor
    import torch
    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model

    ckpt = _download_weights()
    try:
        _model = build_sam3_image_model(checkpoint_path=ckpt,
                                        load_from_HF=False,
                                        device="cuda", eval_mode=True)
    except Exception:
        # SMOKE TEST fallback: if the 3.1 multiplex checkpoint cannot be
        # loaded by the image builder directly, fall back to the
        # builder's default HF download path and note it in the logs.
        print("Direct 3.1 checkpoint load failed; using builder default")
        _model = build_sam3_image_model(device="cuda", eval_mode=True)
    try:
        _processor = Sam3Processor(_model)
    except TypeError:  # some versions want the device explicitly
        _processor = Sam3Processor(_model, device="cuda")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return _processor


@app.function(image=image, gpu=GPU,
              secrets=[modal.Secret.from_name("huggingface-secret")],
              volumes={"/models": weights_volume},
              scaledown_window=120, timeout=900)
@modal.fastapi_endpoint(method="POST", docs=True)
def segment(payload: dict) -> dict:
    """Segment one image with a text concept prompt."""
    import numpy as np
    import torch
    from PIL import Image

    image_b64 = payload.get("image_base64", "")
    prompt = payload.get("prompt", "")
    if not image_b64 or not prompt:
        return {"error": "image_base64 and prompt are required",
                "boxes": [], "scores": [], "mask_base64": None}

    pil_image = Image.open(io.BytesIO(base64.b64decode(image_b64)))
    pil_image = pil_image.convert("RGB")

    processor = _load_model()
    with torch.inference_mode():
        state = processor.set_image(pil_image)
        output = processor.set_text_prompt(state=state, prompt=prompt)

    masks = output["masks"].detach().cpu().numpy()
    boxes = output["boxes"].detach().cpu().numpy()
    scores = output["scores"].detach().cpu().numpy()
    if masks.ndim == 4:  # [N, 1, H, W] -> [N, H, W]
        masks = masks[:, 0]

    mask_b64 = None
    if len(masks):
        union = (masks.any(axis=0).astype(np.uint8) * 255)
        buf = io.BytesIO()
        Image.fromarray(union, mode="L").save(buf, format="PNG")
        mask_b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "prompt": prompt,
        "boxes": [[float(v) for v in box] for box in boxes],
        "scores": [float(s) for s in scores],
        "mask_base64": mask_b64,
    }
