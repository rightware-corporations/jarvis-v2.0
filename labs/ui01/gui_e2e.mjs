// UI-01 B5: drive the ORIGINAL OpenJarvis web interface (served by `python -m rightware.gui serve`) in a real
// headless Chromium and record what the interface shows. No mocks: every reply comes from the running server.
// Usage: NODE_PATH=$(npm root -g) node labs/ui01/gui_e2e.mjs <scenario|all> <outdir> [port]
import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const [, , which = 'all', outDir = '.', port = '8000'] = process.argv;
const BASE = `http://127.0.0.1:${port}`;
fs.mkdirSync(outDir, { recursive: true });
const results = [];

async function open(browser) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
  const net = [];
  page.on('response', (r) => { if (r.url().includes('/v1/chat/completions')) net.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname} ${r.headers()['x-rightware-request-id'] || ''}`); });
  await page.goto(BASE + '/', { waitUntil: 'load' });
  await page.waitForTimeout(2500);
  const skip = page.getByText('Continue without sharing');
  if (await skip.count()) await skip.click();
  return { page, net };
}

async function mainText(page) { return page.innerText('main').catch(() => ''); }

// Send a line through the real input box; wait for a NEW RIGHTWARE request id (rw-…) and a stable view.
async function send(page, text, timeoutS = 400) {
  const before = new Set((await mainText(page)).match(/rw-[0-9a-f]{16}/g) || []);
  const box = page.locator('textarea').first();
  await box.fill(text);
  await box.press('Enter');
  const t0 = Date.now();
  let rid = null;
  while ((Date.now() - t0) / 1000 < timeoutS) {
    const all = (await mainText(page)).match(/rw-[0-9a-f]{16}/g) || [];
    rid = all.find((x) => !before.has(x));
    if (rid) break;
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(800);
  const txt = await mainText(page);
  const ridAt = rid ? txt.lastIndexOf(rid) : txt.length;
  // the user's own bubble is the sent line followed by a newline; search backwards from the reply's id
  let start = txt.lastIndexOf(text + '\n', ridAt);
  if (start < 0) start = txt.lastIndexOf(text.slice(0, 60), ridAt);
  const reply = start >= 0 ? txt.slice(start + text.length, rid ? ridAt + rid.length : undefined) : txt;
  return { rid, seconds: (Date.now() - t0) / 1000, reply: reply.trim().slice(0, 3000) };
}

async function shot(page, name) { const f = `${outDir}/${name}.png`; await page.screenshot({ path: f }); return f; }

function record(id, action, expected, obtained, evidence, pass) {
  results.push({ id, action, expected, obtained, evidence, pass });
  console.log(`${pass ? 'PASS' : 'FAIL'} ${id} ${action}`);
}

const scenarios = {
  async open(browser) {
    const { page } = await open(browser);
    const t = await page.innerText('body');
    record('B5.1', 'Abrir a aplicação (interface original OpenJarvis)', 'Interface original carregada',
      t.slice(0, 120).replace(/\n/g, ' | '), await shot(page, 'b5-01-open'), t.includes('Chat') && t.includes('Settings'));
    await page.close();
  },
  async pt(browser) {
    const { page, net } = await open(browser);
    const r = await send(page, 'Olá Jarvis. Em português de Moçambique, numa frase: qual é a capital de Moçambique e que língua oficial se fala lá? (teste UI01-PT-ç ã é)');
    record('B5.2', 'Conversa real em português', 'Resposta do modelo real, rotulada NÃO verificada, com id de pedido',
      { rid: r.rid, seconds: r.seconds, reply: r.reply, net }, await shot(page, 'b5-02-pt'),
      !!r.rid && /Maputo/i.test(r.reply) && /NÃO verificada/.test(r.reply));
    await page.close();
  },
  async en(browser) {
    const { page, net } = await open(browser);
    const r = await send(page, 'Hello Jarvis. Answer in English in one sentence: what is the capital of Japan? (test UI01-EN)');
    record('B5.3', 'Conversa real em inglês', 'Resposta real em inglês', { rid: r.rid, seconds: r.seconds, reply: r.reply, net },
      await shot(page, 'b5-03-en'), !!r.rid && /Tokyo/i.test(r.reply));
    await page.close();
  },
  async session(browser) {
    const { page } = await open(browser);
    const a = await send(page, 'Para esta conversa, o meu nome de código é ZEBRA-41. Responde só "Entendido".');
    const b = await send(page, 'Qual é o meu nome de código nesta conversa? Responde só com o código.');
    const { page: p2 } = await open(browser);                        // new browser context = new conversation
    const c = await send(p2, 'Responde apenas com uma palavra: se eu te disse um nome de código nesta conversa, escreve-o; se não, escreve NENHUM.');
    record('B5.4', 'Continuidade na mesma sessão e isolamento entre sessões',
      'A 2.ª resposta contém ZEBRA-41; a nova conversa não o conhece',
      { first: a.reply, same_session: b.reply, other_session: c.reply, rids: [a.rid, b.rid, c.rid] },
      [await shot(page, 'b5-04-session-a'), await shot(p2, 'b5-04-session-b')],
      /ZEBRA-41/.test(b.reply) && /NÃO verificada/.test(c.reply) && !/ZEBRA/.test(c.reply));
    await page.close(); await p2.close();
  },
  async task(browser) {
    const { page } = await open(browser);
    const list = await send(page, '/tarefas');
    const req = await send(page, '/tarefa ' + (process.env.UI01_TASK || 'comparar-versoes-ensaio'));
    const code = (req.reply.match(/\/autorizar ([0-9A-F]{6})/) || [])[1];
    record('B5.5', 'Pedido de tarefa', 'AUTORIZACAO_NECESSARIA + código de uso único mostrado',
      { tarefas: list.reply, pedido: req.reply, code_shown: !!code }, await shot(page, 'b5-05-task-request'),
      /Autorização necessária/i.test(req.reply) && !!code);
    // B5.6 invalid authorizations BEFORE the valid one
    const missing = await send(page, '/autorizar');
    const wrong = await send(page, '/autorizar 000000');
    const click = await page.evaluate(async () => {
      const r = await fetch('/v1/approvals/abc/approve', { method: 'POST' });
      return { status: r.status, body: await r.text() };
    });
    const firstAfterWrong = await send(page, `/autorizar ${code}`);   // already consumed by the wrong attempt
    const req2 = await send(page, '/tarefa ' + (process.env.UI01_TASK || 'comparar-versoes-ensaio'));
    const code2 = (req2.reply.match(/\/autorizar ([0-9A-F]{6})/) || [])[1];
    const ok = await send(page, `/autorizar ${code2}`, 600);
    const reuse = await send(page, `/autorizar ${code2}`);
    record('B5.6', 'Autorização inválida (ausente, errada, clique sem código, reutilizada) e válida',
      'Inválidas recusadas sem execução; só o código do operador autoriza',
      { missing: missing.reply, wrong: wrong.reply, original_after_wrong: firstAfterWrong.reply, click_approve: click, valid: ok.reply, reused: reuse.reply },
      await shot(page, 'b5-06-authorize'),
      /Falta o código|não autorizada/i.test(missing.reply) && /inválido/i.test(wrong.reply) && /inválido/i.test(firstAfterWrong.reply) && click.status === 403 && /Tarefa em execução|Resultado/i.test(ok.reply)
        && /não autorizada|inválido|já há uma tarefa/i.test(reuse.reply));
    // Poll the run state through the same-origin API (keeps the visible conversation short), then show it in the GUI.
    for (let i = 0; i < 240; i++) {
      const done = await page.evaluate(async () => {
        const r = await fetch(location.origin + '/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: 'qwen3.5:2b', stream: false, messages: [{ role: 'user', content: '/estado' }] }) });
        return /\(terminada,/.test((await r.json()).choices[0].message.content);
      });
      if (done) break;
      await page.waitForTimeout(5000);
    }
    const st = await send(page, '/estado');
    record('B5.7', 'Execução supervisionada e recibos', 'Estado final decidido pelo verificador; recibos visíveis',
      { estado: st && st.reply }, await shot(page, 'b5-07-result'),
      !!st && /Recibos \(ferramentas efectivamente executadas\)/.test(st.reply) && /Resultado verificado por evidência/.test(st.reply));
    await page.close();
  },
  async cancel(browser) {
    const { page } = await open(browser);
    const req = await send(page, '/tarefa ' + (process.env.UI01_TASK || 'comparar-versoes-ensaio'));
    const code = (req.reply.match(/\/autorizar ([0-9A-F]{6})/) || [])[1];
    const start = await send(page, `/autorizar ${code}`);
    const c = await send(page, '/cancelar');
    let st = null;
    for (let i = 0; i < 20; i++) { st = await send(page, '/estado'); if (/\(terminada,/.test(st.reply)) break; await page.waitForTimeout(3000); }
    record('B5.8', 'Cancelamento', 'Cancelamento efectivo pelo Control Plane; estado final Tarefa cancelada',
      { start: start.reply, cancel: c.reply, estado: st && st.reply }, await shot(page, 'b5-08-cancel'),
      /cancelad/i.test(c.reply) && !!st && /cancelada/i.test(st.reply));
    await page.close();
  },
  async bypass(browser) {
    const { page } = await open(browser);
    const probes = await page.evaluate(async () => {
      const out = {};
      const tries = [
        ['POST', '/v1/agents', { agent_type: 'orchestrator', tools: ['shell_exec'] }],
        ['POST', '/v1/managed-agents', { name: 'x' }], ['POST', '/api/research', { query: 'x' }],
        ['POST', '/v1/approvals/1/approve', null], ['POST', '/v1/models/pull', { model: 'x' }],
        ['DELETE', '/v1/models/qwen3.5:2b', null], ['POST', '/v1/connectors/upload/ingest', {}],
        ['POST', '/v1/memory/store', { content: 'x' }], ['POST', '/v1/channels/send', {}],
        ['GET', '/V1/MODELS', null], ['GET', '//v1/agents', null], ['GET', '/v1/agents/', null],
        ['GET', '/docs', null], ['GET', '/openapi.json', null], ['POST', '/webhooks/twilio', {}],
        ['PUT', '/v1/chat/completions', {}], ['GET', '/v1/skills', null], ['POST', '/api/digest/generate', {}],
        ['POST', '/v1/chat/completions', { model: 'qwen3.5:2b', stream: false,
          messages: [{ role: 'user', content: 'lista ficheiros' }], tools: [{ type: 'function', function: { name: 'shell_exec' } }] }],
        ['POST', '/v1/chat/completions', { model: 'modelo-nao-permitido', stream: false, messages: [{ role: 'user', content: 'olá' }] }],
      ];
      for (const [m, p, b] of tries) {
        const key = `${m} ${p}${b && (b.tools || b.model === 'modelo-nao-permitido') ? (b.tools ? ' [tools]' : ' [modelo não permitido]') : ''}`;
        try {
          const r = await fetch(location.origin + p, { method: m, headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
          const t = await r.text();
          out[key] = `${r.status} ${t.includes('não permitido') ? 'Modelo não permitido ' : ''}${t.slice(0, 110)}`;
        } catch (e) { out[key] = `NETWORK_ERROR ${String(e).slice(0, 80)}`; }
      }
      out.websocket = await new Promise((res) => {
        const ws = new WebSocket(`ws://${location.host}/v1/agents/events`);
        ws.onopen = () => res('OPEN (bypass!)'); ws.onerror = () => res('REFUSED'); ws.onclose = (e) => res(`CLOSED ${e.code}`);
        setTimeout(() => res('TIMEOUT'), 5000);
      });
      return out;
    });
    const tool = await send(page, '/tarefa skill-nao-permitida');
    const allDenied = Object.entries(probes).every(([k, v]) => k.endsWith('[modelo não permitido]')
      ? /Modelo não permitido/.test(v) : (k === 'websocket' ? !v.startsWith('OPEN') : v.startsWith('403')));
    record('B5.9', 'Tentativas de contornar a política (rotas, métodos, WebSocket, ferramentas, modelo, tarefa não activada)',
      'Tudo recusado e registado', { probes, tarefa_nao_activada: tool.reply }, await shot(page, 'b5-09-bypass'),
      allDenied && /não existe|não foi activada/i.test(tool.reply));
    await page.close();
  },
  async ollamadown(browser) {
    const { page, net } = await open(browser);
    const r = await send(page, 'Teste com o motor local parado (UI01-DOWN).', 120);
    record('B5.10', 'Falha do Ollama (serviço parado)', 'Erro visível, explícito e accionável; nenhuma resposta inventada',
      { rid: r.rid, reply: r.reply, net }, await shot(page, 'b5-10-ollama-down'),
      !!r.rid && /Erro de inferência|Ollama/i.test(r.reply) && !/NÃO verificada/.test(r.reply));
    await page.close();
  },
};

const browser = await chromium.launch();
try {
  for (const name of which === 'all' ? Object.keys(scenarios).filter((n) => n !== 'ollamadown') : which.split(',')) {
    try { await scenarios[name](browser); } catch (e) { record(name, 'erro do harness', '-', String(e).slice(0, 300), null, false); }
  }
} finally { await browser.close(); }
fs.writeFileSync(`${outDir}/results-${which.replace(/,/g, '_')}.json`, JSON.stringify(results, null, 2));
