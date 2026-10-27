/* DocTrust demo — Upload (judge mode).
 *
 * The judge downloads a synthetic case pack from the backend, uploads
 * the three images, and watches the agent's trace stream in live over
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

  // Backend base URL. Default is a local backend; the deployed Modal
  // URL (see modal_backend/README.md) can be pasted into the Backend
  // URL field on the page and is persisted to localStorage.
  var DEFAULT_BACKEND_URL = "http://localhost:8000";
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
        ". Start it locally (uvicorn app.main:app in backend/) or deploy " +
        "it (modal_backend/README.md) — the cached cases keep working " +
        "either way.";
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
  var noticeEl = document.getElementById("uploadNotice");
  var verdictEl = document.getElementById("liveVerdict");
  var verdictTitle = document.getElementById("liveVerdictTitle");
  var verdictBody = document.getElementById("liveVerdictBody");
  var fieldsPanel = document.getElementById("fieldsPanel");
  var fieldsTable = document.getElementById("fieldsTable");
  var evidencePanel = document.getElementById("evidencePanel");
  var evidenceGrid = document.getElementById("evidenceGrid");
  var eventSource = null;

  function showNotice(text) {
    noticeEl.textContent = text;
    noticeEl.hidden = false;
  }
  function resetRun() {
    traceEl.innerHTML = "";
    verdictEl.hidden = true;
    noticeEl.hidden = true;
    fieldsPanel.hidden = true;
    evidencePanel.hidden = true;
    fieldsTable.innerHTML = "";
    evidenceGrid.innerHTML = "";
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
    var phase = document.createElement("span");
    phase.className = "phase";
    phase.textContent = event.phase || event.type;
    var p = document.createElement("p");
    p.textContent = event.text || "";
    li.appendChild(phase);
    li.appendChild(p);
    traceEl.appendChild(li);
  }

  function renderResult(result) {
    // Fields table
    var docs = result.documents || {};
    var docNames = Object.keys(docs);
    if (docNames.length) {
      var html = "";
      docNames.forEach(function (doc) {
        html += "<h3 class='fields-doc'>" +
          (DOC_LABELS[doc] || doc) + "</h3><table class='fields-table'>" +
          "<tr><th>Field</th><th>Read value</th><th>Canonical</th>" +
          "<th>Views</th></tr>";
        Object.keys(docs[doc]).forEach(function (field) {
          var fr = docs[doc][field];
          var views = (fr.reads || []).map(function (r) {
            return r.view + ": " + (r.value || "UNREADABLE");
          }).join(" · ");
          html += "<tr><td>" + field + (fr.uncertain
            ? " <span class='uncertain-tag'>uncertain</span>" : "") +
            "</td><td>" + (fr.value || "— unreadable —") + "</td><td>" +
            (fr.canonical || "") + "</td><td class='views-cell'>" +
            views + "</td></tr>";
        });
        html += "</table>";
      });
      fieldsTable.innerHTML = html;
      fieldsPanel.hidden = false;
    }
    // Evidence images
    var evidence = result.evidence || [];
    if (evidence.length) {
      evidenceGrid.innerHTML = evidence.map(function (e) {
        return "<figure class='evidence-item'><img src='" + e.data_url +
          "' alt=''><figcaption>" +
          (DOC_LABELS[e.doc_type] || e.doc_type) + " · " + e.view +
          "</figcaption></figure>";
      }).join("");
      evidencePanel.hidden = false;
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

  runBtn.addEventListener("click", function () {
    var missing = DOC_TYPES.filter(function (d) { return !files[d]; });
    if (missing.length) {
      showNotice("Choose all three documents first — missing: " +
        missing.map(function (d) { return DOC_LABELS[d]; }).join(", ") +
        ". Download a case pack above if you need synthetic documents.");
      return;
    }
    resetRun();
    runBtn.disabled = true;
    runStatus.textContent = "Uploading…";
    var base = backendUrl();
    var form = new FormData();
    DOC_TYPES.forEach(function (d) { form.append(d, files[d]); });

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
        if (eventSource) { eventSource.close(); }
        eventSource = new EventSource(
          base + "/api/review/" + job.job_id + "/events");
        eventSource.addEventListener("trace", function (ev) {
          try { addTrace(JSON.parse(ev.data)); } catch (e) { /* ignore */ }
        });
        eventSource.addEventListener("done", function (ev) {
          eventSource.close();
          var done = {};
          try { done = JSON.parse(ev.data); } catch (e) { /* ignore */ }
          fetch(base + "/api/review/" + job.job_id)
            .then(function (r) { return r.json(); })
            .then(function (result) {
              runBtn.disabled = false;
              if (done.state === "reader_not_configured" ||
                  result.state === "reader_not_configured") {
                runStatus.textContent = "Finished — reader not configured.";
                showNotice("The backend ran preprocessing and segmentation " +
                  "but has NO vision reader configured, so no fields were " +
                  "read and no verdict was produced. Nothing here is faked: " +
                  "configure BASETEN_API_KEY on the backend (see " +
                  "modal_backend/README.md) and run again — or use the " +
                  "cached cases to see a full run.");
                if (result.evidence && result.evidence.length) {
                  renderResult(result);
                }
              } else if (done.state === "failed") {
                runStatus.textContent = "Run failed.";
                showNotice("The backend reported a failure: " +
                  (result.message || done.message || "unknown error"));
              } else {
                runStatus.textContent = "Done.";
                renderResult(result);
              }
            })
            .catch(function () {
              runBtn.disabled = false;
              runStatus.textContent = "Could not fetch the result.";
            });
        });
        eventSource.onerror = function () {
          // EventSource also fires this when the stream ends normally on
          // some browsers; only complain if we never saw 'done'.
          if (runBtn.disabled && runStatus.textContent.indexOf("Running") === 0) {
            runStatus.textContent = "Stream interrupted.";
          }
        };
      })
      .catch(function (err) {
        runBtn.disabled = false;
        runStatus.textContent = "Backend unreachable.";
        showNotice("Could not run the review: " + err.message +
          ". No live run was simulated. Check the Backend URL above, or " +
          "switch back to the cached cases.");
      });
  });
})();
