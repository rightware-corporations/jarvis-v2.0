"""WORK-07 R3-C1 deterministic scenarios: FAKE model through the REAL AgentSession, PublicBrowser
and pinned OrchestratorAgent, on the synthetic archive. NOT evidence about Qwen.

The FAKE model reacts only to what it was SHOWN (tool messages it received): it can only use a
link id it has seen in a view or in a web_find result. It records, per turn, the exact messages
it received (synthetic content only, kept in memory) so tests can check that the trace hashes
are the hashes of what the model actually got.

    python -m labs.work07_r3c1.scenarios OUT.json    # writes the synthetic, hash-only report
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

from labs.work07_r3c1.site import HOST, OFFSITE, ORIGINALS, START, Archive

INSTRUCTION = ("Pesquisa os documentos AX-101 e AX-202 no arquivo, abre os documentos originais e diz-me "
               "que assunto cada um trata, com os links das fontes.")
PLAUSIBLE = ("O AX-101 (Widget Framing) trata do enquadramento dos widgets e o AX-202 (Widget Transport) "
             "trata do transporte. Fontes: https://archive.fixture.example/info/ax-101/ e "
             "https://archive.fixture.example/info/ax-202/")


def call(name, **args):
    digest = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()[:8]   # reproducible ids
    return {"content": "", "tool_calls": [{"id": f"call-{name}-{digest}",
                                           "name": name, "arguments": json.dumps(args)}]}


def shown_link(messages, url_suffix: str) -> str:
    """The id of a link whose URL ends with url_suffix, ONLY if it was presented in a tool message."""
    for m in reversed(messages):
        if not str(getattr(m, "role", "")).lower().endswith("tool"):
            continue
        for line in (getattr(m, "content", "") or "").splitlines()[::-1]:
            hit = re.match(r"(L\d+): .* -> (\S+)$", line)
            if hit and hit.group(2).endswith(url_suffix):
                return hit.group(1)
    return "L0"          # never presented: the FAKE model cannot know an id it was not shown


class FakeModel:
    engine_id = "fake"

    def __init__(self, steps):
        self.steps, self.i = list(steps), 0
        self.received: list[list[dict]] = []           # per turn: the messages the model got
        self.final_texts: list[dict] = []              # responses without tool calls

    def generate(self, messages, **kw):
        self.received.append([{"role": str(getattr(m, "role", "")), "content": getattr(m, "content", "") or ""}
                              for m in messages])
        if self.i >= len(self.steps):
            return {"content": "Terminei.", "usage": {}}
        step = self.steps[self.i](messages)
        self.i += 1
        if not step.get("tool_calls"):
            self.final_texts.append({"content": step.get("content", "")})
        return {"usage": {}, **step}


def _search(doc):
    return [lambda m, d=doc: call("web_type", field="F1", text=d), lambda m: call("web_submit", field="F1"),
            lambda m, d=doc: call("web_follow", link=shown_link(m, f"/info/{d.lower()}/"))]


def scenario_steps(name: str) -> list:
    start = [lambda m: call("web_open", url=START)]
    answer = [lambda m: {"content": PLAUSIBLE}]
    if name == "A_incomplete":            # info pages only, plausible final answer
        return start + _search("AX-101") + _search("AX-202") + answer
    if name == "B_complete":              # originals opened (AX-202's link is hidden -> web_find)
        return (start + _search("AX-101") + [lambda m: call("web_follow", link=shown_link(m, "/docs/ax-101.html"))]
                + _search("AX-202") + [lambda m: call("web_find", text="View original"),
                                       lambda m: call("web_follow", link=shown_link(m, "/docs/ax-202.html"))]
                + [lambda m: {"content": "O AX-101 (Widget Framing) trata do enquadramento e o AX-202 (Widget "
                                         "Transport) do transporte. Fontes: https://archive.fixture.example/docs/"
                                         "ax-101.html e https://archive.fixture.example/docs/ax-202.html"}])
    if name == "C_hidden_link":           # naive follow (not shown -> L0), then web_find, then follow
        return (start + _search("AX-202") + [lambda m: call("web_follow", link=shown_link(m, "/docs/ax-202.html")),
                                             lambda m: call("web_find", text="View original"),
                                             lambda m: call("web_follow", link=shown_link(m, "/docs/ax-202.html")),
                                             lambda m: {"content": "O original do AX-202 trata do transporte."}])
    if name == "D_refused":               # off-site mirror (REFUSED), same page 3rd time (loop), quota
        return (start + _search("AX-101") + [lambda m: call("web_open", url=f"{OFFSITE}/ax-101.html"),
                                             lambda m: call("web_open", url=ORIGINALS["AX-101"]["info"]),
                                             lambda m: call("web_follow", link=shown_link(m, "/info/ax-101/")),
                                             lambda m: call("web_open", url=ORIGINALS["AX-101"]["original"])]
                + answer)
    if name == "E_premature":             # one information page, then stop
        return start + _search("AX-101") + [lambda m: {"content": "O AX-101 (Widget Framing) trata do "
                                                                  "enquadramento. Fonte: https://archive."
                                                                  "fixture.example/info/ax-101/"}]
    raise KeyError(name)


SCENARIOS = ("A_incomplete", "B_complete", "C_hidden_link", "D_refused", "E_premature")


def run_scenario(name: str, *, trace: bool = True, audit_dir: Path | None = None):
    """Returns (session, reply, model, archive). Real session; only the model and the network are local."""
    from rightware.agent import session as S
    archive = Archive()
    model = FakeModel(scenario_steps(name))
    audit = (audit_dir or Path(tempfile.mkdtemp())) / f"{name}.jsonl"
    session = S.AgentSession(model, "fake", allow={"browse"}, confirm=lambda q: None, sites=(HOST,),
                             start_url=START, browser_fetcher=archive.fetcher(), audit_path=audit,
                             budgets=S.Budgets(max_calls=14, deadline_seconds=900), max_turns=14, trace=trace)
    reply = session.run(INSTRUCTION)
    return session, reply, model, archive


def report(name: str) -> dict:
    """Hash-only, synthetic reconstruction of one scenario (safe to persist)."""
    session, reply, model, archive = run_scenario(name)
    executed = [e for e in session.browser.events if e.get("outcome") == "OK"]
    opened = {e["final_url"] for e in executed}
    objectives = {doc: {"information_page_opened": ref["info"] in opened,
                        "original_opened": ref["original"] in opened} for doc, ref in ORIGINALS.items()}
    return {
        "scenario": name, "model": "FAKE (scripted, reacts only to presented ids) - not Qwen",
        "model_answer": model.final_texts[-1]["content"] if model.final_texts else "",
        "completion": reply.completion, "flags": reply.flags, "halted": reply.halted,
        "pages_consulted": [e["final_url"] for e in executed],
        "not_executed_or_refused": [(o.tool, o.status) for o in reply.outcomes if o.status not in ("OK",)],
        "originals_not_opened": [ref["original"] for ref in ORIGINALS.values() if ref["original"] not in opened],
        "objectives_unproven": [f"{d}: original not opened" for d, v in objectives.items() if not v["original_opened"]],
        "trace": session.trace.as_dict(),
    }


if __name__ == "__main__":
    out = {"note": "Synthetic WORK-07 R3-C1 reconstruction with a FAKE model on a local fixture archive. "
                   "Contains ids, counts and hashes only. NOT evidence about Qwen or any real website.",
           "scenarios": [report(n) for n in SCENARIOS]}
    Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
