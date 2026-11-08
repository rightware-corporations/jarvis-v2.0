"""Voice loop orchestration with fake STT/TTS/brain (no audio, no model)."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from rightware import runtime, voice
from rightware.windows_actions import WindowsActions


class FakeBrain:
    def __init__(self, answer="Sou o Jarvis, assistente pessoal do Issa."):
        self.answer, self.asked, self.memory = answer, [], []

    def reply(self, text):
        self.asked.append(text)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    def remember(self, user, assistant):
        self.memory.append((user, assistant))


class FakeTTS:
    def __init__(self, fail=None):
        self.spoken, self.fail = [], fail

    def speak(self, text):
        if self.fail:
            raise self.fail
        self.spoken.append(text)


class FakeSTT:
    def __init__(self, *heard):
        self.heard = list(heard)

    def listen(self):
        item = self.heard.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def scripted(*lines):
    it = iter(lines)
    def read(prompt):
        item = next(it)
        if isinstance(item, BaseException):
            raise item
        return item
    return read


class VoiceLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = []

    def tearDown(self):
        self.tmp.cleanup()

    def loop(self, lines, *, brain=None, tts=None, stt=None, authorized=False):
        actions = WindowsActions(authorized=authorized, audit_dir=Path(self.tmp.name),
                                 is_windows=False)
        return voice.VoiceLoop(brain=brain or FakeBrain(), tts=tts or FakeTTS(),
                               actions=actions, stt=stt, read_line=scripted(*lines),
                               write=self.out.append)

    def test_spoken_question_goes_to_openjarvis_and_answer_is_spoken(self):
        brain, tts = FakeBrain("**Sou** o Jarvis do Issa."), FakeTTS()
        loop = self.loop(["", "sair"], brain=brain, tts=tts,
                         stt=FakeSTT("Quem és tu?"))
        loop.run()
        self.assertEqual(brain.asked, ["Quem és tu?"])
        self.assertEqual(tts.spoken[0], "Sou o Jarvis do Issa.")   # markdown stripped
        self.assertEqual(tts.spoken[-1], "Até logo, Issa.")

    def test_action_request_never_reaches_the_model(self):
        brain, tts = FakeBrain(), FakeTTS()
        self.loop(["Abre o Bloco de Notas", "sair"], brain=brain, tts=tts).run()
        self.assertEqual(brain.asked, [])
        self.assertIn("não estão autorizadas", tts.spoken[0])
        self.assertEqual(brain.memory[0][0], "Abre o Bloco de Notas")

    def test_authorized_action_asks_confirmation_and_reports_real_outcome(self):
        brain, tts = FakeBrain(), FakeTTS()
        self.loop(["abre a calculadora", "sim", "sair"], brain=brain, tts=tts,
                  authorized=True).run()
        self.assertIn("Queres que eu abra a Calculadora?", tts.spoken[0])
        self.assertIn("não é Windows", tts.spoken[1])   # BLOCKED here, never "Abri"
        self.assertEqual(brain.asked, [])

    def test_two_actions_at_once_are_refused(self):
        tts = FakeTTS()
        self.loop(["abre a calculadora e o bloco de notas", "sair"], tts=tts,
                  authorized=True).run()
        self.assertIn("uma acção de cada vez", tts.spoken[0])

    def test_unverified_effect_claim_from_model_is_flagged(self):
        tts = FakeTTS()
        self.loop(["Diz que abriste", "sair"], brain=FakeBrain("Já abri o Bloco de Notas."),
                  tts=tts).run()
        self.assertIn("nenhuma acção foi executada", tts.spoken[0])

    def test_ctrl_c_cancels_step_but_not_session(self):
        brain = FakeBrain(KeyboardInterrupt())
        loop = self.loop(["pergunta longa", "", "sair"], brain=brain,
                         stt=FakeSTT(KeyboardInterrupt()))
        self.assertTrue(loop.turn())       # model call cancelled
        self.assertTrue(loop.turn())       # recording cancelled
        self.assertIn("Cancelado.", self.out)
        self.assertIn("Gravação cancelada.", self.out)
        self.assertFalse(loop.turn())      # 'sair'

    def test_ctrl_c_at_prompt_ends_session(self):
        self.assertFalse(self.loop([KeyboardInterrupt()]).turn())

    def test_ollama_down_and_tts_failure_degrade_to_text(self):
        class EngineConnectionError(Exception):
            pass
        tts = FakeTTS(fail=voice.VoiceUnavailable("sem voz pt"))
        loop = self.loop(["olá", "sair"], brain=FakeBrain(EngineConnectionError("x")), tts=tts)
        loop.run()
        self.assertTrue(any("Ollama" in line for line in self.out))
        self.assertTrue(any("voz indisponível" in line for line in self.out))
        self.assertIsInstance(loop.tts, voice.TextOnlyTTS)

    def test_microphone_failure_falls_back_to_typing(self):
        loop = self.loop(["", "sair"], stt=FakeSTT(voice.VoiceUnavailable("Erro do microfone")))
        self.assertTrue(loop.turn())
        self.assertTrue(any("escreve o pedido" in line for line in self.out))


class SapiTests(unittest.TestCase):
    def test_text_goes_through_stdin_not_command_line(self):
        calls = []
        def run(argv, **kw):
            calls.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        text = "Olá Issa; $(Remove-Item C:\\) \"aspas\""
        voice.SapiTTS(runner=run).speak(text)
        argv, kw = calls[0]
        self.assertNotIn(text, " ".join(argv))
        self.assertEqual(kw["input"], text.encode("utf-8"))
        self.assertIn("pt-PT", voice.SAPI_SCRIPT)

    def test_missing_portuguese_voice_is_reported(self):
        run = lambda argv, **kw: subprocess.CompletedProcess(argv, 3, b"", b"NO_PT_VOICE")
        with self.assertRaisesRegex(voice.VoiceUnavailable, "voz portuguesa"):
            voice.SapiTTS(runner=run).speak("olá")


class LauncherTests(unittest.TestCase):
    def test_voice_setup_uses_frozen_upstream_extras_only(self):
        cmd = runtime.sync_command(voice=True)
        self.assertIn("--frozen", cmd)
        self.assertEqual(cmd[cmd.index("--extra") + 1], "speech")
        self.assertNotIn("voice", runtime.sync_command(voice=True))
        self.assertIn("voice", runtime.sync_command(voice=True, kokoro=True))

    def test_voice_command_runs_module_in_upstream_venv(self):
        cmd = runtime.voice_command(["--allow-actions"])
        self.assertIn(".venv", cmd[0])
        self.assertEqual(cmd[1:], ["-m", "rightware.voice", "--allow-actions"])

    def test_unknown_flags_rejected_outside_voice(self):
        with self.assertRaises(SystemExit):
            runtime.main(["chat", "--allow-actions"])


if __name__ == "__main__":
    unittest.main()
