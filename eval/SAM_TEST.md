# SAM 3.1 vs. Pillow heuristic — stamp-masking comparison protocol

> **Status: PROTOCOL FIXED IN ADVANCE; box-IoU stage run
> 2026-10-27, remaining stages pending.**
> The cases, prompts and scoring below are specified before the
> comparison run, so they cannot be tuned after seeing results. The
> heuristic side can run offline today; the SAM side runs against
> SAM 3.1 hosted on the Meta Model API (`MetaSAMSegmenter`) — the
> self-hosted Modal app remains implemented but is not deployed,
> because the owner's Modal workspace cannot add the payment method
> its GPU functions require. The first stage of the comparison —
> bounding-box IoU against the ground-truth stamp box — was run on
> 2026-10-27 and is recorded below. The recovered-read and
> final-verdict stages have not been run yet; those cells still read
> _pending_ and no claim is made from them either way.

## Question

DocTrust's investigation step re-reads a field after masking the
stamp that occludes it. Two segmenters can produce that mask:

- **Pillow heuristic** (`PillowFallbackSegmenter`): finds saturated
  blue/purple ink by colour and masks its bounding box. It was built
  for the generator's original purple stamp.
- **SAM 3.1 via the Meta Model API** (`MetaSAMSegmenter`):
  open-vocabulary concept segmentation of the same prompt, using
  Meta's hosted endpoint for the same SAM 3.1 weights. (A self-hosted
  Modal segmenter, `ModalSegmenter`, is also implemented; it is not
  the route under test here.)

If SAM does not beat the heuristic somewhere real, "SAM as a tool"
adds nothing over a colour filter, and the README should say so.
This protocol exists to find out, on cases chosen to stress the
heuristic — not to flatter SAM.

## Fixed protocol

- **Same agent, same reader, same sets.** The only variable is the
  injected segmenter. Everything else — perturbation views,
  investigation triggers, comparator — is the production loop.
- **Prompts, fixed in advance:** `"stamp"`, `"circular ink stamp"`,
  `"rubber stamp"`. All three are run and all three are reported,
  including whichever performs worst. No prompt is edited after a
  run; a prompt change starts a new, separately reported run.
- **Ground truth:** the generator draws the stamp, so its exact box
  is known: `ground_truth.json` → `stamp_box` for the birth
  certificate.
- **Per case, record:**
  - Mask IoU of each segmenter's box against `stamp_box`
    (intersection over union of the rectangles).
  - Whether the occluded field was read correctly after masking
    (per prompt, per segmenter).
  - The final verdict, per segmenter.
- **What counts as a win:** SAM achieves higher IoU **and** recovers
  a correct read of the occluded field that the heuristic does not.
  Higher IoU alone, with the same read outcome, is a tie — reported
  as a tie.

## Cases

Two to three independently seeded sets per case. The stamp styles
come from `generator/generate.py --stamp-style`.

### Case A — non-purple stamp (heuristic expected to miss)

Black or red-orange circular-style stamp over the birth
certificate's date-of-birth digits (`stamp_style` `black` /
`red_orange`). The heuristic keys on blue/purple saturation, so it
should find nothing; SAM is asked to find a stamp it can only
recognise by concept, not colour.

### Case B — faded stamp

Low-contrast grey stamp (`stamp_style` `faded_grey`) partly over
the ID number. Even a colour-keyed detector gets little signal at
this contrast; the question is whether SAM segments a stamp that is
barely darker than the page — and whether masking it changes the
read at all.

### Case C — false-positive trap

A blue-ink handwritten-style field placed next to a purple stamp
(the generator's default). The risk runs the other way here: the
heuristic may mask the *handwriting* — real content — along with or
instead of the stamp, destroying the field it meant to recover.
Record what each segmenter's mask actually covers, not just its IoU
against the stamp box.

> Case C needs a handwriting-style field near the stamp; if the
> generator cannot place one yet, the case is recorded as *blocked
> on generator support* rather than quietly dropped.

## Results — full protocol (pending)

The bounding-box IoU stage of this scoring was run separately on
2026-10-27 — see the next section. The read-recovery and verdict
columns below remain _pending_.

| Case | Segmenter | Prompt | Mask IoU | Occluded field read correctly | Verdict |
|---|---|---|---|---|---|
| A | Pillow heuristic | — (no prompt) | _ | _ | _ |
| A | SAM 3.1 | stamp | _pending_ | _pending_ | _pending_ |
| A | SAM 3.1 | circular ink stamp | _pending_ | _pending_ | _pending_ |
| A | SAM 3.1 | rubber stamp | _pending_ | _pending_ | _pending_ |
| B | Pillow heuristic | — | _ | _ | _ |
| B | SAM 3.1 | (all three prompts) | _pending_ | _pending_ | _pending_ |
| C | Pillow heuristic | — | _ | _ | _ |
| C | SAM 3.1 | (all three prompts) | _pending_ | _pending_ | _pending_ |

Generator support for the recovered-read stage now exists: the
generator accepts `stamp_position="over_dob"` (CLI
`--stamp-position over_dob`), which centres the same stamp graphic
on the birth certificate's Born-row value — ground-truth
`stamp_box` `[298, 223, 448, 373]` — instead of the bottom margin,
so the date of birth sits under the stamp and masking it is what
makes the field readable again. Sets for this stage can be
generated today; the stage itself has not been run yet.

For the demo video: one side-by-side overlay — heuristic mask vs.
SAM mask — on Case A or Case C, whichever shows the clearer
difference, including if the difference favours the heuristic.

### Recovered-read probe log (2026-10-27)

Single-set live probes on one genuine set with a black stamp over
the birth certificate's DOB (`stamp_position="over_dob"`), run
through the full agent loop with the production reader. These are
probes, not the multi-set comparison above — n = 1 per segmenter,
and the verdict column of the full protocol is still pending the
evaluation run.

1. **Pre-trigger-fix probe.** The birth-certificate DOB's first-pass
   reads were [UNREADABLE, value, UNREADABLE]. Partial unreadability
   did not count as disagreement then, so the investigation never
   fired, the segmenter was never exercised, and the outcome was
   decided by read variance alone.
2. **Post-trigger-fix probe** (same set, one run per segmenter).
   The investigation fired in both runs. The `zoom_tight` view
   recovered the true DOB (১২/০৩/১৯৯০) in both runs' evidence trails.
   The `stamp_masked` view read UNREADABLE in both runs: the
   heuristic found no mask on the black stamp, and SAM's masked
   copy covers the stamp box — which for an over-field stamp also
   covers the digits underneath, a recorded design limit of
   cover-masking for over-field stamps. The field's five reads
   therefore ended scattered — the true value once, a wrong value
   (১২/০৯/১৯৯০) once, the rest UNREADABLE — and the majority vote
   broke the tie to the wrong value in both runs: a false
   DISCREPANCY verdict on a genuine set, n = 1 per segmenter.
3. **Tie fix (same day).** `_majority` now returns a value only
   when it is the unique plurality winner; any tie for the top
   count returns no value, so read scatter of this shape ends in
   the recapture verdict rather than a coin-flip flag. The full
   multi-set verdict comparison (heuristic vs. SAM, recovered-read
   and verdict columns above) is still pending the evaluation run.

## Results — box IoU stage (2026-10-27)

This stage covers only the detection half of the protocol. Each
segmenter was run on `birth_certificate.png` from the generator's
clean sets — one set per stamp style — and the box it returned was
compared with the ground-truth `stamp_box`, `[750, 440, 900, 590]`
(the same box for all four styles). The metric is **bounding-box
IoU** — intersection over union of the predicted box and the
ground-truth box; mask IoU has not been measured yet. SAM ran on
Meta-hosted SAM 3.1 through the Meta Model API
(`MetaSAMSegmenter`); the heuristic ran locally
(`PillowFallbackSegmenter`, no prompt). Where a SAM prompt returned
one box, that box's IoU is reported; where it returned no boxes,
the IoU is 0.00.

| Stamp style | Heuristic box | Heuristic IoU | SAM "stamp" | SAM "circular ink stamp" | SAM "rubber stamp" |
|---|---|---|---|---|---|
| purple | [750, 440, 900, 587.5] | 0.98 | 0.99 (1 box) | 0.99 (1 box) | 0 boxes (0.00) |
| black | none | 0.00 | 0.99 (1 box) | 0.99 (1 box) | 0 boxes (0.00) |
| red_orange | none | 0.00 | 0.99 (1 box) | 0.99 (1 box) | 0 boxes (0.00) |
| faded_grey | none | 0.00 | 0.99 (1 box) | 0.99 (1 box) | 0 boxes (0.00) |

The colour heuristic is exactly as brittle as predicted: near
perfect (0.98) on the purple ink it was built for, and blind to
every other ink — black, red-orange and faded grey all returned no
box at all. Hosted SAM found the stamp at 0.99 box IoU in all four
styles under two of the three pre-registered prompts. The third
prompt, "rubber stamp", returned no boxes in all four styles:
prompt wording matters, and that negative is reported here as the
protocol requires, not tuned away.

Caveats, stated plainly:

- **Box IoU only.** Mask IoU — the overlap of the actual masks —
  has not been measured yet.
- **n = 1 clean set per style.** These are single samples, not a
  distribution; a different seed could move any of these numbers.
- **Synthetic documents only**, rendered by the same generator that
  supplies the ground truth.
- **The recovered-read and final-verdict columns of the protocol
  are still pending.** They run through the full agent loop, so
  this stage alone does not complete the protocol — and by the
  protocol's own definition, higher IoU without a recovered read
  is not yet a win.
- **Case C (the false-positive trap) remains blocked** on
  generator support for a handwriting-style field near the stamp.

## Reporting rule

**If SAM loses a case, the loss is reported here with the reason**
(prompt mismatch, checkpoint behaviour on synthetic stamps, mask
covering the wrong region — whatever the trace shows). A reported
loss with a reason is a credible result; a comparison that only
publishes wins is marketing. The README's segmentation section is
updated from this file's outcome, in whichever direction it lands.
