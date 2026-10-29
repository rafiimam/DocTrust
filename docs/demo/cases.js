/* DocTrust demo cases — cached agent runs on synthetic data.
 *
 * These are hand-built replays in the shape of the real pipeline's runs:
 * the same document types and fields as generator/generate.py (same base
 * person), the same view names as backend/app/agent.py (original, zoom,
 * contrast, stamp_masked, zoom_tight), the same deterministic
 * normalization rules as backend/app/normalize.py, and the comparator's
 * verdict language (CONSISTENT / DISCREPANCY / UNREADABLE) rendered for
 * humans. They are NOT live model output and claim no accuracy.
 */
window.DOCTRUST_CASES = [
  {
    id: "discrepancy",
    tab: "Case A — Discrepancy under a stamp",
    summary: "A stamp sits over the date of birth on the birth certificate. " +
      "The agent's reads disagree, it investigates by masking the stamp, " +
      "and cross-examination still finds a one-digit difference.",
    documents: [
      {
        id: "nid", type: "National Identity Card (sample)", bn: "জাতীয় পরিচয় পত্র",
        tone: "green", photo: true,
        fields: [
          { id: "name", label: "Name", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father", value: "Abdul Karim" },
          { id: "dob", label: "Date of Birth", value: "12/03/1990" },
          { id: "id_number", label: "ID No", value: "১২৩৪৫৬৭৮৯০", bn: true }
        ]
      },
      {
        id: "birth_certificate", type: "Birth Certificate (sample)", bn: "জন্ম সনদ",
        tone: "cream",
        fields: [
          { id: "name", label: "Name", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father", value: "আব্দুল করিম", bn: true },
          { id: "dob", label: "Born", value: "১২/০৩/১৯৯০", bn: true, stamp: true },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      },
      {
        id: "bank_form", type: "Account Opening Form (sample)", bn: "হিসাব খোলার ফরম",
        tone: "blue",
        fields: [
          { id: "name", label: "Applicant", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father's Name", value: "Mohammad Abdul Karim" },
          { id: "dob", label: "DOB (DD/MM/YYYY)", value: "12/03/1991" },
          { id: "id_number", label: "NID Number", value: "1234567890" },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      }
    ],
    steps: [
      {
        phase: "Segment",
        text: "SAM 3.1 (via the Meta Model API) is called as a tool with concept " +
          "prompts — \"stamp\", \"signature\", \"handwritten date\", \"photo\" — and " +
          "returns field regions on all three documents. Three documents, 13 fields to review.",
        highlights: ["nid", "birth_certificate", "bank_form"], hl: "focus"
      },
      {
        phase: "Read · original",
        text: "Muse Spark Open reads each field. The bank form's date of birth " +
          "reads cleanly as <code>12/03/1991</code> and the NID's as <code>12/03/1990</code>, " +
          "but the birth certificate's date is partly covered by the office stamp: " +
          "<code>12/0?/1990</code> is the best first read.",
        highlights: ["nid:dob", "bank_form:dob", "birth_certificate:dob"], hl: "focus"
      },
      {
        phase: "Read · zoom + contrast",
        text: "Each field is re-read under perturbations. Most fields are stable, " +
          "but the birth certificate date is not: zoom reads <code>12/03/1990</code>, " +
          "contrast reads <code>12/08/1990</code>. The reads disagree — that " +
          "disagreement, not a model's confidence score, is the uncertainty signal.",
        highlights: ["birth_certificate:dob"], hl: "warn", tone: "warn"
      },
      {
        phase: "Uncertainty",
        text: "Date of birth on the birth certificate is marked <strong>uncertain</strong> " +
          "and routed to investigation. Every other field had agreeing reads and moves on.",
        highlights: ["birth_certificate:dob"], hl: "warn", tone: "warn"
      },
      {
        phase: "Investigate · mask the stamp",
        text: "The agent calls SAM 3.1 again with the prompt <code>\"stamp\"</code>, takes " +
          "the returned mask, and builds a stamp-masked copy of the certificate — " +
          "the <code>stamp_masked</code> view. Watch the stamp fade on the document.",
        highlights: ["birth_certificate:dob"], hl: "focus", stamp: "hide"
      },
      {
        phase: "Re-read · stamp_masked + zoom_tight",
        text: "Re-reading the masked copy settles the field: <code>১২/০৩/১৯৯০</code> " +
          "(Bangla digits) under both investigation views. The certificate's date " +
          "is <code>12/03/1990</code> — the stamp was hiding the 3, not an 8.",
        highlights: ["birth_certificate:dob"], hl: "good", tone: "good"
      },
      {
        phase: "Normalize",
        text: "Deterministic code canonicalizes every read: Bangla digits become " +
          "Latin (ID <code>১২৩৪৫৬৭৮৯০</code> → <code>1234567890</code>), slash dates are " +
          "parsed day-first into ISO form, and name spellings are folded to canonical tokens.",
        highlights: ["nid:id_number", "bank_form:id_number", "birth_certificate:dob"], hl: "focus"
      },
      {
        phase: "Cross-examine",
        text: "Every shared fact is compared across documents. Name: agrees. " +
          "ID number: agrees. Father's name: the bank form says <code>Mohammad Abdul Karim</code> " +
          "where the other two say <code>Abdul Karim</code> — a mismatch. Date of birth: " +
          "<code>1990-03-12</code> on the NID and the (now unmasked) certificate, but " +
          "<code>1991-03-12</code> on the bank form — one digit in the year.",
        highlights: ["bank_form:dob", "nid:dob", "birth_certificate:dob", "bank_form:father_name"],
        hl: "bad", tone: "bad"
      },
      {
        phase: "Verdict",
        text: "Two findings are pinned to their evidence regions above for the reviewer.",
        highlights: ["bank_form:dob", "bank_form:father_name"], hl: "bad",
        verdict: {
          kind: "discrepancy",
          title: "Discrepancy, needs human review",
          body: "Date of birth differs by one digit (1990 vs 1991) and the father's " +
            "name on the bank form carries an extra token. DocTrust does not decide " +
            "which document is right and never auto-rejects — a human reviewer makes " +
            "the call, with the evidence in view."
        }
      }
    ]
  },

  {
    id: "variation",
    tab: "Case B — Genuine variation",
    summary: "The same person, three legitimate surface differences: a Md./Mohammed " +
      "name variation, Bangla digits beside Latin digits, and three different date " +
      "formats. An exact-match pipeline would reject this customer; DocTrust should not.",
    documents: [
      {
        id: "nid", type: "National Identity Card (sample)", bn: "জাতীয় পরিচয় পত্র",
        tone: "green", photo: true,
        fields: [
          { id: "name", label: "Name", value: "Md. Abdul Rahman" },
          { id: "father_name", label: "Father", value: "Abdul Karim" },
          { id: "dob", label: "Date of Birth", value: "12/03/1990" },
          { id: "id_number", label: "ID No", value: "১২৩৪৫৬৭৮৯০", bn: true }
        ]
      },
      {
        id: "birth_certificate", type: "Birth Certificate (sample)", bn: "জন্ম সনদ",
        tone: "cream",
        fields: [
          { id: "name", label: "Name", value: "মোহাম্মদ আব্দুল রহমান", bn: true },
          { id: "father_name", label: "Father", value: "আব্দুল করিম", bn: true },
          { id: "dob", label: "Born", value: "১২/০৩/১৯৯০", bn: true },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      },
      {
        id: "bank_form", type: "Account Opening Form (sample)", bn: "হিসাব খোলার ফরম",
        tone: "blue",
        fields: [
          { id: "name", label: "Applicant", value: "Mohammed Abdul Rahaman" },
          { id: "father_name", label: "Father's Name", value: "Abdul Karim" },
          { id: "dob", label: "DOB", value: "12 March 1990" },
          { id: "id_number", label: "NID Number", value: "1234567890" },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      }
    ],
    steps: [
      {
        phase: "Segment",
        text: "SAM 3.1 locates the stamp region on the certificate — the region the " +
          "agent masks if an occluded field needs an investigation re-read. The " +
          "reader reads named fields from each document view. Three documents, " +
          "13 fields — and almost every shared field is written differently somewhere.",
        highlights: ["nid", "birth_certificate", "bank_form"], hl: "focus"
      },
      {
        phase: "Read · original + perturbations",
        text: "Muse Spark Open reads every field three times (original, zoom, contrast). " +
          "Within each document the reads agree — no field is marked uncertain, so no " +
          "investigation views are needed in this set.",
        highlights: ["nid:name", "birth_certificate:name", "bank_form:name"], hl: "focus"
      },
      {
        phase: "Normalize · names",
        text: "Transliteration-aware folding, not string equality: <code>Md.</code> → " +
          "<code>mohammad</code>, <code>Mohammed</code> → <code>mohammad</code>, " +
          "<code>Rahaman</code> → <code>rahman</code>, and the certificate's Bangla name " +
          "is read in Latin transliteration. All three names canonicalize to the " +
          "same tokens: <code>mohammad abdul rahman</code>.",
        highlights: ["nid:name", "birth_certificate:name", "bank_form:name"], hl: "good", tone: "good"
      },
      {
        phase: "Normalize · digits and dates",
        text: "Bangla digits convert to Latin: the NID number <code>১২৩৪৫৬৭৮৯০</code> becomes " +
          "<code>1234567890</code>, matching the form digit for digit. Dates parse day-first: " +
          "<code>12/03/1990</code>, <code>১২/০৩/১৯৯০</code> and <code>12 March 1990</code> all " +
          "become <code>1990-03-12</code>.",
        highlights: ["nid:id_number", "bank_form:id_number", "nid:dob", "birth_certificate:dob", "bank_form:dob"],
        hl: "good", tone: "good"
      },
      {
        phase: "Cross-examine",
        text: "After normalization every shared fact agrees. The comparator records the " +
          "name as a <strong>variant</strong> finding — same person, different " +
          "transliteration — not a mismatch. An exact-match baseline would have flagged " +
          "the name, the ID's digit system, and the date format on this genuine set.",
        highlights: ["nid:name", "bank_form:name"], hl: "good", tone: "good"
      },
      {
        phase: "Verdict",
        text: "No discrepancy findings. The variant finding stays visible in the " +
          "evidence so the reviewer can see exactly why the set passed.",
        highlights: [], hl: "good",
        verdict: {
          kind: "consistent",
          title: "Consistent",
          body: "Name variation, mixed Bangla/Latin digits, and different date " +
            "formats all resolve to the same underlying facts after deterministic " +
            "normalization. Legitimate variation is not a discrepancy — this is " +
            "the false rejection DocTrust exists to prevent."
        }
      }
    ]
  },

  {
    id: "degraded",
    tab: "Case C — Degraded capture",
    summary: "A glare-lit, blurred phone capture. Some fields cannot be read under " +
      "any view — and a field that cannot be read is never treated as a discrepancy.",
    documents: [
      {
        id: "nid", type: "National Identity Card (sample)", bn: "জাতীয় পরিচয় পত্র",
        tone: "green", photo: true,
        fields: [
          { id: "name", label: "Name", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father", value: "Abdul Karim" },
          { id: "dob", label: "Date of Birth", value: "12/03/1990" },
          { id: "id_number", label: "ID No", value: "১২৩৪৫৬৭৮৯০", bn: true, fx: "glare", fxTag: "glare" }
        ]
      },
      {
        id: "birth_certificate", type: "Birth Certificate (sample)", bn: "জন্ম সনদ",
        tone: "cream",
        fields: [
          { id: "name", label: "Name", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father", value: "আব্দুল করিম", bn: true },
          { id: "dob", label: "Born", value: "১২/০৩/১৯৯০", bn: true },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      },
      {
        id: "bank_form", type: "Account Opening Form (sample)", bn: "হিসাব খোলার ফরম",
        tone: "blue",
        fields: [
          { id: "name", label: "Applicant", value: "Mohammad Abdul Rahman" },
          { id: "father_name", label: "Father's Name", value: "Abdul Karim" },
          { id: "dob", label: "DOB (DD/MM/YYYY)", value: "12/03/1990", fx: "blur", fxTag: "blurred photo" },
          { id: "id_number", label: "NID Number", value: "1234567890", fx: "blur", fxTag: "blurred photo" },
          { id: "address", label: "Address", value: "House 12, Rajshahi, Bangladesh" }
        ]
      }
    ],
    steps: [
      {
        phase: "Segment",
        text: "SAM 3.1 checks the set for a stamp to mask and finds none. Two capture " +
          "problems are visible before any reading: a glare patch across the NID " +
          "number, and motion blur over the bank form's lower rows.",
        highlights: ["nid:id_number", "bank_form:dob", "bank_form:id_number"], hl: "warn", tone: "warn"
      },
      {
        phase: "Read · original",
        text: "Names and father's names read fine, and the dates on the NID and the " +
          "certificate agree. But the NID number under the glare and both blurred " +
          "form fields return <code>UNREADABLE</code> — the reader is not asked to guess.",
        highlights: ["nid:id_number", "bank_form:dob", "bank_form:id_number"], hl: "warn", tone: "warn"
      },
      {
        phase: "Read · zoom + contrast",
        text: "Perturbation reads agree with the first pass in the worst way: the " +
          "same three fields come back <code>UNREADABLE</code> under zoom and under " +
          "contrast. With no readable value at all, the fields route to investigation.",
        highlights: ["nid:id_number", "bank_form:dob", "bank_form:id_number"], hl: "warn", tone: "warn"
      },
      {
        phase: "Investigate · stamp_masked + zoom_tight",
        text: "There is no stamp to mask here — the segmenter finds no occluding " +
          "stamp, so the masked view changes nothing, and <code>zoom_tight</code> " +
          "cannot recover digits that the camera never captured. The fields stay " +
          "unreadable after investigation, exactly as the loop is designed to leave them.",
        highlights: ["nid:id_number", "bank_form:id_number"], hl: "warn", tone: "warn"
      },
      {
        phase: "Cross-examine",
        text: "Everything that could be read agrees across the set — name, father's " +
          "name, and date of birth all match after normalization. But the ID number " +
          "exists in only one readable copy, so it cannot be cross-examined. The " +
          "comparator records it as an <strong>unreadable</strong> finding, never a mismatch: " +
          "a bad photo is not evidence against an applicant.",
        highlights: ["nid:id_number", "bank_form:id_number"], hl: "warn", tone: "warn"
      },
      {
        phase: "Verdict",
        text: "The review cannot complete on this capture, and the reason is the " +
          "photograph, not the person.",
        highlights: [], hl: "warn",
        verdict: {
          kind: "unreadable",
          title: "Unreadable, request recapture",
          body: "The ID number could not be read under any view, so the set cannot " +
            "be cross-examined. The applicant is asked to re-photograph the documents " +
            "— flatter light, no glare — and resubmit. Nothing here is flagged as a " +
            "discrepancy."
        }
      }
    ]
  }
];
