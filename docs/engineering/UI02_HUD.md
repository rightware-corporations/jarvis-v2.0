# UI-02 — RIGHTWARE JARVIS HUD sobre a interface React original do OpenJarvis (implementação)

Estado: **implementado no ramo `integration/jrv-ui02-hud-20261123`, PR Draft para `develop`. O merge exige nova revisão.** Data: 23/11/2026. Plano de origem: `UI02_HUD_PLAN.md`.
Classificação das afirmações: **FACTO** (medido ou testado neste host ou em CI), **INFERÊNCIA**, **NÃO VERIFICADO**.

## 1. Arquitectura (sem segundo frontend, sem segundo backend)
- **Frontend:** o mesmo frontend React do pin `f21d902`, obtido por `git archive` para `.runtime/gui`. O overlay RIGHTWARE (`rightware/gui/frontend/`) é copiado para `frontend/rightware/` no build isolado, e o vendor nunca é escrito.
  - `vite.rightware.ts` faz merge da `vite.config.ts` do pin e acrescenta o plugin `rightwareOverlay`. O plugin:
    - troca, por `resolveId`, os **10 módulos** listados em `overlay.manifest.json`, cada um com `upstream_sha256`;
    - aplica **23 substituições de texto declaradas** (PT-MZ, via `__rwT`; 2 acrescentadas no ramo WEB-01: aviso de motor indisponível) e o título HTML;
    - remove o PWA/service worker.

    Se o hash upstream de um módulo substituído, ou um padrão de texto, deixar de coincidir (por exemplo, numa mudança de pin), **o build falha**. Teste: `tests/test_ui02_hud.py::OverlayManifest`.
  - `rightware/gui/runtime.py` regista no manifesto do runtime o `overlay_tree_sha256`.
- **Backend:** a mesma ChatBridge da UI-01 (TextFacade/TaskEntry + ControlPlane) atrás da PolicyApp (deny-by-default). Rotas novas na allowlist:
  - `GET /v1/rightware/state`
  - `POST /v1/rightware/tasks/{request,authorize,cancel}`

  A HUD é outra vista **do mesmo** ControlPlane. Os comandos `/tarefa` e `/autorizar` no chat continuam a funcionar.

## 2. O que foi entregue (os 10 pontos autorizados)
| # | Item | Implementação | Estado |
|---|---|---|---|
| 1 | Overlay reproduzível, vendor intacto | Manifesto com hashes; build falha em deriva; pin inalterado | FACTO (tsc/vitest/E2E) |
| 2 | Núcleo JARVIS animado por estados reais | `JarvisCore.tsx`; modo derivado só de `/v1/rightware/state` e do stream: offline, ready, thinking, mission, verified, unverified, failed | FACTO (Vitest + U5) |
| 3 | MissionsPanel, ExecutionTimeline, Capacidades | `/agents` → Missões, `/data-sources` → Capacidades, `/dashboard` → HUD completa, painel lateral no chat. Capacidades não integradas mostram o estado e o motivo, nunca dados simulados (finanças sem cotações) | FACTO |
| 4 | PT-MZ por omissão + inglês | `src/i18n` (`rw-lang`), alternador na barra lateral | FACTO (U2) |
| 5 | Autenticação local e sessões explícitas | Token de arranque de uso local, `/rw-login?t=` → cookie `rw_session` (HttpOnly, SameSite=Strict), ficheiro `.runtime/gui/session-url` com modo 0600; tudo exige sessão excepto os ficheiros estáticos do bundle. Cabeçalho `X-Rightware-Conversation` → sessão de conversa por (sessão local, conversa, modelo) | FACTO (unit + U1, U3) |
| 6 | Cancelamento efectivo | Desconexão do cliente (Stop) → `facade.cancel` → `adapter.abort()`, que **fecha os sockets** registados por um `httpcore` network backend próprio (fechar o cliente httpx não interrompe um `read` bloqueado; medido) | FACTO (unit com servidor lento: abort < 2 s; real: Ollama regista **499** no momento do Stop; a pergunta seguinte responde em 8,1 s) |
| 7 | CPU e `num_thread` | Ver §3 | FACTO |
| 8 | Autorização só por código | `authorize` exige 6 hex escritos (sem código: 400 `CODIGO_EM_FALTA_OU_INVALIDO`); o botão está desactivado sem código válido; o código errado é consumido e recusado; o estado nunca expõe o código | FACTO (unit + U7) |
| 9 | Frontend, TS, Vitest e E2E em CI | `.github/workflows/ui02-frontend.yml`: setup do pin, `tsc --noEmit`, Vitest (RIGHTWARE + upstream não substituído) e E2E Chromium contra `labs/ui02/serve_fake.py` (**FAKE, marcado `[FAKE-CI]`**: evidência de interface, nunca de modelo) | FACTO (ver §5) |
| 10 | Missão goose real pela GUI | Ver §4 | ver §4 |

## 3. Orçamento de CPU (R-7)
- **Causa medida:** a animação upstream `hud-grid-drift` (background-position em ecrã inteiro) e os `backdrop-filter` custavam **241 %** de CPU ao Chromium headless sem GPU.
- **Mitigação:**
  - ambos desactivados;
  - `html.rw-busy` pausa toda a animação enquanto o modelo ou uma missão trabalham;
  - o núcleo roda com `steps()` (≈ 2 repaints/s);
  - `MotionConfig reducedMotion` enquanto ocupado;
  - polling de 1,5 s (ocupado), 5 s (inactivo) e 15 s (separador oculto).
- **Medido (U6, 30 s idle):**
  - real: chat **3,7 %**, HUD **4 %** de um núcleo;
  - CI: 0,4 % / 0,4 %;
  - orçamento: ≤ 10 %.
- **`num_thread`:**
  - **FACTO:** o endpoint OpenAI-compatível do Ollama ignora `options.num_thread` (medido).
  - O Model Tap (`rightware/gateway/model_tap.py --num-thread N`) cria um modelo derivado `<modelo>-rw-t<N>` via `/api/create` com `parameters.num_thread` e reescreve o nome do modelo nos pedidos de chat.
  - **FACTO:** esse parâmetro é respeitado (1 thread: 24,6 s contra 8,0 s base).
  - O adaptador goose usa N = núcleos − 1 (aqui, 3).
  - Declarado em `PARITY.json` com o motivo "UI-02 R-7 controlled num_thread"; `model_requests.jsonl` regista `num_thread_pinned` e `model_forwarded`.

## 4. Missão goose real pela GUI
**FACTO: RESULTADO VERIFICADO.** Missão `pesquisa-fixture-goose` (p2-p7ygr7gx), em 23/11/2026, das 13:39:53 às 13:48:18 UTC, com o Qwen 3.5 4b real no Ollama local.
- **Pedido e autorização na HUD (Missões), no Chromium:**
  - sem código: 400;
  - botão desactivado até haver um código válido;
  - código `000000`: recusado ("inválido… Nada foi executado");
  - o código correcto, escrito, iniciou a missão.
- **Veredicto do verificador RIGHTWARE:** `TASK_VERIFIED_LIMITED`; `verified=true`; 490,3 s.
  - 7 recibos: `web_open`, 5×`web_follow` (um `HTTP_ERROR` recuperado de 503), `submit_report`.
  - 4/4 objectivos `PAGE_OBSERVED`.
  - Correspondência HTTP↔recibos: 6/6.
  - Gate semântico do relatório: PASS.
  - Cadeia de submissão válida; 0 violações.
  - Isolamento confirmado: a fixture e a Internet estão BLOQUEADAS para o contentor goose; só o Gateway é alcançável.
- **`num_thread`:** todos os 6 pedidos de chat com `num_thread_pinned=3` e `model_forwarded=qwen3.5:4b-rw-t3`.
- **CPU durante a missão:**
  - anfitrião (4 vCPU): 58,9 % em média;
  - Chromium com a HUD aberta: 3,1 % em média, máximo 15,9 %.
- **Evidência:** `docs/evidence/ui02/goose-real/`:
  - `results-real-goose.json`;
  - `verification.json`;
  - `cpu_threads_summary.json`;
  - capturas de ecrã "em execução" e "resultado".
- **Limites honestos:**
  - É **uma** execução verificada. Na UI-01 houve 4 tentativas pela GUI sem verificação, antes das mitigações R-7.
  - Uma execução não estabelece taxa de sucesso, por isso a capacidade continua marcada **PARCIAL** na HUD.
  - O catálogo é SINTÉTICO (fixture isolada), não é Internet pública.
  - A captura "em execução" foi tirada 2,5 s após o clique, antes de o pedido de autorização regressar (≤ 3 s); por isso ainda mostra o estado anterior (recusa do código errado). Não é um erro de execução.

## 5. Testes e CI
- **Python:** `vendor/openjarvis/.venv/bin/python -m unittest discover -s tests`, com `tests/test_ui02_hud.py` novo e `tests/test_ui01_gui.py` actualizado.
- **Frontend:**
  - `python -m rightware.gui frontend-check`: `tsc` rc 0;
  - Vitest: 21 ficheiros, 116 testes (RIGHTWARE + upstream não substituído; os 3 testes de módulos substituídos estão em `replacedTests`).
- **E2E real (local, Qwen 3.5 2b, porta 8000):** U1–U7 PASS. Ficheiros:
  - `docs/evidence/ui02/real/results-real-run1.json`;
  - repetição do U4 após a correcção do abort: `results-real-stop-rerun.json`.
- **E2E FAKE (CI):** U1–U7. O run 45185214218 (`7b7875e`) falhou em **U5**: o runner não tem Ollama e o núcleo ficou `offline`. Correcção: sonda de motor FAKE no `serve_fake.py` (`df46209`).
- **Nota de honestidade:** no run real 1, o U4 passou **indevidamente** (a resposta seguinte foi `MODEL_BUSY`; o critério era fraco). Isso revelou que fechar o cliente httpx não aborta a geração. A correcção é o abort por socket, o critério passou a rejeitar `MODEL_BUSY`, e a repetição real está no ficheiro acima.

## 6. Limites (o que a UI-02 **não** faz)
- Modo de operador único local: o código é mostrado na própria HUD para ser **escrito**. A entrega fora da banda (para outro dispositivo) fica para B6.
- Voz, inteligência financeira, memória persistente e SIC: **NÃO INTEGRADAS**. Internet pública e acções Windows: **BLOQUEADAS** (WEB-01 requer autorização própria; ver `WEB01_PUBLIC_RESEARCH_PLAN.md`).
- A GUI escuta só em 127.0.0.1, sem túneis nem deploy público.
- Comentário do modelo é sempre mostrado como **NÃO verificado**; o veredicto vem dos recibos e do verificador.
