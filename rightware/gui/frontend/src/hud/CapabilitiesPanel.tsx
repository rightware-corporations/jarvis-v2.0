import { t, useLang } from '../i18n';
import { useHud, useHudValue } from '../lib/hud-store';
import { CapabilityBadge } from './CapabilityBadge';

export function CapabilitiesPanel() {
  useLang();
  const caps = useHudValue((s) => s.state)?.capabilities ?? [];
  return (
    <section className="rw-panel" aria-label={t('caps.title')}>
      <h3 className="rw-panel__title">{t('caps.title')}</h3>
      <p className="rw-muted rw-small">{t('caps.subtitle')}</p>
      <ul className="rw-caps">
        {caps.map((c) => (
          <li key={c.id} data-cap={c.id}>
            <div className="rw-row"><b>{c.label}</b> <CapabilityBadge status={c.status} /></div>
            {c.reason && <div className="rw-muted rw-small">{c.reason}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
