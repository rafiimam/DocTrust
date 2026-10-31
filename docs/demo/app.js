/* DocTrust demo — trace replay engine.
 *
 * Renders a cached case (cases.js) as styled document cards and replays
 * the agent's trace step by step. Each trace step highlights the fields
 * it talks about; the stamp step in Case A fades the stamp overlay the
 * way the stamp_masked investigation view removes it. No network calls,
 * no model — this is a replay, and the page says so.
 */
(function () {
  "use strict";

  var cases = window.DOCTRUST_CASES || [];
  var state = { caseIndex: 0, step: -1, playing: false, timer: null, delay: 1500 };

  var pickerEl = document.getElementById("casePicker");
  var summaryEl = document.getElementById("caseSummary");
  var docsEl = document.getElementById("docs");
  var traceEl = document.getElementById("trace");
  var verdictEl = document.getElementById("verdict");
  var verdictTitleEl = document.getElementById("verdictTitle");
  var verdictBodyEl = document.getElementById("verdictBody");
  var playBtn = document.getElementById("playBtn");
  var stepBtn = document.getElementById("stepBtn");
  var resetBtn = document.getElementById("resetBtn");
  var progressEl = document.getElementById("progress");

  // --- Pipeline stage tracker + live status ------------------------------
  var stageBar = document.getElementById("stageBarCached");
  var statusText = document.getElementById("agentStatusTextCached");
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
  // trace entry and used to brief the agent-presence card.
  var TECH_BY_STAGE = {
    locate: "SAM 3.1",
    read: "Muse Spark",
    investigate: "Planner · Muse Spark",
    normalize: "Deterministic code",
    cross: "Deterministic comparator",
    verdict: "Deterministic comparator"
  };
  var cardText = document.getElementById("agentCardTextCached");
  var CARD_INTRO = "Press Play and I'll walk you through this set — what I " +
    "read, where I'm unsure, and what I suggest checking next.";

  function plainText(html) {
    var tmp = document.createElement("div");
    tmp.innerHTML = html || "";
    return tmp.textContent || "";
  }

  function setCard(text) { if (cardText) { cardText.textContent = text; } }

  function currentCase() { return cases[state.caseIndex]; }

  function fieldHTML(field) {
    var cls = "fvalue" + (field.bn ? " bn" : "");
    var inner = '<span class="' + cls + '">' + field.value + "</span>";
    if (field.fxTag) {
      inner += '<span class="degraded-tag">(' + field.fxTag + ")</span>";
    }
    if (field.fx === "glare") {
      inner += '<span class="glare" aria-hidden="true"></span>';
    }
    var hostCls = "field" + (field.fx === "blur" ? " blurred" : "") +
      (field.stamp ? " stamp-host" : "");
    var stamp = field.stamp
      ? '<span class="stamp" data-stamp>OFFICE STAMP</span>' +
        '<span class="mask-note">masked by SAM 3.1</span>'
      : "";
    return '<div class="' + hostCls + '" data-field="' + field.id + '">' +
      '<span class="flabel">' + field.label + "</span>" +
      '<span class="fwrap">' + inner + stamp + "</span></div>";
  }

  function docHTML(doc) {
    var fields = doc.fields.map(fieldHTML).join("");
    var photo = doc.photo ? '<div class="photo-box">PHOTO</div>' : "";
    return '<article class="doc-card tone-' + doc.tone + '" data-doc="' + doc.id + '">' +
      '<div class="doc-head"><span class="doc-title">' + doc.type +
      "<small>" + doc.bn + '</small></span><span class="specimen-chip">SPECIMEN</span></div>' +
      '<div class="doc-body">' + photo + '<div class="fields">' + fields +
      "</div></div></article>";
  }

  function renderCase() {
    var c = currentCase();
    summaryEl.textContent = c.summary;
    docsEl.innerHTML = c.documents.map(docHTML).join("");
    Array.prototype.forEach.call(pickerEl.children, function (btn, i) {
      btn.setAttribute("aria-selected", i === state.caseIndex ? "true" : "false");
    });
    resetReplay();
  }

  function clearHighlights() {
    Array.prototype.forEach.call(
      docsEl.querySelectorAll(".hl-focus,.hl-warn,.hl-bad,.hl-good"),
      function (el) {
        el.classList.remove("hl-focus", "hl-warn", "hl-bad", "hl-good");
      });
  }

  function highlight(ref, hl) {
    var parts = ref.split(":");
    var sel = parts.length === 2
      ? '[data-doc="' + parts[0] + '"] [data-field="' + parts[1] + '"]'
      : '[data-doc="' + parts[0] + '"]';
    var el = docsEl.querySelector(sel);
    if (el) { el.classList.add("hl-" + (hl || "focus")); }
  }

  function setStamp(masked) {
    Array.prototype.forEach.call(docsEl.querySelectorAll("[data-stamp]"),
      function (el) { el.classList.toggle("masked", masked); });
    Array.prototype.forEach.call(docsEl.querySelectorAll(".stamp-host"),
      function (el) { el.classList.toggle("masked", masked); });
  }

  function updateProgress() {
    var total = currentCase().steps.length;
    var shown = Math.max(state.step + 1, 0);
    progressEl.textContent = "Step " + shown + " / " + total;
    stepBtn.disabled = state.step >= total - 1;
  }

  function applyStep(i) {
    var c = currentCase();
    var step = c.steps[i];
    if (!step) { return; }
    state.step = i;
    clearHighlights();
    (step.highlights || []).forEach(function (ref) { highlight(ref, step.hl); });
    if (step.stamp === "hide") { setStamp(true); }
    if (step.stamp === "show") { setStamp(false); }

    var li = document.createElement("li");
    if (step.tone) { li.className = "tone-" + step.tone; }
    var stage = stageForPhase(step.phase);
    if (stage === "investigate") {
      li.classList.add("decision-card");
      var chip = document.createElement("span");
      chip.className = "decision-chip";
      chip.textContent = "Agent suggestion";
      li.appendChild(chip);
    }
    var phase = document.createElement("span");
    phase.className = "phase";
    phase.textContent = step.phase;
    li.appendChild(phase);
    if (stage && TECH_BY_STAGE[stage]) {
      var tag = document.createElement("span");
      tag.className = "tech-tag";
      tag.textContent = TECH_BY_STAGE[stage];
      li.appendChild(tag);
    }
    var p = document.createElement("p");
    p.innerHTML = step.text;
    li.appendChild(p);
    traceEl.appendChild(li);
    traceEl.scrollTop = traceEl.scrollHeight;
    setStage(stage);
    setStatus(step.phase);
    var narration = plainText(step.text);
    setCard(stage === "investigate" ? "My suggestion: " + narration : narration);

    if (step.verdict) {
      verdictTitleEl.textContent = step.verdict.title;
      verdictBodyEl.textContent = step.verdict.body;
      verdictEl.className = "verdict verdict-" + step.verdict.kind;
      verdictEl.hidden = false;
    }
    updateProgress();
  }

  function stopPlaying() {
    state.playing = false;
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    playBtn.textContent = "▶ Play";
  }

  function startPlaying() {
    if (state.step >= currentCase().steps.length - 1) { resetReplay(); }
    state.playing = true;
    playBtn.textContent = "⏸ Pause";
    state.timer = setInterval(function () {
      if (state.step >= currentCase().steps.length - 1) { stopPlaying(); return; }
      applyStep(state.step + 1);
      if (state.step >= currentCase().steps.length - 1) { stopPlaying(); }
    }, state.delay);
  }

  function resetReplay() {
    stopPlaying();
    state.step = -1;
    traceEl.innerHTML = '<li class="trace-empty" style="border:none;background:none;">' +
      "Press Play (or Step) to replay the agent's cross-examination of this set.</li>";
    verdictEl.hidden = true;
    clearHighlights();
    clearStages();
    setStatus("Idle — press Play to replay the run");
    setCard(CARD_INTRO);
    setStamp(false);
    updateProgress();
  }

  // Case picker tabs
  cases.forEach(function (c, i) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "case-tab";
    btn.textContent = c.tab;
    btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
    btn.addEventListener("click", function () {
      state.caseIndex = i;
      renderCase();
    });
    pickerEl.appendChild(btn);
  });

  playBtn.addEventListener("click", function () {
    if (state.playing) { stopPlaying(); } else { startPlaying(); }
  });
  stepBtn.addEventListener("click", function () {
    stopPlaying();
    var empty = traceEl.querySelector(".trace-empty");
    if (empty && state.step === -1) { traceEl.innerHTML = ""; }
    if (state.step < currentCase().steps.length - 1) {
      applyStep(state.step + 1);
    }
  });
  resetBtn.addEventListener("click", resetReplay);

  // The Step handler removes the placeholder on first use; Play must too.
  playBtn.addEventListener("click", function () {
    var empty = traceEl.querySelector(".trace-empty");
    if (empty && state.playing) { traceEl.innerHTML = ""; }
  });

  renderCase();
})();
