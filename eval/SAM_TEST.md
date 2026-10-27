# SAM 3.1 vs. Pillow heuristic — stamp-masking comparison protocol

> **Status: PROTOCOL FIXED IN ADVANCE; comparison results pending.**
> The cases, prompts and scoring below are specified before the
> comparison run, so they cannot be tuned after seeing results. The
> heuristic side can run offline today; the SAM side runs against
> SAM 3.1 hosted on the Meta Model API (`MetaSAMSegmenter`) — the
> self-hosted Modal app remains implemented but is not deployed,
> because the owner's Modal workspace cannot add the payment method
> its GPU functions require. Until the comparison is run, every SAM
> cell reads _pending_ and no claim is made either way.

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

## Results (pending)

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

For the demo video: one side-by-side overlay — heuristic mask vs.
SAM mask — on Case A or Case C, whichever shows the clearer
difference, including if the difference favours the heuristic.

## Reporting rule

**If SAM loses a case, the loss is reported here with the reason**
(prompt mismatch, checkpoint behaviour on synthetic stamps, mask
covering the wrong region — whatever the trace shows). A reported
loss with a reason is a credible result; a comparison that only
publishes wins is marketing. The README's segmentation section is
updated from this file's outcome, in whichever direction it lands.
