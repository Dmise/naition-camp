#!/usr/bin/env node
/**
 * Scrapes ALL Yandex Metrika Webvisor visits via Chrome DevTools Protocol.
 * Requires Chrome with --remote-debugging-port=9222 and logged-in Metrika session.
 *
 * Env:
 *   CDP_URL              default http://127.0.0.1:9222
 *   WEBVISOR_PERIOD      week | month | quarter (default week)
 *   WEBVISOR_CONCURRENCY default 3
 *   WEBVISOR_OUT_DIR     default analysis
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const CDP_HOST = process.env.CDP_URL || 'http://127.0.0.1:9222';
const COUNTER_ID = '111696929';
const PERIOD = process.env.WEBVISOR_PERIOD || 'week';
const CONCURRENCY = Number(process.env.WEBVISOR_CONCURRENCY || 3);
const OUT_ROOT = path.resolve(ROOT, process.env.WEBVISOR_OUT_DIR || 'analysis');
const VISITS_DIR = path.join(OUT_ROOT, 'webvisor');

const LIST_URL =
  `https://metrika.yandex.ru/stat/visor?period=${PERIOD}&id=${COUNTER_ID}` +
  '&group=day&isMinSamplingEnabled=false&currency=RUB' +
  '&attr=%7B%22attributionId%22%3A%22LastSign%22%2C%22isCrossDevice%22%3Atrue%7D' +
  '&isUndefinedEnabled=false';

const API_MARKERS = [
  'getVisitInfo',
  'getCalculatedVisitInfo',
  'fetchHit',
  'getCounterGoalsById',
  'getDefaultVisitDimensions',
];

function playerUrl(visit) {
  const p = new URLSearchParams({
    id: COUNTER_ID,
    offset: '0',
    date: visit.date,
    date_visit: '',
    visit_id: visit.visit_id,
    watch_id: '',
    user_id_hash: visit.user_id_hash,
    dn: '',
    tld: 'ru',
  });
  return `https://metrika.yandex.ru/inpage/visor-proto?${p}`;
}

function visitOutPath(visit) {
  const dateDir = visit.date || 'unknown';
  return path.join(VISITS_DIR, dateDir, `visit_${visit.visit_id}.json`);
}

async function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timeout after ${ms}ms`)), ms);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url, init) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

class CdpSession {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.handlers = [];
    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(String(event.data));
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
        return;
      }
      for (const h of this.handlers) h(msg);
    });
  }

  onMessage(handler) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  static async connect(wsUrl) {
    const ws = new WebSocket(wsUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true });
      ws.addEventListener('error', reject, { once: true });
    });
    const session = new CdpSession(ws);
    await session.send('Runtime.enable');
    await session.send('Page.enable');
    await session.send('Network.enable');
    return session;
  }

  close() {
    this.ws.close();
  }
}

async function listTargets() {
  return fetchJson(`${CDP_HOST}/json/list`);
}

async function findExistingVisorPage() {
  const targets = await listTargets();
  return targets.find(
    (t) => t.type === 'page' && t.url.includes('/stat/visor') && t.url.includes(`id=${COUNTER_ID}`),
  );
}

async function createTarget(url) {
  return fetchJson(`${CDP_HOST}/json/new?${new URLSearchParams({ url })}`, { method: 'PUT' });
}

async function closeTarget(id) {
  await fetch(`${CDP_HOST}/json/close/${id}`, { method: 'PUT' }).catch(() => {});
}

async function connectSession(target) {
  return CdpSession.connect(target.webSocketDebuggerUrl);
}

async function waitForPageLoad(session, timeoutMs = 120000) {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Page load timeout')), timeoutMs);
    const off = session.onMessage((msg) => {
      if (msg.method === 'Page.loadEventFired') {
        clearTimeout(timer);
        off();
        resolve();
      }
    });
  }).catch(async () => {
    await waitForReadyState(session, timeoutMs);
  });
}

async function waitForReadyState(session, timeoutMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const { result } = await session.send('Runtime.evaluate', {
      expression: 'document.readyState',
      returnByValue: true,
    });
    if (result.value === 'complete') return;
    await new Promise((r) => setTimeout(r, 300));
  }
}

async function withTarget(url, fn, { keepOpen = false, existingTarget = null } = {}) {
  const ownsTarget = !existingTarget;
  const target = existingTarget || (await createTarget(url));
  const session = await connectSession(target);
  try {
    if (!existingTarget) {
      await waitForPageLoad(session).catch(() => {});
      await waitForReadyState(session, 30000);
    }
    return await fn(session, target);
  } finally {
    session.close();
    if (ownsTarget && !keepOpen) await closeTarget(target.id);
  }
}

/** Reusable worker tab: navigate instead of open/close per visit. */
class WorkerTab {
  constructor(target, session) {
    this.target = target;
    this.session = session;
    this.busy = false;
  }

  static async create() {
    const target = await createTarget('about:blank');
    const session = await connectSession(target);
    return new WorkerTab(target, session);
  }

  async navigate(url) {
    await this.session.send('Page.navigate', { url });
    await waitForReadyState(this.session, 60000);
  }

  async close() {
    this.session.close();
    await closeTarget(this.target.id);
  }
}

async function createWorkerPool(size) {
  const workers = [];
  for (let i = 0; i < size; i++) workers.push(await WorkerTab.create());
  return workers;
}

async function closeWorkerPool(workers) {
  await Promise.all(workers.map((w) => w.close()));
}

async function evalInPage(session, fnBody) {
  const { result } = await session.send('Runtime.evaluate', {
    expression: `(() => { ${fnBody} })()`,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(JSON.stringify(result.exceptionDetails));
  }
  return result.value;
}

async function waitForIframe(session, timeoutMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const state = await evalInPage(session, `
      const iframe = document.querySelector('iframe');
      const doc = iframe?.contentDocument;
      const links = doc?.querySelectorAll('a[href*="visor-proto"]')?.length || 0;
      return { hasIframe: !!iframe, hasDoc: !!doc, links };
    `);
    if (state?.hasDoc && state.links > 0) return state;
    await new Promise((r) => setTimeout(r, 800));
  }
  throw new Error('Timeout waiting for iframe visit list');
}

async function getListPaginationState(session) {
  return evalInPage(session, `
    const doc = document.querySelector('iframe')?.contentDocument;
    if (!doc) return { error: 'no iframe doc' };
    const allText = doc.body?.innerText || '';
    const match = allText.match(/Показано\\s+(\\d+)\\s+из\\s+(\\d+)\\s+строк/i);
    const shown = match ? Number(match[1]) : null;
    const total = match ? Number(match[2]) : null;
    const links = doc.querySelectorAll('a[href*="visor-proto"]').length;
    const btn = [...doc.querySelectorAll('button, [role="button"], a, span')].find(el =>
      /показать ещё/i.test(el.textContent || '')
    );
    return { shown, total, links, hasMoreButton: !!btn, buttonText: btn?.textContent?.trim() || null };
  `);
}

async function clickShowMore(session) {
  return evalInPage(session, `
    const doc = document.querySelector('iframe')?.contentDocument;
    if (!doc) return { clicked: false, reason: 'no doc' };
    const btn = [...doc.querySelectorAll('button, [role="button"], a, span')].find(el =>
      /показать ещё/i.test(el.textContent || '')
    );
    if (!btn) return { clicked: false, reason: 'no button' };
    btn.click();
    return { clicked: true };
  `);
}

async function loadAllVisitsFromList(session) {
  await waitForIframe(session);

  let prevLinks = 0;
  let stagnant = 0;
  const maxClicks = 500;

  for (let i = 0; i < maxClicks; i++) {
    const state = await getListPaginationState(session);
    console.log(
      `  list page: links=${state.links}, shown=${state.shown ?? '?'} / ${state.total ?? '?'}, more=${state.hasMoreButton}`,
    );

    if (state.total && state.links >= state.total) break;
    if (!state.hasMoreButton) break;

    const click = await clickShowMore(session);
    if (!click.clicked) break;

    await new Promise((r) => setTimeout(r, 1500));

    const after = await getListPaginationState(session);
    if (after.links <= prevLinks) {
      stagnant += 1;
      if (stagnant >= 3) break;
    } else {
      stagnant = 0;
      prevLinks = after.links;
    }
  }

  const visits = await evalInPage(session, `
    const doc = document.querySelector('iframe')?.contentDocument;
    if (!doc) return [];
    return [...doc.querySelectorAll('a[href*="visor-proto"]')].map((a) => {
      const u = new URL(a.href);
      const row = a.closest('tr') || a.closest('[role="row"]') || a.parentElement?.parentElement;
      const cells = row
        ? [...row.querySelectorAll('td, [role="gridcell"], span, div')].map(el => el.textContent?.trim()).filter(Boolean)
        : [];
      return {
        visit_id: u.searchParams.get('visit_id'),
        user_id_hash: u.searchParams.get('user_id_hash'),
        date: u.searchParams.get('date'),
        player_url: a.href,
        row_text: cells.slice(0, 10),
      };
    });
  `);

  const unique = new Map();
  for (const v of visits || []) {
    if (v?.visit_id) unique.set(v.visit_id, v);
  }
  return [...unique.values()];
}

async function getVisitsFromList() {
  const existing = await findExistingVisorPage();
  const runner = async (session) => loadAllVisitsFromList(session);

  if (existing) {
    console.log(`Using existing visor tab: ${existing.url}`);
    return withTarget(existing.url, runner, { existingTarget: existing });
  }
  console.log(`Opening visor list: ${LIST_URL}`);
  return withTarget(LIST_URL, runner);
}

async function waitForApis(captured, timeoutMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const hasInfo = !!captured.api.getVisitInfo;
    const hasHit = !!captured.api.fetchHit;
    if (hasInfo && hasHit) return;
    if (hasInfo && Date.now() - start > 15000) return; // fetchHit optional after 15s
    await new Promise((r) => setTimeout(r, 400));
  }
}

function parseEvents(fetchHit) {
  const events = fetchHit?.result?.data?.events || fetchHit?.events || [];
  const parsed = events.map((ev) => {
    let data;
    try {
      data = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data;
    } catch {
      data = { raw: ev.data };
    }
    return { stamp: ev.stamp, group: ev.group, ...data };
  });

  const times = parsed.map((e) => e.time ?? e.stamp ?? 0);
  const durationMs = times.length ? Math.max(...times) : 0;

  return {
    parsed_events: parsed,
    summary: {
      total_events: parsed.length,
      clicks: parsed.filter((e) => e.type === 'click').length,
      scrolls: parsed.filter((e) => e.type === 'scroll').length,
      mousemoves: parsed.filter((e) => e.type === 'mousemove').length,
      inputs: parsed.filter((e) => e.type === 'input' || e.type === 'change').length,
      keydowns: parsed.filter((e) => e.type === 'keydown' || e.type === 'keyup').length,
      duration_ms: durationMs,
      duration_sec: Math.round(durationMs / 1000),
    },
  };
}

function extractVisitInfo(api) {
  const info = api.getVisitInfo?.result || api.getVisitInfo?.data || api.getVisitInfo;
  const calc = api.getCalculatedVisitInfo?.result || api.getCalculatedVisitInfo?.data || api.getCalculatedVisitInfo;
  return { visit_info: info || null, calculated: calc || null };
}

async function capturePlayerData(visit, worker) {
  return withTimeout(doCapturePlayerData(visit, worker), 120000, `visit ${visit.visit_id}`);
}

async function doCapturePlayerData(visit, worker) {
  const captured = {
    visit_id: visit.visit_id,
    user_id_hash: visit.user_id_hash,
    date: visit.date,
    player_url: playerUrl(visit),
    list_row: visit.row_text,
    scraped_at: new Date().toISOString(),
    api: {},
    ui: {},
  };

  const session = worker.session;
  const pendingBodies = new Set();

  const off = session.onMessage(async (msg) => {
    if (msg.method !== 'Network.responseReceived') return;
    const { response, requestId } = msg.params;
    const url = response?.url || '';
    if (!url.includes('/i-proxy/i-webvisor') && !url.includes('i-webvisor2-api')) return;
    const marker = API_MARKERS.find((m) => url.includes(m));
    if (!marker || captured.api[marker]) return;
    pendingBodies.add(requestId);
    try {
      await new Promise((r) => setTimeout(r, 200));
      const body = await session.send('Network.getResponseBody', { requestId });
      const text = body.base64Encoded ? Buffer.from(body.body, 'base64').toString('utf8') : body.body;
      captured.api[marker] = JSON.parse(text);
    } catch {
      // body may be unavailable
    } finally {
      pendingBodies.delete(requestId);
    }
  });

  try {
    await worker.navigate(captured.player_url);
    await waitForApis(captured, 90000);
    await new Promise((r) => setTimeout(r, 1000));

    const ui = await evalInPage(session, `
      const result = {
        title: document.title,
        page_url: location.href,
        visit_panel: {},
        player_status: window.ym_webvisor_player_status,
        loading_status: window.ym_webvisor_loading_status,
      };
      const texts = [...document.querySelectorAll('body *')]
        .map(el => el.childNodes.length === 1 && el.textContent ? el.textContent.trim() : '')
        .filter(Boolean);
      for (const label of ['Дата визита','Длительность','Просмотры','Регион','Последний источник','Страница входа','Страница выхода','Устройство','Браузер']) {
        const idx = texts.indexOf(label);
        if (idx >= 0 && texts[idx + 1]) result.visit_panel[label] = texts[idx + 1];
      }
      const siteLink = document.querySelector('a[href^="http"]:not([href*="yandex"])');
      if (siteLink) result.site_url = siteLink.href;
      if (window.player?.store?.getState) {
        const state = window.player.store.getState();
        result.timeline = {
          duration_ms: state.player?.duration ?? state.duration,
          current_ms: state.player?.currentTime ?? state.currentTime,
          events_count: state.events?.length ?? state.player?.events?.length,
        };
      }
      return result;
    `).catch(() => ({}));
    captured.ui = ui || {};
  } finally {
    off();
  }

  Object.assign(captured, extractVisitInfo(captured.api));

  const eventData = parseEvents(captured.api.fetchHit);
  captured.parsed_events = eventData.parsed_events;
  captured.summary = eventData.summary;

  if (captured.ui.visit_panel?.['Длительность'] && !captured.summary?.duration_sec) {
    const m = captured.ui.visit_panel['Длительность'].match(/(\d+):(\d+)/);
    if (m) {
      captured.summary = captured.summary || {};
      captured.summary.duration_sec = Number(m[1]) * 60 + Number(m[2]);
    }
  }

  if (!captured.api.getVisitInfo && !captured.parsed_events?.length) {
    throw new Error('No API data captured (getVisitInfo/fetchHit missing)');
  }

  return captured;
}

async function runPool(items, workers, workerFn) {
  const results = new Array(items.length);
  let index = 0;

  async function runner(worker) {
    while (true) {
      const i = index++;
      if (i >= items.length) break;
      results[i] = await workerFn(items[i], i, worker);
    }
  }

  await Promise.all(workers.map((w) => runner(w)));
  return results;
}

async function main() {
  await ensureDir(VISITS_DIR);
  await fetchJson(`${CDP_HOST}/json/version`);

  console.log(`Collecting visit list (period=${PERIOD})...`);
  const visits = await getVisitsFromList();

  if (!visits.length) {
    console.error('No visits found in Webvisor list.');
    process.exit(1);
  }

  console.log(`Found ${visits.length} visits. Concurrency=${CONCURRENCY}`);

  const manifest = {
    counter_id: COUNTER_ID,
    period: PERIOD,
    scraped_at: new Date().toISOString(),
    concurrency: CONCURRENCY,
    output_root: OUT_ROOT,
    total_visits: visits.length,
    visits: [],
    stats: { ok: 0, error: 0, by_date: {} },
  };

  const workers = await createWorkerPool(CONCURRENCY);
  console.log(`Created ${workers.length} worker tabs`);

  try {
  await runPool(visits, workers, async (visit, idx, worker) => {
    const filePath = visitOutPath(visit);
    await ensureDir(path.dirname(filePath));
    const relFile = path.relative(OUT_ROOT, filePath).replace(/\\/g, '/');

    console.log(`[${idx + 1}/${visits.length}] ${visit.visit_id} (${visit.date})`);
    try {
      const data = await capturePlayerData(visit, worker);
      await fs.writeFile(filePath, JSON.stringify(data, null, 2), 'utf8');
      manifest.visits.push({
        visit_id: visit.visit_id,
        date: visit.date,
        file: relFile,
        status: 'ok',
        summary: data.summary || null,
        visit_panel: data.ui?.visit_panel || null,
      });
      manifest.stats.ok += 1;
      manifest.stats.by_date[visit.date] = (manifest.stats.by_date[visit.date] || 0) + 1;
      console.log(`  saved -> ${filePath}`);
      return data;
    } catch (err) {
      const payload = {
        visit_id: visit.visit_id,
        date: visit.date,
        error: String(err?.message || err),
        scraped_at: new Date().toISOString(),
      };
      await fs.writeFile(filePath, JSON.stringify(payload, null, 2), 'utf8');
      manifest.visits.push({
        visit_id: visit.visit_id,
        date: visit.date,
        file: relFile,
        status: 'error',
        error: payload.error,
      });
      manifest.stats.error += 1;
      console.error(`  error: ${payload.error}`);
      return payload;
    }
  });
  } finally {
    await closeWorkerPool(workers);
  }

  await fs.writeFile(path.join(OUT_ROOT, '_manifest.json'), JSON.stringify(manifest, null, 2), 'utf8');
  console.log(`Done: ${manifest.stats.ok}/${visits.length} ok, ${manifest.stats.error} errors -> ${OUT_ROOT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
