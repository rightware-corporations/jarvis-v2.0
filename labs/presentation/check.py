"""Essential presentation check: identity + Issa-like questions through the GUI HTTP API (real local Qwen)."""
import json
import sys
from pathlib import Path

from labs.op01.acceptance import PY, chat, serve

Q = ["Olá JARVIS, quem és tu?",
     "Faz-me um plano financeiro para aumentar os meus lucros.",
     "Ajuda-me a organizar as minhas receitas e despesas.",
     "Desenvolve uma estratégia financeira para os próximos 90 dias.",
     "Como posso melhorar as minhas margens de lucro?",
     "Qual é a cotação actual do XAU/USD?",
     "Qual é a taxa de câmbio do dólar em relação ao metical?",
     "Pesquisa informação actualizada sobre os factores que influenciam o preço do ouro."]

Q2 = ["Olá JARVIS, bom dia!",
      "Ajuda-me a organizar as minhas receitas e despesas.",
      "Se eu vender 120 unidades a 350 meticais e cada uma me custar 210 meticais, qual é a minha margem de lucro em percentagem?",
      "Qual é a taxa de câmbio do dólar em relação ao metical?",
      "Quantos meticais preciso para comprar 250 dólares à taxa de venda?",
      "Qual é a cotação actual do XAU/USD?"]

if __name__ == "__main__":
    out, mode = Path(sys.argv[1]), sys.argv[2:]
    questions = Q2 if "--q2" in mode else (["Qual é a cotação actual do XAU/USD?"] if "--xau" in mode else Q)
    mode = [m for m in mode if m not in ("--q2", "--xau")]
    out.mkdir(parents=True, exist_ok=True)
    p, url = serve([PY, "-m", "labs.presentation.serve", *mode, "--port", "8000"], 8000)
    try:
        res = chat(8000, url, questions, "qwen3.5:2b", "issa-check")
    finally:
        p.terminate(); p.wait(10)
    (out / ("presentation-check-q2.json" if questions is Q2 else "presentation-check-xau.json" if len(questions) == 1
            else "presentation-check.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1))
