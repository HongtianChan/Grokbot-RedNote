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
let phase = "idle"; // "idle" | "waiting" | "completing"
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
window.setScene = async function setScene(payload) {
  const activity = payload && payload.busy ? payload.activity : null;

  if (activity) {
    clearHold();
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

function renderResults(payload) {
  const resultsEl = document.getElementById("results");
  const curatedList = document.getElementById("curated-list");
  const allList = document.getElementById("all-list");
  const curatedHeading = document.getElementById("curated-heading");
  const allHeading = document.getElementById("all-heading");
  const emptyEl = document.getElementById("results-empty");
  const loadBtn = document.getElementById("load-saved");
  if (!resultsEl || !curatedList || !allList) return;

  const curated = Array.isArray(payload && payload.curated) ? payload.curated : [];
  const all = uniqueNotes(payload && payload.notes);
  const savedAvailable = !!(payload && payload.saved_available);
  if (loadBtn) {
    loadBtn.classList.toggle("show", savedAvailable && curated.length === 0 && all.length === 0);
  }

  if (!curated.length && !all.length) {
    document.body.classList.remove("has-results");
    curatedList.innerHTML = "";
    allList.innerHTML = "";
    if (emptyEl) emptyEl.hidden = false;
    return;
  }

  document.body.classList.add("has-results");
  if (emptyEl) emptyEl.hidden = true;
  if (curatedHeading) curatedHeading.textContent = "精选 " + curated.length;
  if (allHeading) allHeading.textContent = "全部结果 " + all.length;
  curatedList.innerHTML = curated.map(noteItem).join("");
  allList.innerHTML = all.map(noteItem).join("");
}

let resultsRevision = null;
let resultsTimer = 0;

async function fetchResults(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("results " + response.status);
  return response.json();
}

async function pollResults(force) {
  if (!document.getElementById("results")) return;
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

function startResultsPoll() {
  if (!document.getElementById("results")) return;
  const loadBtn = document.getElementById("load-saved");
  if (loadBtn) {
    loadBtn.addEventListener("click", () => {
      loadSavedHooks().catch(() => {});
    });
  }
  pollResults(true);
  if (!resultsTimer) {
    resultsTimer = window.setInterval(() => {
      pollResults(false);
    }, 800);
  }
}

async function boot() {
  startResultsPoll();
  if (await waitForSetAvatar()) paint("happy");
}

boot();
