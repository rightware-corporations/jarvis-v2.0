// RIGHTWARE JARVIS — one explicit activation per browser session (JRV-V02). Browsers only allow audio after a user
// gesture: the operator clicks "Activar JARVIS" once; the contextual greeting (local hour + authorised profile name)
// is then played through the SHARED upstream player (TTS cache on the host). Stored in sessionStorage, so page changes
// and reloads in the same tab do not repeat it. The microphone is NOT touched here.
import { useEffect, useState } from 'react';
import { useTtsStore } from '@/lib/tts';
import { t, useLang } from '../i18n';
import { useHudValue } from '../lib/hud-store';
import { greetingText } from '../lib/voice';

const KEY = 'rw-jarvis-activated';

export function isActivated(): boolean {
  try { return sessionStorage.getItem(KEY) === '1'; } catch { return false; }
}

export function SessionActivation() {
  useLang();
  const profile = useHudValue((s) => s.state?.profile);
  const available = useTtsStore((s) => s.available);
  const ensureHealth = useTtsStore((s) => s.ensureHealth);
  const [done, setDone] = useState(isActivated());
  useEffect(() => { if (profile?.voice) void ensureHealth(); }, [profile?.voice, ensureHealth]);
  if (done || !profile?.voice || available !== true) return null;
  const activate = () => {
    try { sessionStorage.setItem(KEY, '1'); } catch { /* private mode: still works for this page */ }
    setDone(true);
    void useTtsStore.getState().speak('rw-greeting', greetingText(new Date().getHours(), profile.display_name));
  };
  return (
    <button type="button" className="rw-activate" data-rw="session-activate" onClick={activate}>
      {t('voice.activate')}
    </button>
  );
}
