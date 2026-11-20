"""WORK-03 GATE 4 — one short, isolated real tool call by the model.

Same harness, policy and sandbox as WORK-02, but the only task is to list the
workspace (write is NOT authorized). PASS only if the MODEL itself called
list_workspace successfully and its answer names a document that exists.
Exit codes: 0 PASS, 1 model did not do it (QWEN REAL FAIL), 2 environment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

LAB = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:11434"
TASK = ("Issa: usa a ferramenta list_workspace para ver que documentos existem na pasta de trabalho "
        "e diz-me os nomes exactos. Não escrevas nenhum relatório.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--engine-timeout", type=float, default=600.0)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fake", action="store_true", help="validate this script only (FAKE)")
    args = ap.parse_args(argv)
    for key in list(os.environ):
        if key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} or key.upper().endswith("API_KEY"):
            os.environ.pop(key)
    os.environ.setdefault("JARVIS_NUM_CTX", "8192")
    sys.path.insert(0, str(LAB))
    from w02lab import fake, fixtures, harness

    if args.fake:
        engine = fake.ScriptedEngine([{"tool_calls": [fake.call("list_workspace")]},
                                      {"content": f"Documentos: {fixtures.DOC_A}, {fixtures.DOC_B}."}])
        mode = "FAKE"
    else:
        from openjarvis.engine.ollama import OllamaEngine
        engine, mode = OllamaEngine(host=HOST, timeout=args.engine_timeout), "QWEN REAL"
    cfg = harness.RunConfig(model=args.model, max_turns=3, max_tokens=256, write_authorized=False,
                            timeout_seconds=args.timeout, task_prompt=TASK)
    ev = harness.run_task(engine, seed=4242, cfg=cfg, mode_label=mode)
    listed = [t for t in ev["trace"] if t["tool"] == "list_workspace" and t["success"]]
    answer = ev["final_answer"] or ""
    named = [d for d in (fixtures.DOC_A, fixtures.DOC_B) if d in answer]
    env_error = ev["error"] and ("Connect" in ev["error"] or "Timeout" in ev["error"])
    if env_error or ev["timed_out"]:
        status = "ENVIRONMENT BLOCKED"
    elif listed and named and not any(ev["violations"].values()):
        status = f"{mode} PASS"
    else:
        status = f"{mode} FAIL"
    result = {"gate": 4, "status": status, "mode": mode, "model": args.model,
              "model_called_list_workspace": bool(listed), "answer_names_documents": named,
              "trace": ev["trace"], "policy_log": ev["policy_log"], "violations": ev["violations"],
              "engine_steps": ev["engine_steps"], "latency": ev["latency"], "error": ev["error"],
              "final_answer": answer[:500]}
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("gate", "status", "model_called_list_workspace",
                                             "answer_names_documents", "latency")}, ensure_ascii=False))
    return 0 if status.endswith("PASS") else (2 if status == "ENVIRONMENT BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
