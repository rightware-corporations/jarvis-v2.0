import { t, useLang } from '../i18n';
import type { CapabilityStatus } from '../lib/rightware-api';

export function CapabilityBadge({ status }: { status: CapabilityStatus }) {
  useLang();
  return <span className={`rw-badge rw-badge--${status.toLowerCase()}`} data-status={status}>{t(`status.${status}`)}</span>;
}
