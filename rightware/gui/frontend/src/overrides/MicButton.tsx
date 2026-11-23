// RIGHTWARE JARVIS (UI-02): voice is NOT integrated yet; the pinned microphone button becomes an explicit,
// disabled indicator (never records, never calls /v1/speech/*).
import { MicOff } from 'lucide-react';
import { t, useLang } from '@rw/i18n';

interface MicButtonProps { state: unknown; onClick: () => void; disabled?: boolean; reason?: string }

export function MicButton(_props: MicButtonProps) {
  useLang();
  return (
    <button type="button" disabled className="p-2 rounded-lg opacity-60 cursor-not-allowed" title={t('voice.notIntegrated')}
            aria-label={t('voice.notIntegrated')} data-rw="voice-not-integrated">
      <MicOff size={16} />
    </button>
  );
}
