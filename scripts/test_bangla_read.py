"""The gate test: can Muse Spark Open actually read Bangla documents?

Everything in DocTrust depends on this. Generate a sample set first:

    python -m generator.generate --out data/gate_test --variant clean

then, with a Baseten API key in the environment:

    BASETEN_API_KEY=... python scripts/test_bangla_read.py data/gate_test

It reads four fields from the synthetic NID — including the Bangla-digit
ID number — and prints what the model returned next to the ground truth.
Judge it harshly: this is the go/no-go check for the whole architecture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.providers import BasetenReader  # noqa: E402

FIELDS = ["name", "dob", "id_number", "father_name"]


def main() -> None:
    sample_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/gate_test")
    truth = json.loads((sample_dir / "ground_truth.json").read_text())
    expected = truth["documents"]["nid"]
    reader = BasetenReader()
    image = str(sample_dir / "nid.png")
    print(f"model: meta-models/muse-spark-open-1026 via Baseten\nimage: {image}\n")
    for field in FIELDS:
        got = reader.read_field(image, "nid", field, "original")
        print(f"{field:12s} expected={expected.get(field)!r}\n"
              f"{'':12s} got     ={got!r}\n")


if __name__ == "__main__":
    main()
