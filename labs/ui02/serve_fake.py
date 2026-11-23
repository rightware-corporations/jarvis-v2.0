"""UI-02 CI harness ONLY: the real GUI server (policy, auth, bridge, original OpenJarvis app, HUD build) with a FAKE
text model and a FAKE mission executor, so the browser E2E can run in CI without model weights. Every fake reply is
labelled [FAKE-CI]; never use this for evidence about the model. Usage:
  PYTHONPATH=. .runtime/gui/venv/bin/python labs/ui02/serve_fake.py --port 8010"""
import argparse
import time

from rightware import control_plane as CP
from rightware.gui import server as S


class FakeText:
    def __init__(self):
        import threading
        self.stop = threading.Event()

    def reply(self, text, history):
        if text.startswith("LONGO"):
            self.stop.clear()
            if self.stop.wait(30):                         # aborted like the real engine socket
                raise ConnectionError("[FAKE-CI] aborted")
        return f"[FAKE-CI] eco: {text} (histórico={len(history)})"

    def abort(self):
        self.stop.set()
        return True

    def close(self):
        pass


class FakeMission:
    capability = "missao-ci-fake"
    description = "[FAKE-CI] missão de teste da interface (sem modelo, sem efeitos)."

    def run(self, cancelled, on_start=None):
        if on_start:
            on_start()
        for _ in range(40):
            if cancelled.is_set():
                return CP.TaskOutcome(CP.State.TAREFA_CANCELADA, self.capability, "CANCELLED", False, None, (), 0, (),
                                      "CANCELLED", "NONE", "", 1.0)
            time.sleep(0.1)
        return CP.TaskOutcome(CP.State.RESULTADO_VERIFICADO, self.capability, "FAKE_CI_VERIFIED", True, None,
                              (("FAKE_OBJECTIVE", "VERIFIED", 1),), 1, ((1, "fake_tool", "OK"),), "NONE", "NONE",
                              "[FAKE-CI] comentário do modelo", 4.0)

    def cancel(self):
        return True


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=8010)
    args = a.parse_args()
    app, bridge = S.build_app(port=args.port, models=["qwen3.5:2b"], goose=FakeMission(), adapter_factory=lambda m: FakeText())
    bridge.installed_models = lambda: {"qwen3.5:2b"}          # [FAKE-CI] engine probe: CI has no Ollama
    print("FAKE-CI GUI:", app.session_url, flush=True)
    S.serve(app, args.port)
