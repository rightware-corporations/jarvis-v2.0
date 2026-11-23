// Voice and financial-intelligence cards: they show the REAL integration status and never any data/number until
// the capability is integrated (no simulated quotes, charts or audio).
import { t, useLang } from '../i18n';
import { useHud, useHudValue } from '../lib/hud-store';
import { CapabilityBadge } from './CapabilityBadge';

function Card({ id, title, note }: { id: string; title: string; note?: string }) {
  const cap = useHudValue((s) => s.state)?.capabilities.find((c) => c.id === id);
  return (
    <section className="rw-panel rw-card" data-card={id}>
      <div className="rw-row"><h3 className="rw-panel__title">{title}</h3>{cap && <CapabilityBadge status={cap.status} />}</div>
      {cap?.reason && <p className="rw-muted rw-small">{cap.reason}</p>}
      {note && <p className="rw-small">{note}</p>}
    </section>
  );
}

export function VoicePanel() {
  useLang();
  return <Card id="voz" title={t('voice.title')} />;
}

export function FinanceIntelPanel() {
  useLang();
  return <Card id="inteligencia-financeira" title={t('finance.title')} note={t('finance.note')} />;
}
