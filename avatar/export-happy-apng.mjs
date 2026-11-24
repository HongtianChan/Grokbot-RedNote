/**
 * Render the official `happy` clip (Done_A) to a lossless 60 fps APNG
 * using the local grok-bot-avatar-engine, with body #E5050F and
 * opaque white eyes via two-argument paintOf.
 *
 * Usage (from the Grokbot-RedNote project root, on the Mac):
 *   node avatar/export-happy-apng.mjs
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, mkdir, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");
const engineRoot = path.join(here, "grok-bot-avatar-engine");
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const BODY = "#E5050F";
const EYES = "#FFFFFF";
const SHAPE = "blob";
const STATE = "happy";
const SIZE = 1024;
const FILL = 0.62;
const FPS = 60;
const SEED = "xhs-reader-happy";
const MAX_FRAME_RATE = 60;
const BATCH = 20;

const { client, bodyFor, paintOf, STATES } = await import(
  pathToFileURL(path.join(engineRoot, "src", "index.mjs")).href
);

if (!STATES.includes("happy") || !STATES.includes("loading")) {
  throw new Error(`Official STATES missing happy/loading: ${STATES.join(", ")}`);
}

const { eo, f_, go, hp, no, s_, u_, Xg } = client;

function renderFrame(state, time, { size = SIZE, fill = FILL, seed = SEED } = {}) {
  const appearance = paintOf(BODY, EYES);
  const props = f_({
    size,
    id: `avatar-${SHAPE}`,
    body: bodyFor(SHAPE),
    appearance,
    state,
    isPlaying: true,
    isStatic: false,
    fill,
    maxFrameRate: MAX_FRAME_RATE,
  });
  const driver = eo({ body: props.body });
  const machine = go(driver, props.state, {
    seed: u_(String(seed)),
    isCompact: size < s_,
    isResting: false,
  });
  const resolution = props.resolution ?? Math.round(size * no(props.fill) * 100) / 100;
  const step = 1 / Math.max(1, props.maxFrameRate);
  for (let elapsed = 0; elapsed < time; elapsed += step) {
    machine.advance(step);
    driver.advance(step);
  }
  return hp(
    Xg(driver.frame(), props.appearance, resolution, props.id, {
      displaySize: size,
      extent: size,
    }),
  );
}

function clipDuration(state) {
  const driver = eo({ body: bodyFor(SHAPE) });
  go(driver, state, {
    seed: u_(String(SEED)),
    isCompact: false,
    isResting: false,
  });
  return driver.duration;
}

function startServer(root) {
  const mime = {
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".png": "image/png",
  };
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      const url = new URL(req.url, "http://127.0.0.1");
      const rel = decodeURIComponent(url.pathname);
      const file = path.join(root, rel === "/" ? "index.html" : rel);
      if (!file.startsWith(root)) {
        res.writeHead(403).end();
        return;
      }
      try {
        const data = await readFile(file);
        res.writeHead(200, { "content-type": mime[path.extname(file)] || "application/octet-stream" });
        res.end(data);
      } catch {
        res.writeHead(404).end("not found");
      }
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

async function cdpSend(ws, id, method, params) {
  return new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id !== id) return;
      ws.removeEventListener("message", onMessage);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: opts.stdio ?? "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`))));
  });
}

const duration = clipDuration(STATE);
const frameCount = Math.round(duration * FPS);
const times = Array.from({ length: frameCount }, (_, i) => (i / FPS) % duration);
console.log(`STATES=${STATES.length} happy=${STATES.includes("happy")} loading=${STATES.includes("loading")}`);
console.log(`happy duration=${duration}s frames=${frameCount} fps=${FPS} size=${SIZE} format=APNG`);

const work = await mkdtemp(path.join(tmpdir(), "xhs-happy-apng-"));
const svgDir = path.join(work, "svg");
const pngDir = path.join(work, "png");
await mkdir(svgDir);
await mkdir(pngDir);

const svgs = [];
for (let i = 0; i < times.length; i++) {
  const svg = renderFrame(STATE, times[i]);
  const file = path.join(svgDir, `f${String(i).padStart(3, "0")}.svg`);
  await writeFile(file, svg);
  svgs.push({ i, file, t: times[i] });
}
console.log("wrote", svgs.length, "svg frames to", svgDir);

await writeFile(
  path.join(work, "index.html"),
  `<!doctype html>
<meta charset="utf-8">
<script>
  window.rasterize = async (files, size) => {
    const out = [];
    for (const file of files) {
      const img = new Image();
      img.src = file;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size, size);
      ctx.drawImage(img, 0, 0, size, size);
      out.push(canvas.toDataURL("image/png"));
    }
    return out;
  };
</script>
`,
);

const { server, port } = await startServer(work);
const userData = await mkdtemp(path.join(tmpdir(), "xhs-chrome-"));
const child = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--no-default-browser-check",
  `--user-data-dir=${userData}`,
  "--remote-debugging-port=0",
  "--remote-debugging-address=127.0.0.1",
  "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });

try {
  const dbgPort = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Chrome debug port timeout")), 20000);
    let buf = "";
    const onData = (chunk) => {
      buf += chunk.toString();
      const match = buf.match(/DevTools listening on ws:\/\/[^:]+:(\d+)/);
      if (match) {
        clearTimeout(timer);
        child.stderr.off("data", onData);
        child.stdout.off("data", onData);
        resolve(Number(match[1]));
      }
    };
    child.stderr.on("data", onData);
    child.stdout.on("data", onData);
    child.on("error", reject);
  });

  const targets = await fetch(`http://127.0.0.1:${dbgPort}/json/list`).then((r) => r.json());
  const page = targets.find((t) => t.type === "page") || targets[0];
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", reject);
  });

  let n = 1;
  await cdpSend(ws, n++, "Page.enable");
  await cdpSend(ws, n++, "Runtime.enable");
  await cdpSend(ws, n++, "Page.navigate", { url: `http://127.0.0.1:${port}/index.html` });
  await new Promise((resolve) => {
    const onMessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.method === "Page.loadEventFired") {
        ws.removeEventListener("message", onMessage);
        resolve();
      }
    };
    ws.addEventListener("message", onMessage);
  });

  for (let start = 0; start < svgs.length; start += BATCH) {
    const batch = svgs.slice(start, start + BATCH);
    const files = batch.map((f) => `/svg/f${String(f.i).padStart(3, "0")}.svg`);
    const { result } = await cdpSend(ws, n++, "Runtime.evaluate", {
      expression: `rasterize(${JSON.stringify(files)}, ${SIZE})`,
      awaitPromise: true,
      returnByValue: true,
    });
    const urls = result.value;
    for (let j = 0; j < urls.length; j++) {
      const b64 = urls[j].replace(/^data:image\/png;base64,/, "");
      const idx = batch[j].i;
      await writeFile(path.join(pngDir, `f${String(idx).padStart(3, "0")}.png`), Buffer.from(b64, "base64"));
    }
    console.log(`rasterized ${Math.min(start + BATCH, svgs.length)}/${svgs.length}`);
  }
  ws.close();
} finally {
  child.kill("SIGTERM");
  server.close();
}

const outApng = path.join(projectRoot, "happy.png");
await run("ffmpeg", [
  "-y",
  "-start_number", "0",
  "-framerate", String(FPS),
  "-i", path.join(pngDir, "f%03d.png"),
  "-c:v", "apng",
  "-plays", "0",
  "-pix_fmt", "rgba",
  "-pred", "mixed",
  "-f", "apng",
  outApng,
]);
console.log("wrote", outApng);
console.log("png frames", pngDir);
