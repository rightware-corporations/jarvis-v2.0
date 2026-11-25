// RIGHTWARE JARVIS (VOICE): the pinned microphone, in PT-MZ/EN. Active ONLY when the host started with --voz and the
// upstream /v1/speech/health reports a backend; otherwise an explicit "Voz não integrada" indicator (never records).
// Recording, upload and transcription stay in the pinned useSpeech hook; the transcript goes into the SAME chat input.
import { Mic, MicOff, Loader2 } from 'lucide-react';
import { t, useLang } from '@rw/i18n';

interface MicButtonProps {
  state: 'idle' | 'recording' | 'transcribing' | string;
  onClick: () => void;
  disabled?: boolean;
  reason?: 'not-enabled' | 'no-backend' | 'streaming';
}

export function micTitle(state: string, reason?: string): string {
  if (reason === 'no-backend') return t('voice.notIntegrated');
  if (reason === 'not-enabled') return t('voice.enableInSettings');
  if (reason === 'streaming') return t('voice.wait');
  if (state === 'recording') return t('voice.stop');
  if (state === 'transcribing') return t('voice.transcribing');
  return t('voice.start');
}

export function MicButton({ state, onClick, disabled, reason }: MicButtonProps) {
  useLang();
  const title = micTitle(state, reason);
  if (reason === 'no-backend') {
    return (
      <button type="button" disabled className="p-2 rounded-lg opacity-60 cursor-not-allowed" title={title}
              aria-label={title} data-rw="voice-not-integrated">
        <MicOff size={16} />
      </button>
    );
  }
  const inactive = !!disabled || state === 'transcribing';
  return (
    <button type="button" onClick={onClick} disabled={inactive} title={title} aria-label={title}
            data-rw={`voice-${state}`} className="p-2 rounded-xl shrink-0"
            style={{ background: state === 'recording' ? 'var(--color-error)' : 'transparent',
                     color: state === 'recording' ? 'white' : 'var(--color-text-secondary)',
                     opacity: inactive ? 0.4 : 1, cursor: inactive ? 'default' : 'pointer' }}>
      {state === 'transcribing' ? <Loader2 size={16} /> : <Mic size={16} />}
    </button>
  );
}
