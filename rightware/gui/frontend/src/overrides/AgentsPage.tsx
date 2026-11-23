// RIGHTWARE JARVIS (UI-02): /agents shows the supervised Missions page (the pinned agent manager is not integrated).
import { MissionsPanel } from '@rw/hud/MissionsPanel';
import { JarvisCore } from '@rw/hud/JarvisCore';

export function AgentsPage() {
  return (
    <div className="rw-page">
      <div className="rw-page__core"><JarvisCore size={140} /></div>
      <MissionsPanel />
    </div>
  );
}
