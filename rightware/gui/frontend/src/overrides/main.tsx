// RIGHTWARE JARVIS (UI-02): replaces the pinned src/main.tsx. Same bootstrap, plus: RIGHTWARE theme and i18n, the HUD
// state poller, the CPU budget wiring (motion reduced while the model/mission works) and NO analytics init.
import '@/lib/polyfills';
import { StrictMode, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { MotionConfig } from 'motion/react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import App from '@/App';
import { initApiBase } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import '@/index.css';
import '@rw/theme/rightware.css';
import { installGlobalTranslator } from '@rw/i18n';
import { installGlobalSpeakable } from '@rw/lib/voice';
import { ConversationController } from '@rw/hud/ConversationController';
import { SessionActivation } from '@rw/hud/SessionActivation';
import { isBusy, startHudPolling, useHud, useHudValue } from '@rw/lib/hud-store';

installGlobalTranslator();
installGlobalSpeakable();
document.documentElement.classList.add('dark', 'rw-hud');

// Upstream chat streaming → HUD busy signal (no extra polling).
useAppStore.subscribe((s) => {
  const streaming = !!s.streamState?.isStreaming;
  if (streaming !== useHud.getState().chatStreaming) useHud.getState().setChatStreaming(streaming);
});

function Budget({ children }: { children: ReactNode }) {
  const busy = useHudValue(isBusy);
  return <MotionConfig reducedMotion={busy ? 'always' : 'user'}>{children}</MotionConfig>;
}

initApiBase().finally(() => {
  startHudPolling();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary>
        <BrowserRouter>
          <Budget>
            <App />
            <SessionActivation />
            <ConversationController />
          </Budget>
        </BrowserRouter>
      </ErrorBoundary>
    </StrictMode>,
  );
});
