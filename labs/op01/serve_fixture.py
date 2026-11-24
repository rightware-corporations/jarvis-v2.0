"""OP01 LAB: serve the REAL GUI (B6 code + OP01 persona + tool chat) with the offline FIXTURE corpus as the only
"web". Real local Qwen; NO network; loopback only. Evidence from this server is FIXTURE evidence.
Usage: .runtime/gui/venv/bin/python -m labs.op01.serve_fixture [--port 8000] [--model qwen3.5:2b] [--ambiente cloud]"""
import argparse

from labs.op01.fixture import fixture_fetcher, fixture_sites
from rightware.gui.server import build_app, serve

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--model", default="qwen3.5:2b")
    a.add_argument("--ambiente", default="cloud", choices=("cloud", "local", "unknown"))
    a.add_argument("--deadline", type=float, default=240.0)
    x = a.parse_args()
    app, _ = build_app(port=x.port, models=[x.model], deadline=x.deadline, environment=x.ambiente,
                       tool_sites=fixture_sites(), browser_fetcher=fixture_fetcher(), tool_label="FIXTURE de teste",
                       tool_search_template="https://pesquisa.op01.example/search?q={q}")
    print("OP01 FIXTURE GUI (sem rede):", app.session_url, flush=True)
    serve(app, x.port)
