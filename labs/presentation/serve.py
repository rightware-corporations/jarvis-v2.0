"""ISSA PRESENTATION RELEASE (LAB launcher, EXPERIMENTAL tools/transport): the REAL GUI (B6 auth + HUD + JARVIS
persona) whose chat runs through AgentSession/Orchestrator (native tool calling, AgentPolicy, receipts) with ONLY two
host-declared tools:
  get_exchange_rate — BM bulletins (USD/MZN & other MZN pairs, XAU/USD) + optional ECB (Frankfurter) for EUR/USD, GBP/USD;
  web_research      — Wikipedia (pt/en) search + read best article.
Answers get host-built source lines and a financial integrity check (labs/f01/integrity.py).
Modes: --offline (replay of the documents collected in OP01-FX-REAL-PROXY; research → NOT_RETRIEVED, no network)
       --proxy   (session-proxy transport; requires --autorizacao and --janela-inicio of an operator authorisation).
Usage: .runtime/gui/venv/bin/python -m labs.presentation.serve --offline|--proxy [...] [--public-origin URL --public-minutes N]"""
import argparse
import re
import datetime as dt
import json
from pathlib import Path

from labs.f01.bm_fx import TOOL_SPEC, ExchangeRateTool, Source
from labs.f01.integrity import check
from labs.f01.research_tool import SPEC as RSPEC, ResearchTool
from rightware.agent.policy import ToolDef
from rightware.agent.session import ToolOutcome
from rightware.agent.web import WebRefused
from rightware.assistant_tools import ToolChatAdapter
from rightware.gui.server import build_app, serve
from rightware.persona import RuntimeFacts, system_prompt

BM = ("www.bancomoc.mz", "bancomoc.mz")
WIKI = ("pt.wikipedia.org", "en.wikipedia.org")
ECB = ("api.frankfurter.dev",)     # 25/11: .app now 301-redirects here; needs a NEW authorisation including this host
TEMPLATES = {"pt": "https://pt.wikipedia.org/w/index.php?search={q}&fulltext=1&ns0=1",
             "en": "https://en.wikipedia.org/w/index.php?search={q}&fulltext=1&ns0=1"}
FX_DEF = ToolDef("get_exchange_rate", TOOL_SPEC["function"]["description"],
                 {"base_currency": {"type": "string", "maxLength": 3, "description": "ISO: USD, EUR, GBP, ZAR, XAU…"},
                  "quote_currency": {"type": "string", "maxLength": 3, "description": "ISO: MZN ou USD"},
                  "reference_date": {"type": "string", "maxLength": 10, "description": "AAAA-MM-DD ou latest"}},
                 ("base_currency",), session_flag="fx", consequential=False, max_calls=4)
C_DEF = ToolDef("calculator", "Calcula uma expressão matemática exacta (ex.: (50000-35000)/50000*100). Usa para "
                "qualquer conta com números; não faças contas de cabeça.",
                {"expression": {"type": "string", "maxLength": 200, "description": "expressão matemática"}},
                ("expression",), session_flag="calc", consequential=False, max_calls=6)
R_DEF = ToolDef("web_research", RSPEC["function"]["description"],
                {"query": {"type": "string", "maxLength": 120, "description": "2 a 6 palavras-chave"},
                 "language": {"type": "string", "enum": ["pt", "en"], "maxLength": 2, "description": "pt ou en"}},
                ("query",), session_flag="research", consequential=False, max_calls=3)


def proxy_source(fetcher, store: Path) -> Source:
    """BM/ECB documents through the experimental fetcher; bytes read back from its audited store (sha256)."""
    def get(url):
        try:
            fetcher.fetch(url, host_allowed=lambda h: True)
        except WebRefused:
            pass
        last = fetcher.audit[-1] if fetcher.audit else {}
        if last.get("status") != 200 or not last.get("sha256"):
            return None
        return (store / f"{last['sha256']}.bin").read_bytes(), last.get("content_type", ""), last["utc"]
    return Source(get, "Banco de Moçambique / BCE via transporte EXPERIMENTAL session_proxy")


HOST_LABEL = re.compile(r"^\s*[*_>\-•]*\s*(Fonte:|\*\*Fonte|✓ Verificação do anfitrião|⚠ Verificação do anfitrião|"
                        r"⚠ Nenhuma ferramenta financeira)", re.I)


def strip_imitated(answer: str) -> tuple[str, int]:
    """The HOST owns its labels: model lines imitating host source/verification annotations are removed."""
    kept, removed = [], 0
    for line in answer.split("\n"):
        if HOST_LABEL.match(line) and ("anfitrião" in line or "bancomoc.mz" in line or "wikipedia.org" in line
                                       or "frankfurter" in line or "Nenhuma ferramenta" in line):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


def annotate(answer, records, question):
    fx = [r for r in records if r.get("tool") == "get_exchange_rate"]
    rs = [r for r in records if r.get("tool") == "web_research" and r.get("status") == "OK"]
    lines = []
    for r in fx:
        if r.get("status") in ("OK", "DERIVED"):
            p = r["provenance"]
            lines.append(f"Fonte: {p['document_url']} — dados de {r.get('reference_date')}"
                         + (f", boletim {p['bulletin']}" if p.get("bulletin") else "") + f" (obtido {p['retrieved_at']})")
    for r in rs:
        lines.append(f"Fonte: {r['read_url']} (lida pelo JARVIS; conteúdo externo não verificado)")
    if fx:
        c = check(answer, fx, question)
        if c["issues"]:
            lines.append("⚠ Verificação do anfitrião: valores sem correspondência no registo da ferramenta: "
                         + ", ".join(sorted({i["value"] for i in c["issues"]})) + " — não os considere confirmados.")
        elif c["sustained"]:
            lines.append(f"✓ Verificação do anfitrião: {len(c['sustained'])} valor(es) financeiro(s) conferem com o registo.")
    elif any(k in answer.lower() for k in ("cotação", "taxa de câmbio", "xau", "onça")) and not records:
        lines.append("⚠ Nenhuma ferramenta financeira foi consultada nesta resposta: valores numéricos não confirmados.")
    return ("\n\n" + "\n".join(lines)) if lines else ""


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    m = a.add_mutually_exclusive_group(required=True)
    m.add_argument("--offline", action="store_true")
    m.add_argument("--proxy", action="store_true")
    a.add_argument("--autorizacao", default="")
    a.add_argument("--janela-inicio", type=float)
    a.add_argument("--janela-minutos", type=float, default=60.0)   # authorised window length (operator decision)
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--model", default="qwen3.5:2b")
    a.add_argument("--hoje", default=dt.date.today().isoformat())
    a.add_argument("--public-origin")
    a.add_argument("--public-minutes", type=float)
    a.add_argument("--voz", action="store_true")
    x = a.parse_args()
    if x.proxy:
        from labs.op01.proxy_transport import SessionProxyFetcher
        if not x.autorizacao or x.janela_inicio is None:
            a.error("--proxy exige --autorizacao e --janela-inicio")
        store = Path(".runtime/presentation-net")
        fetcher = SessionProxyFetcher(BM + WIKI + ECB, authorisation=x.autorizacao, store=store,
                                      window_start=x.janela_inicio, per_question=8, per_window=80,
                                      window_s=min(x.janela_minutos, 90.0) * 60)
        src, ecb, rfetch, label = proxy_source(fetcher, store), proxy_source(fetcher, store), fetcher, "EXPERIMENTAL session_proxy"
    else:
        from labs.f01.offline import replay_source
        from labs.f01.run import ReplayFetcher
        src, ecb, rfetch, label = replay_source(), None, ReplayFetcher(), "OFFLINE (documentos recolhidos a 24/11/2026)"
        fetcher = None

    def tools():
        fx = ExchangeRateTool(src, today=x.hoje, ecb=ecb)
        rt = ResearchTool(rfetch, templates=TEMPLATES, article_hosts=WIKI)

        def model_view(r):
            """What the MODEL sees: unambiguous values only (number + formatted text with unit); the printed
            document form and full provenance stay in the HOST record (used for sources and the integrity check)."""
            def fmt(v):
                return None if v is None else f"{v:,.2f}".replace(",", " ").replace(".", ",")
            unit = r.get("unit", "")
            keep = {k: r[k] for k in ("status", "detail", "reference_date", "instrument", "rate_type", "note",
                                      "consulted_on", "derivation") if r.get(k) is not None}
            for f, label in (("buy", "compra"), ("sell", "venda"), ("mid", "média"), ("value", "valor")):
                if r.get(f) is not None:
                    keep[label] = f"{fmt(r[f])} {unit}"
            if r.get("inverse"):
                keep["inverso"] = f"{r['inverse']['value']} {r['inverse']['unit']}"
            return keep

        def run_fx(args):
            r = fx(args.get("base_currency", ""), args.get("quote_currency", "MZN"), args.get("reference_date"))
            return ToolOutcome("get_exchange_rate", "OK" if r["status"] in ("OK", "DERIVED") else "FAILED",
                               json.dumps(model_view(r), ensure_ascii=False), {"status": r["status"]})

        def run_r(args):
            r = rt(args.get("query", ""), args.get("language", "pt"))
            return ToolOutcome("web_research", "OK" if r["status"] == "OK" else "FAILED",
                               json.dumps(r, ensure_ascii=False), {"status": r["status"]})
        def run_c(args):                               # REUSE: the pinned OpenJarvis CalculatorTool (safe AST eval)
            from openjarvis.tools.calculator import CalculatorTool
            r = CalculatorTool().execute(expression=str(args.get("expression", ""))[:200])
            return ToolOutcome("calculator", "OK" if r.success else "FAILED", r.content, {"success": r.success})
        return ({"get_exchange_rate": (FX_DEF, run_fx), "web_research": (R_DEF, run_r), "calculator": (C_DEF, run_c)},
                lambda: fx.records + rt.records)

    facts = RuntimeFacts(model=x.model, environment="cloud",
                         tools=("calculadora exacta (calculator) para qualquer conta",
                                "cotações oficiais com data e fonte (get_exchange_rate: Banco de Moçambique — metical e "
                                "ouro XAU/USD; BCE — EUR/USD, GBP/USD)", "pesquisa geral numa enciclopédia autorizada "
                                "(web_research)"))
    from rightware.assistant_tools import ModelRouter
    from rightware.text_adapter import LocalSimpleTextAdapter
    persona = system_prompt(facts)
    router = ModelRouter(x.model, "cotações (câmbio, ouro), pesquisa geral, calculadora")
    direct = LocalSimpleTextAdapter(x.model, timeout_seconds=240, max_tokens=768, system_prompt=persona)
    annotate.clean = strip_imitated
    adapter = ToolChatAdapter(x.model, sites=(), persona=persona, allow=("fx", "research", "calc"),
                              extra_tools_factory=tools, post_check=annotate, timeout_seconds=240,
                              browser_fetcher=fetcher, router=router, direct=direct)
    app, bridge = build_app(port=x.port, models=[x.model], deadline=240.0, adapter_factory=lambda m: adapter,
                            public_origin=x.public_origin, public_minutes=x.public_minutes, voice=x.voz)
    bridge.adapters = {x.model: adapter}
    bridge.tools_label = lambda m: f"ferramentas: cotações oficiais e pesquisa ({label})"
    print(f"JARVIS — apresentação ({label}).", flush=True)
    if x.public_origin:
        print("Acesso privado B6 activo; ligação de uso único em .runtime/gui/session-url (não impressa).", flush=True)
    else:
        print("Sessão local:", app.session_url, flush=True)
    serve(app, x.port)
