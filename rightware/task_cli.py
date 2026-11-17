"""TE-03: explicit opt-in public IANA research task through RIGHTWARE AgentSession.

No arbitrary host, no file/shell/Windows tools and no natural-language grants.
Only the host-owned IANA reserved/example-domains contract and public GET browser are permitted.
This CLI is an experimental technical demonstration, not an accepted JARVIS UI.
"""
from __future__ import annotations

import argparse
import datetime as dt
import dataclasses
import json
from pathlib import Path
import sys
import time

from rightware import runtime
from rightware.task_entry import TaskEntry
from rightware.text_facade import TextFacade

DEFAULT_INSTRUCTION = (
    "Consulta as páginas de domínios reservados e domínios de exemplo da IANA; explica em português "
    "o propósito de cada página e indica as duas fontes. Não declares a tarefa concluída "
    "se não conseguires ler ambos os documentos."
)
HOST = "www.iana.org"
START = "https://www.iana.org/domains/reserved"
PRESET = "iana-reserved-example-public-readonly"
WARMUP_PROMPT = "Responde apenas: ok"


def warm_up(engine, model: str, timer=time.perf_counter) -> dict:
    """TE-05: ONE controlled local generation WITHOUT tools, before the task, so the model load
    is not paid inside the task deadline. Its cost is never hidden: it is returned (numbers only)
    and counted in the total wall time. No page, tool, contract or user text is involved."""
    from openjarvis.core.types import Message, Role
    from rightware.agent.diagnostics import generation_metric

    started, result, state = timer(), None, "OK"
    try:
        result = engine.generate([Message(role=Role.USER, content=WARMUP_PROMPT)], model=model,
                                 temperature=0.0, max_tokens=8)
    except Exception as exc:              # reported, never fatal: the task path decides
        state = f"FAILED_{type(exc).__name__}"[:60]
    metric = generation_metric(0, "model", result, timer() - started)
    return {"state": state, **dataclasses.asdict(metric)}


def main(argv=None, *, engine_factory=None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS TE-03 — tarefa IANA apenas leitura")
    parser.add_argument("instruction", nargs="?", default=DEFAULT_INSTRUCTION)
    parser.add_argument("--allow-public-read", action="store_true",
                        help="autoriza esta tarefa de leitura apenas em www.iana.org")
    parser.add_argument("--model", default=None, help="modelo Ollama local instalado")
    parser.add_argument("--json", action="store_true", help="emitir resultado estruturado sem transcrição")
    parser.add_argument("--warmup", action="store_true",
                        help="aquecer o modelo local (sem ferramentas) antes da tarefa; custo reportado à parte")
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
        t0 = time.perf_counter()
        warmup = warm_up(engine, model) if args.warmup else None
        t1 = time.perf_counter()
        result = bridge.run_trusted_public_iana_task(session_id, args.instruction)
        t2 = time.perf_counter()
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
            "halt_reason_code": result.halt_reason_code,
            "receipt_events": [
                {"sequence": seq, "tool": tool, "status": status}
                for seq, tool, status in result.receipt_events
            ],
            "receipt_reason_codes": [
                {"sequence": seq, "code": code} for seq, code in result.receipt_reason_codes
            ],
            "continuations": result.continuations,
            "generations": [dataclasses.asdict(m) for m in result.generation_metrics],
            "generation_totals": _totals(result.generation_metrics),
            "timing": {
                "warmup": warmup,
                "warmup_wall_seconds": round(t1 - t0, 3),
                "task_wall_seconds": round(t2 - t1, 3),
                "total_wall_seconds": round(t2 - t0, 3),
                "note": ("task deadline is checked between steps only; the engine timeout is a client "
                         "(httpx) timeout and server-side work may continue after it"),
            },
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


def _totals(metrics) -> dict:
    from rightware.agent.diagnostics import summarize
    return summarize(metrics)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"TE-03 não concluída ({type(exc).__name__}).", file=sys.stderr)
        raise SystemExit(1)
