// UI-02: drive the RIGHTWARE JARVIS HUD (original OpenJarvis frontend + overlay) in a real Chromium.
// UI02_MODE=real (default): real backend (Ollama/Qwen, P1/goose missions) → evidence.
// UI02_MODE=fake: CI against labs/ui02/serve_fake.py (FAKE text model + FAKE mission, labelled [FAKE-CI]).
// Usage: NODE_PATH=$(npm root -g) node labs/ui02/hud_e2e.mjs <outdir> [port] [scenarios,comma]
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const [, , outDir = '.', port = '8000', only = ''] = process.argv;
const MODE = process.env.UI02_MODE || 'real';
const BASE = `http://127.0.0.1:${port}`;
const SESSION = (process.env.UI02_SESSION_FILE || '.runtime/gui/session-url');
const MISSION = process.env.UI02_MISSION || (MODE === 'fake' ? 'missao-ci-fake' : 'comparar-versoes-ensaio');
fs.mkdirSync(outDir, { recursive: true });
const results = [];
const rec = (id, action, expected, obtained, evidence, pass) => {
  results.push({ id, action, expected, obtained, evidence, pass, mode: MODE });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${action}`);
};
const shot = async (p, n) => { const f = `${outDir}/${n}.png`; await p.screenshot({ path: f }); return f; };

function chromeCpuSeconds() {          // utime+stime of every Chromium process (Linux /proc), in seconds
  let ticks = 0;
  for (const pid of fs.readdirSync('/proc').filter((d) => /^\d+$/.test(d))) {
    try {
      const comm = fs.readFileSync(`/proc/${pid}/comm`, 'utf8').trim();
      if (!/chrom|headless/i.test(comm)) continue;
      const f = fs.readFileSync(`/proc/${pid}/stat`, 'utf8').split(') ')[1].split(' ');
      ticks += Number(f[11]) + Number(f[12]);
    } catch { /* process ended */ }
  }
  return ticks / 100;
}

async function login(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const sent = [];
  page.on('request', (r) => { if (r.url().endsWith('/v1/chat/completions')) sent.push(r.headers()); });
  await page.goto(fs.readFileSync(SESSION, 'utf8').trim(), { waitUntil: 'load' });
  await page.waitForTimeout(2500);
  return { ctx, page, sent };
}

async function send(page, text, timeoutS = 400) {
  const before = new Set((await page.innerText('main')).match(/rw-[0-9a-f]{16}/g) || []);
  const box = page.locator('textarea').first();
  await box.fill(text);
  await box.press('Enter');
  const t0 = Date.now();
  let rid = null;
  while ((Date.now() - t0) / 1000 < timeoutS) {
    rid = ((await page.innerText('main')).match(/rw-[0-9a-f]{16}/g) || []).find((x) => !before.has(x));
    if (rid) break;
    await page.waitForTimeout(400);
  }
  const txt = await page.innerText('main');
  const end = rid ? txt.lastIndexOf(rid) : txt.length;
  const start = txt.lastIndexOf(text.slice(0, 50), end);
  return { rid, seconds: (Date.now() - t0) / 1000, reply: txt.slice(start + Math.min(50, text.length), end + (rid ? rid.length : 0)).trim().slice(0, 1500) };
}

async function api(page, path, body) {
  return page.evaluate(async ([p, b]) => {
    const r = await fetch(p, b === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
    return { status: r.status, body: await r.json().catch(() => null) };
  }, [path, body]);
}

async function waitMissionEnd(page, maxS) {
  const t0 = Date.now();
  let st = null;
  while ((Date.now() - t0) / 1000 < maxS) {
    st = (await api(page, '/v1/rightware/state')).body;
    if (st && !st.task.running && st.last) return st;
    await page.waitForTimeout(3000);
  }
  return st;
}

const S = {
  async auth(browser) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const r = await p.goto(BASE + '/');
    const blocked = { status: r.status(), text: (await p.innerText('body')).slice(0, 120) };
    const apiNoSession = await p.evaluate(async () => (await fetch('/v1/rightware/state')).status);
    await ctx.close();
    const { ctx: c2, page } = await login(browser);
    const nav = await page.innerText('nav');
    rec('U1', 'Sessão local obrigatória; ligação do anfitrião abre a HUD', '401 sem sessão; HUD após login',
      { blocked, apiNoSession, nav }, await shot(page, 'u1-login-ok'),
      blocked.status === 401 && /Sessão local necessária/.test(blocked.text) && apiNoSession === 401 && /Conversa/.test(nav));
    await c2.close();
  },
  async i18n(browser) {
    const { ctx, page } = await login(browser);
    const pt = await page.innerText('nav');
    await page.locator('.rw-lang-toggle').click();
    await page.waitForTimeout(500);
    const en = await page.innerText('nav');
    const shotEn = await shot(page, 'u2-english');
    await page.locator('.rw-lang-toggle').click();
    rec('U2', 'PT-MZ por omissão; inglês disponível', 'Conversa/Missões → Chat/Missions',
      { pt, en }, shotEn, /Missões/.test(pt) && /Missions/.test(en));
    await ctx.close();
  },
  async chat(browser) {
    const { ctx, page, sent } = await login(browser);
    const r = await send(page, MODE === 'fake' ? 'Olá HUD (teste CI)' : 'Olá JARVIS. Numa frase curta em português: qual é a capital de Moçambique?');
    const conv = sent.map((h) => h['x-rightware-conversation']).filter(Boolean);
    rec('U3', 'Conversa pela HUD com id de conversa explícito', 'Resposta com id rw-… e cabeçalho X-Rightware-Conversation',
      { ...r, conversation_header: conv[0] || null }, await shot(page, 'u3-chat'),
      !!r.rid && conv.length > 0 && (MODE === 'fake' ? /histórico=0/.test(r.reply) : /Maputo/i.test(r.reply) && /NÃO verificada/.test(r.reply)));
    await ctx.close();
  },
  async stop(browser) {
    const { ctx, page } = await login(browser);
    const box = page.locator('textarea').first();
    await box.fill(MODE === 'fake' ? 'LONGO pedido' : 'Escreve um texto longo e detalhado, com pelo menos dez parágrafos, sobre a história de Maputo.');
    await box.press('Enter');
    await page.waitForTimeout(4000);
    await page.locator('button[title="Parar a geração"]').click();
    const t0 = Date.now();
    await page.waitForTimeout(1500);
    const after = await send(page, MODE === 'fake' ? 'curto' : 'Quanto é 2+2? Responde só o número.', 120);
    rec('U4', 'Parar a geração liberta o modelo (cancelamento efectivo)', 'Pedido seguinte responde sem esperar pelo anterior',
      { next_seconds: after.seconds, next: after.reply.slice(0, 200), since_stop_s: (Date.now() - t0) / 1000 },
      await shot(page, 'u4-stop'), !!after.rid && after.seconds < (MODE === 'fake' ? 5 : 20) && !/MODEL_BUSY|Pedido anterior ainda/.test(after.reply));
    await ctx.close();
  },
  async hud(browser) {
    const { ctx, page } = await login(browser);
    await page.goto(BASE + '/dashboard', { waitUntil: 'load' });
    await page.waitForTimeout(2500);
    const mode = await page.getAttribute('.rw-core', 'data-mode');
    const caps = await page.locator('[data-cap]').evaluateAll((els) => els.map((e) => [e.getAttribute('data-cap'), e.querySelector('[data-status]')?.getAttribute('data-status')]));
    const finance = await page.locator('[data-card="inteligencia-financeira"]').innerText();
    rec('U5', 'HUD com estado real (núcleo, missões, capacidades, voz, finanças)', 'núcleo ready; capacidades com estado; finanças sem dados',
      { mode, caps, finance }, await shot(page, 'u5-hud'),
      mode === 'ready' && caps.some(([id, st]) => id === 'voz' && st === 'NAO_INTEGRADA') && !/\$|USD|\d+[.,]\d+/.test(finance));
    await ctx.close();
  },
  async cpu(browser) {
    const { ctx, page } = await login(browser);
    const out = {};
    for (const [path, name] of [['/', 'chat'], ['/dashboard', 'hud']]) {
      await page.goto(BASE + path, { waitUntil: 'load' });
      await page.waitForTimeout(4000);
      const a = chromeCpuSeconds(); const t0 = Date.now();
      await page.waitForTimeout(30000);
      out[name] = +((chromeCpuSeconds() - a) / ((Date.now() - t0) / 1000) * 100).toFixed(1);
    }
    rec('U6', 'Orçamento de CPU da interface (idle 30 s, Chromium sem GPU)', '≤ 10% de um núcleo', out,
      await shot(page, 'u6-cpu'), out.chat <= 10 && out.hud <= 10);
    await ctx.close();
  },
  async mission(browser) { await runMission(browser, 'U7', MISSION); },
  async freeresearch(browser) { await freeResearch(browser); },
  async research(browser) {
    // WEB-01 W2: the real research executor over the local FIXTURE corpus (no network), via the same HUD flow.
    const { page, ctx, st, timeline } = await runMission(browser, 'U8', 'pesquisa-publica', true);
    const sources = await page.locator('.rw-sources li').count();
    const supports = await page.locator('.rw-sources li[data-supports]').evaluateAll((els) => els.map((e) => e.getAttribute('data-supports')).filter(Boolean));
    rec('U8', `Pesquisa pública de leitura pela HUD (modo ${process.env.UI02_RESEARCH_MODE || 'FIXTURE'})`,
      'RESULTADO_VERIFICADO; fontes com URL, data, sha256 e bytes; cada objectivo suportado por uma fonte designada',
      { last: st && st.last, sources, supports, timeline: timeline.slice(0, 900) }, await shot(page, 'u8-research-result'),
      !!st?.last?.verified && st.last.operational_state === `RESEARCH_VERIFIED_${process.env.UI02_RESEARCH_MODE || 'FIXTURE'}` && sources >= 1
        && ['CAPITAL', 'MOEDA', 'BANCO_CENTRAL'].every((o) => supports.join(' ').includes(o)));
    await ctx.close();
  },
};

async function freeResearch(browser) {
  // W3.1: free question in the chat → plan + single-use code (no network yet) → operator types /autorizar CODE → result.
  const { ctx, page } = await login(browser);
  const q = process.env.UI02_FREE_QUESTION || 'Em que ano Moçambique se tornou independente?';
  const plan = await send(page, q, 400);
  const code = (plan.reply.match(/\/autorizar ([0-9A-F]{6})/) || [])[1];
  const proposed = /Pesquisa proposta — nada foi executado ainda/.test(await page.innerText('main'));
  const planShot = await shot(page, 'u9-plan');
  let run = null, st = null;
  if (code) {
    run = await send(page, `/autorizar ${code}`, 120);
    st = await waitMissionEnd(page, Number(process.env.UI02_MISSION_MAX_S || 900));
  }
  await page.goto(BASE + '/agents', { waitUntil: 'load' });
  await page.waitForTimeout(3000);
  const timeline = await page.locator('.rw-timeline').first().innerText();
  const last = st && st.last;
  rec('U9', 'Pergunta livre na conversa → plano → código → pesquisa → resposta com citações (W3.1)',
    'plano proposto sem rede; código obrigatório; estado final honesto (nunca VERIFICADO para pergunta livre)',
    { question: q, plan: plan.reply.slice(0, 1200), code_present: !!code, last, timeline: timeline.slice(0, 1500) },
    [planShot, await shot(page, 'u9-result')],
    !!code && proposed && !!last && last.verified === false
      && ['RESPOSTA_FUNDAMENTADA', 'EXECUCAO_PARCIAL', 'RESULTADO_DESCONHECIDO'].includes(last.state));
  await ctx.close();
}

async function runMission(browser, id, MISSION, keep = false) {
    const { ctx, page } = await login(browser);
    await page.goto(BASE + '/agents', { waitUntil: 'load' });
    await page.waitForTimeout(2000);
    const noCode = await api(page, '/v1/rightware/tasks/authorize', { approve: true });
    const item = page.locator('.rw-missions li', { hasText: MISSION });
    await item.getByRole('button').click();
    await page.waitForTimeout(800);
    const authBtn = page.getByRole('button', { name: /Autorizar com o código/ });
    const disabledBefore = await authBtn.isDisabled();
    await page.locator('.rw-input').fill('000000');
    await authBtn.click();
    await page.waitForTimeout(1500);
    const wrong = await page.innerText('.rw-panel');
    await item.getByRole('button').click();
    await page.waitForTimeout(800);
    const code = (await page.innerText('.rw-code')).trim();
    await page.locator('.rw-input').fill(code);
    await page.getByRole('button', { name: /Autorizar com o código/ }).click();
    await page.waitForTimeout(2500);
    const runningShot = await shot(page, `u7-mission-running-${MISSION}`);
    const st = await waitMissionEnd(page, Number(process.env.UI02_MISSION_MAX_S || 1200));
    await page.waitForTimeout(2500);
    const timeline = await page.locator('.rw-timeline').first().innerText();
    if (keep) return { page, ctx, st, timeline };
    rec(id, `Missão supervisionada pela HUD (${MISSION}) só com o código escrito`,
      'sem código → 400; botão desactivado sem código; código errado recusado; código certo executa; resultado do verificador',
      { noCode, disabledBefore, wrong: wrong.match(/inválido[^\n]*/i)?.[0] || null, last: st && st.last, timeline: timeline.slice(0, 600) },
      [runningShot, await shot(page, `u7-mission-result-${MISSION}`)],
      noCode.status === 400 && disabledBefore && !!st?.last && (process.env.UI02_EXPECT_VERIFIED === '0' || st.last.verified));
    await ctx.close();
}

const browser = await chromium.launch();
try {
  for (const name of (only ? only.split(',') : Object.keys(S))) {
    try { await S[name](browser); } catch (e) { rec(name, 'erro do harness', '-', String(e).slice(0, 400), null, false); }
  }
} finally { await browser.close(); }
fs.writeFileSync(`${outDir}/results-${MODE}.json`, JSON.stringify(results, null, 2));
process.exitCode = results.every((r) => r.pass) ? 0 : 1;
