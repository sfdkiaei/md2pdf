#!/usr/bin/env node
/**
 * HTML -> PDF through a local Chrome, with no npm dependencies.
 *
 * Chrome is driven over the DevTools Protocol using Node's built-in WebSocket
 * and fetch (Node >= 22). Puppeteer would do the same thing, but it is one more
 * install to keep current — and the only feature we need beyond `chrome
 * --print-to-pdf` is a footer template, which the CLI cannot express.
 *
 * Usage: node render.mjs <input.html> <output.pdf> [waitMs]
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    try { readFileSync(p); return p; } catch { /* keep looking */ }
  }
  throw new Error(
    'No Chrome found. Set CHROME_PATH to a Chrome/Chromium/Edge binary.\n' +
    'Looked in:\n  ' + CHROME_CANDIDATES.join('\n  '));
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** Minimal CDP client: send(method, params) -> result. */
class CDP {
  #ws; #id = 0; #pending = new Map();
  static async connect(url) {
    const c = new CDP();
    c.#ws = new WebSocket(url);
    await new Promise((ok, bad) => { c.#ws.onopen = ok; c.#ws.onerror = bad; });
    c.#ws.onmessage = e => {
      const m = JSON.parse(e.data);
      const p = c.#pending.get(m.id);
      if (!p) return;                      // an event, not a reply
      c.#pending.delete(m.id);
      m.error ? p.bad(new Error(m.error.message)) : p.ok(m.result);
    };
    return c;
  }
  send(method, params = {}) {
    const id = ++this.#id;
    this.#ws.send(JSON.stringify({ id, method, params }));
    return new Promise((ok, bad) => this.#pending.set(id, { ok, bad }));
  }
  close() { this.#ws.close(); }
}

const [htmlPath, pdfPath, waitMsArg] = process.argv.slice(2);
if (!htmlPath || !pdfPath) {
  console.error('usage: node render.mjs <input.html> <output.pdf> [waitMs]');
  process.exit(2);
}
const maxWaitMs = Number(waitMsArg || 60000);

const profile = mkdtempSync(join(tmpdir(), 'md2pdf-'));
const chrome = spawn(findChrome(), [
  '--headless=new',
  '--remote-debugging-port=0',          // Chrome picks a free port and reports it
  `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check',
  '--no-sandbox', '--disable-setuid-sandbox',
  '--disable-gpu', '--font-render-hinting=none',
  '--allow-file-access-from-files',
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

let stderr = '';
chrome.stderr.on('data', d => { stderr += d; });

async function devtoolsPort() {
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 200; i++) {
    try {
      const [port] = readFileSync(portFile, 'utf8').split('\n');
      if (port) return port.trim();
    } catch { /* not written yet */ }
    await sleep(50);
  }
  throw new Error('Chrome did not start.\n' + stderr.slice(-800));
}

const footer = `
<div style="width:100%;font-family:'IRANSans','IRANSansWeb',Tahoma,sans-serif;
            font-size:8pt;color:#5a6373;text-align:center;padding-top:2mm;">
  <span class="pageNumber"></span>
</div>`;

try {
  const port = await devtoolsPort();
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,
                                   { method: 'PUT' })).json();
  const cdp = await CDP.connect(target.webSocketDebuggerUrl);

  await cdp.send('Page.enable');
  await cdp.send('Page.navigate', { url: 'file://' + resolve(htmlPath) });

  // The page sets window.__READY__ once mermaid has drawn and fonts have
  // loaded. Polling that flag is what keeps a diagram from being printed
  // half-rendered; the timeout keeps a broken page from hanging the build.
  const deadline = Date.now() + maxWaitMs;
  let ready = false;
  while (Date.now() < deadline) {
    const r = await cdp.send('Runtime.evaluate',
                             { expression: 'window.__READY__ === true', returnByValue: true });
    if (r.result?.value === true) { ready = true; break; }
    await sleep(120);
  }
  if (!ready) console.error('warning: page never signalled ready; printing anyway');

  const { data } = await cdp.send('Page.printToPDF', {
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: footer,
    // The stylesheet owns page size and margins.
    preferCSSPageSize: true,
  });
  writeFileSync(pdfPath, Buffer.from(data, 'base64'));
  cdp.close();
  console.log('wrote ' + pdfPath);
} finally {
  chrome.kill('SIGKILL');
  try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ }
}
