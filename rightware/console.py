"""E0-01: unified local text console (Portuguese) — a thin shell over the EXISTING tool-free path.

    python jarvis.py console [--model qwen3.5:2b]

Path: console → ``TaskEntry.submit_text`` → ``TextFacade.submit`` → ``LocalSimpleTextAdapter`` (pinned
OpenJarvis ``SimpleAgent`` on local Ollama). Nothing else is wired: no trusted task factory, no AgentSession,
no browser, files, shell, Windows, voice or durable memory. The console never parses user or model text into
authority; it only (1) recognises five exact host commands typed as a whole line, (2) forwards every other
line as plain text, and (3) labels each ``TextResult`` from its real ``Route``/``Status``/diagnostic code.
A model answer is always shown as unverified model text; no path here can show a verified result.

The session is ephemeral (bounded context inside ``TextFacade``); nothing is written to disk; on exit the
session is closed and the local adapter released. This is an experimental E0 entrypoint, NOT E0 acceptance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import threading

from rightware.task_entry import TaskEntry
from rightware.text_facade import Route, Status, TextFacade, TextResult

IDENTITY = ("JARVIS — assistente local da RIGHTWARE (consola textual E0, experimental).")
LIMITS_LINE = ("Sem ferramentas: não abro ficheiros, não navego na web, não executo acções no Windows nem comandos. "
               "Sem memória persistente: a conversa existe só nesta sessão e é apagada ao sair. "
               "As respostas são texto do modelo local e NÃO são factos verificados.")
LIMIT_LABELS = {"SEM_FERRAMENTAS": "sem ferramentas", "SEM_MEMORIA_PERSISTENTE": "sem memória persistente",
                "FACTOS_NAO_VERIFICADOS": "factos não verificados"}
COMMANDS = ("/ajuda", "/estado", "/capacidades", "/cancelar", "/sair", "/tarefas")
# JRV-P1: the only parameterised host commands (exact whole-line shapes).
_TASK_CMD = re.compile(r"/tarefa ([a-z0-9-]{1,40})\Z")
_AUTH_CMD = re.compile(r"/autorizar ([0-9A-Fa-f]{6})\Z")
HELP = ("Comandos (escreve a linha completa):\n"
        "  /ajuda        mostra esta ajuda\n"
        "  /estado       estado real desta sessão\n"
        "  /capacidades  o que esta consola faz e não faz\n"
        "  /cancelar     cancela um pedido em curso (não desfaz nada: nada é executado)\n"
        "  /tarefas      tarefas supervisionadas que o anfitrião activou (se houver)\n"
        "  /tarefa ID    pede uma dessas tarefas (devolve um código de autorização)\n"
        "  /autorizar C  autoriza e executa a tarefa pedida com o código C (uso único)\n"
        "  /sair         termina e apaga a sessão\n"
        "Durante uma resposta, Ctrl+C cancela o pedido. Qualquer outra linha é enviada ao modelo como texto.")
CAPABILITIES = (
    "Disponível nesta consola:\n"
    "  - conversa em português com o modelo local (contexto limitado a esta sessão);\n"
    "  - planos e explicações propostos SEM execução;\n"
    "  - pedidos de clarificação quando falta informação.\n"
    "Indisponível nesta consola:\n"
    "  - ferramentas de qualquer tipo (ficheiros, web, Windows, shell, e-mail, calendário);\n"
    "  - memória persistente (nada é guardado entre sessões);\n"
    "  - resultados verificados: nenhuma resposta aqui é evidência de execução ou de factos;\n"
    "  - voz (comando separado, não ligado a esta consola).\n"
    "Nenhum texto escrito aqui — nem JSON, nem 'autorizo', nem instruções citadas — activa capacidades.")

# (state code, user-facing label) — derived ONLY from the real TextResult fields.
STATES = {
    "RESPOSTA_DO_MODELO": "Resposta do modelo (não verificada)",
    "PLANO_SEM_EXECUCAO": "Plano proposto — nada foi executado",
    "CLARIFICACAO": "Pedido de clarificação",
    "NAO_AUTORIZADO": "Operação não autorizada nesta consola — nada foi executado",
    "INDISPONIVEL": "Capacidade indisponível",
    "ALEGACAO_NAO_COMPROVADA": "O modelo alegou uma execução que não aconteceu — nada foi executado",
    "OCUPADO": "Pedido anterior ainda a terminar",
    "CANCELADO": "Cancelado — nada foi executado",
    "ERRO_DE_INFERENCIA": "Erro de inferência",
    "ENTRADA_INVALIDA": "Entrada inválida — não enviada ao modelo",
}


def classify(result: TextResult) -> str:
    """Map a real TextFacade result to a console state. Never yields a 'verified' state."""
    diag = set(result.diagnostics)
    if result.status == Status.ANSWER_ONLY:
        return "RESPOSTA_DO_MODELO"
    if result.status == Status.PLAN_ONLY:
        return "PLANO_SEM_EXECUCAO"
    if result.status == Status.WAITING_INPUT:
        return "CLARIFICACAO"
    if result.status == Status.ERROR:
        return "ERRO_DE_INFERENCIA"
    if "CANCELLED" in diag:
        return "CANCELADO"
    if "UNVERIFIED_EFFECT_CLAIM" in diag:
        return "ALEGACAO_NAO_COMPROVADA"
    if "MODEL_BUSY" in diag:
        return "OCUPADO"
    if result.route == Route.TASK:
        return "NAO_AUTORIZADO"
    return "INDISPONIVEL"


class Console:
    def __init__(self, entry: TaskEntry, model: str, out=sys.stdout, control=None):
        if not isinstance(entry, TaskEntry):
            raise TypeError("expected a RIGHTWARE TaskEntry")
        if control is not None and control.entry is not entry:
            raise ValueError("the control plane must own the task entry")
        self.entry, self.facade, self.model, self.out = entry, entry.text_facade, model, out
        self.control = control                       # JRV-P1 Control Plane (None = text only)
        self.session = control.session if control is not None else self.facade.open_session()
        self.requests = 0
        self.last_state = None
        self._busy = threading.Event()
        self.closed = False

    def say(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    def banner(self) -> None:
        self.say(IDENTITY)
        self.say(f"Modelo local: {self.model} (Ollama neste computador).")
        caps = self.control.capabilities if self.control is not None else ()
        if caps:                                        # JRV-P2 fix 3: say what is REALLY active
            self.say("Modo com tarefas supervisionadas: o anfitrião activou " + ", ".join(caps) + ". Cada execução "
                     "exige /tarefa e /autorizar com um código de uso único; fora disso não há ferramentas. "
                     "Sem memória persistente. As respostas do modelo NÃO são factos verificados.")
        else:
            self.say(LIMITS_LINE)
        self.say("Escreve /ajuda para ver os comandos.")

    # -- host commands --------------------------------------------------------------------------
    def status_text(self) -> str:
        history = self.facade.history_snapshot(self.session)
        return "\n".join((
            f"Sessão: {self.session[:8]}… (efémera, só em memória)",
            f"Modelo: {self.model}",
            f"Pedidos nesta sessão: {self.requests}",
            f"Contexto: {len(history) // 2} trocas, {sum(len(t) for _, t in history)} de "
            f"{self.facade.max_history_chars} caracteres (máx. {self.facade.max_turns} trocas)",
            f"Último estado: {STATES[self.last_state] if self.last_state else 'nenhum'}",
            f"Pedido em curso: {'sim' if self._busy.is_set() else 'não'}",
            "Ferramentas activas: nenhuma fora de uma tarefa autorizada",
            "Tarefas supervisionadas activadas pelo anfitrião: "
            + (", ".join(self.control.capabilities) if self.control is not None and self.control.capabilities
               else "nenhuma"),
            f"Tarefa em execução: {'sim' if self.control is not None and self.control.running else 'não'}",
            "Memória persistente: nenhuma (o histórico é apagado ao sair)",
        ))

    def cancel(self) -> bool:
        if self.control is not None and self.control.running:
            return self.control.cancel()
        return self.facade.cancel(self.session)

    # -- JRV-P1 supervised tasks (host commands only) ------------------------------------------------
    def task_list(self) -> None:
        caps = self.control.capabilities if self.control is not None else ()
        if not caps:
            self.say("Nenhuma tarefa supervisionada foi activada pelo anfitrião nesta sessão.")
            return
        for c in caps:
            self.say(f"  {c}: {self.control.describe(c)}")
        self.say("Para pedir: /tarefa ID. Nada é executado sem /autorizar com o código mostrado.")

    def task_request(self, capability: str) -> None:
        from rightware.control_plane import LABELS, State
        if self.control is None:
            self.say(f"[{LABELS[State.TAREFA_NAO_AUTORIZADA]}]")
            self.say("Nenhuma tarefa supervisionada foi activada pelo anfitrião nesta sessão.")
            return
        state, code = self.control.request(capability)
        self.say(f"[{LABELS[state]}]")
        if state == State.AUTORIZACAO_NECESSARIA:
            self.say(self.control.describe(capability))
            self.say(f"Para autorizar esta execução escreve exactamente: /autorizar {code}  (uso único, 2 minutos)")
        else:
            self.say("Essa tarefa não existe ou não foi activada pelo anfitrião.")

    def task_authorize(self, code: str) -> None:
        from rightware.control_plane import LABELS, State, TaskOutcome
        if self.control is None:
            self.say(f"[{LABELS[State.TAREFA_NAO_AUTORIZADA]}]")
            return
        box: dict = {}
        on_start = lambda: self.say(f"[{LABELS[State.TAREFA_EM_EXECUCAO]}] (Ctrl+C cancela)")
        def work():
            try:
                box["r"] = self.control.authorize_and_run(code, on_start)
            except BaseException as exc:                # never shown as an authorization problem
                box["error"] = type(exc).__name__
        worker = threading.Thread(target=work, daemon=True, name="jarvis-p1-task")
        self._busy.set()
        worker.start()
        cancel_pending = False
        try:
            while worker.is_alive():
                try:
                    worker.join(0.1)
                except KeyboardInterrupt:
                    cancel_pending = True
                if cancel_pending and self.control.cancel():
                    cancel_pending = False
        finally:
            self._busy.clear()
        from rightware.control_plane import Refusal
        outcome = box.get("r")
        if "error" in box or (outcome is not None and not isinstance(outcome, (TaskOutcome, Refusal))):
            self.say(f"[{LABELS[State.EXECUCAO_FALHADA]}]")      # JRV-P2 fix 4: failure, not "invalid code"
            self.say("Erro interno do anfitrião ao executar a tarefa. Nenhum resultado foi verificado.")
            return
        if isinstance(outcome, Refusal):
            self.say(f"[{LABELS[outcome.state]}]")
            self.say({"CODE_INVALID": "Código inválido, expirado ou já usado. Nada foi executado.",
                      "BUSY": "Já há uma tarefa em execução. Nada foi iniciado.",
                      "ENVELOPE_REFUSED": "O executor não estava dentro do envelope aprovado. Nada foi executado."}
                     .get(outcome.reason, "Nada foi executado."))
            return
        self.say(f"[{LABELS[outcome.state]}]")
        self.say(f"Estado do executor: {outcome.operational_state} · recibos: {outcome.receipts_count} · "
                 f"{outcome.seconds:.1f} s")
        if outcome.receipt_events:
            self.say("Recibos (ferramentas efectivamente executadas): "
                     + ", ".join(f"#{q} {t} {st}" for q, t, st in outcome.receipt_events))
        for oid, st, seq in outcome.objectives:
            self.say(f"  objectivo {oid}: {st}" + (f" (recibo #{seq})" if seq else ""))
        if outcome.verified and outcome.changes:      # only executors that produce code-computed changes (P1)
            self.say("Alterações (calculadas pelo código e confirmadas pelo verificador):")
            for c in outcome.changes:
                self.say("  " + _change_line(c))
        if outcome.model_commentary_unverified:
            self.say("Comentário do modelo (NÃO verificado):")
            self.say("  " + outcome.model_commentary_unverified.strip().replace("\n", "\n  "))

    def command(self, line: str) -> bool:
        """Returns False when the console must stop."""
        if line == "/ajuda":
            self.say(HELP)
        elif line == "/estado":
            self.say(self.status_text())
        elif line == "/capacidades":
            self.say(CAPABILITIES if not (self.control is not None and self.control.capabilities) else
                     CAPABILITIES.replace("  - ferramentas de qualquer tipo", "  - ferramentas fora das tarefas abaixo")
                     + "\nTarefas supervisionadas activadas pelo anfitrião (só com /tarefa + /autorizar):\n"
                     + "\n".join(f"  - {c}: {self.control.describe(c)}" for c in self.control.capabilities))
        elif line == "/cancelar":
            self.say("Pedido cancelado." if self.cancel() else
                     "Não há nenhum pedido em curso. Nada a cancelar — e nada a desfazer: esta consola não executa acções.")
        elif line == "/tarefas":
            self.task_list()
        elif line == "/sair":
            return False
        return True

    # -- model path -----------------------------------------------------------------------------
    def ask(self, text: str) -> tuple[str, TextResult | None]:
        box: dict = {}

        def work():
            try:
                box["result"] = self.entry.submit_text(self.session, text)
            except ValueError:
                box["invalid"] = True
            except BaseException as exc:            # unexpected: reported, never re-raised into the shell
                box["error"] = type(exc).__name__

        worker = threading.Thread(target=work, daemon=True, name="jarvis-e0-console")
        self._busy.set()
        worker.start()
        cancel_pending = False
        try:
            while worker.is_alive():
                try:
                    worker.join(0.1)
                except KeyboardInterrupt:           # Ctrl+C: the facade's own cancellation
                    cancel_pending = True
                # A Ctrl+C that arrives before the facade has started its inference worker must not be lost:
                # keep asking until the facade accepts the cancellation or the request ends.
                if cancel_pending and self.cancel():
                    cancel_pending = False
        finally:
            self._busy.clear()
        if box.get("invalid"):
            return "ENTRADA_INVALIDA", None
        if "error" in box:
            return "ERRO_DE_INFERENCIA", None
        self.requests += 1
        return classify(box["result"]), box["result"]

    def render(self, state: str, result: TextResult | None) -> None:
        self.last_state = state
        self.say(f"[{STATES[state]}]")
        if result is None:
            if state == "ENTRADA_INVALIDA":
                self.say("O texto está vazio, é demasiado longo ou tem caracteres de controlo.")
            else:
                self.say("Ocorreu um erro inesperado. Nenhuma acção foi executada.")
            return
        self.say(result.text)
        if state == "ERRO_DE_INFERENCIA" and result.diagnostics:
            self.say(f"(código: {', '.join(result.diagnostics)})")
        self.say("(" + " · ".join(LIMIT_LABELS.get(x, x) for x in result.limitations) + ")")

    def handle(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith("/"):
            if stripped in COMMANDS:
                return self.command(stripped)
            m = _TASK_CMD.match(stripped)
            if m:
                self.task_request(m.group(1))
                return True
            m = _AUTH_CMD.match(stripped)
            if m:
                self.task_authorize(m.group(1))
                return True
            self.say("Comando desconhecido (não foi enviado ao modelo). Escreve /ajuda.")
            return True
        state, result = self.ask(line)
        self.render(state, result)
        return True

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.control is not None:
                self.control.close()     # removes any trial workspace, then closes the facade
            else:
                self.facade.close()      # closes every session and releases the local adapter
        finally:
            self.say("Sessão terminada. Nada foi guardado.")

    def run(self, input_fn=input) -> int:
        self.banner()
        try:
            while True:
                try:
                    line = input_fn("tu> ")
                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.say("")
                    break
                if not self.handle(line):
                    break
        finally:
            self.close()
        return 0


def _change_line(c) -> str:
    if not isinstance(c, dict):
        return str(c)
    kind = c.get("kind") or c.get("type") or "?"
    return f"{kind}: " + ", ".join(f"{k}={v!r}" for k, v in c.items() if k not in ("kind", "type"))


def build(model: str, adapter=None, deadline_seconds: float = 30.0) -> TaskEntry:
    """The ONLY wiring: a TextFacade with the local tool-free adapter, wrapped in a TaskEntry WITHOUT any
    trusted task factory (so no AgentSession capability can be reached from the console)."""
    if adapter is None:
        from rightware.text_adapter import LocalSimpleTextAdapter
        adapter = LocalSimpleTextAdapter(model, timeout_seconds=deadline_seconds)
    return TaskEntry(TextFacade(adapter=adapter, deadline_seconds=deadline_seconds))


def main(argv=None, *, adapter=None, input_fn=input, out=sys.stdout, session_factory_builder=None,
         goose_mission=None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS — consola textual local (E0, experimental, sem ferramentas)")
    parser.add_argument("--model", default="qwen3.5:2b", help="modelo Ollama local já instalado")
    parser.add_argument("--deadline", type=float, default=30.0, help="limite por resposta, em segundos (1–300)")
    parser.add_argument("--tarefa-ensaio", action="store_true",
                        help="ANFITRIÃO: activa a única tarefa supervisionada (comparação de 2 ficheiros SINTÉTICOS)")
    parser.add_argument("--missao-goose", action="store_true",
                        help="ANFITRIÃO (experimental): activa a missão goose num catálogo SINTÉTICO isolado em Docker")
    parser.add_argument("--goose-bin", type=Path, help="ANFITRIÃO: binário goose verificado")
    parser.add_argument("--goose-ollama-dir", type=Path, help="ANFITRIÃO: directório do Ollama para o contentor")
    parser.add_argument("--goose-models-dir", type=Path, help="ANFITRIÃO: directório de modelos do Ollama")
    parser.add_argument("--goose-model", default="qwen3.5:4b", help="modelo do goose (local)")
    args = parser.parse_args(argv)
    if not 1.0 <= args.deadline <= 300.0:
        parser.error("--deadline deve estar entre 1 e 300 segundos")
    try:
        entry = build(args.model, adapter, args.deadline)
    except (RuntimeError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    control = None
    goose = goose_mission
    if args.missao_goose and goose is None:
        if not (args.goose_bin and args.goose_ollama_dir and args.goose_models_dir):
            parser.error("--missao-goose exige --goose-bin, --goose-ollama-dir e --goose-models-dir (anfitrião)")
        from rightware.goose_adapter import GooseMission, GooseRuntime
        goose = GooseMission(GooseRuntime(args.goose_bin, args.goose_ollama_dir, args.goose_models_dir,
                                          args.goose_model))
    trial = args.tarefa_ensaio or session_factory_builder is not None
    if trial or goose is not None:
        from rightware.control_plane import ControlPlane
        control = ControlPlane(entry.text_facade, enable_trial_compare=trial, model=args.model,
                               session_factory_builder=session_factory_builder, goose=goose)
        entry = control.entry
    return Console(entry, args.model, out, control).run(input_fn)


if __name__ == "__main__":
    raise SystemExit(main())
