"""`python jarvis.py agent "instrução"` — one instruction through the product agent.

Capabilities are off unless enabled for this session:
  --allow-web      read public web pages (read-only)
  --allow-actions  ask for allow-listed Windows actions (each confirmed by you)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from rightware import runtime


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="JARVIS agent (uma instrução)")
    ap.add_argument("instruction")
    ap.add_argument("--model", default=None)
    ap.add_argument("--allow-web", action="store_true")
    ap.add_argument("--allow-actions", action="store_true")
    ap.add_argument("--json", action="store_true", help="imprime também o resultado verificado em JSON")
    args = ap.parse_args(argv)

    config = runtime.prepare_config()
    model = args.model or config["intelligence"]["default_model"]
    runtime.chat_command(model)              # rejects cloud/remote model names
    from openjarvis.engine.ollama import OllamaEngine
    from rightware.agent.session import AgentSession, reply_json
    from rightware.windows_actions import WindowsActions

    allow = ({"web"} if args.allow_web else set()) | ({"actions"} if args.allow_actions else set())
    logs = runtime.STATE / "logs"

    def confirm(question: str) -> str | None:     # the human answers, never the model
        print(f"Jarvis: {question}")
        try:
            return input("Confirmar (sim/não)> ")
        except (EOFError, KeyboardInterrupt):
            return None

    engine = OllamaEngine(host="http://127.0.0.1:11434", timeout=300)
    session = AgentSession(engine, model, allow=allow, confirm=confirm,
                           actions=WindowsActions(authorized=args.allow_actions, audit_dir=logs),
                           audit_path=logs / f"agent-{dt.datetime.now(dt.timezone.utc):%Y%m%d}.jsonl")
    reply = session.run(args.instruction)
    print(f"Jarvis: {reply.text}")
    if args.json:
        print(reply_json(reply))
    return 0 if reply.completion != "ERROR" else 1


if __name__ == "__main__":
    sys.exit(main())
