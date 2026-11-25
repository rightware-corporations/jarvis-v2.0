// RIGHTWARE JARVIS voice helpers (JRV-V02). Pure functions + the global hook used by the declared patch in the pinned
// lib/message-text.ts (toSpeakableText). The HOST owns what is spoken:
//  - the RIGHTWARE footer (after "\n---\n"), request ids, context notes and host source/verification lines are never read;
//  - if the host flagged financial values as NOT confirmed (⚠), the answer is NOT read: only a spoken warning is.
import { t } from '../i18n';

const HOST_LINE = /^\s*[*_>\-•]*\s*(Fonte:|Fonte \(registo|✓ Verificação do anfitrião|_Contexto:|`?rw-[0-9a-f]{16}`?\s*$)/i;
const UNCONFIRMED = /⚠\s*(Verificação do anfitrião|Nenhuma ferramenta financeira)/;

export function speakable(text: string): string {
  if (UNCONFIRMED.test(text)) return t('voice.unconfirmed');
  const body = text.split(/\n-{3,}\n/)[0];
  return body.split('\n').filter((l) => !HOST_LINE.test(l)).join('\n').trim();
}

export function dayPart(hour: number): 'morning' | 'afternoon' | 'evening' {
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
}

/** Greeting from the USER's local hour and the authorised profile name only (no other personal data). */
export function greetingText(hour: number, name?: string | null): string {
  const base = t(`chat.greeting.${dayPart(hour)}`);
  return t('voice.greeting', { greeting: base, name: name ? `, ${name}` : '' });
}

export function installGlobalSpeakable(): void {
  globalThis.__rwSpeakable = speakable;
}
