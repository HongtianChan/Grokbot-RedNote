import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const root = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(root, "scene.js"), "utf8");

let now = 1_000_000;
const timers = new Map();
let nextTimerId = 1;

function flush(ms = 0) {
  now += ms;
  const due = [...timers.entries()]
    .filter(([, t]) => t.at <= now)
    .sort((a, b) => a[1].at - b[1].at);
  for (const [id, t] of due) {
    timers.delete(id);
    t.fn();
  }
}

class FakeClassList {
  constructor() {
    this._on = false;
  }
  add(name) {
    if (name === "on") this._on = true;
  }
  remove(name) {
    if (name === "on") this._on = false;
  }
  contains(name) {
    return name === "on" && this._on;
  }
}

function installScene() {
  const statusEl = { textContent: "", classList: new FakeClassList() };
  const paints = [];
  const windowObj = {
    setTimeout(fn, ms) {
      const id = nextTimerId++;
      timers.set(id, { fn, at: now + (ms || 0) });
      return id;
    },
    setInterval() {
      throw new Error("unexpected setInterval");
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    setAvatar(config) {
      paints.push(config.state);
    },
  };

  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    DateNow: Date.now,
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
  };

  Date.now = () => now;
  globalThis.setTimeout = windowObj.setTimeout;
  globalThis.clearTimeout = windowObj.clearTimeout;
  globalThis.window = windowObj;
  globalThis.document = {
    getElementById(id) {
      if (id === "status") return statusEl;
      // Results panel is optional in this animation harness.
      return null;
    },
  };

  // scene.js calls boot() at load, which paints happy once setAvatar exists.
  (0, eval)(source);

  return {
    paints,
    statusEl,
    windowObj,
    async tick() {
      await Promise.resolve();
      await Promise.resolve();
    },
    restore() {
      Date.now = previous.DateNow;
      globalThis.setTimeout = previous.setTimeout;
      globalThis.clearTimeout = previous.clearTimeout;
      if (previous.window === undefined) delete globalThis.window;
      else globalThis.window = previous.window;
      if (previous.document === undefined) delete globalThis.document;
      else globalThis.document = previous.document;
    },
  };
}

const { paints, statusEl, windowObj, tick, restore } = installScene();
const setScene = windowObj.setScene;
const snap = () => windowObj.__xhsScene();

try {
  await tick();
  assert.deepEqual(paints, ["happy"], "boot should paint official happy");
  assert.equal(snap().currentActivity, null);
  assert.equal(snap().phase, "idle");
  assert.equal(snap().holdTimer, 0);
  assert.equal(statusEl.textContent, "");

  await setScene({ busy: true, activity: "search", keyword: "猫" });
  assert.deepEqual(paints, ["happy", "thinking"]);
  assert.equal(snap().currentActivity, "search");
  assert.equal(snap().phase, "waiting");
  assert.equal(snap().holdTimer, 0);
  assert.equal(statusEl.textContent, "搜索中 · 猫");
  assert.equal(statusEl.classList.contains("on"), true);

  // Results arrive immediately; play official loading once, clear the
  // in-progress status. Do not jump straight to happy.
  await setScene({ busy: false });
  assert.equal(paints.at(-1), "loading", "busy end must play loading once");
  assert.ok(snap().holdTimer, "completion timer should be armed");
  assert.equal(snap().phase, "completing");
  assert.equal(snap().currentActivity, null);
  assert.equal(statusEl.classList.contains("on"), false);

  // Second search during the completion beat: same activity name, new
  // keyword. Must cancel the hold, re-enter the dots wait, and update text.
  await setScene({ busy: true, activity: "search", keyword: "狗" });
  assert.equal(snap().holdTimer, 0, "second search must cancel the hold");
  assert.equal(snap().currentActivity, "search");
  assert.equal(snap().phase, "waiting");
  assert.equal(statusEl.textContent, "搜索中 · 狗");
  assert.deepEqual(paints, ["happy", "thinking", "loading", "thinking"]);

  await setScene({ busy: false });
  assert.ok(snap().holdTimer, "second idle should arm the one-shot loading play");
  assert.equal(paints.at(-1), "loading");
  assert.equal(snap().phase, "completing");
  assert.equal(statusEl.classList.contains("on"), false);

  flush(2490);
  assert.equal(paints.at(-1), "loading", "loading must play through to completion");
  assert.equal(snap().phase, "completing");

  flush(20);
  assert.equal(paints.at(-1), "happy", "after the one-shot, return to looping happy");
  assert.equal(snap().currentActivity, null);
  assert.equal(snap().phase, "idle");
  assert.equal(snap().holdTimer, 0);
  assert.equal(statusEl.classList.contains("on"), false);
  flush(260);
  assert.equal(statusEl.textContent, "");

  // A later search after happy must enter thinking again, then loading, then happy.
  await setScene({ busy: true, activity: "search", keyword: "猫" });
  assert.equal(statusEl.textContent, "搜索中 · 猫");
  assert.equal(paints.at(-1), "thinking");
  assert.equal(snap().currentActivity, "search");
  assert.equal(snap().phase, "waiting");
  await setScene({ busy: false, activity: "note" });
  assert.equal(paints.at(-1), "loading");
  flush(2500);
  assert.equal(paints.at(-1), "happy");
  assert.equal(snap().currentActivity, null);
  assert.equal(snap().phase, "idle");

  // Note activity updates status text and uses the same busy path.
  await setScene({ busy: true, activity: "note", keyword: "https://www.rednote.com/x" });
  assert.equal(statusEl.textContent, "打开笔记中");
  assert.equal(paints.at(-1), "thinking");
  assert.equal(snap().phase, "waiting");

  // Async race: a stale paint("thinking") or paint("loading") must not
  // stomp a later happy. Start a busy pulse whose wait is still pending,
  // then go idle long enough for goHappy, then let the leftover await resolve.
  const pendingPaints = paints.length;
  const savedAvatar = windowObj.setAvatar;
  delete windowObj.setAvatar;
  const staleBusy = setScene({ busy: true, activity: "search", keyword: "迟到" });
  // Idle while setAvatar is missing: completion hold starts, seq advances.
  await setScene({ busy: false });
  // Restore and let the original waitForSetAvatar resume after 40ms.
  windowObj.setAvatar = savedAvatar;
  // Fast-forward past the one-shot so goHappy commits happy first.
  flush(2500);
  // Then let the 40ms waiter (already due, or due now) plus the stale await run.
  flush(40);
  await staleBusy;
  await tick();
  const afterRace = paints.slice(pendingPaints);
  assert.ok(afterRace.includes("happy"), "race cleanup should still reach happy");
  assert.notEqual(paints.at(-1), "loading", "stale loading must not stomp happy");
  assert.notEqual(paints.at(-1), "thinking", "stale thinking must not stomp happy");
  assert.equal(snap().currentActivity, null);
  assert.equal(snap().phase, "idle");
  assert.equal(statusEl.classList.contains("on"), false);
  flush(260);
  assert.equal(statusEl.textContent, "");

  console.log("ok");
  console.log(
    JSON.stringify(
      {
        paints,
        finalActivity: snap().currentActivity,
        finalPhase: snap().phase,
        finalHold: snap().holdTimer,
        finalStatus: statusEl.textContent,
      },
      null,
      2,
    ),
  );
} finally {
  restore();
}
