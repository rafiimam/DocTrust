"""The gate test: can Muse Spark actually read Bangla documents?

Everything in DocTrust depends on this. Generate a sample set first:

    python -m generator.generate --out data/gate_test --variant clean

then run it with an API key for the chosen provider in the environment:

    GATE_READER=meta    MODEL_API_KEY=...   python scripts/test_bangla_read.py data/gate_test
    GATE_READER=baseten BASETEN_API_KEY=... python scripts/test_bangla_read.py data/gate_test

GATE_READER selects the provider (default: meta — the Meta Model API;
baseten — Muse Spark Open hosted on Baseten). It reads four fields
from the synthetic NID — including the Bangla-digit ID number — and
prints what the model returned next to the ground truth. Judge it
harshly: this is the go/no-go check for the whole architecture.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.providers import BasetenReader, MetaReader  # noqa: E402

FIELDS = ["name", "dob", "id_number", "father_name"]

_PROVIDERS = {
    "meta": ("Meta Model API", MetaReader, "MODEL_API_KEY"),
    "baseten": ("Baseten", BasetenReader, "BASETEN_API_KEY"),
}


def _make_reader():
    which = os.environ.get("GATE_READER", "meta").strip().lower()
    if which not in _PROVIDERS:
        raise SystemExit(
            f"Unknown GATE_READER={which!r}; use 'meta' or 'baseten'.")
    label, cls, key_env = _PROVIDERS[which]
    if not os.environ.get(key_env):
        raise SystemExit(
            f"{key_env} is not set. Export the {label} API key first, "
            f"e.g. {key_env}=... python scripts/test_bangla_read.py")
    return label, cls()


def main() -> None:
    sample_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/gate_test")
    truth = json.loads((sample_dir / "ground_truth.json").read_text())
    expected = truth["documents"]["nid"]
    provider, reader = _make_reader()
    image = str(sample_dir / "nid.png")
    print(f"provider: {provider}\nmodel: {reader.model}\nimage: {image}\n")
    for field in FIELDS:
        got = reader.read_field(image, "nid", field, "original")
        print(f"{field:12s} expected={expected.get(field)!r}\n"
              f"{'':12s} got     ={got!r}\n")


if __name__ == "__main__":
    main()
