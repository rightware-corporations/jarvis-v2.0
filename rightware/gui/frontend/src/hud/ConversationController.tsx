// RIGHTWARE JARVIS — continuous voice conversation controller (JRV-V02). Always mounted (InputArea unmounts the
// microphone button while a reply streams). Active ONLY after the user explicitly enables it; the microphone is opened
// once with echo cancellation and fully released when the mode is switched off.
//   VAD (local, WebAudio) → MediaRecorder per utterance → upstream /v1/speech/transcribe → SAME chat input + send →
//   reply finished → host-filtered speakable text → sentence-by-sentence speech through the SHARED upstream player.
// Half-duplex: while JARVIS thinks or speaks the VAD ignores the microphone (no self-transcription). "Interromper"
// stops playback at once and drops the pending sentences.
import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '@/lib/store';
import { useTtsStore } from '@/lib/tts';
import { transcribeAudio } from '@/lib/api';
import { toSpeakableText } from '@/lib/message-text';
import { t, useLang } from '../i18n';
import { VadDecider, speakProgressive, splitSentences, useConversation } from '../lib/conversation';

const FRAME_MS = 50;
const MAX_RECORDING_MS = 15000;


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
  const manualAction = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);
  const metrics = useConversation((s) => s.metrics);

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
    let startedAt = 0;
    let manual = false;
    let lastMeterAt = 0;
    let speechEndAt = 0;
    let lastSpokenId: string | null = null;
    let sentAt = 0;
    const vad = new VadDecider();
    let alive = true;
    setReady(false);
    conv.mark('audio_rms', 0);
    conv.mark('vad_threshold', 0);
    conv.mark('audio_context_running', 0);
    conv.mark('capture_bytes', 0);
    conv.mark('capture_duration_ms', 0);

    const recover = (key: string) => {
      if (!alive) return;
      vad.reset();
      conv.setPhase('listening', t(key));
    };

    const onUtterance = async (blob: Blob) => {
      if (!alive) return;
      conv.mark('capture_bytes', blob.size);
      if (!blob.size) { recover('conv.emptyAudio'); return; }
      conv.setPhase('transcribing');
      const t0 = performance.now();
      try {
        const r = await transcribeAudio(blob, 'fala.webm');
        if (!alive) return;
        conv.mark('transcription_ms', Math.round(performance.now() - t0));
        const text = (r.text || '').trim();
        if (!text) { recover('conv.noSpeech'); return; }
        sentAt = performance.now();
        if (!sendToChat(text)) { recover('conv.noInput'); return; }
        conv.setPhase('thinking');
      } catch (error) {
        const message = error instanceof Error ? error.message : '';
        recover(message.startsWith('RW_NO_SPEECH:') ? 'conv.noSpeech' : 'conv.transcriptionFailed');
      }
    };

    const finishRecording = () => {
      if (!alive || !recorder || recorder.state !== 'recording') return;
      const rec = recorder;
      speechEndAt = performance.now();
      conv.mark('capture_duration_ms', Math.round(speechEndAt - startedAt));
      conv.setPhase('transcribing'); // gate the next VAD tick BEFORE asynchronous onstop
      try { rec.stop(); } catch {
        rec.onstop = null;
        recorder = null;
        manual = false;
        recover('conv.recorderFailed');
      }
    };

    const startRecording = (byHand: boolean) => {
      if (!alive || !stream || recorder || useConversation.getState().phase !== 'listening') return;
      if (useAppStore.getState().streamState.isStreaming) return;
      if (!stream.getAudioTracks().some((track) => track.readyState === 'live' && track.enabled)) {
        recover('conv.microphoneLost'); return;
      }
      try {
        const rec = new MediaRecorder(stream);
        const captured: Blob[] = [];
        recorder = rec;
        manual = byHand;
        rec.ondataavailable = (event) => { if (alive && recorder === rec && event.data.size) captured.push(event.data); };
        rec.onerror = () => {
          if (!alive || recorder !== rec) return;
          rec.onstop = null;
          recorder = null;
          manual = false;
          if (rec.state !== 'inactive') { try { rec.stop(); } catch { /* already stopped */ } }
          recover('conv.recorderFailed');
        };
        rec.onstop = () => {
          if (!alive || recorder !== rec) return;
          recorder = null;
          manual = false;
          vad.reset();
          void onUtterance(new Blob(captured, { type: rec.mimeType || captured[0]?.type || 'audio/webm' }));
        };
        rec.start(250);
        startedAt = performance.now();
        conv.setPhase('recording');
      } catch {
        recorder = null;
        manual = false;
        recover('conv.recorderFailed');
      }
    };

    const start = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true,
                                                                      autoGainControl: true } });
      } catch {
        if (alive) conv.setPhase('error', t('conv.microphoneFailed'));
        return;
      }
      if (!alive) { stream.getTracks().forEach((tr) => tr.stop()); return; }
      for (const track of stream.getAudioTracks()) {
        track.onended = () => {
          if (!alive) return;
          setReady(false);
          if (recorder) {
            recorder.onstop = null;
            if (recorder.state !== 'inactive') { try { recorder.stop(); } catch { /* stopped */ } }
            recorder = null;
          }
          conv.setPhase('error', t('conv.microphoneLost'));
        };
      }
      manualAction.current = () => {
        if (!alive) return;
        // A user gesture may resume WebAudio, but manual capture does not depend on it.
        if (ctx?.state === 'suspended') void ctx.resume().catch(() => undefined);
        const ph = useConversation.getState().phase;
        if (ph === 'recording') finishRecording();
        else if (ph === 'listening') startRecording(true);
      };
      setReady(true);
      let an: AnalyserNode | null = null;
      try {
        ctx = new AudioContext();
        const src = ctx.createMediaStreamSource(stream);
        an = ctx.createAnalyser();
        an.fftSize = 1024;
        src.connect(an);
        if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);
      } catch {
        recover('conv.vadUnavailable');
      }
      const buf = new Float32Array(an?.fftSize ?? 1024);
      timer = setInterval(() => {
        if (!alive) return;
        const ph = useConversation.getState().phase;
        const now = performance.now();
        if (ph === 'recording' && now - startedAt >= MAX_RECORDING_MS) {
          finishRecording(); return;
        }
        if (ph !== 'listening' && ph !== 'recording') { vad.reset(); return; }
        const running = !!an && ctx?.state === 'running';
        if (!running) {
          if (now - lastMeterAt >= 250) {
            conv.mark('audio_context_running', 0);
            lastMeterAt = now;
          }
          vad.reset();
          return; // manual capture remains available even when AudioContext is suspended
        }
        an!.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        if (now - lastMeterAt >= 250) {
          conv.mark('audio_context_running', 1);
          conv.mark('audio_rms', rms);
          conv.mark('vad_threshold', vad.threshold());
          lastMeterAt = now;
        }
        if (manual || useAppStore.getState().streamState.isStreaming) { vad.reset(); return; }
        const ev = vad.push(rms, FRAME_MS);
        if (ev === 'start' && ph === 'listening') startRecording(false);
        else if (ev === 'end' && ph === 'recording') finishRecording();
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
      manualAction.current = null;
      if (recorder) {
        recorder.onstop = null;
        recorder.onerror = null;
        if (recorder.state !== 'inactive') { try { recorder.stop(); } catch { /* stopped */ } }
      }
      stream?.getTracks().forEach((tr) => tr.stop());                // microphone fully released
      if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => undefined);
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
      {ready && (phase === 'listening' || phase === 'recording') && (
        <button type="button" className="rw-btn" data-rw="conv-manual" onClick={() => manualAction.current?.()}>
          {t(phase === 'recording' ? 'conv.manualStop' : 'conv.manualStart')}
        </button>
      )}
      {ready && (phase === 'listening' || phase === 'recording') && (
        <span className="rw-small" data-rw="conv-audio-status">
          {metrics.audio_context_running ? t('conv.audioLevel', { rms: (metrics.audio_rms ?? 0).toFixed(4), threshold: (metrics.vad_threshold ?? 0).toFixed(4) }) : t('conv.vadUnavailable')}
        </span>
      )}
      {(phase === 'speaking' || phase === 'thinking') && (
        <button type="button" className="rw-btn" data-rw="conv-interrupt" onClick={interrupt}>{t('conv.interrupt')}</button>
      )}
      <button type="button" className="rw-btn" data-rw="conv-off" onClick={() => useConversation.getState().setEnabled(false)}>
        {t('conv.off')}
      </button>
    </div>
  );
}
