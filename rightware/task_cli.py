"""TE-03: explicit opt-in public IANA research task through RIGHTWARE AgentSession.

No arbitrary host, no file/shell/Windows tools and no natural-language grants.
Only the host-owned IANA Reserved Domains/9112 contract and public GET browser are permitted.
This CLI is an experimental technical demonstration, not an accepted JARVIS UI.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

from rightware import runtime
from rightware.task_entry import TaskEntry
from rightware.text_facade import TextFacade

DEFAULT_INSTRUCTION = (
    "Consulta directamente os IANA Reserved Domains e IANA Example Domains no IANA Editor, explica em português "
    "o tema de cada um e indica as duas fontes. Não declares a tarefa concluída "
    "se não conseguires ler ambos os documentos."
)
HOST = "www.iana.org"
START = "https://www.iana.org/domains/reserved"
PRESET = "iana-reserved-example-public-readonly"


def main(argv=None, *, engine_factory=None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS TE-03 — tarefa IANA apenas leitura")
    parser.add_argument("instruction", nargs="?", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--allow-public-read", action="store_true",
                        help="autoriza esta tarefa de leitura apenas em www.iana.org")
    parser.add_argument("--model", default=None, help="modelo Ollama local instalado")
    parser.add_argument("--json", action="store_true", help="emitir resultado estruturado sem transcrição")
    args = parser.parse_args(argv)
    if not args.allow_public_read:
        print("TE-03 indisponível: indicação explícita --allow-public-read necessária.", file=sys.stderr)
        return 2

    cfg = runtime.prepare_config()
    model = args.model or cfg["intelligence"]["default_model"]
    runtime.chat_command(model)  # Existing local-only guard: rejects cloud URLs

    # The vendor imports remain lazy; no tool-bearing path is initialized by chat.
    if engine_factory is None:
        from openjarvis.engine.ollama import OllamaEngine
        engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=120)
    else:
        engine = engine_factory()

    facade = TextFacade(owner_id="local")
    session_id = facade.open_session()
    try:
        if session_factory is None:
            from rightware.agent.session import AgentSession, Budgets
            logs = runtime.STATE / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

            def make_session():
                return AgentSession(
                    engine, model, allow={"browse"}, confirm=lambda _: None,
                    actions=None, sites=(HOST,), start_url=START,
                    task_preset=PRESET, receipts=True, completion_gate=True,
                    budgets=Budgets(max_calls=10, deadline_seconds=115),
                    max_turns=10, max_tokens=768, temperature=0.2,
                    audit_path=logs / f"te03-iana-{stamp}.jsonl",
                )
        else:
            make_session = session_factory

        bridge = TaskEntry(facade, public_session_factory=make_session)
        result = bridge.run_trusted_public_iana_task(session_id, args.instruction)
        record = {
            "task": "TE-03_IANA_PUBLIC_READ_ONLY",
            "request_id": result.request_id,
            "route": result.route,
            "operational_state": result.operational_state,
            "objectives": [
                {"id": oid, "state": state, "receipt_sequence": seq}
                for oid, state, seq in result.objective_states
            ],
            "receipts_count": result.receipts_count,
            "factual_verified": False,
            "completion_verified": result.completion_verified,
            "limitations": result.limitations,
        }
        if args.json:
            print(json.dumps(record, ensure_ascii=False, indent=2))
        else:
            print(f"Estado operacional: {result.operational_state}")
            for item in record["objectives"]:
                print(f"- {item['id']}: {item['state']} (recibo {item['receipt_sequence']})")
            print(f"Recibos: {result.receipts_count}. Factos verificados: NÃO.")
            if result.model_commentary_unverified:
                print("Resposta do modelo (NÃO VERIFICADA factual ou editorialmente):")
                print(result.model_commentary_unverified)
        # UNKNOWN_IDENTITY is not a verified-complete task, even if two pages load.
        return 0 if result.completion_verified else 3
    finally:
        facade.close()
        close = getattr(engine, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"TE-03 não concluída ({type(exc).__name__}).", file=sys.stderr)
        raise SystemExit(1)
