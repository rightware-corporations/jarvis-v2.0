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
        <circle className="rw-core__halo" cx="100" cy="100" r="92" />
        <g className="rw-core__ring rw-core__ring--outer">
          <circle cx="100" cy="100" r="80" strokeDasharray="6 10" />
        </g>
        <g className="rw-core__ring rw-core__ring--mid">
          <circle cx="100" cy="100" r="62" strokeDasharray="40 14 6 14" />
        </g>
        <circle className="rw-core__ring--inner" cx="100" cy="100" r="44" />
        <circle className="rw-core__heart" cx="100" cy="100" r="22" />
        <g className="rw-core__tick"><rect x="97" y="10" width="6" height="16" rx="2" /></g>
      </svg>
      <div className="rw-core__label">{coreLabel(mode, hud.state?.model_busy ?? 0)}</div>
      {mode === 'mission' && elapsed != null && (
        <div className="rw-core__sub">{hud.state?.task.capability} · {t('core.elapsed', { s: Math.round(elapsed) })}</div>
      )}
    </div>
  );
}
