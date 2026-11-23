// Last supervised result exactly as decided by receipts + the RIGHTWARE verifier. The model's commentary is kept
// apart and labelled NOT verified.
import { t, useLang } from '../i18n';
import type { Outcome } from '../lib/rightware-api';

export function verdictClass(o: Outcome): 'verified' | 'failed' | 'unverified' {
  if (o.verified) return 'verified';
  return o.state === 'EXECUCAO_FALHADA' || o.state === 'TAREFA_NAO_AUTORIZADA' ? 'failed' : 'unverified';
}

export function ExecutionTimeline({ outcome, compact = false }: { outcome: Outcome | null; compact?: boolean }) {
  useLang();
  if (!outcome) return <div className="rw-timeline rw-muted">{t('timeline.none')}</div>;
  const v = verdictClass(outcome);
  return (
    <div className={`rw-timeline rw-timeline--${v}`} data-verdict={v}>
      <div className="rw-timeline__head">
        <span className={`rw-verdict rw-verdict--${v}`}>{outcome.label}</span>
        {outcome.operational_state && <span className="rw-muted"> · {outcome.operational_state}</span>}
        {outcome.seconds != null && <span className="rw-muted"> · {outcome.seconds.toFixed(1)} s</span>}
      </div>
      {outcome.verified && <div className="rw-muted rw-small">{t('timeline.verifiedBy')}</div>}
      {!!outcome.receipts?.length && (
        <>
          <div className="rw-section">{t('timeline.receipts')}</div>
          <ol className="rw-receipts">
            {outcome.receipts.map((r) => (
              <li key={r.seq} data-status={r.status}><span className="rw-mono">#{r.seq}</span> {r.tool} <b>{r.status}</b></li>
            ))}
          </ol>
        </>
      )}
      {!compact && !!outcome.objectives?.length && (
        <>
          <div className="rw-section">{t('timeline.objectives')}</div>
          <ul className="rw-objectives">
            {outcome.objectives.map((o) => (
              <li key={o.id}>{o.id}: <b>{o.status}</b>{o.receipt ? ` (#${o.receipt})` : ''}</li>
            ))}
          </ul>
        </>
      )}
      {!compact && outcome.verified && !!outcome.changes?.length && (
        <>
          <div className="rw-section">{t('timeline.changes')}</div>
          <ul className="rw-objectives">{outcome.changes.map((c) => <li key={c}>{c}</li>)}</ul>
        </>
      )}
      {!!outcome.commentary_unverified && (
        <blockquote className="rw-unverified" data-unverified="true">
          <div className="rw-section">⚠ {t('timeline.commentary')}</div>
          <div className="rw-unverified__text">{compact ? outcome.commentary_unverified.slice(0, 280) : outcome.commentary_unverified}</div>
        </blockquote>
      )}
    </div>
  );
}
