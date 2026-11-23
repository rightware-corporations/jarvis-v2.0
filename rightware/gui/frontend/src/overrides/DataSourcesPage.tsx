// RIGHTWARE JARVIS (UI-02): /data-sources shows the real state of every JARVIS capability.
import { CapabilitiesPanel } from '@rw/hud/CapabilitiesPanel';
import { FinanceIntelPanel, VoicePanel } from '@rw/hud/StatusCards';

export function DataSourcesPage() {
  return (
    <div className="rw-page">
      <CapabilitiesPanel />
      <div className="rw-grid2"><VoicePanel /><FinanceIntelPanel /></div>
    </div>
  );
}
