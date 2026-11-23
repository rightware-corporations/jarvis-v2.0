// RIGHTWARE JARVIS (UI-02): /dashboard is the full HUD — core, engine, missions, capabilities, voice and finance cards.
import { JarvisCore } from '@rw/hud/JarvisCore';
import { MissionsPanel } from '@rw/hud/MissionsPanel';
import { CapabilitiesPanel } from '@rw/hud/CapabilitiesPanel';
import { FinanceIntelPanel, VoicePanel } from '@rw/hud/StatusCards';
import { t, useLang } from '@rw/i18n';
import { useHudValue } from '@rw/lib/hud-store';

export function DashboardPage() {
  useLang();
  const engine = useHudValue((s) => s.state)?.engine;
  return (
    <div className="rw-page rw-hud-page">
      <h1 className="rw-title">{t('hud.title')}</h1>
      <div className="rw-hud-grid">
        <div className="rw-panel rw-center">
          <JarvisCore size={220} />
          <div className="rw-small rw-muted">{t('hud.engine')}: {engine?.healthy ? 'Ollama · 127.0.0.1' : '—'}</div>
          <div className="rw-small rw-muted">{t('hud.models')}: {(engine?.models ?? []).join(', ') || '—'}</div>
          <div className="rw-small rw-muted">{t('hud.unverifiedNote')}</div>
        </div>
        <MissionsPanel />
        <CapabilitiesPanel />
        <div className="rw-col"><VoicePanel /><FinanceIntelPanel /></div>
      </div>
    </div>
  );
}
