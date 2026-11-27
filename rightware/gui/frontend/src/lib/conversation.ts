// RIGHTWARE JARVIS — continuous voice conversation (JRV-V02, opt-in, explicit consent).
// Pure helpers (VAD decisions, sentence splitting, progressive speaking) + a tiny store shared by the toggle (MicButton)
// and the always-mounted controller. Reuses the upstream endpoints/stores: transcription via api.transcribeAudio, speech
// via the shared TTS store (one player: a new phrase tears down the previous one, so audio never overlaps).
import { create } from 'zustand';

export type ConvPhase = 'off' | 'listening' | 'recording' | 'transcribing' | 'thinking' | 'speaking' | 'error';

interface ConvStore {
  enabled: boolean;
  phase: ConvPhase;
  error: string | null;
  metrics: Record<string, number>;
  setEnabled: (v: boolean) => void;
  setPhase: (p: ConvPhase, error?: string | null) => void;
  mark: (k: string, v: number) => void;
}

export const useConversation = create<ConvStore>((set) => ({
  enabled: false,
  phase: 'off',
  error: null,
  metrics: {},
  setEnabled: (v) => set({ enabled: v, phase: v ? 'listening' : 'off', error: null }),
  setPhase: (p, error = null) => set({ phase: p, error }),
  mark: (k, v) => set((s) => ({ metrics: { ...s.metrics, [k]: v } })),
}));

if (typeof globalThis !== 'undefined') (globalThis as unknown as { __rwConv?: unknown }).__rwConv = useConversation;  // read-only probe for E2E

/** Energy VAD with an adaptive noise floor. Pure: feed it RMS frames, it says when speech starts / ends. */
export class VadDecider {
  private floor = 0.004;
  private speechMs = 0;
  private silenceMs = 0;
  speaking = false;

  constructor(private readonly opts = { minSpeechMs: 200, endSilenceMs: 1500, ratio: 3, absMin: 0.012 }) {}

  threshold(): number {
    return Math.max(this.opts.absMin, this.floor * this.opts.ratio);
  }

  /** Returns 'start' | 'end' | null for one frame of ``frameMs`` with energy ``rms``. */
  push(rms: number, frameMs: number): 'start' | 'end' | null {
    const loud = rms > this.threshold();
    if (!this.speaking) {
      if (!loud) this.floor = this.floor * 0.95 + rms * 0.05;       // learn the room only while silent
      this.speechMs = loud ? this.speechMs + frameMs : 0;
      if (this.speechMs >= this.opts.minSpeechMs) { this.speaking = true; this.silenceMs = 0; return 'start'; }
      return null;
    }
    this.silenceMs = loud ? 0 : this.silenceMs + frameMs;
    if (this.silenceMs >= this.opts.endSilenceMs) { this.speaking = false; this.speechMs = 0; return 'end'; }
    return null;
  }

  reset(): void { this.speaking = false; this.speechMs = 0; this.silenceMs = 0; }
}

/** Sentences for progressive speech: split on . ! ? ; (never on ':' — keeps "taxa: 63,91" together); merge very short pieces; cap length. */
export function splitSentences(text: string, min = 25, max = 220): string[] {
  const raw = text.replace(/\s+/g, ' ').split(/(?<=[.!?;])\s+/).map((s) => s.trim()).filter(Boolean);
  const out: string[] = [];
  for (const s of raw) {
    const last = out[out.length - 1];
    if (last && (last.length < min || s.length < min) && last.length + s.length + 1 <= max) out[out.length - 1] = `${last} ${s}`;
    else if (s.length > max) { for (let i = 0; i < s.length; i += max) out.push(s.slice(i, i + max)); }
    else out.push(s);
  }
  return out;
}

export interface Speaker {
  speak: (id: string, text: string) => Promise<void>;
  waitIdle: () => Promise<void>;
  cancelled: () => boolean;
  now?: () => number;
}

/** Speak sentence by sentence through the shared player; stops at once when cancelled. Returns time to first audio. */
export async function speakProgressive(id: string, sentences: string[], sp: Speaker): Promise<{ firstAudioMs: number | null; spoken: number }> {
  const now = sp.now ?? (() => performance.now());
  const t0 = now();
  let first: number | null = null;
  let spoken = 0;
  for (let i = 0; i < sentences.length; i++) {
    if (sp.cancelled()) break;
    await sp.speak(`${id}#${i}`, sentences[i]);           // resolves when playback STARTS (upstream store)
    if (first === null) first = now() - t0;
    if (sp.cancelled()) break;
    await sp.waitIdle();                                   // until this phrase ended (or was stopped)
    spoken += 1;
  }
  return { firstAudioMs: first, spoken };
}
