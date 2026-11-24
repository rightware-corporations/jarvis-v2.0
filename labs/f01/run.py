"""F01-A controlled comparison — REAL local Qwen, OFFLINE (no network). Configurations (frozen in frozen_eval.json):
A  persona, no tools (pinned SimpleAgent)                         — parametric knowledge only;
B  AgentSession/Orchestrator + generic browse + web_search          — over the OFFLINE replay of the real BM pages and
                                                                      the fictional OP01 fixture;
C  native Ollama tool calling with ONLY get_exchange_rate           — minimal LAB loop (not a product engine);
D  AgentSession/Orchestrator + browse + web_search + get_exchange_rate (host-declared extra tool).
Host attribution of sources is built from tool records and stored SEPARATELY from the model's text. Scoring is done
afterwards by score.py with gold records computed independently by the evaluator.
Usage: .runtime/gui/venv/bin/python -m labs.f01.run <outdir> <model> <configs e.g. A,B,C,D> [conversation ids]"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

from labs.f01.bm_fx import TOOL_SPEC, ExchangeRateTool, pdf_text
from labs.f01.offline import replay_source
from labs.op01.fixture import fixture_fetcher, fixture_sites
from rightware.agent.policy import ToolDef
from rightware.agent.session import AgentSession, ToolOutcome
from rightware.agent.web import Page, WebRefused, html_to_text
from rightware.persona import RuntimeFacts, system_prompt

ROOT = Path(__file__).resolve().parents[2]
TODAY = "2026-11-24"
BM = ("www.bancomoc.mz", "bancomoc.mz")
SITES = BM + fixture_sites()
SEARCH = "https://pesquisa.op01.example/search?q={q}"
ENTRIES = ("https://www.bancomoc.mz/pt/tabelas-de-taxas-de-cambio-de-referencia-diarias/2026-2025/",)
FX_DEF = ToolDef("get_exchange_rate", TOOL_SPEC["function"]["description"],
                 {"base_currency": {"type": "string", "maxLength": 3, "description": "ISO, ex.: USD"},
                  "quote_currency": {"type": "string", "maxLength": 3, "description": "ISO, normalmente MZN"},
                  "reference_date": {"type": "string", "maxLength": 10, "description": "AAAA-MM-DD ou latest"}},
                 ("base_currency",), session_flag="fx", consequential=False, max_calls=4)


class ReplayFetcher:
    """PublicBrowser fetcher over the OFFLINE replay (BM pages + PDF→text) and the OP01 fixture. No socket."""
    def __init__(self):
        self.replay, self.fixture = replay_source(), fixture_fetcher()

    def fetch(self, url, host_allowed=None):
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or "").lower()
        if host_allowed is not None and not host_allowed(host):
            raise WebRefused("servidor fora dos sites autorizados nesta tarefa")
        if host not in BM:
            return self.fixture.fetch(url, host_allowed)
        got = self.replay.get(url)
        if got is None:
            raise WebRefused("documento não disponível na reprodução offline")
        raw, ctype, _ = got
        text = pdf_text(raw) if "pdf" in ctype else html_to_text(raw.decode("utf-8", "replace"))
        markup = raw.decode("utf-8", "replace") if "html" in ctype else ""
        return Page(url, url, 200, ctype, text[:60000], hashlib.sha256(raw).hexdigest(), len(text) > 60000, markup)


class CountingEngine:
    def __init__(self, inner):
        self.inner, self.engine_id, self.prompt_tokens, self.calls = inner, inner.engine_id, 0, 0

    def generate(self, messages, **kw):
        out = self.inner.generate(messages, **kw)
        self.calls += 1
        self.prompt_tokens += int((out.get("usage") or {}).get("prompt_tokens") or 0)
        return out

    def close(self):
        self.inner.close()


def engine():
    from openjarvis.engine.ollama import OllamaEngine
    return CountingEngine(OllamaEngine(host="http://127.0.0.1:11434", timeout=240))


def persona(model, cfg):
    tools = {"A": (), "B": ("pesquisa e leitura de páginas web nas fontes autorizadas",),
             "C": ("consulta cambial estruturada get_exchange_rate (Banco de Moçambique)",),
             "D": ("pesquisa e leitura de páginas web nas fontes autorizadas",
                   "consulta cambial estruturada get_exchange_rate (Banco de Moçambique)")}[cfg]
    return system_prompt(RuntimeFacts(model=model, environment="cloud", tools=tools,
                                      sites=SITES if cfg in "BD" else (), search_template=SEARCH if cfg in "BD" else "",
                                      entry_urls=ENTRIES if cfg in "BD" else ()))


def attribution(records):
    """Host-built source line from the tool records of THIS turn (never from model text)."""
    ok = [r for r in records if r.get("status") in ("OK", "DERIVED")]
    if not ok:
        return ""
    p = ok[-1]["provenance"]
    return (f"Fonte (registo da ferramenta, atribuída pelo anfitrião): Banco de Moçambique, boletim {p['bulletin']}, "
            f"dados de {ok[-1]['reference_date']}, {p['document_url']} (sha256 {p['sha256'][:12]}…)")


# ------------------------------------------------------------------------------------------- configs
def run_a(model, q, history):
    from rightware.text_adapter import LocalSimpleTextAdapter
    eng = engine()
    a = LocalSimpleTextAdapter(model, engine_factory=lambda: eng, timeout_seconds=240, max_tokens=512,
                               system_prompt=persona(model, "A"))
    return a.reply(q, tuple(history)), [], [], eng


def run_session(model, cfg, q, history):
    eng, fx = engine(), ExchangeRateTool(replay_source(), today=TODAY)

    def fx_runner(args):
        r = fx(args.get("base_currency", ""), args.get("quote_currency", "MZN"), args.get("reference_date"))
        return ToolOutcome("get_exchange_rate", "OK" if r["status"] in ("OK", "DERIVED") else "FAILED",
                           json.dumps(r, ensure_ascii=False), {"status": r["status"]})
    s = AgentSession(eng, model, allow={"browse"} | ({"fx"} if cfg == "D" else set()), confirm=lambda x: None,
                     sites=SITES, browser_fetcher=ReplayFetcher(), persona=persona(model, cfg), search_template=SEARCH,
                     extra_tools={"get_exchange_rate": (FX_DEF, fx_runner)} if cfg == "D" else None)
    r = s.run(q, history=tuple(history))
    return r.text, [o.tool for o in r.outcomes], fx.records, eng


def run_c(model, q, history, max_rounds=4):
    fx = ExchangeRateTool(replay_source(), today=TODAY)
    msgs = [{"role": "system", "content": persona(model, "C")}] + \
           [{"role": r, "content": t} for r, t in history] + [{"role": "user", "content": q}]
    tools, ptok, calls = [], 0, 0
    for _ in range(max_rounds):
        body = json.dumps({"model": model, "stream": False, "think": False, "messages": msgs, "tools": [TOOL_SPEC],
                           "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 768}}).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=300).read())
        calls += 1
        ptok += d.get("prompt_eval_count") or 0
        m = d.get("message", {})
        tcs = m.get("tool_calls") or []
        if not tcs:
            class E: pass
            e = E(); e.prompt_tokens, e.calls = ptok, calls
            return m.get("content", ""), tools, fx.records, e
        msgs.append(m)
        for tc in tcs:
            f = tc.get("function", {})
            args = f.get("arguments") if isinstance(f.get("arguments"), dict) else json.loads(f.get("arguments") or "{}")
            tools.append(f.get("name"))
            out = (fx(args.get("base_currency", ""), args.get("quote_currency", "MZN"), args.get("reference_date"))
                   if f.get("name") == "get_exchange_rate" else {"status": "REFUSED", "detail": "ferramenta inexistente"})
            msgs.append({"role": "tool", "content": json.dumps(out, ensure_ascii=False)})
    class E: pass
    e = E(); e.prompt_tokens, e.calls = ptok, calls
    return "[limite de chamadas atingido sem resposta]", tools, fx.records, e


if __name__ == "__main__":
    out, model, cfgs = Path(sys.argv[1]), sys.argv[2], sys.argv[3].split(",")
    only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    out.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((ROOT / "labs/f01/frozen_eval.json").read_text())
    for cfg in cfgs:
        rows = []
        for conv in frozen["conversations"]:
            if only and conv["id"] not in only:
                continue
            history = []
            for t in conv["turns"]:
                t0 = time.time()
                try:
                    if cfg == "A":
                        text, tools, recs, eng = run_a(model, t["q"], history)
                    elif cfg == "C":
                        text, tools, recs, eng = run_c(model, t["q"], history)
                    else:
                        text, tools, recs, eng = run_session(model, cfg, t["q"], history)
                    err = None
                except Exception as exc:                         # recorded, never hidden
                    text, tools, recs, err = "", [], [], f"{type(exc).__name__}: {str(exc)[:160]}"
                    class E: pass
                    eng = E(); eng.prompt_tokens, eng.calls = 0, 0
                row = {"config": cfg, "model": model, "conversation": conv["id"], "id": t["id"], "q": t["q"],
                       "answer": text, "host_attribution": attribution(recs), "tools": tools, "records": recs,
                       "seconds": round(time.time() - t0, 1), "model_calls": eng.calls,
                       "prompt_tokens": eng.prompt_tokens, "error": err}
                rows.append(row)
                history += [("user", t["q"]), ("assistant", text or "(sem resposta)")]
                print(f"[{cfg} {model}] {t['id']} {row['seconds']}s tools={tools} | {text[:220]!r}", flush=True)
        (out / f"{cfg}-{model.replace(':', '_')}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
