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
   disagreement-triggered investigation — model-directed steps with
   a deterministic fallback — same comparator). The runner's "reads"
   for this configuration count planner consultations as model
   calls too (see CountingReader).

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

from app import agent, comparator, judge, normalize  # noqa: E402
from app.providers import Reader  # noqa: E402
from generator.generate import (  # noqa: E402
    BANGLA_PERSONAS, STAMP_STYLES, generate_set)

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
    script: str = "bangla"
    # Multi-persona batches only (--persona-batch / --persona-genuine):
    # which BANGLA_PERSONAS entry the set is generated for, the
    # bank-form injection planted in it (discrepancy batch only), and
    # whether the degraded treatment is layered on top of the
    # discrepancy variant. All defaults = the legacy batches.
    persona_index: int | None = None
    injection: dict | None = None
    degrade: bool = False


# Hindi-script composition per 10 sets (--hindi): mostly clean and
# variation, a couple of discrepancies, one degraded. The remainder
# from scaling goes to the earliest categories first.
_HINDI_QUOTAS = {"clean": 4, "variation": 3, "discrepancy": 2, "degraded": 1}


def _hindi_counts(n: int) -> dict[str, int]:
    counts = {c: (n * q) // 10 for c, q in _HINDI_QUOTAS.items()}
    remainder = n - sum(counts.values())
    order = list(_HINDI_QUOTAS)
    i = 0
    while remainder > 0:
        counts[order[i % len(order)]] += 1
        remainder -= 1
        i += 1
    return counts


# ---------------------------------------------------------------------------
# Multi-persona batch (--persona-batch)
# ---------------------------------------------------------------------------
# Every batch before this one reused the generator's single base
# person, so the name rules were only ever tested on the names they
# were tuned against. The persona batch plants discrepancies on a
# pool of ten personas instead. Injections are near-miss names and
# one-digit changes on the bank form (see generator.generate's
# INJECTION_FIELDS), keyed to each persona so the values fit it.

# Near-miss surname replacements for the father's name (applied to
# its last token) and for the person's own name. Pairs are chosen so
# the consonant skeletons differ — a same-skeleton pair (Salam ->
# Salim, Islam -> Aslam) would be transliteration residue under the
# comparator, not a discrepancy, and is never used.
_FATHER_NEAR_MISS = {
    "Karim": "Rahim", "Kader": "Kamal", "Islam": "Rahim",
    "Malek": "Kamal", "Haque": "Hasan", "Rahim": "Karim",
    "Aziz": "Azim", "Salam": "Kamal", "Rahman": "Rahim",
}
_NAME_NEAR_MISS = {
    "Rahman": "Rahim", "Hossain": "Hasan", "Akter": "Akhtar",
    "Hasan": "Hossain", "Akhtar": "Akter", "Jahan": "Jamal",
    "Hosen": "Hasan", "Begum": "Khatun",
}

# Injection kinds cycled within a third of the batch. The over-DOB
# third leads with dob (the field the stamp covers); the other two
# thirds lead with the near-miss father names.
_KINDS_OVER_DOB = ("dob", "father_name", "id_number", "name")
_KINDS_PLAIN = ("father_name", "dob", "id_number", "name")


def _persona_dob_injection(persona: dict) -> dict:
    """Day + 1 on the persona's DOB. Persona DOB days are all <= 25,
    so the result is always a valid, genuinely different date."""
    day, month, year = persona["dob"].split("/")
    return {"field": "dob",
            "value": f"{int(day) + 1:02d}/{month}/{year}"}


def _persona_id_injection(persona: dict) -> dict:
    """The ID's 5th digit, +1 mod 10 — a one-digit change."""
    digits = persona["id_number"]
    bumped = str((int(digits[4]) + 1) % 10)
    return {"field": "id_number",
            "value": digits[:4] + bumped + digits[5:]}


def _persona_name_injection(persona: dict, field: str,
                            mapping: dict[str, str]) -> dict | None:
    """Replace the last token of the persona's name/father's name via
    `mapping` — but only when the result is a genuine comparator
    mismatch. Two prescribed pairs fail that test and must not be
    planted: Akter <-> Akhtar folds to identical tokens in
    normalize._NAME_VARIANTS (a 'match'), and Hosen -> Hasan shares
    a consonant skeleton at edit distance 2 (a 'variant'). Those
    return None and the caller falls back to a DOB injection, so no
    generated set ever carries a non-discrepancy as its injection."""
    original = persona["father_en" if field == "father_name"
                       else "name_en"]
    tokens = original.split()
    replacement = mapping.get(tokens[-1])
    if replacement is None:
        return None
    candidate = " ".join([*tokens[:-1], replacement])
    if normalize.names_match(original, candidate) != "mismatch":
        return None
    return {"field": field, "value": candidate}


def _persona_injection(persona: dict, kind: str) -> dict:
    """The injection of `kind` for one persona, guaranteed to be a
    genuine mismatch under the comparator: name kinds fall back to a
    DOB injection when the persona's surname has no usable near-miss
    (unmapped token, or a mapped pair the comparator treats as the
    same name — see _persona_name_injection)."""
    if kind == "dob":
        return _persona_dob_injection(persona)
    if kind == "id_number":
        return _persona_id_injection(persona)
    if kind == "father_name":
        injection = _persona_name_injection(
            persona, "father_name", _FATHER_NEAR_MISS)
    elif kind == "name":
        injection = _persona_name_injection(
            persona, "name", _NAME_NEAR_MISS)
    else:
        raise ValueError(f"unknown injection kind {kind!r}")
    return injection if injection is not None \
        else _persona_dob_injection(persona)


def _persona_specs(persona_batch: int, seed_base: int,
                   index: int) -> list[SetSpec]:
    """The persona-batch specs, appended after the regular sets with
    seeds continuing the caller's index sequence. Composition in
    thirds (remainder to the earliest thirds): the first third puts
    the stamp over the birth-certificate DOB, the second is plain
    margin sets, the last third layers the degraded treatment over
    the discrepancy. Personas cycle 0..9 across the whole batch."""
    base, remainder = divmod(persona_batch, 3)
    sizes = [base + (1 if t < remainder else 0) for t in range(3)]
    specs: list[SetSpec] = []
    position_in_batch = 0
    for third, size in enumerate(sizes):
        for k in range(size):
            persona_index = position_in_batch % len(BANGLA_PERSONAS)
            persona = BANGLA_PERSONAS[persona_index]
            if third == 0:
                stamp_position, degrade = "over_dob", False
                kind = _KINDS_OVER_DOB[k % len(_KINDS_OVER_DOB)]
            elif third == 1:
                stamp_position, degrade = "margin", False
                kind = _KINDS_PLAIN[k % len(_KINDS_PLAIN)]
            else:
                stamp_position, degrade = "margin", True
                kind = _KINDS_PLAIN[k % len(_KINDS_PLAIN)]
            specs.append(SetSpec(
                set_id=f"persona-disc-{position_in_batch + 1:02d}",
                category="discrepancy",
                variant="discrepancy",
                seed=seed_base + index,
                stamp_style=_STAMP_STYLE_CYCLE[
                    index % len(_STAMP_STYLE_CYCLE)],
                stamp_position=stamp_position,
                persona_index=persona_index,
                injection=_persona_injection(persona, kind),
                degrade=degrade,
            ))
            index += 1
            position_in_batch += 1
    return specs


def _persona_genuine_specs(persona_genuine: int, seed_base: int,
                           index: int) -> list[SetSpec]:
    """The genuine multi-persona specs (--persona-genuine), appended
    after the persona discrepancy batch with seeds continuing the
    caller's index sequence: the first ceil(n/2) are clean sets, the
    rest variation sets (each persona's own spelling pair), personas
    cycling 0..9 across the appended sets in order, every stamp in
    the margin. The discrepancy batch cannot measure false flags —
    this is the batch that does, across the same persona pool."""
    n_clean = (persona_genuine + 1) // 2
    specs: list[SetSpec] = []
    for j in range(persona_genuine):
        if j < n_clean:
            category = "clean"
            set_id = f"persona-clean-{j + 1:02d}"
        else:
            category = "variation"
            set_id = f"persona-var-{j - n_clean + 1:02d}"
        specs.append(SetSpec(
            set_id=set_id,
            category=category,
            variant=category,
            seed=seed_base + index,
            stamp_style=_STAMP_STYLE_CYCLE[
                index % len(_STAMP_STYLE_CYCLE)],
            stamp_position="margin",
            persona_index=j % len(BANGLA_PERSONAS),
        ))
        index += 1
    return specs


def build_dataset(counts: dict[str, int], seed_base: int = 7,
                  over_dob: int = 3, hindi: int = 0,
                  persona_batch: int = 0,
                  persona_genuine: int = 0) -> list[SetSpec]:
    """Deterministic set list: fixed category order, seeds seed_base+i,
    stamp styles cycled, the first `over_dob` discrepancy sets placing
    the stamp over the birth-certificate DOB. With hindi > 0, that many
    Hindi-script sets (see _HINDI_QUOTAS) are appended with continuing
    seeds; they are scored separately and never enter the headline
    pools (the Bangla comparison stays apples-to-apples). With
    persona_batch > 0, that many multi-persona discrepancy sets (see
    _persona_specs) are appended next, again with continuing seeds;
    they are Bangla discrepancy sets and score in the headline pools
    under their category like any other discrepancy set. With
    persona_genuine > 0, that many genuine multi-persona sets (see
    _persona_genuine_specs) are appended last; they are Bangla clean
    and variation sets and join the headline genuine pool."""
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
    if hindi > 0:
        hindi_counts = _hindi_counts(hindi)
        for category in CATEGORIES:
            for i in range(hindi_counts.get(category, 0)):
                position = "over_dob" if (
                    category == "discrepancy" and i == 0) else "margin"
                specs.append(SetSpec(
                    set_id=f"hindi-{category}-{i + 1:02d}",
                    category=category,
                    variant=category,
                    seed=seed_base + index,
                    stamp_style=_STAMP_STYLE_CYCLE[
                        index % len(_STAMP_STYLE_CYCLE)],
                    stamp_position=position,
                    script="hindi",
                ))
                index += 1
    if persona_batch > 0:
        specs += _persona_specs(persona_batch, seed_base, index)
    if persona_genuine > 0:
        # len(specs) is the running index: every appended spec so
        # far consumed exactly one seed/style slot.
        specs += _persona_genuine_specs(persona_genuine, seed_base,
                                        len(specs))
    return specs


def generate_dataset(specs: list[SetSpec], data_dir: Path) -> dict[str, dict]:
    """Render every set (idempotent) and return {set_id: ground_truth}."""
    truths: dict[str, dict] = {}
    for spec in specs:
        out = data_dir / spec.set_id
        truth = generate_set(out, spec.variant, spec.seed,
                             stamp_style=spec.stamp_style,
                             stamp_position=spec.stamp_position,
                             script=spec.script,
                             person=(BANGLA_PERSONAS[spec.persona_index]
                                     if spec.persona_index is not None
                                     else None),
                             injection=spec.injection,
                             degrade=spec.degrade)
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
    """Wraps a reader: counts model calls and accumulates token usage
    when the wrapped reader reports it (a `last_usage` dict attribute
    set after each call, with input/prompt and output/completion
    token keys). Current live readers report no usage -> tokens stay
    None and the run reports reads only.

    A "call" here is any billed model call: field reads AND planner
    consultations both count — the planner is part of configuration
    3's cost, and leaving it out would understate the agent's reads.
    """

    def __init__(self, inner: Reader):
        self.inner = inner
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.usage_seen = False

    def _absorb_usage(self) -> None:
        usage = getattr(self.inner, "last_usage", None)
        if isinstance(usage, dict):
            self.usage_seen = True
            self.input_tokens += int(
                usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            self.output_tokens += int(
                usage.get("output_tokens",
                          usage.get("completion_tokens", 0)) or 0)

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        self.calls += 1
        value = self.inner.read_field(image_path, doc_type, field,
                                      perturbation)
        self._absorb_usage()
        return value

    def plan_investigation(self, image_path: str, doc_type: str,
                           field: str, reads: list[dict],
                           actions: dict) -> dict:
        """Forward a planner consultation, counted like a read.

        A wrapped reader with no planner raises BEFORE the counter
        moves — no model call happened — and the agent answers with
        its fallback sequence, exactly as it would unwrapped.
        """
        planner = getattr(self.inner, "plan_investigation", None)
        if planner is None:
            raise RuntimeError(
                "wrapped reader has no investigation planner")
        self.calls += 1
        decision = planner(image_path, doc_type, field, reads, actions)
        self._absorb_usage()
        return decision


class PlannerSuppressingReader:
    """Reader wrapper for the --no-planner ablation: reads delegate
    to the wrapped reader, but `plan_investigation` is hidden, so
    the agent runs its deterministic fallback investigation sequence
    — the same code path as a reader with no planner at all. Every
    other attribute (including `last_usage`) passes through."""

    def __init__(self, inner):
        self._inner = inner

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        return self._inner.read_field(image_path, doc_type, field,
                                      perturbation)

    def __getattr__(self, name):
        if name == "plan_investigation":
            raise AttributeError(name)
        return getattr(self._inner, name)


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
                 reader_factory, segmenter, no_planner: bool = False
                 ) -> dict:
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
    raw_agent_reader = reader_factory(spec, "agent", truth)
    if no_planner:
        raw_agent_reader = PlannerSuppressingReader(raw_agent_reader)
    agent_reader = CountingReader(raw_agent_reader)
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
        # The planner's measured activity: per-field investigation
        # logs ({action, reason, source} entries). Absent from runs
        # made before this field existed; renderers must tolerate it.
        "investigations": {
            f"{fr.doc_type}.{fr.field}": fr.investigation
            for fr in outcome.field_reads if fr.investigation},
        **_usage_cells(agent_reader, agent_latency),
    }
    return configs


def evaluate_set(spec: SetSpec, truth: dict, expected: dict,
                 data_dir: Path, reader_factory, segmenter,
                 no_planner: bool = False) -> dict:
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
        "script": spec.script,
        "expected_verdict": expected["verdict"],
        "injected_fields": expected["injected_fields"],
        "configs": {},
    }
    record["configs"] = _run_configs(images, truth, spec,
                                     reader_factory, segmenter,
                                     no_planner=no_planner)
    record["status"] = "ok"
    return record


def evaluate_physical_set(spec: PhysicalSpec, reader_factory,
                          segmenter, no_planner: bool = False) -> dict:
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
        "script": "physical",
        "conditions": spec.conditions,
        "expected_verdict": expected["verdict"],
        "injected_fields": expected["injected_fields"],
        "configs": {},
    }
    record["configs"] = _run_configs(spec.images, truth, spec,
                                     reader_factory, segmenter,
                                     no_planner=no_planner)
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
    their expectation (see _scoring_category). Hindi-script sets are
    scored in their own section and NEVER enter the headline pools —
    the headline comparison is the Bangla sets only. Only
    status == 'ok' records are scored; errored sets are counted
    separately and never enter a denominator."""
    done = [r for r in records if r.get("status") == "ok"]
    hindi = [r for r in done if r.get("script") == "hindi"]
    headline = [r for r in done if r.get("script") != "hindi"]
    physical = [r for r in headline if r["category"] == "physical"]
    summary: dict = {"sets_ok": len(done),
                     "sets_error": len(records) - len(done),
                     "physical_sets": len(physical),
                     "hindi_sets": len(hindi),
                     "configs": {}, "by_category": {},
                     "physical": {"configs": {}, "by_expectation": {}},
                     "hindi": {"configs": {}, "by_category": {}}}
    for config in CONFIGS:
        summary["configs"][config] = _cells_for(headline, config)
        summary["by_category"][config] = {
            c: _cells_for([r for r in headline if r["category"] == c], config)
            for c in CATEGORIES
        }
        summary["physical"]["configs"][config] = _cells_for(physical, config)
        summary["physical"]["by_expectation"][config] = {
            exp: _cells_for([r for r in physical
                             if r["expectation"] == exp], config)
            for exp in PHYSICAL_EXPECTATIONS
        }
        summary["hindi"]["configs"][config] = _cells_for(hindi, config)
        summary["hindi"]["by_category"][config] = {
            c: _cells_for([r for r in hindi if r["category"] == c], config)
            for c in CATEGORIES
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


def _planner_activity(records: list[dict]) -> list[str]:
    """Planner-activity lines for the run summary, computed from the
    agent records' investigation logs. Empty when no record carries
    logs (runs made before the field existed, or no field was ever
    uncertain)."""
    fields = 0
    by_action: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for record in records:
        agent_cfg = (record.get("configs") or {}).get("agent") or {}
        for entries in (agent_cfg.get("investigations") or {}).values():
            fields += 1
            for entry in entries:
                by_action[entry.get("action", "?")] = \
                    by_action.get(entry.get("action", "?"), 0) + 1
                by_source[entry.get("source", "?")] = \
                    by_source.get(entry.get("source", "?"), 0) + 1
    if not fields:
        return []
    actions = ", ".join(f"{k} ×{v}" for k, v in sorted(by_action.items()))
    sources = ", ".join(f"{k} ×{v}" for k, v in sorted(by_source.items()))
    return [
        "",
        "### Investigation planner activity (full agent)",
        "",
        f"- Fields investigated: {fields}",
        f"- Steps by action: {actions}",
        f"- Steps by source: {sources}",
    ]


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
    if meta.get("no_planner"):
        lines.append(
            "- Planner: DISABLED for configuration 3 (ablation run — "
            "deterministic fallback investigation sequence)")
    if meta.get("physical_sets"):
        lines.append(
            f"- Physically captured sets: {meta['physical_sets']} "
            f"(from {meta.get('physical_dir')})")
    if meta.get("hindi_sets"):
        lines.append(
            f"- Hindi-script sets: {meta['hindi_sets']} "
            "(secondary script, reported separately below; not in "
            "the headline tables)")
    if meta.get("persona_sets"):
        lines.append(
            f"- Multi-persona sets: {meta['persona_sets']} "
            "(discrepancy sets planted across a pool of ten Bangla "
            "personas, not just the base person; scored in the "
            "headline tables as discrepancy sets)")
    if meta.get("persona_genuine_sets"):
        lines.append(
            f"- Multi-persona genuine sets: "
            f"{meta['persona_genuine_sets']} "
            "(clean and variation sets across the same pool of ten "
            "Bangla personas; scored in the headline tables as "
            "genuine sets)")
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
    lines += _planner_activity(records)
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
    if any(r.get("script") == "hindi" for r in records):
        lines += [
            "",
            "### Hindi-script sets (secondary, small n)",
            "",
            "_The same three configurations over the Hindi-script "
            "(Devanagari) sets only. These sets are NOT included in "
            "the headline tables above — the headline comparison is "
            "the Bangla sets. Claims stay narrow: Bangla primary, "
            "Hindi secondary, small n._",
            "",
        ]
        lines += _metric_table(summary["hindi"]["configs"])
        lines += [
            "",
            "#### By category — full agent (configuration 3)",
            "",
            "| Category | False flags (x/n) | Discrepancies caught (x/n) "
            "| Silent errors | Recovered / recapture (x/n) |",
            "|---|---|---|---|---|",
        ]
        hb = summary["hindi"]["by_category"]["agent"]
        for category in CATEGORIES:
            pool = "genuine" if category in GENUINE_CATEGORIES else category
            lines.append(_split_row(category, hb[category], pool))
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
        elif r.get("script") == "hindi":
            descriptor = (f"{r['category']}, script hindi, stamp "
                          f"{r['stamp_style']}/{r['stamp_position']}")
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
                   seed_base: int = 7, over_dob: int = 3, hindi: int = 0,
                   persona_batch: int = 0, persona_genuine: int = 0,
                   data_dir: Path, out_path: Path,
                   reader=None, reader_factory=None, segmenter=None,
                   workers: int = 4, resume: bool = False,
                   physical_dir: Path | None = None,
                   no_planner: bool = False) -> RunResult:
    """Build the dataset and evaluate every set — the synthetic sets
    plus, when `physical_dir` is given, every physically captured set
    discovered there. `hindi` > 0 appends that many Hindi-script sets,
    scored separately; `persona_batch` > 0 appends that many
    multi-persona discrepancy sets and `persona_genuine` > 0 that
    many genuine multi-persona sets (see build_dataset).

    reader_factory(spec, phase, truth) -> Reader, phase in
    {"single", "agent"}. Without a factory, `reader` is shared by all
    phases and sets (the CLI path: one stateless live reader).
    """
    counts = dict(counts or DEFAULT_COUNTS)
    specs = build_dataset(counts, seed_base=seed_base, over_dob=over_dob,
                          hindi=hindi, persona_batch=persona_batch,
                          persona_genuine=persona_genuine)
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
        "hindi_sets": sum(1 for s in specs if s.script == "hindi"),
        "persona_sets": sum(1 for s in specs
                            if s.set_id.startswith("persona-disc-")),
        "persona_genuine_sets": sum(
            1 for s in specs
            if s.set_id.startswith(("persona-clean-", "persona-var-"))),
        "reader": type(reader).__name__ if reader is not None
                  else "factory",
        "segmenter": type(segmenter).__name__,
        "no_planner": no_planner,
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
                                Path(data_dir), reader_factory, segmenter,
                                no_planner=no_planner)
        except Exception:
            return _error_record({
                "set_id": spec.set_id, "category": spec.category,
                "variant": spec.variant, "seed": spec.seed,
                "stamp_style": spec.stamp_style,
                "stamp_position": spec.stamp_position,
                "script": spec.script,
            })

    def work_physical(spec: PhysicalSpec) -> dict:
        try:
            return evaluate_physical_set(spec, reader_factory, segmenter,
                                         no_planner=no_planner)
        except Exception:
            return _error_record({
                "set_id": spec.set_id, "category": "physical",
                "expectation": spec.expectation, "variant": "physical",
                "seed": None, "stamp_style": "capture",
                "stamp_position": "n/a", "script": "physical",
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
    ap.add_argument("--hindi", type=int, default=0,
                    help="add N Hindi-script (Devanagari) sets, scored "
                         "separately from the headline Bangla tables "
                         "(default 0; 10 = 4 clean / 3 variation / "
                         "2 discrepancy / 1 degraded)")
    ap.add_argument("--persona-batch", type=int, default=0,
                    help="add N multi-persona discrepancy sets across "
                         "the generator's pool of ten Bangla personas "
                         "(near-miss name and one-digit bank-form "
                         "injections; composed in thirds: stamp over "
                         "the DOB, plain, degraded — default 0)")
    ap.add_argument("--persona-genuine", type=int, default=0,
                    help="add N genuine multi-persona sets across "
                         "the same persona pool (first half clean, "
                         "rest variation, each persona's own spelling "
                         "pair) — the false-flag direction the "
                         "discrepancy persona batch cannot measure "
                         "(default 0)")
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
    ap.add_argument("--no-planner", action="store_true",
                    help="ablation: hide the reader's investigation "
                         "planner from configuration 3, so it runs "
                         "the deterministic fallback sequence — "
                         "planner vs fixed-sequence comparison")
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
        hindi=args.hindi, persona_batch=args.persona_batch,
        persona_genuine=args.persona_genuine,
        data_dir=Path(args.data_dir), out_path=Path(args.out),
        reader=reader, segmenter=judge.resolve_segmenter(),
        workers=args.workers, resume=args.resume,
        physical_dir=Path(args.physical_dir),
        no_planner=args.no_planner)
    print(render_markdown(result.summary, result.meta, result.records))
    print(f"\nWrote {args.out} (+ .md summary alongside)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
