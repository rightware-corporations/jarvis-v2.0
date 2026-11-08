"""Jarvis do Issa — voice loop: microphone -> STT -> OpenJarvis/Ollama -> TTS.

Run inside the pinned OpenJarvis virtualenv (``python jarvis.py voice``).
Reuses upstream pieces: FasterWhisperBackend + record_until_silence (STT),
SimpleAgent + OllamaEngine (conversation), KokoroTTSBackend + play_wav
(optional TTS). Windows effects go only through ``windows_actions``.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
import threading

from rightware import runtime
from rightware.windows_actions import WindowsActions, describe, detect_actions

EXIT_WORDS = {"sair", "adeus", "/quit", "/exit", "termina", "terminar"}
_CLAIMS_EFFECT = re.compile(
    r"\b(abri|executei|lancei|iniciei|ja abri|ja executei)\b", re.IGNORECASE)


class VoiceUnavailable(RuntimeError):
    """A speech component is missing or failed; the loop keeps working in text."""


def interruptible(fn, *args, poll=0.1):
    """Run a blocking call in a worker so Ctrl+C reaches the main thread.

    On Windows a KeyboardInterrupt is not delivered while the main thread is
    inside a blocking C call (httpx socket read, CTranslate2 decode); it would
    only arrive after the model answered. Polling join() keeps cancellation
    within ``poll`` seconds; an abandoned worker's result is discarded.
    """
    box = {}

    def work():
        try:
            box["value"] = fn(*args)
        except BaseException as exc:  # re-raised in the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(poll)
    if "error" in box:
        raise box["error"]
    return box.get("value")


# ---------------------------------------------------------------- STT ----
class WhisperSTT:
    """Upstream FasterWhisperBackend, explicitly local (no cloud discovery)."""

    def __init__(self, model="small", device="cpu", compute_type="int8", language="pt"):
        self.language = language
        try:
            from openjarvis.speech.faster_whisper import FasterWhisperBackend
        except ImportError as exc:  # pragma: no cover - depends on install
            raise VoiceUnavailable("Instala a voz: python jarvis.py setup --voice") from exc
        self._backend = FasterWhisperBackend(model_size=model, device=device,
                                             compute_type=compute_type)

    def load(self) -> None:
        if not self._backend.health():
            raise VoiceUnavailable(f"Whisper não carregou: {self._backend.last_error()}")

    def listen(self) -> str:
        from openjarvis.speech.voice_io import record_until_silence
        try:
            audio = record_until_silence()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise VoiceUnavailable(f"Erro do microfone: {exc}") from exc
        return interruptible(self.transcribe, audio)

    def transcribe(self, wav: bytes) -> str:
        return self._backend.transcribe(wav, format="wav", language=self.language).text.strip()


# ---------------------------------------------------------------- TTS ----
# The script travels as -EncodedCommand (no quoting issues) and the text in
# an environment variable (Unicode-safe, never on the command line).
# Exit 3 = no enabled Portuguese voice installed.
SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled })
if ($env:JARVIS_TTS_LIST -eq '1') {
  foreach ($v in $voices) { [Console]::Out.WriteLine($v.VoiceInfo.Culture.Name + '|' + $v.VoiceInfo.Name) }
  exit 0
}
$pick = $null
foreach ($c in @('pt-PT', 'pt-BR')) {
  $pick = $voices | Where-Object { $_.VoiceInfo.Culture.Name -eq $c } | Select-Object -First 1
  if ($pick) { break }
}
if (-not $pick -and $env:JARVIS_TTS_ANY_VOICE -eq '1' -and $voices.Count -gt 0) { $pick = $voices[0] }
if (-not $pick) { [Console]::Error.WriteLine('NO_PT_VOICE'); exit 3 }
$s.SelectVoice($pick.VoiceInfo.Name)
if ($env:JARVIS_TTS_WAV) { $s.SetOutputToWaveFile($env:JARVIS_TTS_WAV) }
$s.Speak([string]$env:JARVIS_TTS_TEXT)
$s.Dispose()
"""


def _powershell(script: str) -> list[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


class SapiTTS:
    """Windows built-in speech (System.Speech): offline, nothing to install."""

    name = "sapi"

    def __init__(self, runner=subprocess.run, wav_path: str | None = None,
                 any_voice: bool = False):
        self._runner, self._wav, self._any = runner, wav_path, any_voice

    def _call(self, **extra_env):
        env = dict(os.environ, **extra_env)
        if self._wav:
            env["JARVIS_TTS_WAV"] = str(self._wav)
        if self._any:
            env["JARVIS_TTS_ANY_VOICE"] = "1"
        try:
            return self._runner(_powershell(SAPI_SCRIPT), env=env, capture_output=True,
                                timeout=180, check=False)
        except FileNotFoundError as exc:
            raise VoiceUnavailable("PowerShell não encontrado: a voz SAPI só existe no Windows.") from exc

    def voices(self) -> list[tuple[str, str]]:
        """Installed, enabled SAPI voices as (culture, name)."""
        proc = self._call(JARVIS_TTS_LIST="1")
        if proc.returncode:
            raise VoiceUnavailable("SAPI falhou: " + proc.stderr.decode("utf-8", "replace")[-200:])
        lines = proc.stdout.decode("utf-8", "replace").splitlines()
        return [tuple(line.split("|", 1)) for line in lines if "|" in line]

    def speak(self, text: str) -> None:
        proc = self._call(JARVIS_TTS_TEXT=text)
        if proc.returncode == 3:
            raise VoiceUnavailable(
                "Nenhuma voz portuguesa do Windows instalada. Definições > Hora e idioma > "
                "Idioma > adicionar Português (Portugal) com voz, ou usar --tts kokoro.")
        if proc.returncode:
            raise VoiceUnavailable("SAPI falhou: " + proc.stderr.decode("utf-8", "replace")[-200:])


class KokoroTTS:
    """Upstream KokoroTTSBackend; voice pf_dora is Brazilian Portuguese."""

    name = "kokoro"

    def __init__(self, voice_id="pf_dora"):
        self.voice_id = voice_id
        try:
            from openjarvis.speech.kokoro_tts import KokoroTTSBackend
        except ImportError as exc:  # pragma: no cover
            raise VoiceUnavailable("Kokoro não instalado: python jarvis.py setup --voice --kokoro") from exc
        self._backend = KokoroTTSBackend()

    def speak(self, text: str) -> None:
        from openjarvis.speech.voice_io import play_wav
        try:
            result = interruptible(lambda: self._backend.synthesize(
                text, voice_id=self.voice_id, output_format="wav"))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise VoiceUnavailable(f"Kokoro falhou: {exc}") from exc
        if result.audio:
            play_wav(result.audio, sample_rate=result.sample_rate)


class TextOnlyTTS:
    name = "none"

    def speak(self, text: str) -> None:
        pass


def speech_text(text: str) -> str:
    """Strip Markdown so the synthesizer does not read symbols aloud."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>|]+", " ", text)
    return " ".join(text.split())


# --------------------------------------------------------------- brain ----
class OpenJarvisBrain:
    """Upstream SimpleAgent on local Ollama, keeping the session conversation."""

    def __init__(self, model: str, max_tokens: int = 256, temperature: float = 0.2):
        from openjarvis.agents._stubs import AgentContext
        from openjarvis.agents.simple import SimpleAgent
        from openjarvis.core.types import Message, Role
        from openjarvis.engine.ollama import OllamaEngine
        self._Message, self._Role = Message, Role
        self._engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=180)
        self._agent = SimpleAgent(self._engine, model, temperature=temperature,
                                  max_tokens=max_tokens, engine_options={"num_ctx": 4096})
        self._ctx = AgentContext()

    def remember(self, user: str, assistant: str) -> None:
        self._ctx.conversation.add(self._Message(role=self._Role.USER, content=user))
        self._ctx.conversation.add(self._Message(role=self._Role.ASSISTANT, content=assistant))

    def reply(self, text: str) -> str:
        """Answer only; the loop records the exchange once it was not cancelled."""
        return self._agent.run(text, context=self._ctx).content or ""

    def close(self) -> None:
        self._engine._client.close()


# ---------------------------------------------------------------- loop ----
class VoiceLoop:
    def __init__(self, *, brain, tts, actions: WindowsActions, stt=None,
                 read_line=input, write=print):
        self.brain, self.tts, self.actions, self.stt = brain, tts, actions, stt
        self.read_line, self.write = read_line, write

    def say(self, text: str) -> None:
        self.write(f"Jarvis: {text}")
        try:
            self.tts.speak(speech_text(text))
        except KeyboardInterrupt:
            self.write("(voz interrompida)")
        except VoiceUnavailable as exc:
            self.write(f"[voz indisponível: {exc}] — a continuar só em texto.")
            self.tts = TextOnlyTTS()

    def hear(self, prompt: str) -> str | None:
        """Typed text, or (Enter on an empty line) one recorded utterance."""
        typed = self.read_line(prompt).strip()
        if typed or self.stt is None:
            return typed
        self.write("A ouvir… (fala agora; Ctrl+C cancela)")
        try:
            heard = self.stt.listen()
        except KeyboardInterrupt:
            self.write("Gravação cancelada.")
            return None
        except VoiceUnavailable as exc:
            self.write(f"[{exc}] — escreve o pedido.")
            return None
        self.write(f"Issa (voz): {heard}" if heard else "Não percebi. Tenta outra vez.")
        return heard or None

    def handle(self, text: str) -> str:
        requested = detect_actions(text)
        if len(requested) > 1:
            reply = "Pede uma acção de cada vez: o Bloco de Notas ou a Calculadora."
            self.brain.remember(text, reply)
            return reply
        if requested:
            def confirm(question: str) -> str | None:
                self.say(question)
                return self.hear("Confirmar (sim/não)> ")
            result = self.actions.run(requested[0], confirm)
            reply = describe(result)
            self.brain.remember(text, reply)   # later turns know the real outcome
            return reply
        reply = interruptible(self.brain.reply, text)
        if _CLAIMS_EFFECT.search(reply):
            reply += " (Nota: nenhuma acção foi executada neste pedido.)"
        self.brain.remember(text, reply)
        return reply

    def turn(self) -> bool:
        """One interaction. Returns False to end the session."""
        try:
            text = self.hear("Issa> [escreve, ou Enter para falar] ")
        except (EOFError, KeyboardInterrupt):
            return False
        if not text:
            return True
        if text.strip().lower() in EXIT_WORDS:
            self.say("Até logo, Issa.")
            return False
        try:
            reply = self.handle(text)
        except KeyboardInterrupt:
            self.write("Cancelado.")
            return True
        except Exception as exc:
            name = type(exc).__name__
            if "Connection" in name or "Connect" in str(exc):
                reply = "Não consigo ligar ao modelo local. Confirma que o Ollama está a correr."
            else:
                reply = f"Ocorreu um erro e o pedido não foi concluído ({name})."
        self.say(reply)
        return True

    def run(self) -> None:
        while self.turn():
            pass


def build_tts(choice: str):
    if choice == "none":
        return TextOnlyTTS()
    if choice == "kokoro":
        return KokoroTTS()
    return SapiTTS()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis do Issa — voz local em português")
    parser.add_argument("--model", help="Modelo Ollama local")
    parser.add_argument("--allow-actions", action="store_true",
                        help="Autoriza nesta sessão abrir o Bloco de Notas e a Calculadora (cada uma pede confirmação)")
    parser.add_argument("--tts", choices=("sapi", "kokoro", "none"), default="sapi")
    parser.add_argument("--stt-model", default="small",
                        help="Whisper: tiny, base, small (por omissão), medium")
    parser.add_argument("--text-only", action="store_true", help="Sem microfone (só teclado)")
    args = parser.parse_args(argv)

    config = runtime.prepare_config()
    model = args.model or config["intelligence"]["default_model"]
    if any(x in model.lower() for x in ("cloud", "://")):
        print("ERROR: escolhe um modelo local, não cloud.", file=sys.stderr)
        return 1
    actions = WindowsActions(authorized=args.allow_actions, audit_dir=runtime.STATE / "logs")
    print("Jarvis do Issa — voz local. Ctrl+C cancela o passo actual; 'sair' termina.")
    print("Acções Windows:", "AUTORIZADAS (com confirmação)" if args.allow_actions else "desactivadas")
    stt = None
    if not args.text_only:
        try:
            stt = WhisperSTT(model=args.stt_model)
            print(f"A carregar Whisper '{args.stt_model}' (primeira vez descarrega o modelo)…")
            stt.load()
        except VoiceUnavailable as exc:
            print(f"[{exc}] — modo texto.")
            stt = None
    try:
        tts = build_tts(args.tts)
    except VoiceUnavailable as exc:
        print(f"[{exc}] — respostas só em texto.")
        tts = TextOnlyTTS()
    brain = OpenJarvisBrain(model,
                            max_tokens=int(config["intelligence"].get("max_tokens", 256)),
                            temperature=float(config["intelligence"].get("temperature", 0.2)))
    try:
        VoiceLoop(brain=brain, tts=tts, actions=actions, stt=stt).run()
    finally:
        brain.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
