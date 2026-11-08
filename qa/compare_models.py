"""RIGHTWARE Jarvis do Issa: reproducible, real-model comparison.

Run with the pinned OpenJarvis virtualenv on a host running local Ollama.
Six synthetic conversation turns use SimpleAgent; calculator is a separate
native_react test, and PASS is not assigned by a heuristic.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from rightware import runtime

MODELS = ("qwen3.5:2b", "qwen3.5:4b")
HOST = "http://127.0.0.1:11434"
QUESTIONS = [
    {"id": "identity", "question": "Quem és tu, para quem trabalhas e quem te desenvolveu?"},
    {"id": "orion_fact", "question": "Para este teste fictício: o projecto Orion serve para gerir piscinas. Guarda só estes dois factos."},
    {"id": "maputo", "question": "Qual é a capital de Moçambique?"},
    {"id": "orion_recall", "question": "Como se chama o projecto fictício que apresentei e qual é a finalidade dele?"},
    {"id": "orion_unknown", "question": "Qual é o orçamento do Orion e quais equipamentos foram comprados?"},
    {"id": "no_action", "question": "Já abriste o Bloco de Notas? Não abras nenhuma aplicação; apenas responde."},
]


def request_ollama(path: str, payload: dict | None = None, timeout: int = 180) -> dict:
    """Direct loopback HTTP even when the host environment contains proxies."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HOST + path, data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def snapshot_hardware() -> dict:
    output = {"gpu": "not_detected", "ram_total_kib": None}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                output["ram_total_kib"] = int(line.split()[1])
                break
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True, capture_output=True, timeout=8, check=False,
        )
        if r.returncode == 0:
            output["gpu"] = r.stdout.strip().splitlines()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return output


def atomic_json(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".tmp")
    staging.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    staging.replace(path)


def git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=runtime.ROOT, text=True,
    ).strip()


def installed_models() -> set[str]:
    return {m["name"] for m in request_ollama("/api/tags").get("models", [])}


def run_conversation(model: str, report: dict, out: Path) -> None:
    from openjarvis.agents._stubs import AgentContext
    from openjarvis.agents.simple import SimpleAgent
    from openjarvis.core.types import Message, Role
    from openjarvis.engine.ollama import OllamaEngine

    entry = {"model": model, "agent": "simple", "status": "IN_PROGRESS",
             "warmup_seconds": None, "turns": [], "tool": None,
             "hardware_before": snapshot_hardware()}
    report["results"].append(entry)
    atomic_json(out, report)
    engine = OllamaEngine(host=HOST, timeout=180)
    try:
        # Measure model load separately, so first-turn quality is comparable.
        started = time.monotonic()
        request_ollama("/api/generate", {
            "model": model, "prompt": "Responde apenas: pronto.",
            "stream": False, "keep_alive": "5m",
            "options": {"num_predict": 12, "num_ctx": 4096},
            "think": False,
        })
        entry["warmup_seconds"] = round(time.monotonic() - started, 3)
        agent = SimpleAgent(engine, model, temperature=0.2, max_tokens=256,
                            engine_options={"num_ctx": 4096})
        ctx = AgentContext()
        for item in QUESTIONS:
            started = time.monotonic()
            record = {"id": item["id"], "question": item["question"],
                      "answer": None, "seconds": None, "error": None}
            try:
                answer = agent.run(item["question"], context=ctx).content
                record["answer"] = answer
                ctx.conversation.add(Message(role=Role.USER, content=item["question"]))
                ctx.conversation.add(Message(role=Role.ASSISTANT, content=answer))
            except Exception as exc:
                record["error"] = type(exc).__name__ + ": " + str(exc)[:300]
            record["seconds"] = round(time.monotonic() - started, 3)
            entry["turns"].append(record)
            atomic_json(out, report)
            print(f"\n[{model}] {record['id']} ({record['seconds']}s)\n"
                  f"Q: {record['question']}\nA: {record['answer'] or record['error']}", flush=True)
            if record["error"]:
                entry["status"] = "REVIEW_INFERENCE_FAILURE"
                break
        else:
            entry["status"] = "REVIEW_MANUAL_JUDGEMENT_REQUIRED"
        # A tool is not available to SimpleAgent. Separate tool-enabled trial.
        try:
            from openjarvis.agents.native_react import NativeReActAgent
            from openjarvis.tools.calculator import CalculatorTool
            tool_agent = NativeReActAgent(
                engine, model, tools=[CalculatorTool()], max_turns=4,
                temperature=0.2, max_tokens=320, interactive=False,
            )
            started = time.monotonic()
            result = tool_agent.run(
                "Usa a ferramenta calculator para calcular 137 * 29. Diz o resultado.",
                context=AgentContext(),
            )
            traces = [{"tool_name": t.tool_name, "success": t.success,
                       "content": t.content} for t in result.tool_results]
            entry["tool"] = {
                "agent": "native_react", "answer": result.content,
                "tool_results": traces,
                "confirmed_calculator": any(
                    t["tool_name"] == "calculator" and t["success"]
                    and t["content"].strip() in ("3973", "3973.0")
                    for t in traces
                ),
                "seconds": round(time.monotonic() - started, 3),
            }
            print(f"\n[{model}] tool: {entry['tool']}", flush=True)
        except Exception as exc:
            entry["tool"] = {"error": type(exc).__name__ + ": " + str(exc)[:300],
                             "confirmed_calculator": False}
        entry["hardware_after"] = snapshot_hardware()
    except Exception as exc:
        entry["status"] = "REVIEW_FATAL"
        entry["fatal_error"] = type(exc).__name__ + ": " + str(exc)[:300]
        print(f"[{model}] ERROR: {entry['fatal_error']}", flush=True)
    finally:
        engine._client.close()
        try:
            request_ollama("/api/generate", {"model": model,
                                             "keep_alive": 0}, timeout=60)
            entry["unloaded"] = True
        except Exception as exc:
            entry["unloaded"] = False
            entry["unload_error"] = type(exc).__name__
        atomic_json(out, report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis do Issa real-model benchmark")
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--output", default=".runtime/evidence/qwen-comparison.json")
    args = parser.parse_args()
    for model in args.models:
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", model) or "cloud" in model.lower():
            parser.error("Only installed local Ollama model names are allowed.")
    # A plain os.environ.update would *retain* proxy/secret keys that were
    # removed from the copied environment. Replace the process environment.
    clean_environment = runtime.child_environment()
    os.environ.clear()
    os.environ.update(clean_environment)
    config = runtime.prepare_config()
    if "Issa" not in config["agent"]["default_system_prompt"]:
        raise RuntimeError("Stale local Jarvis identity. Update the runtime profile first.")
    runtime.verify_source()
    tags = installed_models()
    missing = [model for model in args.models if model not in tags]
    if missing:
        raise RuntimeError("Models not installed in Ollama: " + ", ".join(missing))
    report = {
        "schema": 1,
        "product": "Jarvis do Issa — RIGHTWARE",
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_sha": git_sha(),
        "openjarvis_pin": runtime.PIN,
        "ollama_version": request_ollama("/api/version").get("version"),
        "environment": snapshot_hardware(),
        "criteria": "Six synthetic contextual turns. Scores require human review; calculator only passes if tool_results verifies it.",
        "results": [],
    }
    out = Path(args.output).resolve()
    atomic_json(out, report)
    for model in args.models:
        run_conversation(model, report, out)
    print(f"\nEVIDENCE: {out}\nRESULT: REVIEW — inspect all answers, do not infer a quality percentage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
