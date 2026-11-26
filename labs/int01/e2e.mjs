// JRV-INT01 integrated E2E (LAB) — REAL Chromium against the REAL JARVIS (B6 private mode behind a local TLS front that
// forwards bytes unchanged, like the Dev Tunnel relay with Host/Origin "unchanged"), REAL local Qwen, REAL STT/TTS.
// The microphone is Chromium's fake capture device fed with a WAV of Portuguese speech (synthetic, Kokoro).
// Usage: node labs/int01/e2e.mjs <origin> <wav> <pdf> <out.json> <issa-link-cmd>
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const [ORIGIN, WAV, PDF, OUT, ISSUE] = process.argv.slice(2);
const host = new URL(ORIGIN).hostname;
const log = { steps: [], network: [], origins: [], started: new Date().toISOString() };
const redact = (x) => String(x ?? '').replace(/([?&]t=)[A-Za-z0-9_-]+/g, '$1<redigido>');   // never log link tokens
const step = (n, ok, detail) => { const d = redact(detail); log.steps.push({ n, ok, detail: d }); console.log(`${ok ? 'PASS' : 'FAIL'} ${n} ${d}`); };
const linkOf = (f) => readFileSync(f, 'utf8').trim();

const noProxy = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(https?|all|no)_proxy$/i.test(k)));
const browser = await chromium.launch({ env: noProxy, args: [
  `--host-resolver-rules=MAP ${host} 127.0.0.1`, '--ignore-certificate-errors', '--no-proxy-server',
  '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${WAV}`,
  '--autoplay-policy=no-user-gesture-required'] });

async function newPage() {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['microphone'], viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.accept());
  page.on('request', (r) => { if (r.method() === 'POST') log.origins.push({ path: new URL(r.url()).pathname, origin: r.headers()['origin'] ?? null }); });
  page.on('response', (r) => { const u = new URL(r.url()); if (u.pathname.startsWith('/v1/') || u.pathname === '/rw-login')
    log.network.push({ m: r.request().method(), p: u.pathname, s: r.status() }); });
  return { ctx, page };
}
const bodyText = (page) => page.evaluate(() => document.body.innerText);

async function ask(page, text, timeout = 300000) {
  const before = await bodyText(page);
  const ta = page.locator('textarea');
  await ta.fill(text);
  await ta.press('Enter');
  await page.waitForTimeout(1500);
  await page.waitForFunction(() => !document.querySelector('button[title="Parar a geração"]'), null, { timeout });
  await page.waitForTimeout(1000);
  const after = await bodyText(page);
  return after.slice(Math.max(0, after.indexOf(text) >= 0 ? after.lastIndexOf(text) : before.length));
}

async function login(page, link, label) {
  await page.goto(link);
  await page.reload();                                                     // repeated GET must not burn the link
  const confirm = await page.locator('button', { hasText: 'Entrar no JARVIS' }).count();
  step(`${label}: GET confirmação (2×) não consome`, confirm === 1);
  await page.locator('button', { hasText: 'Entrar no JARVIS' }).click();
  await page.waitForURL(`${ORIGIN}/`, { timeout: 30000 });
  const cookies = await page.context().cookies();
  const s = cookies.find((c) => c.name === 'rw_session');
  step(`${label}: POST consome + cookie Secure/HttpOnly/Strict + redirecção /`, !!s && s.secure && s.httpOnly && s.sameSite === 'Strict',
       s ? `secure=${s.secure}` : 'sem cookie');
  const loginPost = log.origins.find((o) => o.path === '/rw-login');
  step(`${label}: Origin real no POST do formulário (não null)`, loginPost?.origin === ORIGIN, `Origin=${loginPost?.origin}`);
  const replay = await page.context().request.get(link);
  step(`${label}: link usado já não serve`, replay.status() === 403, `status=${replay.status()}`);
}

try {
  // ---------------- operator ----------------
  const { page } = await newPage();
  await login(page, linkOf('.runtime/gui/session-url'), 'operador');
  const st = await (await page.context().request.get(`${ORIGIN}/v1/rightware/state`)).json();
  step('build: bundle corresponde ao código (overlay) e revisão registada', st.build?.match === true,
       JSON.stringify(st.build));
  await page.locator('[data-rw="session-activate"]').click();
  const greet = await page.waitForResponse((r) => r.url().endsWith('/v1/speech/synthesize'), { timeout: 60000 });
  step('activar JARVIS → saudação sintetizada (pf_dora)', greet.status() === 200 &&
       (greet.headers()['content-type'] ?? '').includes('audio'), `status=${greet.status()}`);

  const a1 = await ask(page, 'Quanto é 12 vezes 7?');
  step('conversa por texto (calculadora)', /84/.test(a1), a1.slice(0, 160).replace(/\n/g, ' '));

  // dictation: push-to-talk with the fake microphone (Kokoro speech "Quanto é doze vezes sete?")
  await page.locator('[data-rw="voice-idle"]').click();
  await page.waitForTimeout(7000);
  const tr = page.waitForResponse((r) => r.url().endsWith('/v1/speech/transcribe'), { timeout: 60000 });
  await page.locator('[data-rw="voice-recording"]').click();
  const trr = await tr;
  await page.waitForTimeout(1500);
  const dictated = await page.locator('textarea').inputValue();
  const stuck = await page.locator('[data-rw="voice-transcribing"]').count();
  step('transcrição: multipart aceite e texto ditado no campo', trr.status() === 200 && /doze|12|sete|7/i.test(dictated) && stuck === 0,
       `status=${trr.status()} texto=«${dictated}»`);
  await page.locator('textarea').fill('');

  await page.locator('button[aria-label="Read message aloud"]').last().click();
  const sp = await page.waitForResponse((r) => r.url().endsWith('/v1/speech/synthesize'), { timeout: 60000 });
  step('reproduzir resposta (ouvir)', sp.status() === 200, `status=${sp.status()}`);

  const a2 = await ask(page, 'JARVIS, prefiro que os meus relatórios sejam apresentados em meticais. Lembra-te disto.');
  step('ensinar preferência (escrita real confirmada pelo anfitrião)', /memória\): guardada/.test(a2), a2.slice(-220).replace(/\n/g, ' '));

  await page.locator('button[title="Nova conversa"]').first().click();
  await page.waitForTimeout(1000);
  const a3 = await ask(page, 'Em que moeda devo apresentar o relatório mensal de vendas?');
  step('nova conversa recupera a preferência', /metica/i.test(a3), a3.slice(0, 200).replace(/\n/g, ' '));

  await page.locator('[data-rw="doc-input"]').setInputFiles(PDF);
  await page.waitForFunction(() => /carregado|já estava/.test(document.querySelector('[data-rw="doc-status"]')?.textContent ?? ''), null, { timeout: 60000 });
  step('carregar PDF pela interface', true, await page.locator('[data-rw="doc-status"]').textContent());

  const a4 = await ask(page, 'No relatório anual 2025, qual foi o resultado líquido e em que página aparece?');
  step('consultar informação e página', /96/.test(a4) && /página 2/.test(a4), a4.slice(0, 260).replace(/\n/g, ' '));

  // continuous conversation (opt-in): VAD → recording → transcription → same chat → reply → speech
  await page.locator('[data-rw="conv-toggle-off"]').click();
  const phases = new Set();
  for (let i = 0; i < 180 && !(phases.has('speaking')); i++) {
    phases.add(await page.evaluate(() => globalThis.__rwConv?.getState().phase)); await page.waitForTimeout(1000);
  }
  await page.locator('[data-rw="conv-off"]').click();
  step('conversa contínua: a ouvir → a gravar → a transcrever → a pensar → a falar',
       ['listening', 'recording', 'transcribing', 'thinking', 'speaking'].every((p) => phases.has(p)), [...phases].join(','));

  await page.locator('[data-rw="library-open"]').click();
  await page.waitForSelector('[data-rw="docs-list"]', { timeout: 10000 });
  await page.locator('[data-rw="doc-delete"]').first().click();
  await page.waitForSelector('[data-rw="docs-empty"]', { timeout: 10000 });
  await page.locator('[data-rw="mem-delete"]').first().click();
  await page.waitForSelector('[data-rw="mem-empty"]', { timeout: 10000 });
  step('eliminar documento e memória pelo painel', true);
  await page.locator('[data-rw="library-close"]').click();
  const a5 = await ask(page, 'No relatório anual 2025, qual foi o resultado líquido?');
  step('documento eliminado deixa de ser recuperado', !/96 milhões/.test(a5), a5.slice(0, 200).replace(/\n/g, ' '));

  // ---------------- isolation: Issa's own link, own session ----------------
  execSync(ISSUE, { stdio: 'inherit' });
  const { page: p2 } = await newPage();
  await login(p2, linkOf('.runtime/gui/session-url-issa'), 'issa');
  await p2.locator('[data-rw="library-open"]').click();
  await p2.waitForSelector('[data-rw="docs-empty"]', { timeout: 10000 });
  await p2.waitForSelector('[data-rw="mem-empty"], [data-rw="mem-off"]', { timeout: 10000 });
  step('isolamento: a sessão do Issa não vê documentos nem memórias do operador', true);
} catch (e) {
  step('excepção', false, String(e).slice(0, 400));
} finally {
  log.network = log.network.map((n) => ({ ...n, p: redact(n.p) }));
  log.finished = new Date().toISOString();
  log.pass = log.steps.filter((s) => s.ok).length; log.total = log.steps.length;
  writeFileSync(OUT, JSON.stringify(log, null, 1));
  await browser.close();
}
