// RIGHTWARE JARVIS — continuous voice conversation controller (JRV-V02). Always mounted (InputArea unmounts the
// microphone button while a reply streams). Active ONLY after the user explicitly enables it; the microphone is opened
// once with echo cancellation and fully released when the mode is switched off.
//   VAD (local, WebAudio) → MediaRecorder per utterance → upstream /v1/speech/transcribe → SAME chat input + send →
//   reply finished → host-filtered speakable text → sentence-by-sentence speech through the SHARED upstream player.
// Half-duplex: while JARVIS thinks or speaks the VAD ignores the microphone (no self-transcription). "Interromper"
// stops playback at once and drops the pending sentences.
import { useEffect, useRef } from 'react';
import { useAppStore } from '@/lib/store';
import { useTtsStore } from '@/lib/tts';
import { transcribeAudio } from '@/lib/api';
import { toSpeakableText } from '@/lib/message-text';
import { t, useLang } from '../i18n';
import { VadDecider, speakProgressive, splitSentences, useConversation } from '../lib/conversation';

const FRAME_MS = 50;

function sendToChat(text: string): boolean {
  const ta = document.querySelector('textarea');
  if (!ta) return false;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  setter?.call(ta, text);
  ta.dispatchEvent(new Event('input', { bubbles: true }));            // React onChange → setInput
  requestAnimationFrame(() => ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
  return true;
}

export function ConversationController() {
  useLang();
  const enabled = useConversation((s) => s.enabled);
  const phase = useConversation((s) => s.phase);
  const err = useConversation((s) => s.error);
  const interrupted = useRef(false);

  useEffect(() => {
    if (!enabled) return undefined;
    const conv = useConversation.getState();
    const app = useAppStore.getState();
    const savedAutoplay = app.settings.voiceAutoplay;
    app.updateSettings({ voiceAutoplay: false });              // this mode speaks progressively itself (no double)
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    let recorder: MediaRecorder | null = null;
    let chunks: Blob[] = [];
    let speechEndAt = 0;
    let lastSpokenId: string | null = null;
    let sentAt = 0;
    const vad = new VadDecider();
    let alive = true;

    const onUtterance = async (blob: Blob) => {
      conv.setPhase('transcribing');
      const t0 = performance.now();
      try {
        const r = await transcribeAudio(blob, 'fala.webm');
        conv.mark('transcription_ms', Math.round(performance.now() - t0));
        const text = (r.text || '').trim();
        if (!alive) return;
        if (!text) { conv.setPhase('listening'); return; }
        sentAt = performance.now();
        if (!sendToChat(text)) { conv.setPhase('error', 'no-input'); return; }
        conv.setPhase('thinking');
      } catch (e) {
        conv.setPhase('error', e instanceof Error ? e.message : 'transcription');
        setTimeout(() => alive && useConversation.getState().setPhase('listening'), 1500);
      }
    };

    const start = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true,
                                                                      autoGainControl: true } });
      } catch (e) {
        conv.setPhase('error', 'microphone');
        return;
      }
      if (!alive) { stream.getTracks().forEach((tr) => tr.stop()); return; }
      ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 1024;
      src.connect(an);
      const buf = new Float32Array(an.fftSize);
      timer = setInterval(() => {
        const ph = useConversation.getState().phase;
        if (ph !== 'listening' && ph !== 'recording') { vad.reset(); return; }        // half-duplex gate
        an.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const ev = vad.push(Math.sqrt(sum / buf.length), FRAME_MS);
        if (ev === 'start' && ph === 'listening' && stream) {
          chunks = [];
          recorder = new MediaRecorder(stream);
          recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
          recorder.onstop = () => void onUtterance(new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' }));
          recorder.start();
          conv.setPhase('recording');
        } else if (ev === 'end' && ph === 'recording' && recorder) {
          speechEndAt = performance.now();
          recorder.stop();
        }
      }, FRAME_MS);
    };
    void start();

    // Reply finished → speak it progressively (host filter first: unconfirmed values are never read).
    const unsub = useAppStore.subscribe((s) => {
      const c = useConversation.getState();
      if (c.phase !== 'thinking' || s.streamState.isStreaming) return;
      const last = s.messages[s.messages.length - 1];
      if (!last || last.role !== 'assistant' || last.id === lastSpokenId || !last.content) return;
      lastSpokenId = last.id;
      c.mark('reply_ms', Math.round(performance.now() - sentAt));
      const text = toSpeakableText(last.content);
      const parts = splitSentences(text);
      interrupted.current = false;
      c.setPhase('speaking');
      const tts = useTtsStore.getState;
      void speakProgressive(last.id, parts, {
        speak: (id, txt) => tts().speak(id, txt),
        waitIdle: () => new Promise<void>((res) => {
          const iv = setInterval(() => { if (tts().state === 'idle' || interrupted.current || !alive) { clearInterval(iv); res(); } }, 100);
        }),
        cancelled: () => interrupted.current || !alive,
      }).then((r) => {
        if (r.firstAudioMs !== null) {
          c.mark('first_audio_after_reply_ms', Math.round(r.firstAudioMs));
          if (speechEndAt) c.mark('speech_end_to_first_audio_ms', Math.round(performance.now() - speechEndAt));
        }
        setTimeout(() => alive && useConversation.getState().setPhase('listening'), 400);   // let the room settle
      });
    });

    return () => {
      alive = false;
      unsub();
      if (timer) clearInterval(timer);
      if (recorder && recorder.state === 'recording') { recorder.onstop = null; recorder.stop(); }
      stream?.getTracks().forEach((tr) => tr.stop());                // microphone fully released
      void ctx?.close();
      useTtsStore.getState().stop();
      useAppStore.getState().updateSettings({ voiceAutoplay: savedAutoplay });
    };
  }, [enabled]);

  if (!enabled) return null;
  const interrupt = () => {
    interrupted.current = true;
    useTtsStore.getState().stop();
    useConversation.getState().setPhase('listening');
  };
  return (
    <div className="rw-conv" data-rw={`conv-${phase}`} role="status" aria-live="polite">
      <span className="rw-conv__dot" data-phase={phase} />
      <span>{t(`conv.${phase}`)}{err ? ` (${err})` : ''}</span>
      {(phase === 'speaking' || phase === 'thinking') && (
        <button type="button" className="rw-btn" data-rw="conv-interrupt" onClick={interrupt}>{t('conv.interrupt')}</button>
      )}
      <button type="button" className="rw-btn" data-rw="conv-off" onClick={() => useConversation.getState().setEnabled(false)}>
        {t('conv.off')}
      </button>
    </div>
  );
}
