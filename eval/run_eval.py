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


def evaluate_set(spec: SetSpec, truth: dict, expected: dict,
                 data_dir: Path, reader_factory, segmenter) -> dict:
    """Run all three configurations over one set. Never raises for
    reader errors — the caller records them as set errors."""
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

    # Configurations 1 + 2: one shared read pass, scored two ways.
    single_reader = CountingReader(reader_factory(spec, "single", truth))
    start = time.perf_counter()
    docs = _single_pass_reads(single_reader, images)
    single_latency = time.perf_counter() - start
    for name, fn in (("exact", exact_match_verdict),
                     ("single", single_pass_verdict)):
        verdict, flagged = fn(docs)
        record["configs"][name] = {
            "verdict": verdict,
            "flagged_fields": flagged,
            "documents": docs,
            "reads": single_reader.calls,
            "latency_s": round(single_latency, 3),
            "input_tokens": single_reader.input_tokens
                            if single_reader.usage_seen else None,
            "output_tokens": single_reader.output_tokens
                             if single_reader.usage_seen else None,
            "cost_usd": round(_cost_usd(single_reader.input_tokens,
                                         single_reader.output_tokens), 6)
                        if single_reader.usage_seen else None,
        }

    # Configuration 3: the full agent, its own reader.
    agent_reader = CountingReader(reader_factory(spec, "agent", truth))
    start = time.perf_counter()
    outcome = agent.run_review(agent_reader, images, segmenter=segmenter)
    agent_latency = time.perf_counter() - start
    flagged = [f["field"] for f in outcome.findings
               if f.get("status") == "mismatch"]
    record["configs"]["agent"] = {
        "verdict": outcome.verdict,
        "flagged_fields": flagged,
        "documents": outcome.documents,
        "uncertain_fields": [f"{fr.doc_type}.{fr.field}"
                             for fr in outcome.field_reads if fr.uncertain],
        "reads": agent_reader.calls,
        "latency_s": round(agent_latency, 3),
        "input_tokens": agent_reader.input_tokens
                        if agent_reader.usage_seen else None,
        "output_tokens": agent_reader.output_tokens
                         if agent_reader.usage_seen else None,
        "cost_usd": round(_cost_usd(agent_reader.input_tokens,
                                     agent_reader.output_tokens), 6)
                    if agent_reader.usage_seen else None,
    }
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


def _score_record(cells: dict, record: dict, config: str) -> None:
    cfg = record["configs"][config]
    verdict = cfg["verdict"]
    category = record["category"]
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


def aggregate(records: list[dict]) -> dict:
    """Headline cells per config + the same split by category.
    Only status == 'ok' records are scored; errored sets are counted
    separately and never enter a denominator."""
    done = [r for r in records if r.get("status") == "ok"]
    summary: dict = {"sets_ok": len(done),
                     "sets_error": len(records) - len(done),
                     "configs": {}, "by_category": {}}
    for config in CONFIGS:
        cells = _blank_cells()
        per_category = {c: _blank_cells() for c in CATEGORIES}
        reads, latencies, costs = [], [], []
        for record in done:
            _score_record(cells, record, config)
            _score_record(per_category[record["category"]], record, config)
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
        summary["configs"][config] = cells
        summary["by_category"][config] = per_category
    return summary


# ---------------------------------------------------------------------------
# Markdown summary, in EVALUATION.md's table shapes
# ---------------------------------------------------------------------------

def _xn(x: int, n: int) -> str:
    return f"{x}/{n}" if n else "—"


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
        "",
        "**Counts (x/n) throughout — never bare percentages.**",
        "",
        "| Metric | 1. Exact-match | 2. Single-pass + norm. | 3. Full agent |",
        "|---|---|---|---|",
    ]
    c = summary["configs"]
    lines.append(
        "| False flags on genuine sets (x/n) | "
        + " | ".join(_xn(c[k]["false_flags"], c[k]["genuine_n"])
                     for k in CONFIGS) + " |")
    lines.append(
        "| Injected discrepancies caught (x/n) | "
        + " | ".join(_xn(c[k]["caught"], c[k]["discrepancy_n"])
                     for k in CONFIGS) + " |")
    lines.append(
        "| **Silent errors — verdict \"Consistent\" while a "
        "discrepancy exists (count)** | "
        + " | ".join(f"**{c[k]['silent_errors']}**" for k in CONFIGS) + " |")
    lines.append(
        "| Degraded sets: recovered / recapture requested (x/n) | "
        + " | ".join(
            f"{_xn(c[k]['recovered'], c[k]['degraded_n'])} / "
            f"{_xn(c[k]['recapture'], c[k]['degraded_n'])}"
            for k in CONFIGS) + " |")
    lines.append(
        "| Reads per set (mean) | "
        + " | ".join(str(c[k]["reads_mean"]) for k in CONFIGS) + " |")
    lines.append(
        "| Latency per set (mean, s) | "
        + " | ".join(str(c[k]["latency_mean_s"]) for k in CONFIGS) + " |")
    lines.append(
        "| Cost per set (USD, at route prices) | "
        + " | ".join("—" if c[k]["cost_mean_usd"] is None
                     else f"{c[k]['cost_mean_usd']:.4f}"
                     for k in CONFIGS) + " |")
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
        cells = bc[category]
        if category in GENUINE_CATEGORIES:
            ff = _xn(cells["false_flags"], cells["genuine_n"])
        elif category == "degraded":
            ff = _xn(cells["degraded_false_flags"], cells["degraded_n"])
        else:
            ff = "—"
        lines.append(
            f"| {category} | {ff} | "
            f"{_xn(cells['caught'], cells['discrepancy_n'])} | "
            f"{cells['silent_errors']} | "
            f"{_xn(cells['recovered'], cells['degraded_n'])} / "
            f"{_xn(cells['recapture'], cells['degraded_n'])} |")
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
        lines.append(f"- Set {r['set_id']} ({r['category']}, "
                     f"stamp {r['stamp_style']}/{r['stamp_position']}): "
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
                   workers: int = 4, resume: bool = False) -> RunResult:
    """Build the dataset and evaluate every set.

    reader_factory(spec, phase, truth) -> Reader, phase in
    {"single", "agent"}. Without a factory, `reader` is shared by all
    phases and sets (the CLI path: one stateless live reader).
    """
    counts = dict(counts or DEFAULT_COUNTS)
    specs = build_dataset(counts, seed_base=seed_base, over_dob=over_dob)
    truths = generate_dataset(specs, Path(data_dir))

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
        "reader": type(reader).__name__ if reader is not None
                  else "factory",
        "segmenter": type(segmenter).__name__,
    }

    records: dict[str, dict] = {}
    if resume:
        records = _load_records(Path(out_path))
    todo = [s for s in specs
            if records.get(s.set_id, {}).get("status") != "ok"]

    def work(spec: SetSpec) -> dict:
        try:
            return evaluate_set(spec, truths[spec.set_id],
                                expected_from_truth(truths[spec.set_id]),
                                Path(data_dir), reader_factory, segmenter)
        except Exception:
            return {
                "set_id": spec.set_id, "category": spec.category,
                "variant": spec.variant, "seed": spec.seed,
                "stamp_style": spec.stamp_style,
                "stamp_position": spec.stamp_position,
                "status": "error",
                "error": traceback.format_exc(limit=3).strip().splitlines()[-1],
                "configs": {},
            }

    if workers and workers > 1 and len(todo) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, s): s for s in todo}
            for fut in as_completed(futures):
                record = fut.result()
                records[record["set_id"]] = record
                _write_output(Path(out_path), meta, records)
    else:
        for spec in todo:
            record = work(spec)
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
        workers=args.workers, resume=args.resume)
    print(render_markdown(result.summary, result.meta, result.records))
    print(f"\nWrote {args.out} (+ .md summary alongside)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
