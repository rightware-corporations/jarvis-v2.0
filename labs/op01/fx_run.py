"""OP01-FX-REAL-PROXY: real run through the GUI path (B6 server + persona + AgentSession/Orchestrator, Qwen local)
with the EXPERIMENTAL session-proxy transport, restricted to the authorised Banco de Moçambique hosts.
Samples the HUD activity during each turn. No expected values are given to the model.
Usage: .runtime/gui/venv/bin/python -m labs.op01.fx_run <outdir> <window_start_epoch> [model]"""
import json
import sys
import threading
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

from labs.op01.acceptance import PY, serve

TURNS = ["Jarvis, qual é a taxa de câmbio mais recente do dólar em relação ao metical?",
         "Qual é a diferença entre as taxas de compra e venda?",
         "De que dia são esses dados?",
         "Qual foi a tua fonte?",
         "E nesse mesmo documento, qual é a taxa do rand sul-africano?"]
ENTRIES = ["https://www.bancomoc.mz/pt/tabelas-de-taxas-de-cambio-de-referencia-diarias/2026-2025/",
           "https://www.bancomoc.mz/pt/areas-de-actuacao/mercados/mercado-cambial/",
           "https://www.bancomoc.mz/pt/areas-wrapper/taxas-de-cambio-de-referencia-intradiaria/"]

if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    start, model = sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "qwen3.5:2b")
    if len(sys.argv) > 4:                                    # bounded subset, e.g. "0,2"
        TURNS = [TURNS[int(i)] for i in sys.argv[4].split(",")]
    cmd = [PY, "-m", "labs.op01.serve_fx_proxy", "--port", "8000", "--model", model,
           "--sites", "www.bancomoc.mz,bancomoc.mz", "--entradas", ",".join(ENTRIES),
           "--autorizacao", "OP01-FX-REAL-PROXY", "--janela-inicio", start]
    p, url = serve(cmd, 8000)
    res = []
    try:
        jar = CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
        op.open(url, timeout=10)
        msgs = []
        for q in TURNS:
            msgs.append({"role": "user", "content": q})
            phases, done = [], threading.Event()

            def sample():
                while not done.is_set():
                    try:
                        a = json.loads(op.open("http://127.0.0.1:8000/v1/rightware/state", timeout=5).read()).get("activity")
                        if a and (not phases or phases[-1][0] != a["phase"]):
                            phases.append((a["phase"], a["tool_calls"]))
                    except Exception:
                        pass
                    time.sleep(0.7)
            th = threading.Thread(target=sample); th.start()
            t0 = time.time()
            req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", method="POST",
                                         data=json.dumps({"model": model, "stream": False, "messages": msgs}).encode(),
                                         headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8000",
                                                  "X-Rightware-Conversation": "op01-fx"})
            r = json.loads(op.open(req, timeout=400).read())
            done.set(); th.join()
            text = r["choices"][0]["message"]["content"]
            msgs.append({"role": "assistant", "content": text})
            res.append({"question": q, "seconds": round(time.time() - t0, 1), "answer": text, "hud_phases": phases})
            print(f"{round(time.time()-t0,1)}s Q: {q}\n A: {text[:900]}\n HUD: {phases}\n", flush=True)
    finally:
        p.terminate(); p.wait(10)
    (out / f"fx-run-{model.replace(':', '_')}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
