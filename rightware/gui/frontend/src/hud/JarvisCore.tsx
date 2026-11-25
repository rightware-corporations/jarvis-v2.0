// The JARVIS core: a small SVG whose mode comes ONLY from backend state (coreMode). CPU budget (R-7): one slow,
// compositor-friendly rotation while idle; while the model or a mission works, continuous motion stops (html.rw-busy)
// and only a 1 Hz stepped indicator remains; prefers-reduced-motion disables all motion.
import { useEffect, useState } from 'react';
import { t, useLang } from '../i18n';
import { coreMode, useHudValue } from '../lib/hud-store';

export function coreLabel(mode: string, queue: number): string {
  const base = t(`core.${mode}`);
  return mode === 'thinking' && queue > 1 ? `${base} · ${t('core.queue', { n: queue })}` : base;
}

// OP01: phases reported by the backend (rightware.assistant_tools.activity) → i18n keys. Unknown phases are ignored.
const PHASES: Record<string, string> = {
  'A interpretar': 'activity.interpreting', 'A pesquisar': 'activity.searching',
  'A consultar fontes': 'activity.reading', 'A analisar': 'activity.analysing', 'Resposta concluída': 'activity.done',
};

export function activityLabel(mode: string, phase: string | undefined): string | null {
  return mode === 'thinking' && phase && PHASES[phase] ? t(PHASES[phase]) : null;
}

export function JarvisCore({ size = 168 }: { size?: number }) {
  useLang();
  const state = useHudValue((s) => s.state);
  const chatStreaming = useHudValue((s) => s.chatStreaming);
  const error = useHudValue((s) => s.error);
  const hud = { state, chatStreaming, error };
  const mode = coreMode(hud);
  const [, tick] = useState(0);
  const elapsed = hud.state?.task.elapsed;
  useEffect(() => {                         // re-render once per second only while a mission is running
    if (mode !== 'mission') return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [mode]);
  return (
    <div className="rw-core" data-mode={mode} role="status" aria-live="polite">
      <svg width={size} height={size} viewBox="0 0 200 200" aria-hidden="true">
        <circle className="rw-core__halo" cx="100" cy="100" r="96" />
        <circle className="rw-core__fine" cx="100" cy="100" r="88" strokeDasharray="1 5" />
        <path className="rw-core__frame" d="M16 50 A96 96 0 0 1 50 16 M150 16 A96 96 0 0 1 184 50 M184 150 A96 96 0 0 1 150 184 M50 184 A96 96 0 0 1 16 150" />
        <g className="rw-core__ring rw-core__ring--outer">
          <circle cx="100" cy="100" r="80" strokeDasharray="6 10" />
        </g>
        <g className="rw-core__ring rw-core__ring--mid">
          <circle cx="100" cy="100" r="62" strokeDasharray="40 14 6 14" />
        </g>
        <circle className="rw-core__ring--inner" cx="100" cy="100" r="44" />
        <circle className="rw-core__fine" cx="100" cy="100" r="33" strokeDasharray="3 5" />
        <circle className="rw-core__heart" cx="100" cy="100" r="16" />
        <circle className="rw-core__lens" cx="100" cy="100" r="8" />
        <g className="rw-core__tick"><rect x="97" y="10" width="6" height="16" rx="2" /></g>
      </svg>
      <div className="rw-core__label">
        {activityLabel(mode, hud.state?.activity?.phase) ?? coreLabel(mode, hud.state?.model_busy ?? 0)}
      </div>
      {mode === 'thinking' && (hud.state?.activity?.tool_calls ?? 0) > 0 && (
        <div className="rw-core__sub">{t('activity.calls', { n: hud.state?.activity?.tool_calls ?? 0 })}</div>
      )}
      {mode === 'mission' && elapsed != null && (
        <div className="rw-core__sub">{hud.state?.task.capability} · {t('core.elapsed', { s: Math.round(elapsed) })}</div>
      )}
    </div>
  );
}
