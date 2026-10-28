# Physically captured evaluation sets — capture guide

The synthetic evaluation sets are rendered and scored entirely
in-silico. The physical batch narrows the synthetic-to-real gap: the
same SPECIMEN pages, printed or displayed, photographed with a
phone, and scored through the same pipeline. The protocol is in
[EVALUATION.md](EVALUATION.md); this file is the how-to for producing
the sets. **Goal: ~10 sets.**

## The workflow

1. **Generate a fresh SPECIMEN set** with the existing generator,
   one per capture set. From the repo root:

   ```bash
   .venv/bin/python -m generator.generate --out /tmp/capture/var-1 --variant variation --seed 21
   ```

   The variant decides the manifest's `expectation`: `clean` and
   `variation` → `genuine`, `discrepancy` → `discrepancy`,
   `degraded` → `degraded`. Use a different seed per set.

2. **Print the three pages** (`nid.png`, `birth_certificate.png`,
   `bank_form.png`) — or display each one full-screen on a monitor
   or tablet. Whichever medium you choose, all three documents of a
   set come from the same generated set.

3. **Photograph each document with a phone** — one photo per
   document, filling the frame, text legible to your own eye unless
   the set is meant to be degraded.

4. **Copy the photos into `eval/physical/<set-name>/`** — the folder
   name becomes the set id (`physical-<set-name>`), so pick
   something descriptive (`kitchen-table`, `window-glare`, …). Name
   the photos `nid`, `birth_certificate` and `bank_form` with a
   `.jpg`, `.jpeg` or `.png` extension:

   ```text
   eval/physical/var-1/
     nid.jpg
     birth_certificate.jpg
     bank_form.jpg
     manifest.json
   ```

5. **Write `manifest.json`** in that folder, built from the
   generated set's `ground_truth.json` (see below).

6. **Run the evaluation.** Physical sets are picked up automatically
   (default `--physical-dir eval/physical`), scored through the
   same three configurations, and reported as their own category in
   the results, split by expectation. Physical genuine sets also
   count in the headline genuine pool.

## manifest.json

Three required pieces:

- `expectation`: `"genuine"`, `"discrepancy"` or `"degraded"` —
  what the set is. Genuine sets must pass; a discrepancy set has
  exactly one field whose value differs in one document; a degraded
  set's facts agree but its capture quality is poor.
- `injected_field`: required **only** when `expectation` is
  `"discrepancy"` — the field that differs (for sets generated with
  `--variant discrepancy`, the generator swaps the bank form's date
  of birth, so this is `"dob"`). Omit it otherwise.
- `documents`: the per-document field values, copied **verbatim**
  from the generated set's `ground_truth.json` under its
  `"documents"` key — the same shape the synthetic sets are scored
  against. Do not retype values from the photos; the manifest is the
  ground truth the reads are scored against.

Optionally, `conditions` records how the set was captured (a short
free-text string) — it is carried into the run's records.

Filled example — a genuine set generated with `--variant variation`
(legitimate name and digit-system differences; the facts agree):

```json
{
  "expectation": "genuine",
  "conditions": "Printed A4, photographed flat on a kitchen table, daylight",
  "documents": {
    "nid": {
      "name": "Md. Abdul Rahman",
      "dob": "12/03/1990",
      "id_number": "১২৩৪৫৬৭৮৯০",
      "father_name": "Abdul Karim"
    },
    "birth_certificate": {
      "name": "Mohammad Abdul Rahman",
      "dob": "১২/০৩/১৯৯০",
      "father_name": "Abdul Karim"
    },
    "bank_form": {
      "name": "Mohammed Abdul Rahaman",
      "dob": "12/03/1990",
      "id_number": "1234567890",
      "father_name": "Abdul Karim"
    }
  }
}
```

For a discrepancy set, add `"injected_field": "dob"` next to
`"expectation": "discrepancy"` (and its `documents` keep the swapped
value exactly as `ground_truth.json` records it).

A folder that is missing a photo, or whose manifest is malformed —
bad JSON, a missing `injected_field` on a discrepancy set, documents
that do not actually encode the declared expectation — is **skipped
with a printed warning**; the run never crashes on a bad capture
folder. If a set you captured does not appear in the results, check
the warnings first.

## The mix to aim for (~10 sets)

- **~4 genuine** — including name transliteration variations and
  Bangla/Latin digit differences (generate with `--variant
  variation`), plus plain `clean` sets.
- **~3 discrepancy** — `--variant discrepancy` sets.
- **~3 degraded** — `--variant degraded` sets, or genuine sets
  captured under deliberately poor conditions.

## Capture conditions to vary

Spread the batch across real capture conditions rather than shooting
ten identical flat scans:

- **glare** — a lamp or window reflection across part of the page;
- **fold / crease** — a fold crossing a field;
- **angle / perspective** — shot at an angle instead of flat-on;
- **low light** and **shadow** falling across the page.

Note what you did in the manifest's `conditions` field.

## Rules

- **SPECIMEN synthetic documents only.** Never photograph, copy or
  upload a real identity document — not for this evaluation, not
  for judge mode.
- All three photos of a set come from the **same** printed/displayed
  set — never mix pages from different generation runs.
- One folder per set under `eval/physical/`; nothing else belongs
  there (stray folders without photos or a manifest are skipped
  with a warning, but keep the directory clean anyway).
