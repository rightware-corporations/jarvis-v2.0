// Supervised missions on the SAME ControlPlane. The operator must TYPE the single-use code; there is no button that
// approves without it (operator decision). Cancel goes through the ControlPlane.
import { useState } from 'react';
import { t, useLang } from '../i18n';
import { useHud, useHudValue } from '../lib/hud-store';
import { authorizeMission, cancelMission, isOperatorCode, requestMission } from '../lib/rightware-api';
import { CapabilityBadge } from './CapabilityBadge';
import { ExecutionTimeline } from './ExecutionTimeline';

export function MissionsPanel({ compact = false }: { compact?: boolean }) {
  useLang();
  const state = useHudValue((s) => s.state);
  const refresh = () => useHud.getState().refresh();
  const [shown, setShown] = useState<{ capability: string; code: string; description?: string } | null>(null);
  const [typed, setTyped] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const missions = (state?.capabilities ?? []).filter((c) => c.mission);
  const running = state?.task.running;

  const ask = async (capability: string) => {
    setBusy(true); setMsg(null); setTyped('');
    try {
      const r = await requestMission(capability);
      setShown(r.code ? { capability, code: r.code, description: r.description } : null);
      if (!r.code) setMsg(r.label);
    } catch (e) { setMsg(String((e as Error).message)); }
    setBusy(false); void refresh();
  };
  const authorize = async () => {
    if (!isOperatorCode(typed)) return;
    setBusy(true);
    try {
      const r = await authorizeMission(typed.trim());
      setMsg(/inválido/i.test(r.text) ? t('missions.codeInvalid') : null);
      setShown(null); setTyped('');
    } catch (e) { setMsg(String((e as Error).message)); }
    setBusy(false); void refresh();
  };
  const cancel = async () => { setBusy(true); await cancelMission().catch(() => null); setBusy(false); void refresh(); };

  return (
    <section className="rw-panel" aria-label={t('missions.title')}>
      <h3 className="rw-panel__title">{t('missions.title')}</h3>
      {!missions.length && <p className="rw-muted">{t('missions.none')}</p>}
      <ul className="rw-missions">
        {missions.map((m) => (
          <li key={m.id}>
            <div className="rw-row"><b>{m.id}</b> <CapabilityBadge status={m.status} /></div>
            {!compact && <div className="rw-muted rw-small">{m.label}</div>}
            <button type="button" className="rw-btn" disabled={busy || !!running} onClick={() => ask(m.id)}>
              {t('missions.request')}
            </button>
          </li>
        ))}
      </ul>
      {shown && !running && (
        <div className="rw-auth">
          <div className="rw-small">{t('missions.codeShown')} <span className="rw-mono rw-code">{shown.code}</span></div>
          <label className="rw-small">{t('missions.typeCode')}
            <input className="rw-input rw-mono" value={typed} maxLength={6} autoComplete="off" spellCheck={false}
                   onChange={(e) => setTyped(e.target.value.toUpperCase())} aria-label={t('missions.typeCode')} />
          </label>
          <button type="button" className="rw-btn rw-btn--primary" disabled={busy || !isOperatorCode(typed)} onClick={authorize}>
            {t('missions.authorize')}
          </button>
          <div className="rw-muted rw-small">{t('missions.noClick')}</div>
        </div>
      )}
      {running && (
        <div className="rw-running">
          <div>{t('missions.running', { cap: state?.task.capability ?? '', s: Math.round(state?.task.elapsed ?? 0) })}</div>
          <button type="button" className="rw-btn rw-btn--danger" disabled={busy} onClick={cancel}>{t('missions.cancel')}</button>
        </div>
      )}
      {msg && <p className="rw-msg">{msg}</p>}
      <ExecutionTimeline outcome={state?.last ?? null} compact={compact} />
    </section>
  );
}
