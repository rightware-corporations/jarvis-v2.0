"""VOICE (opt-in ``--voz``): JARVIS listens and speaks through the UPSTREAM OpenJarvis speech routes
(``/v1/speech/transcribe|synthesize|health|tts/health``) and the upstream frontend (``useSpeech``/``useTts``), in
the SAME chat session: the transcript goes into the same conversation input; answers are spoken from the same
chat messages. No second assistant, no second conversation engine.

* STT: the upstream ``FasterWhisperBackend`` (model ``base``, CPU int8), loaded from ``.runtime/voice/whisper``.
* TTS: ``KokoroOnnxTTS`` — the SAME Kokoro-82M model via ``kokoro-onnx`` (ONNX Runtime) behind the upstream
  ``TTSBackend`` interface. Reason (measured 25/11/2026): the upstream Kokoro backend needs PyTorch (> 1 GB), which
  does not fit the session's disk allowance; the ONNX int8 model is 89 MB + 27 MB of voices.
Everything runs locally on the host; audio never leaves it. Model files live in ``.runtime/voice`` (never committed).
"""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOICE_DIR = ROOT / ".runtime" / "voice"
KOKORO_MODEL = VOICE_DIR / "kokoro" / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES = VOICE_DIR / "kokoro" / "voices-v1.0.bin"
WHISPER_CACHE = VOICE_DIR / "whisper"
DEFAULT_VOICE = "pf_dora"                       # Portuguese (pt-br) female voice of Kokoro v1.0
LANG_BY_PREFIX = {"p": "pt-br", "a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "i": "it"}
MAX_TTS_CHARS = 1500


PACKAGES = ("faster-whisper==1.2.1", "av==16.1.0", "ctranslate2==4.7.1", "kokoro-onnx==0.6.1", "soundfile==0.14.0",
            "onnxruntime==1.32.0")
MODEL_SHA256 = {KOKORO_MODEL: "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb",
                KOKORO_VOICES: "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"}


def setup(python: Path) -> dict:
    """Idempotent: install the pinned voice packages into the GUI runtime venv (``setup`` recreates that venv) and
    verify the local model files against the hashes recorded when they were obtained (25/11/2026)."""
    import hashlib
    import shutil
    import subprocess
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv não encontrado")
    subprocess.run([uv, "pip", "install", "--python", str(python), *PACKAGES], check=True)
    bad = [p.name for p, h in MODEL_SHA256.items() if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h]
    return {"packages": list(PACKAGES), "models_ok": not bad, "models_bad_or_missing": bad,
            "whisper_cache": WHISPER_CACHE.is_dir()}


def available() -> tuple[bool, str]:
    missing = [p.name for p in (KOKORO_MODEL, KOKORO_VOICES) if not p.is_file()]
    if missing:
        return False, f"modelos de voz em falta: {', '.join(missing)}"
    if not WHISPER_CACHE.is_dir():
        return False, "modelo Whisper em falta"
    return True, ""


def whisper_backend():
    """The upstream STT backend, pointed at the local model cache (no download at run time)."""
    os.environ.setdefault("HF_HUB_CACHE", str(WHISPER_CACHE))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from openjarvis.speech.faster_whisper import FasterWhisperBackend
    return FasterWhisperBackend(model_size="base", device="cpu", compute_type="int8")


def make_tts():
    from openjarvis.speech.tts import TTSBackend, TTSResult

    class KokoroOnnxTTS(TTSBackend):
        backend_id = "kokoro-onnx"   # NOT "kokoro": otherwise the upstream applies the config's English voice

        def __init__(self):
            self._k = None
            self._lock = threading.Lock()

        def _engine(self):
            with self._lock:
                if self._k is None:
                    from kokoro_onnx import Kokoro
                    self._k = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
                return self._k

        def synthesize(self, text, *, voice_id="", speed=1.0, output_format="wav"):
            import soundfile as sf
            voice = voice_id if voice_id in self.available_voices() else DEFAULT_VOICE
            text = " ".join(str(text).split())[:MAX_TTS_CHARS]
            audio, rate = self._engine().create(text, voice=voice, speed=max(0.5, min(2.0, float(speed or 1.0))),
                                                lang=LANG_BY_PREFIX.get(voice[0], "pt-br"))
            buf = io.BytesIO()
            sf.write(buf, audio, rate, format="WAV")
            return TTSResult(audio=buf.getvalue(), format="wav", duration_seconds=round(len(audio) / rate, 2),
                             voice_id=voice, sample_rate=rate)

        def available_voices(self):
            try:
                return list(self._engine().get_voices())
            except Exception:
                return [DEFAULT_VOICE]

        def health(self):
            return available()[0]
    return KokoroOnnxTTS()
