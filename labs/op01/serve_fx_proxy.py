"""OP01-FX-REAL-PROXY LAB launcher: the REAL GUI (B6 + persona + AgentSession/Orchestrator) with the EXPERIMENTAL
session-proxy transport (labs/op01/proxy_transport.py), restricted to the authorised hosts. Lab only: the product
CLI keeps the production (direct) transport. Requires an explicit operator authorisation reference and window start."""
import argparse
from pathlib import Path

from labs.op01.proxy_transport import SessionProxyFetcher
from rightware.gui.server import build_app, serve

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--model", default="qwen3.5:2b")
    a.add_argument("--sites", required=True)
    a.add_argument("--entradas", default="")
    a.add_argument("--autorizacao", required=True)
    a.add_argument("--janela-inicio", type=float, required=True)
    x = a.parse_args()
    sites = tuple(h.strip().lower() for h in x.sites.split(",") if h.strip())
    fetcher = SessionProxyFetcher(sites, authorisation=x.autorizacao, store=Path(".runtime/op01-fx"),
                                  window_start=x.janela_inicio)
    app, _ = build_app(port=x.port, models=[x.model], deadline=240.0, environment="cloud", tool_sites=sites,
                       browser_fetcher=fetcher, tool_label="transporte EXPERIMENTAL session_proxy",
                       tool_entry_urls=tuple(u for u in x.entradas.split(",") if u))
    print("OP01 FX PROXY GUI (EXPERIMENTAL):", app.session_url, flush=True)
    serve(app, x.port)
