/** Real local HTTP + Chromium/CDP acceptance checks. No mocks or paid providers. */
import { spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const origin = (
  process.env.LEGAL_AI_BASE_URL ||
  process.env.LEGAL_AI_WEB_URL ||
  "http://127.0.0.1:3000"
).replace(/\/$/, "");
const apiOrigin = (
  process.env.LEGAL_AI_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
function installedBrowser() {
  if (process.env.LEGAL_AI_BROWSER_PATH)
    return process.env.LEGAL_AI_BROWSER_PATH;
  const candidates = [];
  if (process.platform === "win32") {
    const local =
      process.env.LOCALAPPDATA ||
      path.join(process.env.USERPROFILE || homedir(), "AppData", "Local");
    const programs = [
      local,
      process.env.PROGRAMFILES,
      process.env["PROGRAMFILES(X86)"],
    ].filter(Boolean);
    for (const folder of programs) {
      candidates.push(
        path.join(folder, "Google", "Chrome", "Application", "chrome.exe"),
      );
      candidates.push(
        path.join(folder, "Microsoft", "Edge", "Application", "msedge.exe"),
      );
    }
    const playwright = path.join(local, "ms-playwright");
    if (existsSync(playwright)) {
      const versions = readdirSync(playwright)
        .filter((name) => /^chromium-\d+$/.test(name))
        .sort(
          (a, b) => Number(b.split("-").pop()) - Number(a.split("-").pop()),
        );
      for (const version of versions)
        for (const layout of ["chrome-win64", "chrome-win"])
          candidates.push(path.join(playwright, version, layout, "chrome.exe"));
    }
  } else if (process.platform === "darwin") {
    candidates.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      path.join(
        homedir(),
        "Applications",
        "Google Chrome.app",
        "Contents",
        "MacOS",
        "Google Chrome",
      ),
    );
  } else
    candidates.push(
      "/usr/bin/chromium",
      "/usr/bin/chromium-browser",
      "/usr/bin/google-chrome",
      "/opt/google/chrome/chrome",
    );
  return candidates.find((candidate) => existsSync(candidate)) || "";
}
const browserPath = installedBrowser();
const port = Number(process.env.LEGAL_AI_CDP_PORT || 19388);
const output = path.join(root, "artifacts", "browser");
const profile = path.join(root, ".local", `browser-profile-${port}`);
const noSandbox =
  process.env.LEGAL_AI_BROWSER_NO_SANDBOX === "true" ||
  process.env.LEGAL_AI_BROWSER_NO_SANDBOX === "1" ||
  (process.platform === "linux" &&
    ["true", "1"].includes(process.env.CI || ""));
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [],
  runtimeErrors = [],
  externalAttempts = [],
  responses = [];
const pending = new Map();
let ws,
  sessionId,
  sequence = 0,
  browser;
const start = Date.now();

function invariant(value, message) {
  if (!value) throw new Error(message);
}
function send(method, params = {}, session = sessionId) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`CDP timed out: ${method}`));
    }, 90_000);
    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      reject: (error) => {
        clearTimeout(timeout);
        reject(error);
      },
    });
    ws.send(
      JSON.stringify({
        id,
        method,
        params,
        ...(session ? { sessionId: session } : {}),
      }),
    );
  });
}
async function evaluate(expression) {
  const reply = await send("Runtime.evaluate", {
    expression: `(async()=>{const value=await (${expression});return value instanceof Node ? true : value;})()`,
    returnByValue: true,
    awaitPromise: true,
  });
  if (reply.exceptionDetails)
    throw new Error(
      `Browser expression failed: ${reply.exceptionDetails.exception?.description || reply.exceptionDetails.text}`,
    );
  return reply.result.value;
}
async function wait(expression, timeout = 45_000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await evaluate(`Boolean(${expression})`)) return;
    await pause(100);
  }
  throw new Error(`Condition not reached: ${expression.slice(0, 180)}`);
}
async function test(name, fn, critical = false) {
  const at = Date.now();
  try {
    const detail = await fn();
    results.push({
      name,
      passed: true,
      duration_ms: Date.now() - at,
      ...(detail === undefined ? {} : { detail }),
    });
    console.log(`PASS ${name}`);
    return true;
  } catch (error) {
    results.push({
      name,
      passed: false,
      duration_ms: Date.now() - at,
      error: error.message,
    });
    console.error(`FAIL ${name}: ${error.message}`);
    if (critical) throw error;
    return false;
  }
}
const visible = `e => e.getClientRects().length && !e.closest('[hidden]')`;
function buttonExpression(name, contains = false) {
  return `[...document.querySelectorAll('button')].filter(${visible}).find(e => e.textContent.trim()${contains ? ".includes" : "==="}${contains ? `(${JSON.stringify(name)})` : JSON.stringify(name)})`;
}
async function clickExpression(expression) {
  // A selected document header may appear before its detail request finishes.
  // Respect the actual disabled/loading control instead of racing its render.
  await wait(`Boolean(${expression}) && !(${expression}).disabled`, 15_000);
  const point = await evaluate(
    `(() => { const e = ${expression}; if (!e || e.disabled) return null; e.scrollIntoView({block:'center',behavior:'instant'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()`,
  );
  invariant(point, `No enabled visible target: ${expression.slice(0, 140)}`);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", ...point });
  await send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    button: "left",
    clickCount: 1,
    ...point,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    button: "left",
    clickCount: 1,
    ...point,
  });
  await pause(80);
}
async function click(name, contains = false) {
  await clickExpression(buttonExpression(name, contains));
}
async function setInput(selector, value) {
  await evaluate(
    `(() => { const e=document.querySelector(${JSON.stringify(selector)}); if(!e) throw new Error('Input absent'); e.focus(); const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); })()`,
  );
  await pause(40);
}
async function key(key, shift = false) {
  await send("Input.dispatchKeyEvent", {
    type: "keyDown",
    key,
    code: key,
    windowsVirtualKeyCode:
      key === "Tab" ? 9 : key === "Escape" ? 27 : undefined,
    modifiers: shift ? 8 : 0,
  });
  await send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key,
    code: key,
    modifiers: shift ? 8 : 0,
  });
  await pause(40);
}
async function viewport(width, height = 1000, mobile = false) {
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile,
  });
  await pause(100);
}
async function screenshot(name) {
  await pause(250);
  const { data } = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(
    path.join(output, `${name}.png`),
    Buffer.from(data, "base64"),
  );
}
async function navigate(name) {
  if (
    ["Evaluation lab", "Project reference"].includes(name) &&
    !(await evaluate(`Boolean(${buttonExpression(name)})`))
  )
    await click("Developer tools", true);
  await click(name);
  const hash = {
    Home: "home",
    Research: "research",
    "My documents": "documents",
    "Evaluation lab": "evaluations",
    "Project reference": "reference",
  }[name];
  await wait(`location.hash===${JSON.stringify("#" + hash)}`);
  await pause(100);
}
async function research(
  question,
  { configuration = "lexical", jurisdiction = "US-CA", date = "" } = {},
) {
  const previous = await evaluate(
    `(()=>{const dt=[...document.querySelectorAll('section:not([hidden]) .answer-card dt')].find(e=>e.textContent==='Run ID');return dt?.nextElementSibling?.textContent||'';})()`,
  );
  await setInput("#research-question", question);
  await evaluate(`document.querySelector('.query-options').open=true`);
  await setInput(".query-options input[type=date]", date);
  await evaluate(
    `(() => { const selects=document.querySelectorAll('.query-options select'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(selects[0],${JSON.stringify(jurisdiction)}); selects[0].dispatchEvent(new Event('change',{bubbles:true})); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(selects[1],${JSON.stringify(configuration)}); selects[1].dispatchEvent(new Event('change',{bubbles:true})); })()`,
  );
  await evaluate(`document.querySelector('.query-options').open=false`);
  await click("Search legal sources");
  await wait(
    `(()=>{const card=document.querySelector('section:not([hidden]) .answer-card');const dt=[...card?.querySelectorAll('dt')||[]].find(e=>e.textContent==='Run ID');return card&&dt?.nextElementSibling?.textContent!==${JSON.stringify(previous)}&&![...document.querySelectorAll('button')].some(e=>e.textContent.includes('Searching sources'));})()`,
    90_000,
  );
  return evaluate(
    `(() => {const a=document.querySelector('section:not([hidden]) .answer-card');return {badge:a.querySelector('.badge').textContent,answer:a.querySelector('.answer-text').textContent,claims:a.querySelectorAll('.claim').length,support:a.querySelector('.support-caption').textContent,passages:document.querySelectorAll('section:not([hidden]) .passage-tab').length};})()`,
  );
}
async function uploadFile(file) {
  const rootNode = await send("DOM.getDocument");
  const input = await send("DOM.querySelector", {
    nodeId: rootNode.root.nodeId,
    selector: "section:not([hidden]) input[type=file]",
  });
  invariant(input.nodeId, "Document file input absent");
  await send("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [file] });
  await wait(
    `![...document.querySelectorAll('button')].some(e=>e.textContent.includes('Uploading…')) && document.querySelector('section:not([hidden]) .document-detail')`,
    90_000,
  );
}
async function json(pathname, { token, method = "GET", body } = {}) {
  const response = await fetch(`${apiOrigin}/v1${pathname}`, {
    method,
    headers: {
      Origin: origin,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body && !(body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
    },
    ...(body
      ? { body: body instanceof FormData ? body : JSON.stringify(body) }
      : {}),
  });
  const data = response.status === 204 ? null : await response.json();
  return { status: response.status, data };
}

try {
  await mkdir(output, { recursive: true });
  await mkdir(profile, { recursive: true });
  let healthy = false;
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      const health = await fetch(`${apiOrigin}/health/ready`);
      const web = await fetch(origin);
      if (health.ok && web.ok) {
        healthy = true;
        break;
      }
    } catch {}
    await pause(250);
  }
  invariant(healthy, "Local web/API readiness timed out.");
  invariant(
    browserPath && existsSync(browserPath),
    "No installed Chrome/Edge/Chromium executable was found. Set LEGAL_AI_BROWSER_PATH to its full path.",
  );
  await writeFile(
    path.join(output, "synthetic-replacement.txt"),
    "SYNTHETIC REPLACEMENT LEASE\n1. Security deposit\nThe fictional deposit is $1,200. An itemized statement will identify deductions.\n2. Cleaning\nOnly cleaning beyond ordinary wear is described. No legal conclusion is established.\n",
  );
  await writeFile(
    path.join(output, "invalid-synthetic.pdf"),
    "%PDF-1.7\nThis is intentionally incomplete synthetic parser-test data.\n%%EOF\n",
  );
  browser = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-gpu",
      "--disable-extensions",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-sync",
      ...(noSandbox ? ["--no-sandbox", "--disable-setuid-sandbox"] : []),
      "--remote-debugging-address=127.0.0.1",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { windowsHide: true, stdio: "ignore" },
  );
  let version;
  for (let i = 0; i < 80; i++) {
    try {
      version = await (
        await fetch(`http://127.0.0.1:${port}/json/version`)
      ).json();
      break;
    } catch {
      await pause(150);
    }
  }
  invariant(version, "Chromium failed to start; set LEGAL_AI_BROWSER_PATH.");
  ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const request = pending.get(message.id);
      if (request) {
        pending.delete(message.id);
        message.error
          ? request.reject(new Error(JSON.stringify(message.error)))
          : request.resolve(message.result);
      }
    }
    if (message.method === "Runtime.exceptionThrown")
      runtimeErrors.push(
        message.params.exceptionDetails.exception?.description ||
          message.params.exceptionDetails.text,
      );
    if (message.method === "Network.responseReceived") {
      const { url, status } = message.params.response;
      if (url.startsWith(origin + "/api/"))
        responses.push({
          path: new URL(url).pathname.replace(/[a-f0-9]{32,}/g, "{id}"),
          status,
        });
    }
    if (message.method === "Fetch.requestPaused") {
      const { requestId, request } = message.params;
      const allowed =
        request.url.startsWith(origin + "/") ||
        request.url.startsWith("data:") ||
        request.url === "about:blank";
      if (!allowed) externalAttempts.push(new URL(request.url).origin);
      void send(
        allowed ? "Fetch.continueRequest" : "Fetch.failRequest",
        allowed ? { requestId } : { requestId, errorReason: "BlockedByClient" },
        message.sessionId,
      ).catch(() => {});
    }
  });
  const { browserContextId } = await send(
    "Target.createBrowserContext",
    {},
    null,
  );
  const { targetId } = await send(
    "Target.createTarget",
    { url: "about:blank", browserContextId },
    null,
  );
  sessionId = (
    await send("Target.attachToTarget", { targetId, flatten: true }, null)
  ).sessionId;
  for (const method of [
    "Page.enable",
    "Runtime.enable",
    "Network.enable",
    "DOM.enable",
  ])
    await send(method);
  // Use the actual reduced-motion preference for deterministic rapid pointer
  // actions. Otherwise a previous result's smooth scroll can move the next
  // submit button between CDP's layout read and native mouse dispatch.
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  await send("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
  await viewport(1440, 1050);
  await send("Page.navigate", { url: origin });
  await test(
    "Home exposes both primary tasks and creates only its own local session",
    async () => {
      await wait(
        `document.querySelector('.task-grid') && document.body.textContent.includes('Private local session')`,
      );
      invariant(
        await evaluate(
          `document.querySelectorAll('.task-grid>button').length===2 && document.querySelector('.developer-toggle').getAttribute('aria-expanded')==='false'`,
        ),
        "Home task/developer grouping incorrect",
      );
      await screenshot("home-desktop");
      return { tasks: 2 };
    },
    true,
  );
  await test("Mobile Home keeps both task choices visible and readable", async () => {
    await viewport(390, 844, true);
    await evaluate(`window.scrollTo(0,0)`);
    const data = await evaluate(
      `(()=>{const cards=[...document.querySelectorAll('.task-card')];return {cards:cards.map(e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom})),font:parseFloat(getComputedStyle(cards[0].querySelector('span:not([class])')).fontSize),overflow:document.documentElement.scrollWidth>innerWidth};})()`,
    );
    invariant(
      data.cards.every((c) => c.top >= 0 && c.bottom <= 844),
      `Task choices extend below first viewport: ${JSON.stringify(data.cards)}`,
    );
    invariant(
      data.font >= 14 && !data.overflow,
      "Mobile readability or overflow failed",
    );
    await screenshot("home-mobile");
    return data;
  });
  await viewport(1440, 1050);
  await navigate("Research");
  await test(
    "Free-form public research returns actual claims, passages and honest source counts",
    async () => {
      const answer = await research(
        "What paperwork must accompany a security deposit deduction?",
      );
      invariant(
        answer.badge.includes("Source-linked") &&
          answer.claims > 0 &&
          answer.passages > 0,
        `Unexpected research result: ${answer.badge}`,
      );
      invariant(
        answer.support.includes("source link alone"),
        "Source accounting distinction missing",
      );
      await screenshot("research-desktop");
      return answer;
    },
    true,
  );
  await test("Citation selection focuses exact evidence and source dates remain explicit", async () => {
    await clickExpression(
      `document.querySelector('section:not([hidden]) .citation')`,
    );
    await wait(`document.activeElement.matches('[data-source-excerpt]')`);
    invariant(
      await evaluate(
        `document.querySelector('section:not([hidden]) .source-dates').textContent.includes('Unknown') && document.querySelector('section:not([hidden]) .source-body [role=status]').textContent.includes('Showing')`,
      ),
      "Unknown effective dates or source announcement absent",
    );
    await viewport(390, 844, true);
    await screenshot("evidence-mobile");
    await viewport(1440, 1050);
  });
  await test("Saved run provenance loads from the API and distinguishes identity from semantics", async () => {
    await clickExpression(
      `document.querySelector('section:not([hidden]) .answer-card details.advanced summary')`,
    );
    await click("Inspect saved run");
    await wait(
      `document.querySelector('section:not([hidden]) pre[aria-label="Saved run details"]')`,
    );
    invariant(
      await evaluate(
        `document.querySelector('section:not([hidden]) .answer-card').textContent.includes('Not independently assessed')`,
      ),
      "Semantic limits absent",
    );
  });
  await test("Exact statutory citation 1950.5 works", async () => {
    const answer = await research(
      "What does Civil Code 1950.5 say about security deposits?",
    );
    invariant(
      answer.badge.includes("Source-linked") && answer.passages > 0,
      "Exact statutory citation did not retrieve evidence",
    );
    return { claims: answer.claims, passages: answer.passages };
  });
  for (const configuration of ["lexical", "dense", "hybrid", "rerank"])
    await test(`Real ${configuration} retrieval path answers locally`, async () => {
      const answer = await research(
        "What paperwork must accompany a security deposit deduction?",
        { configuration },
      );
      invariant(
        answer.badge.includes("Source-linked"),
        `${configuration} returned ${answer.badge}`,
      );
      return { passages: answer.passages, claims: answer.claims };
    });
  for (const [name, question, options] of [
    [
      "Other jurisdiction abstains",
      "What paperwork accompanies a deposit deduction?",
      { jurisdiction: "US-NY" },
    ],
    [
      "Foreign state named in the question abstains",
      "What paperwork must accompany a security deposit deduction in Massachusetts?",
      {},
    ],
    [
      "Unknown historical applicability abstains",
      "What paperwork accompanies a deposit deduction?",
      { date: "2020-01-01" },
    ],
    [
      "Relative historical applicability abstains",
      "What paperwork was required for a security deposit deduction two years ago?",
      {},
    ],
    [
      "Individual lawfulness verdict abstains",
      "Is my landlord breaking the law by keeping my deposit?",
      {},
    ],
    [
      "Out-of-corpus question abstains",
      "What are the federal patent filing deadlines?",
      {},
    ],
  ])
    await test(name, async () => {
      const answer = await research(question, options);
      invariant(
        answer.badge.includes("Insufficient evidence"),
        `Expected abstention, received ${answer.badge}`,
      );
      return { claims: answer.claims };
    });
  await test("Actual local transport failure is distinct from evidence gaps and retry recovers", async () => {
    await setInput(
      "#research-question",
      "What paperwork must accompany a security deposit deduction?",
    );
    try {
      await send("Network.emulateNetworkConditions", {
        offline: true,
        latency: 0,
        downloadThroughput: 0,
        uploadThroughput: 0,
      });
      await click("Search legal sources");
      await wait(
        `document.querySelector('section:not([hidden]) [role=alert]')`,
      );
      invariant(
        await evaluate(
          `document.querySelector('section:not([hidden]) [role=alert]').textContent.includes('could not be reached') && !document.querySelector('section:not([hidden]) .answer-card')`,
        ),
        "Transport failure was shown as an evidence result",
      );
    } finally {
      await send("Network.emulateNetworkConditions", {
        offline: false,
        latency: 0,
        downloadThroughput: -1,
        uploadThroughput: -1,
      });
    }
    await click("Try again", true);
    await wait(
      `document.querySelector('section:not([hidden]) .answer-card .badge')?.textContent.includes('Source-linked')`,
      90_000,
    );
  });
  await test("Pending real request can be cancelled without a false error result", async () => {
    await setInput(
      "#research-question",
      "What paperwork must accompany a security deposit deduction?",
    );
    try {
      await send("Network.emulateNetworkConditions", {
        offline: false,
        latency: 1500,
        downloadThroughput: -1,
        uploadThroughput: -1,
      });
      await click("Search legal sources");
      await click("Cancel");
      invariant(
        await evaluate(
          `!document.querySelector('section:not([hidden]) .answer-card') && !document.querySelector('section:not([hidden]) [role=alert]')`,
        ),
        "Cancelled request left an error or answer",
      );
    } finally {
      await send("Network.emulateNetworkConditions", {
        offline: false,
        latency: 0,
        downloadThroughput: -1,
        uploadThroughput: -1,
      });
    }
  });
  await test("Keyboard skip link preserves Research and focuses main", async () => {
    await evaluate(`document.querySelector('.skip-link').focus()`);
    await key("Enter");
    invariant(
      await evaluate(
        `document.activeElement===document.querySelector('main') && location.hash==='#research'`,
      ),
      "Skip link changed task or failed focus",
    );
  });
  await navigate("My documents");
  await wait(
    `document.querySelector('section:not([hidden]) .upload-card') && !document.querySelector('section:not([hidden]) .busy')`,
  );
  await test("Keyboard skip link preserves Documents and ignores non-view hashes", async () => {
    await evaluate(`document.querySelector('.skip-link').focus()`);
    await key("Enter");
    invariant(
      await evaluate(
        `document.activeElement===document.querySelector('main') && location.hash==='#documents'`,
      ),
      "Documents skip failed",
    );
    await evaluate(`location.hash='main'`);
    await pause(100);
    invariant(
      await evaluate(
        `document.querySelector('button[aria-current=page]').textContent.includes('My documents')`,
      ),
      "Non-view hash changed task",
    );
    await evaluate(`history.replaceState(null,'','#documents')`);
  });
  await test(
    "Real multipart upload parses sample lease into sections and private passages",
    async () => {
      await uploadFile(path.join(root, "samples", "example-lease.txt"));
      await wait(
        `document.querySelector('section:not([hidden]) .document-detail .badge').textContent==='Ready'`,
      );
      invariant(
        await evaluate(
          `document.querySelector('section:not([hidden]) .document-list').textContent.includes('example-lease.txt') && document.querySelector('section:not([hidden]) .processing-steps').textContent.includes('Ready')`,
        ),
        "Upload ready state absent",
      );
      await click("Read document text");
      invariant(
        await evaluate(
          `document.querySelectorAll('section:not([hidden]) .sections-list article').length>0 && document.querySelector('section:not([hidden]) .sections-list').textContent.includes('$1,500')`,
        ),
        "Actual parsed sections absent",
      );
      return {
        sections: await evaluate(
          `document.querySelectorAll('section:not([hidden]) .sections-list article').length`,
        ),
      };
    },
    true,
  );
  await test("Document analysis returns actual findings and public source comparison", async () => {
    await click("Key points & questions");
    await click("Analyze & compare sources");
    await wait(
      `document.querySelector('section:not([hidden]) .analysis')`,
      90_000,
    );
    invariant(
      await evaluate(
        `document.querySelectorAll('section:not([hidden]) .finding').length>0 && document.querySelector('section:not([hidden]) .comparison .source-inspector')`,
      ),
      "Analysis or comparison absent",
    );
    await screenshot("documents-desktop");
    return {
      findings: await evaluate(
        `document.querySelectorAll('section:not([hidden]) .finding').length`,
      ),
    };
  });
  await test("Document finding link focuses the matching extracted section", async () => {
    await click("Read the document text ↗");
    await wait(`document.activeElement.matches('.sections-list article')`);
    await click("Key points & questions");
  });
  await test("Private document Q&A returns private source passages, not a legal verdict", async () => {
    await setInput(
      "#document-question",
      "What does the document say about the security deposit?",
    );
    await click("Ask about the document");
    await wait(
      `document.querySelector('section:not([hidden]) .answer-card')`,
      90_000,
    );
    invariant(
      await evaluate(
        `document.querySelector('section:not([hidden]) .answer-card .badge').textContent.includes('Source-linked') && [...document.querySelectorAll('section:not([hidden]) .source-body .badge')].some(e=>e.textContent==='Private document')`,
      ),
      "Private grounded answer absent",
    );
    await viewport(390, 844, true);
    await evaluate(
      `document.querySelector('section:not([hidden]) .document-review').scrollIntoView({block:'start'})`,
    );
    await screenshot("documents-mobile");
    await viewport(1440, 1050);
  });
  await test("Document findings, private answer and comparisons reflow at every target width", async () => {
    for (const width of [360, 390, 768, 1024, 1440]) {
      await viewport(width, width < 700 ? 844 : 1000, width < 700);
      invariant(
        await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),
        `Document analysis overflows at ${width}`,
      );
    }
    await viewport(1440, 1050);
  });
  await test("Original download returns actual owned bytes through the browser session", async () => {
    const data = await evaluate(
      `(async()=>{const a=[...document.querySelectorAll('a')].find(e=>e.textContent.includes('Download original'));const r=await fetch(a.href,{credentials:'same-origin'});const text=await r.text();return {status:r.status,synthetic:text.includes('SYNTHETIC RESIDENTIAL LEASE'),hasAmount:text.includes('$1,500')};})()`,
    );
    invariant(
      data.status === 200 && data.synthetic && data.hasAmount,
      "Owned original download incorrect",
    );
  });
  await test("Deletion modal traps Tab, Escape restores focus, and cancellation preserves document", async () => {
    await click("Delete document");
    await wait(`document.querySelector('dialog[open]')`);
    invariant(
      await evaluate(`document.activeElement.textContent==='Keep document'`),
      "Modal did not focus safe choice",
    );
    await key("Tab", true);
    invariant(
      await evaluate(
        `document.activeElement.textContent==='Delete document' && document.activeElement.closest('dialog')`,
      ),
      "Shift+Tab escaped modal",
    );
    await key("Tab");
    invariant(
      await evaluate(`document.activeElement.textContent==='Keep document'`),
      "Tab did not wrap",
    );
    await key("Escape");
    invariant(
      await evaluate(
        `!document.querySelector('dialog[open]') && document.activeElement.textContent==='Delete document' && document.querySelector('section:not([hidden]) .document-detail')`,
      ),
      "Escape focus/retention incorrect",
    );
  });
  await test("Replacement uploads new content and removes the previous current document", async () => {
    await click("Replace file");
    await uploadFile(path.join(output, "synthetic-replacement.txt"));
    await wait(
      `document.querySelector('section:not([hidden]) .document-filename').textContent==='synthetic-replacement.txt'`,
    );
    invariant(
      await evaluate(
        `!document.querySelector('section:not([hidden]) .document-list').textContent.includes('example-lease.txt') && document.querySelector('section:not([hidden]) .document-detail .badge').textContent==='Ready'`,
      ),
      "Prior version remains visible after ready replacement",
    );
  });
  await test("Confirmed deletion reports API result and returns focus to document list", async () => {
    await click("Delete document");
    await wait(`document.querySelector('dialog[open]')`);
    await clickExpression(
      `[...document.querySelectorAll('dialog button')].find(e=>e.textContent==='Delete document')`,
    );
    await wait(
      `!document.querySelector('dialog[open]') && !document.querySelector('section:not([hidden]) .document-detail')`,
    );
    invariant(
      await evaluate(
        `document.querySelector('section:not([hidden]) [role=status]').textContent.includes('confirmed deletion') && document.activeElement.matches('.document-list h2')`,
      ),
      "Deletion success/focus not confirmed",
    );
  });
  await test("Invalid synthetic PDF exposes real parsing failure and retry remains honest", async () => {
    await uploadFile(path.join(output, "invalid-synthetic.pdf"));
    await wait(
      `document.querySelector('section:not([hidden]) .document-detail .badge').textContent==='Needs attention'`,
    );
    const before = responses.filter((r) => r.path.endsWith("/retry")).length;
    await click("Retry processing");
    await wait(
      `![...document.querySelectorAll('button')].some(e=>e.textContent==='Retrying…')`,
    );
    invariant(
      responses.filter((r) => r.path.endsWith("/retry")).length > before,
      "Retry did not call real API",
    );
    invariant(
      await evaluate(
        `document.querySelector('section:not([hidden]) .document-detail .badge').textContent==='Needs attention'`,
      ),
      "Invalid parser data falsely became ready",
    );
    await click("Delete document");
    await clickExpression(
      `[...document.querySelectorAll('dialog button')].find(e=>e.textContent==='Delete document')`,
    );
    await wait(`!document.querySelector('dialog[open]')`);
    return "Retry endpoint exercised on persistently invalid bytes; successful interrupted-worker recovery is covered separately by backend tests.";
  });
  await click("Developer tools", true);
  await navigate("Evaluation lab");
  await test("Evaluation runs a real versioned dataset with all four local configurations", async () => {
    await wait(`document.querySelector('#evaluation-dataset option')?.value`);
    await click("Run evaluation");
    await wait(
      `document.querySelector('section:not([hidden]) .evaluation-result')`,
      90_000,
    );
    invariant(
      await evaluate(
        `document.querySelectorAll('section:not([hidden]) .evaluation-result thead th').length===5 && document.querySelector('section:not([hidden]) .evaluation-result').textContent.includes('Not assessed') && document.querySelector('section:not([hidden]) .evaluation-result').textContent.includes('Judgment provenance')`,
      ),
      "Measured comparison/null provenance absent",
    );
    await screenshot("evaluations-desktop");
    await viewport(390, 844, true);
    await evaluate(
      `document.querySelector('section:not([hidden]) .evaluation-result').scrollIntoView({block:'start'})`,
    );
    await screenshot("evaluations-mobile");
    await viewport(1440, 1050);
  });
  await test("Evaluation preserves actual manifest, case results and list navigation", async () => {
    await clickExpression(
      `document.querySelector('section:not([hidden]) .evaluation-result details.advanced summary')`,
    );
    invariant(
      await evaluate(
        `document.querySelectorAll('section:not([hidden]) .evaluation-result .case-details').length>0 && document.querySelector('section:not([hidden]) .evaluation-result').textContent.includes('Reproduction manifest')`,
      ),
      "Case results/manifest absent",
    );
    await clickExpression(
      `document.querySelector('section:not([hidden]) .run-item')`,
    );
    await wait(`!document.querySelector('section:not([hidden]) .busy')`);
  });
  await navigate("Project reference");
  await test("Reference uses the actual three-source, 122-passage corpus with unknown applicability dates", async () => {
    await wait(`document.querySelectorAll('.corpus-source').length===3`);
    await clickExpression(`document.querySelector('.corpus-source summary')`);
    invariant(
      await evaluate(
        `document.querySelector('.corpus-source').textContent.includes('Unknown') && document.querySelector('.corpus-reference').textContent.includes('3 archived public sources')`,
      ),
      "Corpus source count or unknown dates absent",
    );
    const counts = await evaluate(
      `(async()=>{const corpus=await(await fetch('/api/v1/corpus')).json();let passages=0;for(const source of corpus.sources){const detail=await(await fetch('/api/v1/sources/'+encodeURIComponent(source.source_id))).json();passages+=detail.passages.length;}return {sources:corpus.sources.length,passages};})()`,
    );
    invariant(
      counts.sources === 3 && counts.passages === 122,
      `Corpus identity changed: ${JSON.stringify(counts)}`,
    );
    return counts;
  });
  await test("Customer/developer control names and text field labels are present", async () => {
    const issues = await evaluate(
      `(()=>{const visible=e=>e.getClientRects().length&&!e.closest('[hidden]');return [...document.querySelectorAll('button,input,textarea,select')].filter(visible).filter(e=>{if(e.tagName==='BUTTON')return !(e.getAttribute('aria-label')||e.textContent.trim()); if(e.type==='checkbox')return !e.closest('label')&&!e.labels?.length; return !(e.getAttribute('aria-label')||e.labels?.length);}).map(e=>e.tagName+':'+e.type);})()`,
    );
    invariant(!issues.length, `Unnamed controls: ${issues.join(",")}`);
  });
  await test("All five views reflow at 360, 390, 768, 1024 and 1440 CSS pixels", async () => {
    await navigate("Research");
    await research(
      "What paperwork must accompany a security deposit deduction?",
    );
    const checked = [];
    for (const width of [360, 390, 768, 1024, 1440]) {
      await viewport(width, width < 700 ? 844 : 1000, width < 700);
      for (const name of [
        "Home",
        "Research",
        "My documents",
        "Evaluation lab",
        "Project reference",
      ]) {
        await navigate(name);
        const size = await evaluate(
          `({width:innerWidth,scroll:document.documentElement.scrollWidth})`,
        );
        invariant(
          size.scroll <= size.width + 1,
          `${name} overflows at ${width}: ${size.scroll}`,
        );
        checked.push({ view: name, width });
      }
    }
    await viewport(720, 900);
    await navigate("Research");
    invariant(
      await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),
      "200% equivalent 720 CSS pixel reflow overflow",
    );
    return { layouts: checked.length, zoom_equivalent_css_width: 720 };
  });
  await test("Reduced motion removes animation and key text contrast meets WCAG AA", async () => {
    await send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    invariant(
      await evaluate(`matchMedia('(prefers-reduced-motion: reduce)').matches`),
      "Reduced motion not emulated",
    );
    await navigate("Home");
    const data = await evaluate(
      `(()=>{function rgb(s){return s.match(/[\\d.]+/g).slice(0,3).map(Number)}function lum(s){const v=rgb(s).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4});return .2126*v[0]+.7152*v[1]+.0722*v[2]}const p=document.querySelector('.task-primary');const a=lum(getComputedStyle(p).color),b=lum(getComputedStyle(p).backgroundColor);const text=document.querySelector('.home-heading p');const c=lum(getComputedStyle(text).color),d=lum(getComputedStyle(document.body).backgroundColor);return {primary:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),body:(Math.max(c,d)+.05)/(Math.min(c,d)+.05),transition:getComputedStyle(p).transitionDuration};})()`,
    );
    invariant(
      data.primary >= 4.5 && data.body >= 4.5 && data.transition === "0s",
      `Contrast/motion issue: ${JSON.stringify(data)}`,
    );
    return data;
  });
  await test("Separate-session real HTTP authorization prevents document, source and trace leakage", async () => {
    const a = (
      await json("/sessions", {
        method: "POST",
        body: { label: "Synthetic browser QA owner" },
      })
    ).data;
    const b = (
      await json("/sessions", {
        method: "POST",
        body: { label: "Synthetic browser QA other" },
      })
    ).data;
    invariant(a.workspace_id !== b.workspace_id, "Sessions shared a workspace");
    const form = new FormData();
    form.append(
      "file",
      new File(
        [await readFile(path.join(root, "samples", "example-lease.txt"))],
        "synthetic-isolation.txt",
        { type: "text/plain" },
      ),
    );
    const uploaded = await json("/documents", {
      token: a.access_token,
      method: "POST",
      body: form,
    });
    invariant(
      uploaded.status === 201 && uploaded.data.status === "ready",
      "Isolation fixture upload failed",
    );
    const id = uploaded.data.document_id;
    const own = await json(`/documents/${id}`, { token: a.access_token });
    const source = own.data.passages[0]?.source_id;
    const answer = await json("/research", {
      token: a.access_token,
      method: "POST",
      body: {
        question: "What does this document say about the security deposit?",
        jurisdiction: "US-CA",
        applicable_on: null,
        source_scope: "private",
        document_id: id,
        configuration: "lexical",
        top_k: 5,
      },
    });
    invariant(answer.status === 200, "Own private Q&A failed");
    const checks = [
      [`/documents/${id}`, "GET"],
      [`/documents/${id}/download`, "GET"],
      [`/documents/${id}/analysis`, "POST"],
      [`/documents/${id}/retry`, "POST"],
      [`/documents/${id}`, "DELETE"],
      [`/sources/${source}`, "GET"],
      [`/runs/${answer.data.run_id}`, "GET"],
    ];
    for (const [pathname, method] of checks) {
      const res = await fetch(`${apiOrigin}/v1${pathname}`, {
        method,
        headers: {
          Authorization: `Bearer ${b.access_token}`,
          ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
        },
        ...(method === "POST" ? { body: "{}" } : {}),
      });
      invariant(
        [403, 404].includes(res.status),
        `Foreign ${method} ${pathname.replace(id, "{id}")} returned ${res.status}`,
      );
    }
    invariant(
      (await json("/documents", { token: b.access_token })).data.documents
        .length === 0,
      "Foreign private listing leaked",
    );
    invariant(
      (await json(`/documents/${id}`)).status === 401,
      "Anonymous private access accepted",
    );
    await json(`/documents/${id}`, { token: a.access_token, method: "DELETE" });
    invariant(
      (await json(`/runs/${answer.data.run_id}`, { token: a.access_token }))
        .status === 404,
      "Deletion retained private run diagnostics",
    );
    await json("/session", { token: a.access_token, method: "DELETE" });
    await json("/session", { token: b.access_token, method: "DELETE" });
    return {
      unauthorized_operations: checks.length + 2,
      private_diagnostics_purged: true,
    };
  });
  await test("No browser runtime exceptions or external request attempts occurred", async () => {
    invariant(
      runtimeErrors.length === 0,
      `${runtimeErrors.length} browser runtime exceptions`,
    );
    invariant(
      externalAttempts.length === 0,
      `${externalAttempts.length} external requests blocked`,
    );
    return { exceptions: 0, external_requests: 0 };
  });
  await writeFile(
    path.join(output, "report.json"),
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        browser: version.Browser,
        origin,
        duration_ms: Date.now() - start,
        passed: results.filter((r) => r.passed).length,
        failed: results.filter((r) => !r.passed).length,
        results,
        runtime_errors: runtimeErrors,
        external_attempts: externalAttempts,
        api_responses: responses,
        limitations: [
          "Automated browser checks do not establish novice-user comprehension or an independent accessibility audit.",
          "720 CSS pixels exercise reflow equivalent to 200% zoom on a 1440 CSS pixel viewport; native browser zoom itself is not emulated.",
          "No live provider, Pinecone, deployment or independent semantic-quality gate is exercised.",
          "Persistently invalid PDF retry exercises honest failure; interrupted-job successful recovery remains a backend integration-test gate.",
        ],
      },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      passed: results.filter((r) => r.passed).length,
      failed: results.filter((r) => !r.passed).length,
      report: "artifacts/browser/report.json",
    }),
  );
  if (results.some((r) => !r.passed)) process.exitCode = 1;
} catch (error) {
  await mkdir(output, { recursive: true });
  await writeFile(
    path.join(output, "report.json"),
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        failed: results.filter((r) => !r.passed).length || 1,
        passed: results.filter((r) => r.passed).length,
        error: error.message,
        results,
        runtime_errors: runtimeErrors,
        external_attempts: externalAttempts,
      },
      null,
      2,
    ),
  );
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (ws?.readyState === WebSocket.OPEN) {
    try {
      await send("Browser.close", {}, null);
    } catch {}
    ws.close();
  }
  browser?.kill();
}
