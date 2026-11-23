# Investigação — degradação do goose através da GUI face ao P3A

Data: 23/11/2026. Os dados brutos estão em `docs/evidence/ui01/goose_gui_perf_investigation.json`.

Método: comparar métricas reais (inferência, CPU, memória, contexto e overhead) sem assumir a causa. O ensaio controlado foi feito com o host acabado de reiniciar: missão via CLI e via GUI, com monitorização a cada 5 s.

## 1. O trabalho do modelo é o mesmo (FACTO)

| Corrida | Caminho | Estado | Fim | Intervalos entre pedidos ao modelo (s) |
|---|---|---|---|---|
| P3A real | CLI | VERIFICADO | 0, 271,9 s | 71, 15, 35, 21, 83 |
| R1 corrida 4 | CLI | VERIFICADO | 0, 356,8 s | 188, 13, 30, 27, 68 |
| GUI tentativa 1 | GUI | PARCIAL | TIMED_OUT 900 s | 302, 132, 326 |
| GUI tentativa 2 | GUI | PARCIAL | TIMED_OUT 900 s | 313, 131, 332 |
| GUI tentativa 3 | GUI | FALHADA | saída 1, 793 s | 179, 61, 130, 123 |
| **Controlada CLI** | CLI | **VERIFICADO** | 0, **294,6 s** | 61, 16, 32, 17, 74, 18 |
| **Controlada GUI** | GUI | FALHADA | saída 1, 873 s | **202, 60, 148, 166** |

**Igual em todas as corridas:**
- mensagens por pedido (2, 4, 6, 10, 12…);
- tokens de entrada por turno (cerca de 2,1–3,1 mil) e de saída (150–240);
- `num_ctx` 65536.

O contexto e o volume não explicam a diferença. **Só muda o tempo por turno: 3–9×.**

## 2. Hipóteses testadas

| Hipótese | Teste | Resultado |
|---|---|---|
| Mais contexto ou mais turnos pela GUI | tokens e mensagens por turno (§1) | **Refutada**: são iguais |
| Inferência do Ollama do anfitrião (conversa) em paralelo | logs do Ollama do anfitrião nas janelas das tentativas 1–3 | **Refutada**: nenhum `/api/chat` nessas janelas |
| Memória | MemAvailable mínimo: CLI 8558 MB, GUI 8315 MB; contentor Ollama 6,2–6,4 GB | **Refutada**: sem pressão de memória |
| Steal do hipervisor | máximo: CLI 2,1%, GUI 2,0% | **Refutada** |
| Overhead da bridge e do servidor GUI | `python` (servidor) 0,5% de CPU durante a corrida | **Refutada** |
| **Contenção de CPU pelo browser com a GUI aberta** | CPU instantâneo por processo e micro-benchmark controlado | **Confirmada**, ver §3 |

## 3. Causa medida

- **Na corrida controlada:**
  - CLI: contentor Ollama com 364,5% de CPU em média, load máximo 4,3.
  - GUI: contentor Ollama com **253,7%**, load máximo 7,4, e **chrome-headless a 132%** (instantâneo).
- **Micro-benchmark** `qwen3.5:4b`, `num_ctx` 65536, prompt de 4875 tokens, 128 tokens gerados:

| Condição | CPU do browser | tokens/s de geração | Total |
|---|---|---|---|
| E0: sem browser | — | **4,61** | 28,2 s |
| E1: GUI original aberta (animações normais) | **241%** | **1,01** | 128,6 s |
| E2: GUI aberta com `prefers-reduced-motion` | 0,4% | 5,14 | 25,5 s |
| E3: um núcleo ocupado por um ciclo activo | — | **0,79** | 167,5 s |
| E4: GUI aberta, Ollama com `num_thread=3` | 238% | **4,35** | 70,7 s* |
| E5: sem browser, `num_thread=3` | — | 4,54 | 68,8 s* |

\* O prompt foi re-avaliado porque mudou o `num_thread`.

**Conclusão (FACTO):**
1. A interface original, aberta num browser **sem aceleração GPU** e na mesma máquina de CPU, gasta 1,3–2,4 núcleos com animações.
2. O llama.cpp com tantas threads como núcleos degrada cerca de 5× quando outro processo ocupa um núcleo. E3 reproduz o efeito sem browser.
3. Na CLI não há browser, e o goose passa.
4. As saídas com código 1 aos 793–873 s são **INFERÊNCIA**: turnos demasiado lentos levam o goose a falhar. Não foi verificado no código do goose.

**Limite desta prova:** foi medida com Chromium headless (renderização por software). Um browser com GPU num PC real pode custar menos CPU (NÃO VERIFICADO). O caso relevante, Ollama e browser na mesma máquina sem GPU, é exactamente o do PC do Issa se não houver GPU.

## 4. Mitigações (para UI-02; nada foi alterado no runtime nesta revisão)

1. **Orçamento de CPU da interface:**
   - nenhuma animação contínua enquanto há inferência ou missão activa;
   - respeitar `prefers-reduced-motion`;
   - núcleo animado com `requestAnimationFrame` limitado e pausado em segundo plano.

   E2 mostra que, sem animação, o efeito desaparece.
2. **`num_thread = núcleos − 1`** para o Ollama da missão. E4 recupera de 1,0 para 4,35 tokens/s; E5 mostra custo próximo de zero sem contenção. Formas de o aplicar:
   - injectar a opção no `model_tap`, o que é uma alteração declarada em PARITY;
   - ou limitar o CPU do contentor (`--cpus`).
3. Mostrar na GUI o tempo por turno e a degradação, sem a esconder.
