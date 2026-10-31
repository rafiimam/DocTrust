/* DocTrust demo — Upload (judge mode).
 *
 * The judge downloads a synthetic case pack from the backend, uploads
 * the images (any subset — at least one), and watches the agent's trace stream in live over
 * Server-Sent Events. This mode is honest by construction:
 * - if the backend cannot be reached, it says so and points back to
 *   the cached cases — it never simulates a live run;
 * - if the backend answers reader_not_configured, it shows exactly
 *   that (the preprocessing/segmentation evidence only, no verdict);
 * - uploads are synthetic SPECIMEN documents only, and the page says
 *   so before the file inputs.
 */
(function () {
  "use strict";

  // Backend base URL. Default is the hosted backend on Modal, so
  // judge mode works out of the box. A different backend — e.g. a local
  // one for development — can be pasted into the Backend URL field on
  // the page and is persisted to localStorage.
  var DEFAULT_BACKEND_URL =
    "https://rafiimam96--doctrust-backend-fastapi-app.us-east.modal.run";
  var STORAGE_KEY = "doctrustBackendUrl";
  var DOC_TYPES = ["nid", "birth_certificate", "bank_form"];
  var DOC_LABELS = {
    nid: "National ID",
    birth_certificate: "Birth certificate",
    bank_form: "Bank form"
  };
  var VERDICT_KIND = {
    CONSISTENT: "consistent",
    DISCREPANCY: "discrepancy",
    UNREADABLE: "unreadable"
  };
  var GAP_KIND_LABELS = {
    missing_document: "Missing document",
    unresolved_field: "Unresolved field",
    unresolved_discrepancy: "Unresolved discrepancy"
  };

  function backendUrl() {
    var v = (localStorage.getItem(STORAGE_KEY) || DEFAULT_BACKEND_URL)
      .replace(/\/+$/, "");
    return v || DEFAULT_BACKEND_URL;
  }

  // --- Mode toggle ------------------------------------------------------
  var cachedMain = document.getElementById("cachedMain");
  var uploadMain = document.getElementById("uploadMain");
  var cachedBtn = document.getElementById("modeCachedBtn");
  var uploadBtn = document.getElementById("modeUploadBtn");
  var badge = document.getElementById("modeBadge");

  function setMode(upload) {
    cachedMain.hidden = upload;
    uploadMain.hidden = !upload;
    cachedBtn.setAttribute("aria-selected", upload ? "false" : "true");
    uploadBtn.setAttribute("aria-selected", upload ? "true" : "false");
    badge.textContent = upload ? "Judge mode" : "Demo mode";
    badge.classList.toggle("badge-live", upload);
    if (upload) { checkBackend(); }
  }
  cachedBtn.addEventListener("click", function () { setMode(false); });
  uploadBtn.addEventListener("click", function () { setMode(true); });

  // --- Backend URL setting ----------------------------------------------
  var urlInput = document.getElementById("backendUrl");
  var statusEl = document.getElementById("backendStatus");
  urlInput.value = backendUrl();

  function refreshPackLinks() {
    var base = backendUrl();
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-pack]"), function (a) {
        a.href = base + "/api/case-pack/" + a.getAttribute("data-pack");
      });
  }
  refreshPackLinks();

  document.getElementById("backendSaveBtn").addEventListener("click",
    function () {
      var v = urlInput.value.trim().replace(/\/+$/, "");
      if (v) { localStorage.setItem(STORAGE_KEY, v); }
      urlInput.value = backendUrl();
      refreshPackLinks();
      checkBackend();
    });

  function checkBackend() {
    var base = backendUrl();
    statusEl.textContent = "Checking " + base + " …";
    fetch(base + "/health").then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function () {
      statusEl.textContent = "Backend reachable at " + base + ".";
    }).catch(function () {
      statusEl.textContent = "Backend not reachable at " + base +
        ". The hosted backend scales to zero when idle, so it may just " +
        "be waking up — wait a few seconds and reopen Upload mode. Or " +
        "check the Backend URL above (developers can run a local " +
        "backend instead: uvicorn app.main:app in backend/). The " +
        "cached cases keep working either way.";
    });
  }

  // --- File inputs + previews --------------------------------------------
  var files = {};
  DOC_TYPES.forEach(function (doc) {
    var input = document.getElementById("file-" + doc);
    var preview = document.getElementById("preview-" + doc);
    var nameEl = document.getElementById("name-" + doc);
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      files[doc] = f || null;
      refreshRunBtn();
      if (f) {
        nameEl.textContent = f.name;
        preview.src = URL.createObjectURL(f);
        preview.hidden = false;
      } else {
        nameEl.textContent = "No file chosen";
        preview.hidden = true;
      }
    });
  });

  // --- Run ----------------------------------------------------------------
  var runBtn = document.getElementById("runBtn");
  var runStatus = document.getElementById("runStatus");
  var traceEl = document.getElementById("liveTrace");
  var verdictEl = document.getElementById("liveVerdict");
  var verdictTitle = document.getElementById("liveVerdictTitle");
  var verdictBody = document.getElementById("liveVerdictBody");
  var fieldsPanel = document.getElementById("fieldsPanel");
  var fieldsTable = document.getElementById("fieldsTable");
  var evidencePanel = document.getElementById("evidencePanel");
  var evidenceGrid = document.getElementById("evidenceGrid");
  var gapsPanel = document.getElementById("gapsPanel");
  var gapsList = document.getElementById("gapsList");
  // --- Pipeline stage tracker + live status ------------------------------
  var stageBar = document.getElementById("stageBarLive");
  var statusText = document.getElementById("agentStatusTextLive");
  var STAGE_ORDER = ["locate", "read", "investigate", "normalize", "cross", "verdict"];

  function stageForPhase(phase) {
    var p = (phase || "").split("·")[0].trim().toLowerCase();
    if (p === "segment" || p === "intake" || p === "preprocess") { return "locate"; }
    if (p.indexOf("read") === 0 || p.indexOf("re-read") === 0 || p === "uncertainty") { return "read"; }
    if (p.indexOf("investigate") === 0) { return "investigate"; }
    if (p.indexOf("normalize") === 0) { return "normalize"; }
    if (p.indexOf("cross") === 0 || p === "compare") { return "cross"; }
    if (p === "verdict") { return "verdict"; }
    return null;
  }

  function setStage(stage) {
    if (!stageBar || !stage) { return; }
    var idx = STAGE_ORDER.indexOf(stage);
    Array.prototype.forEach.call(stageBar.children, function (li) {
      var i = STAGE_ORDER.indexOf(li.getAttribute("data-stage"));
      li.classList.toggle("done", i < idx || (stage === "verdict" && i === idx));
      li.classList.toggle("active", i === idx && stage !== "verdict");
    });
  }

  function clearStages() {
    if (!stageBar) { return; }
    Array.prototype.forEach.call(stageBar.children, function (li) {
      li.classList.remove("done", "active");
    });
  }

  function setStatus(text) { if (statusText) { statusText.textContent = text; } }

  // Which part of the stack produced a step — shown as a tag on the
  // trace entry; and the agent-presence card, which narrates the run
  // from the same real events (never invented dialogue: investigation
  // suggestions are templated from the event's own field/action/reason,
  // everything else mirrors the event text).
  var TECH_BY_STAGE = {
    locate: "SAM 3.1",
    read: "Muse Spark",
    investigate: "Planner · Muse Spark",
    normalize: "Deterministic code",
    cross: "Deterministic comparator",
    verdict: "Deterministic comparator"
  };
  var cardText = document.getElementById("agentCardTextLive");
  var CARD_INTRO = "Upload a set and run a review — I'll narrate each " +
    "step here as I work: what I'm reading, where I'm unsure, and " +
    "what I suggest next.";
  var ACTION_PHRASES = {
    stamp_masked: "mask the stamp and re-read",
    zoom_tight: "re-read a tighter zoomed crop",
    recapture: "stop here and request a recapture"
  };

  function setCard(text) { if (cardText) { cardText.textContent = text; } }

  function suggestionFrom(event) {
    var text = event.text || "";
    var m = text.match(/planner chose (\S+)(?: — (.*))?$/);
    if (m) {
      return "My suggestion: " +
        (ACTION_PHRASES[m[1]] || m[1].replace(/_/g, " ")) + " — " +
        (event.field || "the field") + " on the " +
        (DOC_LABELS[event.doc_type] || event.doc_type || "document") +
        (m[2] ? ". Why: " + m[2] : "");
    }
    if (text.indexOf("fallback ran") !== -1) {
      return "The planner wasn't reachable, so I ran the standard " +
        "investigation step instead: " + text;
    }
    return text;
  }

  var eventSource = null;
  // Fallback polling state (see the onerror handler in the run flow):
  // if the SSE stream drops before 'done', the client polls the job's
  // result URL directly instead of declaring the run lost. fallbackTimer
  // holds the pending poll; runSeq identifies the current run so a stale
  // poll from a superseded run can never write into a newer run's UI.
  var fallbackTimer = null;
  var runSeq = 0;

  function stopFallbackPolling() {
    if (fallbackTimer !== null) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
  }

  // Every document is optional, but a review needs at least one: the
  // Run button stays disabled until at least one file is chosen.
  function refreshRunBtn() {
    runBtn.disabled = !DOC_TYPES.some(function (d) { return files[d]; });
  }
  refreshRunBtn();

  // Run status and errors live in the trace panel itself, so the
  // panel is never left blankly empty when something goes wrong.
  function addTraceStatus(text, tone) {
    var li = document.createElement("li");
    if (tone) { li.className = tone; }
    var phase = document.createElement("span");
    phase.className = "phase";
    phase.textContent = "Status";
    var p = document.createElement("p");
    p.textContent = text;
    li.appendChild(phase);
    li.appendChild(p);
    traceEl.appendChild(li);
    traceEl.scrollTop = traceEl.scrollHeight;
  }
  function setTraceStatus(text, tone) {
    traceEl.innerHTML = "";
    addTraceStatus(text, tone);
  }
  function resetRun() {
    stopFallbackPolling();
    runSeq += 1;
    lastResult = null;
    closeLightbox();
    traceEl.innerHTML = "";
    clearStages();
    setStatus("Starting…");
    setCard("Working — watch this space: I'll narrate each step and " +
      "flag anything I suggest checking.");
    verdictEl.hidden = true;
    fieldsPanel.hidden = true;
    evidencePanel.hidden = true;
    gapsPanel.hidden = true;
    fieldsTable.innerHTML = "";
    evidenceGrid.innerHTML = "";
    gapsList.innerHTML = "";
  }
  function addTrace(event) {
    if (event.type === "queued") { return; }
    var li = document.createElement("li");
    if (event.type === "verdict") {
      li.className = event.verdict === "DISCREPANCY" ? "tone-bad"
        : event.verdict === "UNREADABLE" ? "tone-warn" : "tone-good";
    }
    if (event.type === "reader_not_configured" || event.type === "error") {
      li.className = "tone-warn";
    }
    // Investigation decisions are the agent thinking out loud — the
    // planner (or the deterministic fallback) choosing what to do
    // next, with its reason. Give them a distinct decision card.
    if (event.type === "investigation") {
      li.classList.add("decision-card");
      var chip = document.createElement("span");
      chip.className = "decision-chip";
      chip.textContent = "Agent decision";
      li.appendChild(chip);
    }
    var phase = document.createElement("span");
    phase.className = "phase";
    phase.textContent = event.phase || event.type;
    li.appendChild(phase);
    var stage = stageForPhase(event.phase);
    if (stage && TECH_BY_STAGE[stage]) {
      var tag = document.createElement("span");
      tag.className = "tech-tag";
      tag.textContent = TECH_BY_STAGE[stage];
      li.appendChild(tag);
    }
    var p = document.createElement("p");
    p.textContent = event.text || "";
    li.appendChild(p);
    traceEl.appendChild(li);
    traceEl.scrollTop = traceEl.scrollHeight;
    setStage(stage);
    setStatus(event.phase || event.type);
    if (event.type === "investigation") {
      setCard(suggestionFrom(event));
    } else if (event.text) {
      setCard(event.text);
    }
  }

  // Job-result strings are untrusted text: field readings and gap
  // descriptions come from a model interpreting uploaded images, so a
  // crafted reading could contain HTML. Anything taken from the result
  // JSON is escaped before it is interpolated into innerHTML below.
  // (Trace lines and the verdict already render via textContent.)
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;",
               '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var lastResult = null;

  function renderResult(result) {
    lastResult = result;
    // Fields table
    var docs = result.documents || {};
    var docNames = Object.keys(docs);
    if (docNames.length) {
      var html = "";
      docNames.forEach(function (doc) {
        html += "<h3 class='fields-doc'>" +
          escapeHtml(DOC_LABELS[doc] || doc) +
          "</h3><table class='fields-table'>" +
          "<tr><th>Field</th><th>Read value</th><th>Canonical</th>" +
          "<th>Views</th></tr>";
        Object.keys(docs[doc]).forEach(function (field) {
          var fr = docs[doc][field];
          var views = (fr.reads || []).map(function (r) {
            return r.view + ": " + (r.value || "UNREADABLE");
          }).join(" · ");
          // Investigation decisions (planner-chosen steps with their
          // logged reasons, or the fallback sequence), when the field
          // needed any — rendered under the views, escaped like
          // everything else from the result JSON.
          var inv = (fr.investigation || []).map(function (d) {
            return (d.source === "planner" ? "planner" : "fallback") +
              " → " + d.action + (d.reason ? ": " + d.reason : "");
          }).join(" · ");
          html += "<tr><td>" + escapeHtml(field) + (fr.uncertain
            ? " <span class='uncertain-tag'>uncertain</span>" : "") +
            "</td><td>" + escapeHtml(fr.value || "— unreadable —") +
            "</td><td>" +
            escapeHtml(fr.canonical || "") + "</td><td class='views-cell'>" +
            escapeHtml(views) +
            (inv ? "<br><span class='investigation-line'>" +
              escapeHtml(inv) + "</span>" : "") +
            "</td></tr>";
        });
        html += "</table>";
      });
      fieldsTable.innerHTML = html;
      fieldsPanel.hidden = false;
    }
    // Evidence images — click any view to open it full size with the
    // agent's read on that document alongside (see the lightbox code).
    var evidence = result.evidence || [];
    if (evidence.length) {
      evidenceGrid.innerHTML = evidence.map(function (e, i) {
        return "<figure class='evidence-item' data-evidence-idx='" + i +
          "' tabindex='0' role='button' aria-label='View full size'><img src='" +
          escapeHtml(e.data_url) +
          "' alt=''><figcaption>" +
          escapeHtml(DOC_LABELS[e.doc_type] || e.doc_type) + " · " +
          escapeHtml(e.view) +
          "</figcaption></figure>";
      }).join("");
      evidencePanel.hidden = false;
    }
    // Evidence gaps & next steps. Only live judge results carry this
    // list; a result without the key (or with an empty list) renders
    // no section at all.
    var gaps = result.evidence_gaps || [];
    if (gaps.length) {
      gapsList.innerHTML = gaps.map(function (g) {
        return "<div class='gap-item gap-" + escapeHtml(g.kind) + "'>" +
          "<span class='gap-kind'>" +
          escapeHtml(GAP_KIND_LABELS[g.kind] || g.kind) + "</span>" +
          "<p class='gap-detail'>" + escapeHtml(g.detail) + "</p>" +
          "<p class='gap-next'><strong>Next step:</strong> " +
          escapeHtml(g.next_step) + "</p></div>";
      }).join("");
      gapsPanel.hidden = false;
    }
    // Verdict
    if (result.verdict) {
      verdictTitle.textContent = result.verdict_label || result.verdict;
      var findings = (result.findings || []).map(function (f) {
        return f.field + ": " + f.status;
      }).join(" · ");
      verdictBody.textContent = findings ||
        "Every shared fact agreed across the set.";
      verdictEl.className = "verdict verdict-" +
        (VERDICT_KIND[result.verdict] || "consistent");
      verdictEl.hidden = false;
    }
  }

  // Render a finished job. Shared by the SSE 'done' path and the
  // polling fallback, so both confirm the run in exactly the same way.
  // `done` carries the terminal state (and message, when the SSE event
  // or the polled result provided one).
  function showFinalResult(result, done) {
    refreshRunBtn();
    setStatus(!done.state || done.state === "done"
      ? "Complete" : "Finished — " + done.state);
    if (result.verdict) {
      var findingLine = (result.findings || []).map(function (f) {
        return f.field + ": " + f.status;
      }).join(" · ");
      setCard("Done — my verdict: " + (result.verdict_label ||
        result.verdict) + ". " + (findingLine ||
        "Every shared fact agreed across the set."));
    } else if (done.state === "reader_not_configured" ||
        result.state === "reader_not_configured") {
      setCard("I could preprocess and segment the set, but this " +
        "backend has no reader configured — so I read nothing and " +
        "produced no verdict, rather than pretend.");
    }
    if (done.state === "reader_not_configured" ||
        result.state === "reader_not_configured") {
      runStatus.textContent = "Finished — reader not configured.";
      addTraceStatus("The backend ran preprocessing and " +
        "segmentation but has NO vision reader configured, so " +
        "no fields were read and no verdict was produced. " +
        "Nothing here is faked: the backend needs its " +
        "server-side reader key (see modal_backend/README.md) " +
        "— or use the cached cases to see a full run.",
        "tone-warn");
      if (result.evidence && result.evidence.length) {
        renderResult(result);
      }
    } else if (done.state === "failed") {
      runStatus.textContent = "Run failed.";
      addTraceStatus("The backend reported a failure: " +
        (result.message || done.message || "unknown error"),
        "tone-bad");
    } else {
      runStatus.textContent = "Done.";
      renderResult(result);
    }
  }

  runBtn.addEventListener("click", function () {
    var chosen = DOC_TYPES.filter(function (d) { return files[d]; });
    if (!chosen.length) {
      setTraceStatus("Choose at least one document first — each one " +
        "is optional, but a review needs at least one. Download a case " +
        "pack above if you need synthetic documents.", "tone-warn");
      runStatus.textContent = "No files chosen — see the trace panel.";
      return;
    }
    var missing = DOC_TYPES.filter(function (d) { return !files[d]; });
    resetRun();
    var myRun = runSeq;
    runBtn.disabled = true;
    runStatus.textContent = "Uploading…";
    var base = backendUrl();
    setTraceStatus("Uploading " + chosen.length + " of the three " +
      "documents to " + base + " …" + (missing.length
        ? " Not uploaded: " + missing.map(function (d) {
            return DOC_LABELS[d];
          }).join(", ") + " — the result will report them as evidence " +
          "gaps, not errors."
        : ""));
    var form = new FormData();
    chosen.forEach(function (d) { form.append(d, files[d]); });

    fetch(base + "/api/review", { method: "POST", body: form })
      .then(function (r) {
        if (!r.ok) {
          return r.text().then(function (t) {
            throw new Error("HTTP " + r.status + " — " + t.slice(0, 200));
          });
        }
        return r.json();
      })
      .then(function (job) {
        runStatus.textContent = "Running — trace streaming…";
        var resultUrl = base + "/api/review/" + job.job_id;
        var sawDone = false;
        var fallbackStarted = false;
        if (eventSource) { eventSource.close(); }
        eventSource = new EventSource(resultUrl + "/events");
        eventSource.addEventListener("trace", function (ev) {
          try { addTrace(JSON.parse(ev.data)); } catch (e) { /* ignore */ }
        });
        eventSource.addEventListener("done", function (ev) {
          sawDone = true;
          stopFallbackPolling();
          eventSource.close();
          var done = {};
          try { done = JSON.parse(ev.data); } catch (e) { /* ignore */ }
          fetch(resultUrl)
            .then(function (r) { return r.json(); })
            .then(function (result) { showFinalResult(result, done); })
            .catch(function () {
              refreshRunBtn();
              runStatus.textContent = "Could not fetch the result.";
              addTraceStatus("The run finished but its result could " +
                "not be fetched from the backend.", "tone-warn");
            });
        });
        // If the stream drops before 'done', the run itself is usually
        // still fine — only the stream was lost — so fall back to
        // polling the result URL directly (~every 4 s, ~4 min max)
        // before declaring the run interrupted.
        var POLL_INTERVAL_MS = 4000;
        var POLL_MAX_ATTEMPTS = 60;
        function schedulePoll(attempt) {
          if (myRun !== runSeq) { return; }
          if (attempt >= POLL_MAX_ATTEMPTS) {
            refreshRunBtn();
            runStatus.textContent = "Stream interrupted.";
            addTraceStatus("The live event stream was interrupted " +
              "before the run finished, and the result could not be " +
              "confirmed directly either.", "tone-warn");
            return;
          }
          fallbackTimer = setTimeout(function () {
            fallbackTimer = null;
            pollResult(attempt);
          }, POLL_INTERVAL_MS);
        }
        function pollResult(attempt) {
          if (myRun !== runSeq) { return; }
          fetch(resultUrl)
            .then(function (r) { return r.json(); })
            .then(function (result) {
              if (myRun !== runSeq) { return; }
              var state = result && result.state;
              if (state === "done" || state === "reader_not_configured" ||
                  state === "failed" || state === "error") {
                sawDone = true;
                stopFallbackPolling();
                if (eventSource) { eventSource.close(); }
                showFinalResult(result, {
                  state: state === "error" ? "failed" : state,
                  message: result.message
                });
              } else {
                schedulePoll(attempt + 1);
              }
            })
            .catch(function () { schedulePoll(attempt + 1); });
        }
        eventSource.onerror = function () {
          // EventSource also fires this when the stream ends normally on
          // some browsers; only react if we never saw 'done', the
          // fallback is not already running, and this stream still
          // belongs to the current run.
          if (myRun !== runSeq || sawDone || fallbackStarted ||
              !runBtn.disabled) {
            return;
          }
          fallbackStarted = true;
          runStatus.textContent =
            "Stream interrupted — checking result…";
          addTraceStatus("The live event stream was interrupted — " +
            "checking the run result directly…", "tone-warn");
          pollResult(0);
        };
      })
      .catch(function (err) {
        refreshRunBtn();
        runStatus.textContent = "Backend unreachable.";
        setTraceStatus("Could not run the review: " + err.message +
          ". No live run was simulated. Check the Backend URL above, or " +
          "switch back to the cached cases.", "tone-warn");
      });
  });

  // --- Evidence lightbox ---------------------------------------------------
  // Clicking an evidence view opens it full size; the sidebar shows
  // the agent's read on that document — its field values, the
  // comparator findings it takes part in, any planner decisions about
  // it, and reviewer guidance derived deterministically from those
  // results (an explicit all-clear when nothing is wrong). Everything
  // is built with textContent: result strings are untrusted model
  // output and are never interpolated into HTML here.
  var lightbox = document.getElementById("evidenceLightbox");
  var lightboxImg = document.getElementById("lightboxImg");
  var lightboxCaption = document.getElementById("lightboxCaption");
  var lightboxAdvice = document.getElementById("lightboxAdvice");

  var FINDING_LABELS = {
    match: "Agrees with the set",
    variant: "Variant — same person, different spelling",
    mismatch: "DISAGREES with the set",
    unreadable: "Could not be read",
    single_source: "Only readable source in the set"
  };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  function closeLightbox() {
    if (lightbox) { lightbox.hidden = true; }
    if (lightboxImg) { lightboxImg.removeAttribute("src"); }
  }

  function buildAdvice(docType, viewName) {
    var box = lightboxAdvice;
    box.innerHTML = "";
    var result = lastResult || {};
    var docLabel = DOC_LABELS[docType] || docType;

    // Overall verdict for the set this evidence belongs to.
    if (result.verdict) {
      var v = el("div", "lb-verdict lb-verdict-" +
        (VERDICT_KIND[result.verdict] || "consistent"));
      v.appendChild(el("span", "lb-verdict-label",
        result.verdict_label || result.verdict));
      v.appendChild(el("span", "lb-verdict-sub",
        " — overall verdict for this document set"));
      box.appendChild(v);
    }
    box.appendChild(el("p", "lb-context",
      "You are viewing the " + viewName + " view of the " + docLabel +
      " — one of the views the agent actually read."));

    // What the agent read on this document, with the comparator's
    // finding for each field it shares with the set.
    var fields = (result.documents || {})[docType] || {};
    var findings = result.findings || [];
    function findingFor(field) {
      for (var i = 0; i < findings.length; i++) {
        var f = findings[i];
        if (f.field !== field) { continue; }
        if (f.values && !(docType in f.values)) { continue; }
        return f;
      }
      return null;
    }
    var fieldNames = Object.keys(fields);
    if (fieldNames.length) {
      box.appendChild(el("h4", "lb-h", "What the agent read here"));
      fieldNames.forEach(function (field) {
        var fr = fields[field];
        var row = el("div", "lb-field");
        var head = el("div", "lb-field-head");
        head.appendChild(el("span", "lb-field-name", field));
        var f = findingFor(field);
        if (f) {
          head.appendChild(el("span",
            "lb-finding lb-finding-" + f.status,
            FINDING_LABELS[f.status] || f.status));
        } else if (fr.uncertain) {
          head.appendChild(el("span", "lb-finding lb-finding-unreadable",
            "Uncertain reads"));
        }
        row.appendChild(head);
        row.appendChild(el("div", "lb-field-value",
          fr.value || "— unreadable —"));
        (fr.investigation || []).forEach(function (d) {
          row.appendChild(el("div", "lb-investigation",
            (d.source === "planner" ? "Agent decision" : "Fallback step") +
            " → " + d.action + (d.reason ? " — " + d.reason : "")));
        });
        box.appendChild(row);
      });
    }

    // Reviewer guidance, derived from this document's findings.
    var mismatched = findings.filter(function (f) {
      return f.status === "mismatch" &&
        (!f.values || docType in f.values) && fields[f.field];
    });
    var unreadable = findings.filter(function (f) {
      return f.status === "unreadable" &&
        (!f.values || docType in f.values) && fields[f.field];
    });
    var docGaps = (result.evidence_gaps || []).filter(function (g) {
      return (g.detail || "").indexOf(docLabel) !== -1;
    });
    var advice = el("div", "lb-advice");
    if (mismatched.length) {
      advice.classList.add("lb-advice-bad");
      advice.appendChild(el("strong", null, "Reviewer guidance: "));
      advice.appendChild(document.createTextNode(
        "this document disagrees with the rest of the set on " +
        mismatched.map(function (f) { return f.field; }).join(", ") +
        ". Compare the values side by side in “What the agent read” " +
        "before deciding — the set is flagged for human review, " +
        "never auto-rejected."));
    } else if (unreadable.length || fieldNames.some(function (n) {
      return fields[n].uncertain;
    })) {
      advice.classList.add("lb-advice-warn");
      advice.appendChild(el("strong", null, "Reviewer guidance: "));
      advice.appendChild(document.createTextNode(
        "some fields on this document could not be read reliably. " +
        "That is a capture problem, not evidence against the " +
        "applicant — the next step is a clearer re-capture of this " +
        "document."));
    } else if (docGaps.length) {
      advice.classList.add("lb-advice-warn");
      advice.appendChild(el("strong", null, "Reviewer guidance: "));
      advice.appendChild(document.createTextNode(
        docGaps[0].detail + " Next step: " + docGaps[0].next_step));
    } else {
      advice.classList.add("lb-advice-good");
      advice.appendChild(el("strong", null, "All clear on this document: "));
      advice.appendChild(document.createTextNode(
        "every shared fact read here agrees with the rest of the set " +
        "after normalization. Nothing on the " + docLabel +
        " needs reviewer action."));
    }
    box.appendChild(advice);
  }

  function openLightbox(evidenceItem) {
    if (!evidenceItem) { return; }
    lightboxImg.src = evidenceItem.data_url;
    lightboxCaption.textContent =
      (DOC_LABELS[evidenceItem.doc_type] || evidenceItem.doc_type) +
      " · " + evidenceItem.view + " view — as read by the agent";
    buildAdvice(evidenceItem.doc_type, evidenceItem.view);
    lightbox.hidden = false;
    var closeBtn = document.getElementById("lightboxClose");
    if (closeBtn) { closeBtn.focus(); }
  }

  evidenceGrid.addEventListener("click", function (ev) {
    var fig = ev.target.closest("[data-evidence-idx]");
    if (!fig || !lastResult) { return; }
    openLightbox((lastResult.evidence || [])[
      Number(fig.getAttribute("data-evidence-idx"))]);
  });
  evidenceGrid.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter") { return; }
    var fig = ev.target.closest("[data-evidence-idx]");
    if (!fig || !lastResult) { return; }
    openLightbox((lastResult.evidence || [])[
      Number(fig.getAttribute("data-evidence-idx"))]);
  });
  document.getElementById("lightboxClose")
    .addEventListener("click", closeLightbox);
  document.getElementById("lightboxBackdrop")
    .addEventListener("click", closeLightbox);
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && lightbox && !lightbox.hidden) {
      closeLightbox();
    }
  });
})();
