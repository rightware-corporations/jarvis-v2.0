import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { coreMode, isBusy, useHud } from '../lib/hud-store';
import { isOperatorCode, type HudState, type Outcome } from '../lib/rightware-api';
import { installGlobalTranslator, setLang, t } from '../i18n';
import { ExecutionTimeline, verdictClass } from './ExecutionTimeline';
import { MissionsPanel } from './MissionsPanel';
import { JarvisCore } from './JarvisCore';
import { FinanceIntelPanel, VoicePanel } from './StatusCards';
import { CapabilityBadge } from './CapabilityBadge';

const base: HudState = {
  engine: { healthy: true, models: ['qwen3.5:2b'], default_model: 'qwen3.5:2b' },
  model_busy: 0,
  capabilities: [
    { id: 'conversa', label: 'Conversa', status: 'INTEGRADA', reason: '' },
    { id: 'pesquisa-fixture-goose', label: 'Missão goose', status: 'PARCIAL', reason: 'experimental', mission: true },
    { id: 'voz', label: 'Voz', status: 'NAO_INTEGRADA', reason: 'STT/TTS não instalados.' },
    { id: 'inteligencia-financeira', label: 'Finanças', status: 'NAO_INTEGRADA', reason: 'Exige pesquisa web autorizada.' },
  ],
  pending: null,
  task: { running: false, capability: null, elapsed: null },
  last: null,
};
const verified: Outcome = {
  state: 'RESULTADO_VERIFICADO', label: 'Resultado verificado por evidência', verified: true,
  operational_state: 'TASK_VERIFIED_LIMITED', receipts: [{ seq: 1, tool: 'web_open', status: 'OK' }],
  objectives: [{ id: 'CATALOG', status: 'PAGE_OBSERVED', receipt: 1 }], changes: [],
  commentary_unverified: 'Relatório do modelo', seconds: 12.3,
};

beforeEach(() => { setLang('pt-MZ'); useHud.setState({ state: base, error: null, chatStreaming: false }); });
afterEach(() => setLang('pt-MZ'));

describe('core mode comes only from backend state', () => {
  it('maps states', () => {
    expect(coreMode({ state: null, chatStreaming: false, error: null })).toBe('offline');
    expect(coreMode({ state: { ...base, engine: { ...base.engine, healthy: false } }, chatStreaming: false, error: null })).toBe('offline');
    expect(coreMode({ state: base, chatStreaming: false, error: 'network' })).toBe('offline');
    expect(coreMode({ state: base, chatStreaming: false, error: null })).toBe('ready');
    expect(coreMode({ state: base, chatStreaming: true, error: null })).toBe('thinking');
    expect(coreMode({ state: { ...base, model_busy: 1 }, chatStreaming: false, error: null })).toBe('thinking');
    expect(coreMode({ state: { ...base, task: { running: true, capability: 'x', elapsed: 3 } }, chatStreaming: true, error: null })).toBe('mission');
    expect(coreMode({ state: { ...base, last: verified }, chatStreaming: false, error: null })).toBe('verified');
    expect(coreMode({ state: { ...base, last: { ...verified, verified: false, state: 'EXECUCAO_FALHADA' } }, chatStreaming: false, error: null })).toBe('failed');
    expect(coreMode({ state: { ...base, last: { ...verified, verified: false, state: 'EXECUCAO_PARCIAL' } }, chatStreaming: false, error: null })).toBe('unverified');
  });
  it('busy drives the CPU budget', () => {
    expect(isBusy({ state: base, chatStreaming: false })).toBe(false);
    expect(isBusy({ state: base, chatStreaming: true })).toBe(true);
    expect(isBusy({ state: { ...base, task: { running: true, capability: 'x', elapsed: 0 } }, chatStreaming: false })).toBe(true);
  });
  it('renders the mode on the core', () => {
    expect(renderToStaticMarkup(<JarvisCore />)).toContain('data-mode="ready"');
    useHud.setState({ state: { ...base, task: { running: true, capability: 'pesquisa-fixture-goose', elapsed: 42 } } });
    const html = renderToStaticMarkup(<JarvisCore />);
    expect(html).toContain('data-mode="mission"');
    expect(html).toContain('42 s');
  });
});

describe('authorisation needs a typed operator code', () => {
  it('accepts only six hex characters', () => {
    for (const ok of ['A1B2C3', 'abcdef', ' 0F9E2D ']) expect(isOperatorCode(ok)).toBe(true);
    for (const bad of ['', 'click', 'A1B2C', 'A1B2C3D', 'GHIJKL', 'approve']) expect(isOperatorCode(bad)).toBe(false);
  });
  it('the missions panel offers no approve control before a code is requested', () => {
    const html = renderToStaticMarkup(<MissionsPanel />);
    expect(html).toContain('pesquisa-fixture-goose');
    expect(html).toContain(t('missions.request'));
    expect(html).not.toContain(t('missions.authorize'));
  });
});

describe('verified vs NOT verified are visually distinct', () => {
  it('timeline', () => {
    const html = renderToStaticMarkup(<ExecutionTimeline outcome={verified} />);
    expect(html).toContain('data-verdict="verified"');
    expect(html).toContain('#1');
    expect(html).toMatch(/<blockquote[^>]*data-unverified="true"[\s\S]*Relatório do modelo/);
    expect(verdictClass({ ...verified, verified: false, state: 'EXECUCAO_PARCIAL' })).toBe('unverified');
    expect(renderToStaticMarkup(<ExecutionTimeline outcome={null} />)).toContain(t('timeline.none'));
  });
});

describe('not-integrated capabilities are never simulated', () => {
  it('finance shows status and no price/quote/chart', () => {
    const html = renderToStaticMarkup(<FinanceIntelPanel />);
    expect(html).toContain('data-status="NAO_INTEGRADA"');
    expect(html).not.toMatch(/\$|USD|EUR|MZN|\d+[.,]\d+|<svg|<canvas/);
    expect(renderToStaticMarkup(<VoicePanel />)).toContain('data-status="NAO_INTEGRADA"');
  });
});

describe('i18n PT-MZ by default, English supported', () => {
  it('switches language and installs the global translator', () => {
    expect(t('nav.missions')).toBe('Missões');
    expect(renderToStaticMarkup(<CapabilityBadge status="BLOQUEADA" />)).toContain('Bloqueada');
    setLang('en');
    expect(t('nav.missions')).toBe('Missions');
    installGlobalTranslator();
    expect(globalThis.__rwT('status.PARCIAL')).toBe('Partial');
    expect(t('missing.key')).toBe('missing.key');
  });
});

describe('OP01 activity label (real backend phase only)', () => {
  it('shows the backend phase only while thinking and ignores unknown phases', async () => {
    const { activityLabel } = await import('./JarvisCore');
    expect(activityLabel('thinking', 'A pesquisar')).toBeTruthy();
    expect(activityLabel('thinking', 'qualquer coisa')).toBeNull();
    expect(activityLabel('ready', 'A pesquisar')).toBeNull();
    expect(activityLabel('thinking', undefined)).toBeNull();
  });
});

describe('JRV-V02 voice helpers', () => {
  it('greets by the local hour with the profile name only, and never speaks unconfirmed values or host lines', async () => {
    const { greetingText, dayPart, speakable } = await import('../lib/voice');
    expect([dayPart(8), dayPart(14), dayPart(21)]).toEqual(['morning', 'afternoon', 'evening']);
    expect(greetingText(21, 'Issa')).toContain(', Issa.');
    expect(greetingText(9, null)).not.toContain(',');
    const ans = 'A taxa média é 63,91 MZN.\nFonte: https://x/y.pdf — dados de 2026-11-24\n✓ Verificação do anfitrião: 1 valor\n\n---\n_JARVIS · resposta…_\n\n`rw-0123456789abcdef`';
    expect(speakable(ans)).toBe('A taxa média é 63,91 MZN.');
    const bad = 'A taxa é 99,99.\n⚠ Verificação do anfitrião: valores sem correspondência';
    expect(speakable(bad)).not.toContain('99,99');
  });
});

describe('JRV-V02 continuous conversation helpers', () => {
  it('VAD starts after sustained energy and ends after silence; sentences split; progressive speech is cancellable', async () => {
    const { VadDecider, splitSentences, speakProgressive } = await import('../lib/conversation');
    const v = new VadDecider();
    const ev: (string | null)[] = [];
    for (let i = 0; i < 20; i++) ev.push(v.push(0.001, 50));                 // room noise
    for (let i = 0; i < 10; i++) ev.push(v.push(0.2, 50));                   // speech 500 ms
    for (let i = 0; i < 25; i++) ev.push(v.push(0.001, 50));                 // silence 1250 ms
    expect(ev.filter(Boolean)).toEqual(['start', 'end']);
    expect(splitSentences('Olá. A taxa média de referência é 63,91 meticais por dólar. Os dados são do boletim do dia 24 de Novembro.')).toEqual(
      ['Olá. A taxa média de referência é 63,91 meticais por dólar.', 'Os dados são do boletim do dia 24 de Novembro.']);
    expect(splitSentences('Compra: 63,27 meticais por dólar americano hoje.')).toHaveLength(1);
    const said: string[] = [];
    let stop = false;
    const r = await speakProgressive('m', ['um.', 'dois.', 'três.'], {
      speak: async (_id, t) => { said.push(t); if (t === 'dois.') stop = true; },
      waitIdle: async () => undefined, cancelled: () => stop, now: () => 0 });
    expect(said).toEqual(['um.', 'dois.']);                                    // 'três.' dropped after interrupt
    expect(r.spoken).toBe(1);
  });
});
