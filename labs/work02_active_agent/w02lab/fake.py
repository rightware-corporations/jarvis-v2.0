"""FAKE engines (scripted, deterministic). They exist ONLY to validate the
harness, tools and policy. Every result produced with them is labelled FAKE
and is never evidence of model capability."""
from __future__ import annotations

import json
import re
import time

from openjarvis.core.types import Role


def call(name, args=None, *, raw=None, cid=None):
    return {"id": cid or f"fake_{name}", "name": name,
            "arguments": raw if raw is not None else json.dumps(args or {}, ensure_ascii=False)}


class ScriptedEngine:
    """Returns a fixed sequence of responses; each item is a dict or a callable(messages)->dict."""
    engine_id = "fake"

    def __init__(self, script, delay: float = 0.0):
        self.script, self.delay, self.i = list(script), delay, 0
        self.seen: list = []

    def generate(self, messages, **kwargs):
        self.seen.append(messages)
        if self.delay:
            time.sleep(self.delay)
        if self.i >= len(self.script):
            return {"content": "Terminei.", "usage": {}}
        item = self.script[self.i]
        self.i += 1
        if callable(item):
            item = item(messages)
        out = {"content": item.get("content", ""), "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        if item.get("tool_calls"):
            out["tool_calls"] = item["tool_calls"]
        return out


def tool_outputs(messages) -> list[str]:
    return [m.content for m in messages if m.role == Role.TOOL]


def honest_report_from(messages, report_name: str) -> dict:
    """Build a correct report ONLY from what the tools returned (validates the data path)."""
    docs = "\n".join(t for t in tool_outputs(messages) if t.startswith("[DADO"))
    def grab(label):
        m = re.search(label + r":\s*(.+)", docs)
        return m.group(1).strip() if m else "?"
    project = re.search(r"Projecto (\S+)", docs).group(1)
    budgets = re.findall(r"Orçamento [^:]+:\s*(.+)", docs)
    content = (
        f"# Relatório do projecto {project}\n\n"
        f"## Factos principais\n- Responsável técnico: {grab('Responsável técnico')}\n"
        f"- Fornecedor: {grab('Fornecedor seleccionado')}\n"
        f"- Início: {grab('Início dos trabalhos')}\n- Entrega prevista: {grab('Data de entrega prevista')}\n"
        f"- Orçamento (acta): {budgets[0]}\n- Orçamento (relatório financeiro): {budgets[1]}\n\n"
        f"## Contradições\n- Divergência de orçamento entre os documentos: {budgets[0]} vs {budgets[1]}.\n\n"
        f"## Fontes\n- acta_reuniao.md\n- relatorio_financeiro.md\n")
    return {"tool_calls": [call("write_report", {"name": report_name, "content": content})]}


def happy_script(report_name: str) -> list:
    return [
        {"tool_calls": [call("list_workspace")]},
        {"tool_calls": [call("read_document", {"name": "acta_reuniao.md"})]},
        {"tool_calls": [call("read_document", {"name": "relatorio_financeiro.md"})]},
        lambda msgs: honest_report_from(msgs, report_name),
        {"tool_calls": [call("verify_report", {"name": report_name})]},
        {"content": "Criei e verifiquei o relatório."},
    ]
