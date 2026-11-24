"""OP01 acceptance with the REAL local Qwen (Ollama loopback). NO network: part B uses the offline FIXTURE corpus.
P  prompt capture : which system message actually reaches the model (in-process, recording engine wrapper);
A  product chat   : GUI server WITHOUT tools (persona only) through its real HTTP API;
B  tool chat      : GUI server WITH tools on the FIXTURE corpus (labs.op01.serve_fixture) through its HTTP API.
Usage: .runtime/gui/venv/bin/python -m labs.op01.acceptance <outdir> [model]"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".runtime/gui/venv/bin/python")

A_TURNS = ["Olá, quem és tu?", "Em que computador estás a correr neste momento?",
           "What can you help me with? Please answer in English.",
           "Qual é a taxa de câmbio actual do dólar em relação ao metical?",
           "Qual foi a primeira pergunta que te fiz nesta conversa?"]
A2_TURNS = ["Boa tarde. Como te chamas e o que fazes?", "Onde estás a funcionar agora: no meu portátil ou noutro sítio?",
            "Can you tell me in English what you cannot do?", "Qual é o preço actual do ouro?",
            "Qual foi a segunda coisa que te perguntei?"]
B2_TURNS = ["Olá JARVIS, tudo bem?", "Qual é a língua oficial de Corvana?", "E quantos habitantes tem esse país?",
            "O que diz a página do Banco Central de Corvana sobre a moeda?", "Quanto é 144 dividido por 12?"]
A3_TURNS = ["Bom dia! Apresenta-te, por favor.", "Estás instalado no meu telemóvel?",
            "In English, please: summarise what you are.", "Qual é a cotação actual do euro em meticais?",
            "Repete a minha primeira pergunta."]
B3_TURNS = ["Boa noite, JARVIS.", "Em que mar fica Corvana?", "E qual é a capital desse arquipélago?",
            "Desde quando o Banco Central de Corvana emite a moeda?", "Quanto é 25 vezes 4?"]
A4_TURNS = ["Olá! Diz-me quem és, em poucas palavras.", "Tens acesso aos meus ficheiros pessoais?",
            "Please reply in English: which language do you prefer to use with me?",
            "Qual é a taxa de câmbio actual do dólar em relação ao metical?", "O que te perguntei antes desta pergunta?"]
B4_TURNS = ["Olá!", "Que língua se fala em Corvana?", "E em que ano foi fundada a capital desse país?",
            "Quem emite a moeda de Corvana?", "Quanto é 9 vezes 8?"]
B_TURNS = ["Bom dia, JARVIS.", "Qual é a moeda de Corvana e quem a emite?", "E em que ano foi fundada a capital desse país?",
           "Abre a página https://enciclopedia.op01.example/wiki/Arquivo e diz-me o que lá está.",
           "Quanto é 17 vezes 23?"]


def capture_prompt(model):
    from rightware.persona import RuntimeFacts, system_prompt
    from rightware.text_adapter import LocalSimpleTextAdapter
    from openjarvis.engine.ollama import OllamaEngine
    seen = []

    class Rec:
        def __init__(self):
            self.e = OllamaEngine(host="http://127.0.0.1:11434", timeout=120)
            self.engine_id = self.e.engine_id

        def generate(self, messages, **kw):
            seen.append([(str(getattr(m.role, "value", m.role)), m.content) for m in messages])
            return self.e.generate(messages, **kw)

        def close(self):
            self.e.close()
    a = LocalSimpleTextAdapter(model, engine_factory=Rec, timeout_seconds=120,
                               system_prompt=system_prompt(RuntimeFacts(model=model, environment="cloud")))
    reply = a.reply("Apresenta-te numa frase.", ())
    msgs = seen[0]
    return {"roles": [r for r, _ in msgs], "system_excerpt": msgs[0][1][:220],
            "system_contains_openjarvis_default": "You are OpenJarvis" in msgs[0][1], "reply": reply}


def serve(cmd, port):
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = None
    t0 = time.time()
    while time.time() - t0 < 90:
        line = p.stdout.readline()
        m = re.search(r"(http://127\.0\.0\.1:\d+/rw-login\?t=\S+)", line or "")
        if m:
            url = m.group(1)
            break
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            break
        except Exception as e:
            if getattr(e, "code", None):
                break
            time.sleep(1)
    return p, url


def chat(port, url, turns, model, conv):
    jar = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.ProxyHandler({}))
    op.open(url, timeout=10)
    msgs, out = [], []
    for q in turns:
        msgs.append({"role": "user", "content": q})
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", method="POST",
                                     data=json.dumps({"model": model, "stream": False, "messages": msgs}).encode(),
                                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}",
                                              "X-Rightware-Conversation": conv})
        t0 = time.time()
        r = json.loads(op.open(req, timeout=400).read())
        text = r["choices"][0]["message"]["content"]
        state = json.loads(op.open(f"http://127.0.0.1:{port}/v1/rightware/state", timeout=10).read())
        out.append({"question": q, "seconds": round(time.time() - t0, 1), "answer": text, "activity": state.get("activity")})
        msgs.append({"role": "assistant", "content": text})
        print(f"[{conv}] {round(time.time() - t0, 1)}s Q: {q}\n   A: {text[:600]}\n   activity: {state.get('activity')}", flush=True)
    return out


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    model = sys.argv[2] if len(sys.argv) > 2 else "qwen3.5:2b"
    rnd = sys.argv[3] if len(sys.argv) > 3 else "1"
    if rnd == "2":
        A_TURNS, B_TURNS = A2_TURNS, B2_TURNS
    if rnd == "4":
        A_TURNS, B_TURNS = A4_TURNS, B4_TURNS
    if rnd.startswith("3"):
        A_TURNS, B_TURNS = A3_TURNS, B3_TURNS
    res = {"model": model, "network": "NONE (part B = offline FIXTURE corpus)", "P": capture_prompt(model)}
    print("P:", json.dumps(res["P"], ensure_ascii=False)[:700], flush=True)
    p, url = serve([PY, "-m", "rightware.gui", "serve", "--port", "8000", "--model", model, "--ambiente", "cloud"], 8000)
    try:
        res["A"] = chat(8000, url, A_TURNS, model, "op01-a")
    finally:
        p.terminate(); p.wait(10)
    p, url = serve([PY, "-m", "labs.op01.serve_fixture", "--port", "8000", "--model", model], 8000)
    try:
        res["B"] = chat(8000, url, B_TURNS, model, "op01-b")
    finally:
        p.terminate(); p.wait(10)
    (out / f"acceptance-r{rnd}-{model.replace(':', '_')}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
