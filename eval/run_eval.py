"""DocTrust evaluation runner — the ablation from eval/EVALUATION.md.

Builds a fixed-seed synthetic dataset from the generator and runs the
SAME sets through three configurations over the SAME reader:

1. exact-match baseline — one read per field; verdict CONSISTENT iff
   every shared field's raw string is identical across documents (no
   normalization at all); UNREADABLE if any shared field reads
   UNREADABLE/empty.
2. single-pass + normalization — the same single reads, then the
   deterministic normalize + comparator path (backend/app/comparator).
3. full agent — backend.app.agent.run_review (perturbation reads,
   disagreement-triggered investigation, same comparator).

Configurations 1 and 2 share one read pass by design: it is a paired
comparison — the identical reads are scored two ways, so any verdict
difference is attributable to normalization alone. The agent makes its
own reads. A reader factory supplies the reader per (set, phase), so
tests can script a fresh MockReader per phase while the CLI shares
one live reader (live readers are stateless).

Physically captured sets (EVALUATION.md's ~10 printed/displayed
SPECIMEN sets photographed with a phone) are ingested from a
directory of capture folders — one folder per set: the three document
photos plus a manifest.json declaring the expectation (genuine /
discrepancy / degraded) and the documents' canonical values, in the
same shape as the generator's ground truth. They run through the
same three configurations and the same metrics: a physical genuine
set counts in the headline genuine pool, and the batch is also
reported as its own category, split by expectation. See
eval/PHYSICAL_CAPTURE.md for how to capture a set. A capture folder
that is missing photos or has a malformed manifest is skipped with a
warning, never a crash.

Scoring is in COUNTS, exactly as EVALUATION.md prescribes. The runner
writes results incrementally (one JSON record per set, atomically
rewritten after each set completes) and supports --resume.

Usage (from the repo root):

    JUDGE_READER=meta MODEL_API_KEY=... \
        python -m eval.run_eval --out eval/results/results.json

The reader is chosen by environment exactly as in judge mode
(JUDGE_READER=meta|baseten|mock — see backend/app/judge.py); the
segmenter likewise (SEGMENTER / SAM_MODAL_ENDPOINT / Pillow fallback).
No reader configured -> the run refuses to start rather than invent
reads, unless JUDGE_READER=mock is set explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import agent, comparator, judge  # noqa: E402
from app.providers import Reader  # noqa: E402
from generator.generate import STAMP_STYLES, generate_set  # noqa: E402

DOC_TYPES = ("nid", "birth_certificate", "bank_form")
CATEGORIES = ("clean", "variation", "discrepancy", "degraded")
GENUINE_CATEGORIES = ("clean", "variation")
PHYSICAL_EXPECTATIONS = ("genuine", "discrepancy", "degraded")
_PHYSICAL_IMAGE_EXTS = (".png", ".jpg", ".jpeg")
CONFIGS = ("exact", "single", "agent")
CONFIG_LABELS = {
    "exact": "1. Exact-match",
    "single": "2. Single-pass + norm.",
    "agent": "3. Full agent",
}
DEFAULT_COUNTS = {"clean": 12, "variation": 10, "discrepancy": 10,
                  "degraded": 8}

# Route list prices for the cost estimate (USD per million tokens),
# used only when a reader actually reports usage. Overridable via
# EVAL_PRICE_INPUT_PER_MTOK / EVAL_PRICE_OUTPUT_PER_MTOK.
_DEFAULT_PRICES = (1.25, 4.25)

_STAMP_STYLE_CYCLE = sorted(STAMP_STYLES)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class SetSpec:
    set_id: str
    category: str
    variant: str
    seed: int
    stamp_style: str
    stamp_position: str


def build_dataset(counts: dict[str, int], seed_base: int = 7,
                  over_dob: int = 3) -> list[SetSpec]:
    """Deterministic set list: fixed category order, seeds seed_base+i,
    stamp styles cycled, the first `over_dob` discrepancy sets placing
    the stamp over the birth-certificate DOB."""
    specs: list[SetSpec] = []
    index = 0
    for category in CATEGORIES:
        for i in range(counts.get(category, 0)):
            position = "margin"
            if category == "discrepancy" and i < over_dob:
                position = "over_dob"
            specs.append(SetSpec(
                set_id=f"{category}-{i + 1:02d}",
                category=category,
                variant=category,
                seed=seed_base + index,
                stamp_style=_STAMP_STYLE_CYCLE[index % len(_STAMP_STYLE_CYCLE)],
                stamp_position=position,
            ))
            index += 1
    return specs


def generate_dataset(specs: list[SetSpec], data_dir: Path) -> dict[str, dict]:
    """Render every set (idempotent) and return {set_id: ground_truth}."""
    truths: dict[str, dict] = {}
    for spec in specs:
        out = data_dir / spec.set_id
        truth = generate_set(out, spec.variant, spec.seed,
                             stamp_style=spec.stamp_style,
                             stamp_position=spec.stamp_position)
        truths[spec.set_id] = truth
    return truths


def expected_from_truth(truth: dict) -> dict:
    """Expected verdict + injected fields, derived from the generator's
    ground truth itself via the comparator — never re-implemented."""
    result = comparator.compare(truth["documents"])
    return {
        "verdict": result.verdict,
        "injected_fields": [f.field for f in result.findings
                            if f.status == "mismatch"],
        "canonical": {f.field: f.canonical for f in result.findings},
    }


# ---------------------------------------------------------------------------
# Physically captured sets
# ---------------------------------------------------------------------------

@dataclass
class PhysicalSpec:
    """One physically captured set: a folder of phone photos plus a
    manifest. `documents` mirrors ground_truth.json's "documents"
    shape exactly, so expectations derive via the same comparator."""
    set_id: str
    expectation: str
    folder: Path
    images: dict[str, str]
    documents: dict
    injected_field: str | None = None
    conditions: str | None = None
    category: str = "physical"


def _physical_images(folder: Path) -> dict[str, str] | None:
    """{doc_type: image path} if all three document photos exist
    (.png/.jpg/.jpeg), else None."""
    images: dict[str, str] = {}
    for doc in DOC_TYPES:
        found = None
        for ext in _PHYSICAL_IMAGE_EXTS:
            candidate = folder / f"{doc}{ext}"
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            return None
        images[doc] = str(found)
    return images


def _validate_manifest(manifest) -> tuple[dict | None, str | None]:
    """Validate one capture manifest. Returns (fields, None) with
    fields = {expectation, documents, injected_field, conditions},
    or (None, reason) when the manifest is malformed."""
    if not isinstance(manifest, dict):
        return None, "manifest.json is not a JSON object"
    expectation = manifest.get("expectation")
    if expectation not in PHYSICAL_EXPECTATIONS:
        return None, (f"expectation must be one of "
                      f"{'/'.join(PHYSICAL_EXPECTATIONS)}, "
                      f"got {expectation!r}")
    documents = manifest.get("documents")
    if not isinstance(documents, dict):
        return None, "manifest has no 'documents' object"
    for doc in DOC_TYPES:
        fields = documents.get(doc)
        if not isinstance(fields, dict):
            return None, f"documents.{doc} is missing or not an object"
        expected_fields = set(agent.FIELDS_BY_DOC[doc])
        if set(fields) != expected_fields:
            return None, (f"documents.{doc} must carry exactly the "
                          f"fields {sorted(expected_fields)}, got "
                          f"{sorted(fields)}")
        if not all(isinstance(v, str) for v in fields.values()):
            return None, f"documents.{doc} values must all be strings"
    injected = manifest.get("injected_field")
    if expectation == "discrepancy":
        if not isinstance(injected, str) or not injected:
            return None, ("expectation 'discrepancy' requires an "
                          "'injected_field' naming the differing field")
        if injected not in comparator.SHARED_FIELDS:
            return None, (f"injected_field {injected!r} is not a shared "
                          f"field {list(comparator.SHARED_FIELDS)}")
    elif injected is not None:
        return None, ("'injected_field' is only meaningful when "
                      "expectation is 'discrepancy'")
    # The manifest's documents must actually encode the declared
    # expectation — derived via the same comparator as the synthetic
    # ground truth, so a mislabelled capture is caught here, not
    # scored as a mysterious failure later.
    expected = expected_from_truth({"documents": documents})
    if expectation in ("genuine", "degraded"):
        if expected["verdict"] != "CONSISTENT":
            return None, (f"expectation is {expectation!r} but the "
                          f"manifest documents disagree "
                          f"({expected['injected_fields']})")
    else:
        if expected["verdict"] != "DISCREPANCY":
            return None, ("expectation is 'discrepancy' but the "
                          "manifest documents agree after "
                          "normalization — no field differs")
        if injected not in expected["injected_fields"]:
            return None, (f"injected_field {injected!r} is not a field "
                          f"the manifest documents disagree on "
                          f"({expected['injected_fields']})")
    conditions = manifest.get("conditions")
    return {
        "expectation": expectation,
        "documents": documents,
        "injected_field": injected if expectation == "discrepancy" else None,
        "conditions": conditions if isinstance(conditions, str) else None,
    }, None


def discover_physical_sets(physical_dir: Path) -> tuple[list[PhysicalSpec], list[str]]:
    """Discover capture sets under `physical_dir`: each immediate
    subfolder holding the three document photos and a manifest.json
    is one set (id `physical-<folder>`). Folders that are missing
    photos or whose manifest is malformed are skipped with a warning
    printed to stderr (and returned); discovery never raises. A
    missing directory simply yields no sets."""
    specs: list[PhysicalSpec] = []
    warnings: list[str] = []

    def warn(message: str) -> None:
        warnings.append(message)
        print(f"warning: {message}", file=sys.stderr)

    if not physical_dir.is_dir():
        return specs, warnings
    for folder in sorted(p for p in physical_dir.iterdir() if p.is_dir()):
        label = f"physical set folder {folder.name!r}"
        images = _physical_images(folder)
        if images is None:
            warn(f"skipping {label}: missing document photo(s); each "
                 f"set needs nid, birth_certificate and bank_form "
                 f"images ({'/'.join(_PHYSICAL_IMAGE_EXTS)})")
            continue
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            warn(f"skipping {label}: no manifest.json")
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (ValueError, OSError) as exc:
            warn(f"skipping {label}: manifest.json unreadable ({exc})")
            continue
        fields, reason = _validate_manifest(manifest)
        if fields is None:
            warn(f"skipping {label}: malformed manifest — {reason}")
            continue
        specs.append(PhysicalSpec(
            set_id=f"physical-{folder.name}",
            expectation=fields["expectation"],
            folder=folder,
            images=images,
            documents=fields["documents"],
            injected_field=fields["injected_field"],
            conditions=fields["conditions"],
        ))
    return specs, warnings


# ---------------------------------------------------------------------------
# Reader plumbing
# ---------------------------------------------------------------------------

class CountingReader:
    """Wraps a reader: counts calls and accumulates token usage when
    the wrapped reader reports it (a `last_usage` dict attribute set
    after each call, with input/prompt and output/completion token
    keys). Current live readers report no usage -> tokens stay None
    and the run reports reads only."""

    def __init__(self, inner: Reader):
        self.inner = inner
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.usage_seen = False

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        self.calls += 1
        value = self.inner.read_field(image_path, doc_type, field,
                                      perturbation)
        usage = getattr(self.inner, "last_usage", None)
        if isinstance(usage, dict):
            self.usage_seen = True
            self.input_tokens += int(
                usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            self.output_tokens += int(
                usage.get("output_tokens",
                          usage.get("completion_tokens", 0)) or 0)
        return value


def _cost_usd(input_tokens: int, output_tokens: int) -> float:
    pin = float(os.environ.get("EVAL_PRICE_INPUT_PER_MTOK",
                               _DEFAULT_PRICES[0]))
    pout = float(os.environ.get("EVAL_PRICE_OUTPUT_PER_MTOK",
                                _DEFAULT_PRICES[1]))
    return input_tokens / 1e6 * pin + output_tokens / 1e6 * pout


def _is_unreadable(value) -> bool:
    return value is None or str(value).strip() in ("", "UNREADABLE")


# ---------------------------------------------------------------------------
# The three configurations
# ---------------------------------------------------------------------------

def _single_pass_reads(reader: Reader, images: dict[str, str]
                       ) -> dict[str, dict[str, str]]:
    """One read per field at the 'original' view — the shared input
    of configurations 1 and 2."""
    docs: dict[str, dict[str, str]] = {}
    for doc_type in DOC_TYPES:
        docs[doc_type] = {}
        for field in agent.FIELDS_BY_DOC[doc_type]:
            docs[doc_type][field] = reader.read_field(
                images[doc_type], doc_type, field, "original")
    return docs


def exact_match_verdict(docs: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    """Configuration 1: raw-string comparison, no normalization."""
    flagged: list[str] = []
    for field in comparator.SHARED_FIELDS:
        values = [docs[d][field] for d in DOC_TYPES if field in docs.get(d, {})]
        if len(values) < 2:
            continue
        if any(_is_unreadable(v) for v in values):
            return "UNREADABLE", flagged
        if len(set(values)) > 1:
            flagged.append(field)
    return ("DISCREPANCY" if flagged else "CONSISTENT"), flagged


def single_pass_verdict(docs: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    """Configuration 2: the same reads through normalize + comparator.
    The UNREADABLE sentinel is mapped to None first, mirroring the
    agent loop's majority semantics, so an unreadable field is a
    recapture, never a name mismatch."""
    cleaned = {
        doc: {f: (None if _is_unreadable(v) else v) for f, v in fields.items()}
        for doc, fields in docs.items()
    }
    result = comparator.compare(cleaned)
    flagged = [f.field for f in result.findings if f.status == "mismatch"]
    return result.verdict, flagged


def _usage_cells(reader: CountingReader, latency: float) -> dict:
    return {
        "reads": reader.calls,
        "latency_s": round(latency, 3),
        "input_tokens": reader.input_tokens if reader.usage_seen else None,
        "output_tokens": reader.output_tokens if reader.usage_seen else None,
        "cost_usd": round(_cost_usd(reader.input_tokens,
                                     reader.output_tokens), 6)
                    if reader.usage_seen else None,
    }


def _run_configs(images: dict[str, str], truth: dict, spec,
                 reader_factory, segmenter) -> dict:
    """Run all three configurations over one set's images and return
    the per-configuration results. Shared by synthetic and physically
    captured sets — the configurations do not know which they are
    scoring."""
    configs: dict = {}

    # Configurations 1 + 2: one shared read pass, scored two ways.
    single_reader = CountingReader(reader_factory(spec, "single", truth))
    start = time.perf_counter()
    docs = _single_pass_reads(single_reader, images)
    single_latency = time.perf_counter() - start
    for name, fn in (("exact", exact_match_verdict),
                     ("single", single_pass_verdict)):
        verdict, flagged = fn(docs)
        configs[name] = {
            "verdict": verdict,
            "flagged_fields": flagged,
            "documents": docs,
            **_usage_cells(single_reader, single_latency),
        }

    # Configuration 3: the full agent, its own reader.
    agent_reader = CountingReader(reader_factory(spec, "agent", truth))
    start = time.perf_counter()
    outcome = agent.run_review(agent_reader, images, segmenter=segmenter)
    agent_latency = time.perf_counter() - start
    flagged = [f["field"] for f in outcome.findings
               if f.get("status") == "mismatch"]
    configs["agent"] = {
        "verdict": outcome.verdict,
        "flagged_fields": flagged,
        "documents": outcome.documents,
        "uncertain_fields": [f"{fr.doc_type}.{fr.field}"
                             for fr in outcome.field_reads if fr.uncertain],
        **_usage_cells(agent_reader, agent_latency),
    }
    return configs


def evaluate_set(spec: SetSpec, truth: dict, expected: dict,
                 data_dir: Path, reader_factory, segmenter) -> dict:
    """Run all three configurations over one synthetic set. Never
    raises for reader errors — the caller records them as set
    errors."""
    images = {doc: str(data_dir / spec.set_id / f"{doc}.png")
              for doc in DOC_TYPES}
    record: dict = {
        "set_id": spec.set_id,
        "category": spec.category,
        "variant": spec.variant,
        "seed": spec.seed,
        "stamp_style": spec.stamp_style,
        "stamp_position": spec.stamp_position,
        "expected_verdict": expected["verdict"],
        "injected_fields": expected["injected_fields"],
        "configs": {},
    }
    record["configs"] = _run_configs(images, truth, spec,
                                     reader_factory, segmenter)
    record["status"] = "ok"
    return record


def evaluate_physical_set(spec: PhysicalSpec, reader_factory,
                          segmenter) -> dict:
    """Run all three configurations over one physically captured set.
    Expectations derive from the manifest's documents via the same
    comparator as synthetic ground truth; for a discrepancy set the
    manifest's declared injected field is the field that must be
    flagged for the catch to count."""
    truth = {"variant": "physical", "documents": spec.documents}
    expected = expected_from_truth(truth)
    if spec.injected_field is not None:
        expected["injected_fields"] = [spec.injected_field]
    record: dict = {
        "set_id": spec.set_id,
        "category": "physical",
        "expectation": spec.expectation,
        "variant": "physical",
        "seed": None,
        "stamp_style": "capture",
        "stamp_position": "n/a",
        "conditions": spec.conditions,
        "expected_verdict": expected["verdict"],
        "injected_fields": expected["injected_fields"],
        "configs": {},
    }
    record["configs"] = _run_configs(spec.images, truth, spec,
                                     reader_factory, segmenter)
    record["status"] = "ok"
    return record


# ---------------------------------------------------------------------------
# Scoring (counts only, per EVALUATION.md)
# ---------------------------------------------------------------------------

def _blank_cells() -> dict:
    return {
        "genuine_n": 0, "false_flags": 0,
        "discrepancy_n": 0, "caught": 0, "silent_errors": 0,
        "degraded_n": 0, "recovered": 0, "recapture": 0,
        "degraded_false_flags": 0,
    }


def _scoring_category(record: dict) -> str:
    """The scoring pool a record belongs to. Synthetic sets score
    under their own category; a physical set scores under its
    declared expectation, with 'genuine' joining the genuine pool
    alongside the synthetic genuine categories."""
    if record["category"] == "physical":
        return "clean" if record["expectation"] == "genuine" \
            else record["expectation"]
    return record["category"]


def _score_record(cells: dict, record: dict, config: str) -> None:
    cfg = record["configs"][config]
    verdict = cfg["verdict"]
    category = _scoring_category(record)
    if category in GENUINE_CATEGORIES:
        cells["genuine_n"] += 1
        if verdict == "DISCREPANCY":
            cells["false_flags"] += 1
    elif category == "discrepancy":
        cells["discrepancy_n"] += 1
        if verdict == "CONSISTENT":
            cells["silent_errors"] += 1
        elif verdict == "DISCREPANCY" and any(
                f in cfg["flagged_fields"]
                for f in record["injected_fields"]):
            cells["caught"] += 1
    elif category == "degraded":
        cells["degraded_n"] += 1
        if verdict == "CONSISTENT":
            cells["recovered"] += 1
        elif verdict == "UNREADABLE":
            cells["recapture"] += 1
        elif verdict == "DISCREPANCY":
            cells["degraded_false_flags"] += 1


def _cells_for(records: list[dict], config: str) -> dict:
    """Score cells + read/latency/cost means for one configuration
    over one pool of completed records."""
    cells = _blank_cells()
    reads, latencies, costs = [], [], []
    for record in records:
        _score_record(cells, record, config)
        cfg = record["configs"][config]
        reads.append(cfg["reads"])
        latencies.append(cfg["latency_s"])
        if cfg.get("cost_usd") is not None:
            costs.append(cfg["cost_usd"])
    cells["reads_mean"] = round(sum(reads) / len(reads), 2) if reads else None
    cells["latency_mean_s"] = (round(sum(latencies) / len(latencies), 2)
                               if latencies else None)
    cells["cost_mean_usd"] = (round(sum(costs) / len(costs), 6)
                              if costs else None)
    return cells


def aggregate(records: list[dict]) -> dict:
    """Headline cells per config + the same split by category, plus
    the physically captured batch scored on its own (and split by
    expectation). Physical sets also enter the headline pools via
    their expectation (see _scoring_category). Only status == 'ok'
    records are scored; errored sets are counted separately and
    never enter a denominator."""
    done = [r for r in records if r.get("status") == "ok"]
    physical = [r for r in done if r["category"] == "physical"]
    summary: dict = {"sets_ok": len(done),
                     "sets_error": len(records) - len(done),
                     "physical_sets": len(physical),
                     "configs": {}, "by_category": {},
                     "physical": {"configs": {}, "by_expectation": {}}}
    for config in CONFIGS:
        summary["configs"][config] = _cells_for(done, config)
        summary["by_category"][config] = {
            c: _cells_for([r for r in done if r["category"] == c], config)
            for c in CATEGORIES
        }
        summary["physical"]["configs"][config] = _cells_for(physical, config)
        summary["physical"]["by_expectation"][config] = {
            exp: _cells_for([r for r in physical
                             if r["expectation"] == exp], config)
            for exp in PHYSICAL_EXPECTATIONS
        }
    return summary


# ---------------------------------------------------------------------------
# Markdown summary, in EVALUATION.md's table shapes
# ---------------------------------------------------------------------------

def _xn(x: int, n: int) -> str:
    return f"{x}/{n}" if n else "—"


def _metric_table(cells_by_config: dict) -> list[str]:
    """The headline metric rows for one pool of sets, in
    EVALUATION.md's table shape."""
    c = cells_by_config
    return [
        "| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |",
        "|---|---|---|---|",
        "| False flags on genuine sets (x/n) | "
        + " | ".join(_xn(c[k]["false_flags"], c[k]["genuine_n"])
                     for k in CONFIGS) + " |",
        "| Injected discrepancies caught (x/n) | "
        + " | ".join(_xn(c[k]["caught"], c[k]["discrepancy_n"])
                     for k in CONFIGS) + " |",
        "| **Silent errors — verdict \"Consistent\" while a "
        "discrepancy exists (count)** | "
        + " | ".join(f"**{c[k]['silent_errors']}**" for k in CONFIGS) + " |",
        "| Degraded sets: recovered / recapture requested (x/n) | "
        + " | ".join(
            f"{_xn(c[k]['recovered'], c[k]['degraded_n'])} / "
            f"{_xn(c[k]['recapture'], c[k]['degraded_n'])}"
            for k in CONFIGS) + " |",
        "| Reads per set (mean) | "
        + " | ".join(str(c[k]["reads_mean"]) for k in CONFIGS) + " |",
        "| Latency per set (mean, s) | "
        + " | ".join(str(c[k]["latency_mean_s"]) for k in CONFIGS) + " |",
        "| Cost per set (USD, at route prices) | "
        + " | ".join("—" if c[k]["cost_mean_usd"] is None
                     else f"{c[k]['cost_mean_usd']:.4f}"
                     for k in CONFIGS) + " |",
    ]


def _split_row(label: str, cells: dict, pool: str) -> str:
    """One row of a by-category / by-expectation split table.
    `pool` is the scoring pool the row covers: genuine, discrepancy
    or degraded."""
    if pool == "genuine":
        ff = _xn(cells["false_flags"], cells["genuine_n"])
    elif pool == "degraded":
        ff = _xn(cells["degraded_false_flags"], cells["degraded_n"])
    else:
        ff = "—"
    return (
        f"| {label} | {ff} | "
        f"{_xn(cells['caught'], cells['discrepancy_n'])} | "
        f"{cells['silent_errors']} | "
        f"{_xn(cells['recovered'], cells['degraded_n'])} / "
        f"{_xn(cells['recapture'], cells['degraded_n'])} |")


def render_markdown(summary: dict, meta: dict, records: list[dict]) -> str:
    lines = [
        "# DocTrust evaluation — run summary",
        "",
        f"- Date: {meta.get('started_at', 'pending')}",
        f"- Reader: {meta.get('reader', 'unknown')}",
        f"- Segmenter: {meta.get('segmenter', 'unknown')}",
        f"- Seed base: {meta.get('seed_base')} "
        f"(per-set seed = base + set index)",
        f"- Sets completed: {summary['sets_ok']} "
        f"(errors: {summary['sets_error']})",
    ]
    if meta.get("physical_sets"):
        lines.append(
            f"- Physically captured sets: {meta['physical_sets']} "
            f"(from {meta.get('physical_dir')})")
    lines += [
        "",
        "**Counts (x/n) throughout — never bare percentages.**",
        "",
    ]
    lines += _metric_table(summary["configs"])
    lines += [
        "",
        "### By category — full agent (configuration 3)",
        "",
        "| Category | False flags (x/n) | Discrepancies caught (x/n) "
        "| Silent errors | Recovered / recapture (x/n) |",
        "|---|---|---|---|---|",
    ]
    bc = summary["by_category"]["agent"]
    for category in CATEGORIES:
        pool = "genuine" if category in GENUINE_CATEGORIES else category
        lines.append(_split_row(category, bc[category], pool))
    if any(r["category"] == "physical" for r in records):
        lines += [
            "",
            "### Physically captured sets",
            "",
            "_The same three configurations over the physically "
            "captured sets only (see eval/PHYSICAL_CAPTURE.md). "
            "Physical genuine sets also count in the headline "
            "genuine pool above._",
            "",
        ]
        lines += _metric_table(summary["physical"]["configs"])
        lines += [
            "",
            "#### By expectation — full agent (configuration 3)",
            "",
            "| Expectation | False flags (x/n) | Discrepancies "
            "caught (x/n) | Silent errors | Recovered / recapture "
            "(x/n) |",
            "|---|---|---|---|---|",
        ]
        be = summary["physical"]["by_expectation"]["agent"]
        for expectation in PHYSICAL_EXPECTATIONS:
            lines.append(_split_row(expectation, be[expectation],
                                    expectation))
    failures = [
        r for r in records if r.get("status") == "ok" and any(
            r["configs"][k]["verdict"] != r["expected_verdict"]
            for k in CONFIGS)
    ]
    errors = [r for r in records if r.get("status") == "error"]
    lines += ["", "## Failure analysis", ""]
    if not failures and not errors:
        lines.append("- No failures recorded in this run.")
    for r in failures:
        wrong = [f"{CONFIG_LABELS[k]}: expected {r['expected_verdict']}, "
                 f"got {r['configs'][k]['verdict']}"
                 for k in CONFIGS
                 if r["configs"][k]["verdict"] != r["expected_verdict"]]
        if r["category"] == "physical":
            descriptor = (f"physical, expectation "
                          f"{r['expectation']}")
        else:
            descriptor = (f"{r['category']}, stamp "
                          f"{r['stamp_style']}/{r['stamp_position']}")
        lines.append(f"- Set {r['set_id']} ({descriptor}): "
                     + "; ".join(wrong))
    for r in errors:
        lines.append(f"- Set {r['set_id']} ({r['category']}): "
                     f"run error — {r.get('error', 'unknown')}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run orchestration: thread pool, incremental output, resume
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    records: list[dict]
    summary: dict
    meta: dict


def _load_records(out_path: Path) -> dict[str, dict]:
    if not out_path.exists():
        return {}
    try:
        data = json.loads(out_path.read_text())
    except (ValueError, OSError):
        return {}
    return {r["set_id"]: r for r in data.get("sets", [])
            if isinstance(r, dict) and "set_id" in r}


def _write_output(out_path: Path, meta: dict, records: dict[str, dict]) -> dict:
    ordered = [records[k] for k in sorted(records)]
    summary = aggregate(ordered)
    payload = {"meta": meta, "summary": summary, "sets": ordered}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(out_path)
    md_path = out_path.with_suffix(".md")
    md_path.write_text(render_markdown(summary, meta, ordered))
    return summary


def run_evaluation(*, counts: dict[str, int] | None = None,
                   seed_base: int = 7, over_dob: int = 3,
                   data_dir: Path, out_path: Path,
                   reader=None, reader_factory=None, segmenter=None,
                   workers: int = 4, resume: bool = False,
                   physical_dir: Path | None = None) -> RunResult:
    """Build the dataset and evaluate every set — the synthetic sets
    plus, when `physical_dir` is given, every physically captured set
    discovered there.

    reader_factory(spec, phase, truth) -> Reader, phase in
    {"single", "agent"}. Without a factory, `reader` is shared by all
    phases and sets (the CLI path: one stateless live reader).
    """
    counts = dict(counts or DEFAULT_COUNTS)
    specs = build_dataset(counts, seed_base=seed_base, over_dob=over_dob)
    truths = generate_dataset(specs, Path(data_dir))

    physical_specs: list[PhysicalSpec] = []
    if physical_dir is not None:
        physical_specs, _warnings = discover_physical_sets(
            Path(physical_dir))

    if reader_factory is None:
        if reader is None:
            raise ValueError("run_evaluation needs a reader or reader_factory")
        reader_factory = lambda spec, phase, truth: reader  # noqa: E731
    if segmenter is None:
        segmenter = judge.resolve_segmenter()

    meta = {
        "tool": "eval.run_eval",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "seed_base": seed_base,
        "counts": counts,
        "over_dob": over_dob,
        "workers": workers,
        "physical_dir": str(physical_dir) if physical_dir is not None
                        else None,
        "physical_sets": len(physical_specs),
        "reader": type(reader).__name__ if reader is not None
                  else "factory",
        "segmenter": type(segmenter).__name__,
    }

    records: dict[str, dict] = {}
    if resume:
        records = _load_records(Path(out_path))

    def _error_record(base: dict) -> dict:
        base.update({
            "status": "error",
            "error": traceback.format_exc(limit=3).strip().splitlines()[-1],
            "configs": {},
        })
        return base

    def work(spec: SetSpec) -> dict:
        try:
            return evaluate_set(spec, truths[spec.set_id],
                                expected_from_truth(truths[spec.set_id]),
                                Path(data_dir), reader_factory, segmenter)
        except Exception:
            return _error_record({
                "set_id": spec.set_id, "category": spec.category,
                "variant": spec.variant, "seed": spec.seed,
                "stamp_style": spec.stamp_style,
                "stamp_position": spec.stamp_position,
            })

    def work_physical(spec: PhysicalSpec) -> dict:
        try:
            return evaluate_physical_set(spec, reader_factory, segmenter)
        except Exception:
            return _error_record({
                "set_id": spec.set_id, "category": "physical",
                "expectation": spec.expectation, "variant": "physical",
                "seed": None, "stamp_style": "capture",
                "stamp_position": "n/a",
            })

    jobs = [lambda s=spec: work(s) for spec in specs
            if records.get(spec.set_id, {}).get("status") != "ok"]
    jobs += [lambda s=spec: work_physical(s) for spec in physical_specs
             if records.get(spec.set_id, {}).get("status") != "ok"]

    if workers and workers > 1 and len(jobs) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(job) for job in jobs]
            for fut in as_completed(futures):
                record = fut.result()
                records[record["set_id"]] = record
                _write_output(Path(out_path), meta, records)
    else:
        for job in jobs:
            record = job()
            records[record["set_id"]] = record
            _write_output(Path(out_path), meta, records)

    summary = _write_output(Path(out_path), meta, records)
    ordered = [records[k] for k in sorted(records)]
    return RunResult(records=ordered, summary=summary, meta=meta)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="DocTrust evaluation runner (see eval/EVALUATION.md)")
    for name, default in DEFAULT_COUNTS.items():
        ap.add_argument(f"--{name}", type=int, default=None,
                        help=f"sets in category {name} (default {default})")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="multiply the default category counts")
    ap.add_argument("--over-dob", type=int, default=3,
                    help="discrepancy sets with the stamp over the "
                         "birth-certificate DOB (default 3)")
    ap.add_argument("--seed-base", type=int, default=7)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--data-dir", default="eval/data")
    ap.add_argument("--physical-dir", default="eval/physical",
                    help="directory of physically captured sets "
                         "(default eval/physical; a missing or empty "
                         "directory simply adds no sets — see "
                         "eval/PHYSICAL_CAPTURE.md)")
    ap.add_argument("--out", default="eval/results/results.json")
    ap.add_argument("--resume", action="store_true",
                    help="skip sets already completed in the out file")
    args = ap.parse_args(argv)

    counts = {}
    for name, default in DEFAULT_COUNTS.items():
        explicit = getattr(args, name)
        counts[name] = (explicit if explicit is not None
                        else max(0, round(default * args.scale)))

    reader = judge.resolve_reader()
    if reader is None:
        print("No reader configured. Set JUDGE_READER=meta (with "
              "MODEL_API_KEY), JUDGE_READER=baseten (with "
              "BASETEN_API_KEY) or JUDGE_READER=mock — see "
              "backend/app/judge.py. Refusing to invent reads.",
              file=sys.stderr)
        return 2

    result = run_evaluation(
        counts=counts, seed_base=args.seed_base, over_dob=args.over_dob,
        data_dir=Path(args.data_dir), out_path=Path(args.out),
        reader=reader, segmenter=judge.resolve_segmenter(),
        workers=args.workers, resume=args.resume,
        physical_dir=Path(args.physical_dir))
    print(render_markdown(result.summary, result.meta, result.records))
    print(f"\nWrote {args.out} (+ .md summary alongside)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
