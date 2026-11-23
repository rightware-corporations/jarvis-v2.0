// RIGHTWARE JARVIS (UI-02): replaces the pinned right-hand SystemPanel (cost comparison/leaderboard) with the HUD
// side panel: JARVIS core, missions and the last verified/unverified result.
import { X } from 'lucide-react';
import { useAppStore } from '@/lib/store';
import { JarvisCore } from '@rw/hud/JarvisCore';
import { MissionsPanel } from '@rw/hud/MissionsPanel';
import { t, useLang } from '@rw/i18n';
import { useHudValue } from '@rw/lib/hud-store';

export function SystemPanel() {
  useLang();
  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);
  const error = useHudValue((s) => s.error);
  return (
    <aside className="rw-side" aria-label={t('hud.title')}>
      <div className="rw-row rw-side__head">
        <span className="rw-label">{t('app.name')}</span>
        <button type="button" className="rw-icon-btn" onClick={toggleSystemPanel} aria-label="close"><X size={14} /></button>
      </div>
      <JarvisCore size={150} />
      {error && <p className="rw-msg">{t(error === 'session' ? 'error.session' : 'error.state')}</p>}
      <p className="rw-muted rw-small rw-center">{t('hud.unverifiedNote')}</p>
      <MissionsPanel compact />
    </aside>
  );
}
