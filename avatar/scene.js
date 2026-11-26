const statusEl = document.getElementById("status");

// Official Grok Bot ogicon: body #E5050F, opaque white eyes.
// Hex so dark theme cannot invert the body. eyeColor paints the eyes
// instead of cutting them out as transparent holes.
// Live avatar runs at 60 fps via the official engine (rAF, maxFrameRate 60).
const ROBOT = {
  color: "#E5050F",
  eyeColor: "#FFFFFF",
  shape: "blob",
  reducedMotion: false,
  maxFrameRate: 60,
};

// Official `loading` uses the `progress` morph. The engine's morph
// duration table gives progress 2.5s per shot, then a 1.5s rest before
// it would loop. Play that shot once as the completion beat.
const LOADING_ONCE_MS = 2500;

let seq = 0;
let currentActivity = null;
let phase = "idle"; // "idle" | "waiting" | "completing" | "limited" | "error"
const actorSlot = document.getElementById("actor-slot");
let loadingStartedAt = 0;
let holdTimer = 0;

function paint(state) {
  if (!window.setAvatar) return;
  window.setAvatar({
    state,
    color: ROBOT.color,
    eyeColor: ROBOT.eyeColor,
    shape: ROBOT.shape,
    reducedMotion: false,
    maxFrameRate: ROBOT.maxFrameRate,
    isPlaying: true,
  });
}

function labelFor(payload) {
  if (!payload || !payload.busy) return "";
  if (payload.activity === "search") {
    const q = String(payload.keyword || "").trim();
    if (q && q.length <= 24 && !/^https?:/i.test(q)) return `搜索中 · ${q}`;
    return "搜索中";
  }
  if (payload.activity === "note") return "打开笔记中";
  return "";
}

function setStatusText(text) {
  if (text) {
    statusEl.textContent = text;
    statusEl.classList.add("on");
    return;
  }
  statusEl.classList.remove("on");
  window.setTimeout(() => {
    if (!statusEl.classList.contains("on")) statusEl.textContent = "";
  }, 260);
}

function clearHold() {
  if (holdTimer) {
    clearTimeout(holdTimer);
    holdTimer = 0;
  }
}

async function waitForSetAvatar() {
  const started = Date.now();
  while (!window.setAvatar) {
    if (Date.now() - started > 4000) return false;
    await new Promise((r) => setTimeout(r, 40));
  }
  return true;
}

// Idle / standby is official `happy` (Done_A). The official clip machine
// does not mark `happy` as a one-shot (no `next`); the driver loops the
// clip, so the character stays alive after a search finishes.
//
// In-flight search, explore, or note is official `thinking` (Idle_B +
// the `dots` morph): Grok Bot's cycling three-dot wait. This is the
// "still working" state, not official `loading`.
//
// When busy ends (results arrived), official `loading` (Idle_B +
// `progress` morph) plays once for LOADING_ONCE_MS, then we return to
// looping happy. Hat and dive path stay off.
//
// A new busy pulse, including a second search with the same activity
// name, cancels the completion hold and re-enters the dots wait.
// Stale paints are ignored via seq / phase guards so a late loading
// frame cannot stomp happy.

function isLimitState(payload) {
  return !!(
    payload &&
    (payload.limit_reached || payload.scene === "limit" || payload.activity === "limit")
  );
}

function isErrorState(payload) {
  if (!payload || isLimitState(payload)) return false;
  return !!(payload.scene === "error" || payload.error_state);
}

function hideCrying() {
  if (actorSlot) actorSlot.classList.remove("crying");
  if (statusEl) statusEl.classList.remove("steady");
}

function showCrying(kind, text) {
  clearHold();
  hideCrying();
  phase = kind;
  currentActivity = kind;
  if (actorSlot) actorSlot.classList.add("crying");
  if (statusEl) statusEl.classList.add("steady");
  setStatusText(text);
  if (window.setAvatar) paint("sad");
}

window.setScene = async function setScene(payload) {
  const activity = payload && payload.busy ? payload.activity : null;

  if (isLimitState(payload)) {
    const text = payload.status_text || payload.error || "今日搜索次数已用完";
    if (phase === "limited") {
      setStatusText(text);
      if (statusEl) statusEl.classList.add("steady");
      return;
    }
    const token = ++seq;
    showCrying("limited", text);
    if (!window.setAvatar) {
      void waitForSetAvatar().then((ok) => {
        if (!ok || token !== seq) return;
        if (phase !== "limited") return;
        paint("sad");
      });
    }
    return;
  }

  if (isErrorState(payload)) {
    const text = payload.status_text || "出错了";
    if (phase === "error") {
      setStatusText(text);
      if (statusEl) statusEl.classList.add("steady");
      return;
    }
    const token = ++seq;
    showCrying("error", text);
    if (!window.setAvatar) {
      void waitForSetAvatar().then((ok) => {
        if (!ok || token !== seq) return;
        if (phase !== "error") return;
        paint("sad");
      });
    }
    return;
  }

  if (phase === "limited" || phase === "error") {
    hideCrying();
    if (!activity) {
      const token = ++seq;
      phase = "idle";
      currentActivity = null;
      setStatusText("");
      if (window.setAvatar) paint("happy");
      else {
        void waitForSetAvatar().then((ok) => {
          if (!ok || token !== seq) return;
          if (phase !== "idle") return;
          paint("happy");
        });
      }
      return;
    }
  }

  if (activity) {
    clearHold();
    hideCrying();
    setStatusText(labelFor(payload));
    currentActivity = activity;
    phase = "waiting";
    loadingStartedAt = Date.now();
    const token = ++seq;
    if (await waitForSetAvatar()) {
      if (token !== seq) return;
      if (phase !== "waiting") return;
      paint("thinking");
    }
    return;
  }

  // Idle requested. If we are already idle with no completion hold,
  // ignore. If the one-shot loading clip is already playing, ignore
  // extra idle pulses so the shot can finish.
  if (phase === "idle" && !holdTimer) return;
  if (phase === "completing" || holdTimer) return;

  const token = ++seq;
  phase = "completing";
  currentActivity = null;
  setStatusText("");
  loadingStartedAt = Date.now();

  const goHappy = () => {
    holdTimer = 0;
    if (token !== seq) return;
    seq += 1;
    phase = "idle";
    currentActivity = null;
    setStatusText("");
    paint("happy");
  };

  // Arm the timer before painting so a second idle cannot start
  // another completion, and a new busy can cancel this shot.
  // Paint synchronously when the engine is already up so setScene
  // returns with loading on screen. If setAvatar is still missing,
  // do not block this call; a guarded late paint may still land
  // while phase is completing, but cannot stomp a later happy.
  holdTimer = setTimeout(goHappy, LOADING_ONCE_MS);
  if (window.setAvatar) {
    paint("loading");
  } else {
    const paintToken = token;
    void waitForSetAvatar().then((ok) => {
      if (!ok || paintToken !== seq) return;
      if (phase !== "completing") return;
      paint("loading");
    });
  }
};

window.__xhsScene = function __xhsScene() {
  return {
    currentActivity,
    phase,
    holdTimer,
    loadingStartedAt,
    seq,
    loadingOnceMs: LOADING_ONCE_MS,
    minLoadingMs: LOADING_ONCE_MS,
    statusText: statusEl ? statusEl.textContent : "",
  };
};

function formatLikes(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  if (n >= 10000) {
    const wan = n / 10000;
    const text = wan >= 10 ? String(Math.round(wan)) : String(Math.round(wan * 10) / 10);
    return text + "万赞";
  }
  return n.toLocaleString("en-US") + "赞";
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function noteItem(note) {
  const url = String((note && note.url) || "").trim();
  const title = String((note && note.title) || "(无标题)").trim() || "(无标题)";
  const author = String((note && note.author) || "").trim();
  const group = String((note && note.group) || "").trim();
  const likes = formatLikes(note && note.likes_count);
  const meta = [author, likes, group].filter(Boolean).join(" · ");
  const href = url ? escapeHtml(url) : "";
  const inner = `<span class="note-title">${escapeHtml(title)}</span><span class="note-meta">${escapeHtml(meta)}</span>`;
  if (href) {
    return `<li><a href="${href}" rel="noopener noreferrer">${inner}</a></li>`;
  }
  return `<li><div class="note-title">${inner}</div></li>`;
}

function uniqueNotes(notes) {
  const seen = new Set();
  const out = [];
  for (const note of Array.isArray(notes) ? notes : []) {
    const id = String((note && (note.id || note.url || note.title)) || "");
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    out.push(note);
  }
  return out;
}

function renderResults(payload, options) {
  const curatedList = document.getElementById("curated-list");
  const allList = document.getElementById("all-list");
  const curatedLabel = document.getElementById("curated-toggle-label");
  const allLabel = document.getElementById("all-toggle-label");
  const loadBtn = document.getElementById("load-saved");
  const clearBtn = document.getElementById("clear-results");
  const statusEl = document.getElementById("results-status");
  if (!curatedList || !allList) return;

  const curated = Array.isArray(payload && payload.curated) ? payload.curated : [];
  const all = uniqueNotes(payload && payload.notes);
  const savedAvailable = !!(payload && payload.saved_available);
  const empty = curated.length === 0 && all.length === 0;
  if (loadBtn) loadBtn.classList.toggle("show", savedAvailable && empty);
  if (clearBtn) clearBtn.disabled = all.length === 0;
  document.body.classList.toggle("has-results", !empty);

  if (curatedLabel) curatedLabel.textContent = curated.length ? "精选 " + curated.length : "精选";
  if (allLabel) allLabel.textContent = all.length ? "全部结果 " + all.length : "全部结果";
  curatedList.innerHTML = curated.map(noteItem).join("");
  allList.innerHTML = all.map(noteItem).join("");

  if (statusEl) {
    if (options && options.cleared) {
      statusEl.hidden = false;
      statusEl.textContent = "结果已清空";
    } else if (all.length) {
      statusEl.hidden = true;
    }
  }
}

let resultsRevision = null;
let resultsTimer = 0;

async function fetchResults(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("results " + response.status);
  return response.json();
}

async function pollResults(force) {
  if (!document.getElementById("all-list")) return;
  try {
    const data = await fetchResults("/results");
    const revision = data && data.revision;
    if (!force && revision === resultsRevision) {
      const loadBtn = document.getElementById("load-saved");
      if (loadBtn && data) {
        const empty = !(data.curated && data.curated.length) && !(data.notes && data.notes.length);
        loadBtn.classList.toggle("show", !!data.saved_available && empty);
      }
      return;
    }
    resultsRevision = revision;
    renderResults(data);
  } catch (_err) {
    // Keep the last painted list if the service is briefly unreachable.
  }
}

async function loadSavedHooks() {
  const data = await fetchResults("/results?load=hook-search");
  resultsRevision = data && data.revision;
  renderResults(data);
}

async function clearResults() {
  const statusEl = document.getElementById("results-status");
  const clearBtn = document.getElementById("clear-results");
  if (clearBtn) clearBtn.disabled = true;
  try {
    const response = await fetch("/clear-results", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data || data.ok === false) {
      throw new Error((data && data.error) || "clear failed");
    }
    resultsRevision = data && data.revision;
    renderResults({
      curated: [],
      notes: [],
      saved_available: !!(data && data.saved_available),
    }, { cleared: true });
    await pollResults(true);
    if (statusEl && !((data.notes && data.notes.length) || (data.curated && data.curated.length))) {
      statusEl.hidden = false;
      statusEl.textContent = "结果已清空";
    }
  } catch (_err) {
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = "清空失败，请重试";
    }
    if (clearBtn) clearBtn.disabled = false;
    await pollResults(true);
  }
}

function startResultsPoll() {
  if (!document.getElementById("all-list")) return;
  const loadBtn = document.getElementById("load-saved");
  if (loadBtn) {
    loadBtn.addEventListener("click", () => {
      loadSavedHooks().catch(() => {});
    });
  }
  const clearBtn = document.getElementById("clear-results");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      clearResults().catch(() => {});
    });
  }
  pollResults(true);
  if (!resultsTimer) {
    resultsTimer = window.setInterval(() => {
      pollResults(false);
    }, 800);
  }
}

function formatRecordTime(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace("T", " ").replace(/[+-]\d{2}:\d{2}$/, "").replace(/Z$/, "");
}

function renderRecords(payload) {
  const listEl = document.getElementById("records-list");
  const emptyEl = document.getElementById("records-empty");
  const statusEl = document.getElementById("records-status");
  const headingEl = document.getElementById("records-toggle-label") || document.getElementById("records-heading");
  const clearBtn = document.getElementById("clear-records");
  if (!listEl) return;

  const records = Array.isArray(payload && payload.records) ? payload.records : [];
  if (headingEl) headingEl.textContent = records.length ? "搜索记录 " + records.length : "搜索记录";
  if (clearBtn) clearBtn.disabled = records.length === 0;
  if (statusEl && records.length) statusEl.hidden = true;

  if (!records.length) {
    listEl.innerHTML = "";
    if (emptyEl) emptyEl.hidden = false;
    return;
  }

  if (emptyEl) emptyEl.hidden = true;
  listEl.innerHTML = records.map((record) => {
    const query = String((record && record.query) || "搜索").trim() || "搜索";
    const count = Number(record && record.count);
    const when = formatRecordTime(record && record.ts);
    const countText = Number.isFinite(count) ? count + " 条" : "";
    const meta = [when, countText].filter(Boolean).join(" · ");
    const notes = Array.isArray(record && record.notes) ? record.notes : [];
    const items = notes.map((note) => {
      const url = String((note && note.url) || "").trim();
      const title = String((note && note.title) || "(无标题)").trim() || "(无标题)";
      const author = String((note && note.author) || "").trim();
      const href = url ? escapeHtml(url) : "";
      const inner = `<span class="note-title">${escapeHtml(title)}</span><span class="note-meta">${escapeHtml(author)}</span>`;
      if (href) return `<li><a href="${href}" rel="noopener noreferrer">${inner}</a></li>`;
      return `<li><div class="note-title">${inner}</div></li>`;
    }).join("");
    return `<li class="record"><h3 class="record-query">${escapeHtml(query)}</h3><p class="record-meta">${escapeHtml(meta)}</p><ol class="note-list">${items}</ol></li>`;
  }).join("");
}

async function fetchRecords() {
  const response = await fetch("/records", { cache: "no-store" });
  if (!response.ok) throw new Error("records " + response.status);
  return response.json();
}

async function pollRecords() {
  if (!document.getElementById("records-list")) return;
  try {
    const data = await fetchRecords();
    renderRecords(data);
  } catch (_err) {
    // Keep the last painted log if the service is briefly unreachable.
  }
}

async function clearRecords() {
  const statusEl = document.getElementById("records-status");
  const clearBtn = document.getElementById("clear-records");
  if (clearBtn) clearBtn.disabled = true;
  try {
    const response = await fetch("/clear-records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    const data = await response.json();
    if (!response.ok || !data || data.ok === false) {
      throw new Error((data && data.error) || "clear failed");
    }
    renderRecords({ records: [], count: 0 });
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = "记录已清空";
    }
    // Refresh from the service so the panel stays in sync; do not touch /results.
    await pollRecords();
    if (statusEl && !(data.records && data.records.length)) {
      statusEl.hidden = false;
      statusEl.textContent = "记录已清空";
    }
  } catch (_err) {
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = "清空失败，请重试";
    }
    if (clearBtn) clearBtn.disabled = false;
    await pollRecords();
  }
}

function bindFold(toggleId, foldId, panelId) {
  const btn = document.getElementById(toggleId);
  const fold = document.getElementById(foldId);
  if (!btn || !fold) return;
  if (btn.dataset.foldBound === "1") return;
  btn.addEventListener("click", () => {
    const next = btn.getAttribute("aria-expanded") !== "true";
    btn.setAttribute("aria-expanded", next ? "true" : "false");
    fold.classList.toggle("open", next);
    const panel = document.getElementById(panelId) || btn.closest("section");
    if (panel) panel.classList.toggle("is-open", next);
  });
  btn.dataset.foldBound = "1";
}

function startRecordsPanel() {
  if (!document.getElementById("records-panel")) return;
  bindFold("curated-toggle", "curated-fold", "curated");
  bindFold("records-toggle", "records-fold", "records-panel");
  bindFold("all-toggle", "all-fold", "all-results");
  const clearBtn = document.getElementById("clear-records");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      clearRecords().catch(() => {});
    });
  }
  pollRecords();
  window.setInterval(() => {
    pollRecords();
  }, 2000);
}

async function boot() {
  startResultsPoll();
  startRecordsPanel();
  if (await waitForSetAvatar()) paint("happy");
}

boot();

(function previewFromQuery() {
  try {
    const params = new URLSearchParams(window.location.search);
    const scene = params.get("preview") || params.get("scene");
    if (scene === "limit") {
      window.setScene({ limit_reached: true, scene: "limit", status_text: "今日搜索次数已用完" });
    } else if (scene === "error") {
      window.setScene({ error_state: true, scene: "error", status_text: "出错了" });
    }
  } catch (err) {
    // Ignore preview parse errors.
  }
})();
