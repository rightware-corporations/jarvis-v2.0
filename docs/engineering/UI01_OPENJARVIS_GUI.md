# UI-01 — interface original do OpenJarvis com o runtime RIGHTWARE

Estado (Parte I, histórica): **investigação e execução local concluídas; integração por implementar** (aguarda os gates G-MERGE e G-IMPL). **Estado actual: ver a Parte II (G-IMPL implementado).** Data: 23/11/2026. Base: `develop` `ba85c2a85d8290685eba9cd78dfe371eb3e29cc2`; vendor `f21d902f4d3bd7f0f3f138f1a4613019a394b549` (inalterado).

Legenda: **FACTO** = executado ou lido no código no pin; **INFERÊNCIA** = deduzido do código, sem execução; **NÃO VERIFICADO**.

## 1. Como a GUI original foi executada (sem tocar no vendor)

**FACTO.** Cópia isolada do pin, fora do repositório:

```bash
git -C vendor/openjarvis archive f21d902f4d3bd7f0f3f138f1a4613019a394b549 | tar -x -C "$W/oj"
cd "$W/oj" && UV_PROJECT_ENVIRONMENT="$W/venv" SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+gf21d902 uv sync --frozen --extra server --no-dev
cd "$W/oj/frontend" && npx -y npm@11.19.0 ci && npx -y npm@11.19.0 run build   # gera src/openjarvis/server/static
```

O `package.json` exige npm ≥ 11.19 <12 e o ambiente tem npm 10.9. Por isso usa-se `npx npm@11.19.0`, que não instala nada no sistema.

**Arranque:**
- Ollama 0.40.15 em `127.0.0.1:11434`, com `qwen3.5:2b` (`0689d440…`) e `qwen3.5:4b` (`d8b0f5e9…`).
- Servidor, com `HOME` isolado e `config.toml` sem agente, sem telemetria e sem analytics:

  ```bash
  HOME="$W/home" "$W/venv/bin/jarvis" serve --host 127.0.0.1 --port 8000 -e ollama -m qwen3.5:4b
  ```

  O servidor serve a própria GUI compilada em `http://127.0.0.1:8000/`.

**`jarvis gui`** (`src/openjarvis/cli/gui_cmd.py:466`) **não** foi usado tal como está, porque:
1. corre `uv run --extra desktop jarvis start` dentro da checkout do vendor, o que sincroniza o `.venv` do vendor com o extra `desktop` (faster-whisper e outros);
2. corre `npm install` em `vendor/openjarvis/frontend`;
3. arranca o Vite em modo dev.

Tudo isto escreveria dentro do submódulo. O modo equivalente usado aqui é o servidor a servir o build estático.

**Observado no arranque (FACTO):**
- o servidor faz uma verificação de versão ("v1.0.4 disponível"), que é um pedido de saída à Internet;
- `Scheduler: active`;
- `openjarvis_rust` está ausente, por isso o rate limiter fica desactivado (aviso).

## 2. Testes pela GUI original, sem alterações

| Acção na GUI | Esperado | Obtido | Evidência |
|---|---|---|---|
| Abrir `http://127.0.0.1:8000/` | Interface original | FACTO: Chat/Dashboard/Data Sources/Agents/Logs/Settings; modal de opt-in de analytics (recusado com "Continue without sharing") | `docs/evidence/ui01/01-gui-landing-upstream.png` |
| Pergunta em PT com o código `UI01-7Q3K` | Resposta do modelo real | FACTO: "A capital de Moçambique é Maputo." Rodapé da GUI: `ollama - qwen3.5:2b - 91.2s`. O pedido do browser foi `POST /v1/chat/completions` com o modelo `qwen3.5:2b`, `stream:true` e sem `tools`. O servidor registou 200. O Ollama registou `POST /api/chat` 200 em 1m30s (arranque a frio em CPU) | `02-gui-chat-pt-real-qwen.png` |
| Controlo: Ollama parado, enviar mensagem | Nenhuma resposta fabricada | FACTO: a GUI não enviou o pedido e não apareceu nenhuma resposta. **Mas também não mostrou um erro explícito** (lacuna de UX). | `03-gui-control-ollama-down.png` |

O selector de modelo escolhe por omissão o primeiro modelo da lista (`qwen3.5:2b`) e não o `-m` do servidor. A interface só está em inglês: não há i18n em `frontend/src`.

## 3. Mapa de pontos de integração (a–f)

| Capacidade | Componente GUI/API no pin | Ponto de integração RIGHTWARE | Estado | Esforço | Risco | Prova |
|---|---|---|---|---|---|---|
| a) Conversa real com Qwen | `frontend/src/lib/sse.ts:12-22` (`POST /v1/chat/completions`); `components/Chat/InputArea.tsx:378`; `server/routes.py:158-170` (usa o agente do servidor se existir; senão vai directo ao engine) | Adaptador RIGHTWARE em frente do `create_app` do upstream: as mensagens normais seguem o caminho **sem ferramentas** (TextFacade/engine, sem agente, `tools` removido). Os comandos `/tarefas`, `/tarefa`, `/autorizar`, `/estado` e `/cancelar` vão para o ControlPlane, a mesma gramática da consola. | Funciona no upstream sem ferramentas; RIGHTWARE não integrado | M | Médio | FACTO (§2) |
| b) Modelos e idiomas | `server/routes.py:1106` (`GET /v1/models`), `:1150` (pull), `:1188` (delete); `core/config.py:609` (`intelligence.default_model`) | Lista de modelos só de leitura; pull e delete negados (efeitos no anfitrião); PT por omissão no prompt de sistema RIGHTWARE | GUI só em inglês; selector funciona | S (modelo) / L (i18n da GUI) | Baixo | FACTO |
| c) Control Plane e autorizações | `server/approval_routes.py:48-77` + `frontend/src/components/ApprovalBell.tsx:3,58,68` (fila de aprovações do upstream) | Pedido `/tarefa` na conversa → `ControlPlane.request` → resposta com o código. A autorização é feita com `/autorizar CÓDIGO` na conversa; a aprovação com um clique na campainha **não** substitui o código (decisão do operador). Recusas e estados aparecem como mensagens. | Não integrado | M | Alto (autorização) | INFERÊNCIA (código) |
| d) Goose e Gateway P3A | Não existe no upstream | O mesmo `ControlPlane(goose=GooseMission)` da consola, com a capacidade activada pelo anfitrião quando o servidor RIGHTWARE arranca | Não integrado; depende do P3A (PR #29) | M | Médio | — |
| e) Tarefas, actividade, recibos, resultados | `server/ws_bridge.py:66` (`/v1/agents/events`), `api_routes.py:402` (`/v1/traces`), `pages/LogsPage.tsx`, `pages/AgentsPage.tsx` | Resultados e recibos do ControlPlane devolvidos como mensagem da conversa (estado, recibos, comentário NÃO verificado), como na consola; registo em evidência local | Não integrado | M | Médio | INFERÊNCIA |
| f) Ferramentas do OpenJarvis | `cli/serve.py:29` (`_DEFAULT_TOOLS = think, calculator, web_search`), `:42-61`, `:307-372` (agente `orchestrator` por omissão, `core/config.py:1167`); `api_routes.py:77` (`/v1/agents`, spawn com ferramentas arbitrárias); `agent_manager_routes.py:1641,2366` | Desactivadas por omissão. Qualquer ferramenta futura só entra como executor registado no ControlPlane, com política, recibos e verificador. | Upstream com ferramentas por omissão | — | **Crítico** | FACTO (código) |

## 4. Modelo de não-contorno: caminhos do servidor upstream que executam efeitos

| Caminho (no pin) | Efeito | Na configuração por omissão do upstream | Classificação no produto RIGHTWARE (proposta) |
|---|---|---|---|
| `POST /v1/chat/completions` com agente do servidor (`serve.py:307-372`, por omissão `orchestrator` + `think/calculator/web_search`) | Ferramentas executadas pelo agente fora do RIGHTWARE | **CONTORNA** | DESACTIVADO (sem agente; `tools` removido do pedido) |
| `POST /v1/chat/completions` sem agente (`routes.py:161-170`, 795-850) | `tool_calls` devolvidos ao cliente, não executados | controlado | CONTROLADO (tool-free) |
| `WS /v1/chat/stream` (`api_routes.py:766`) | Só o engine, sem agente (comentário no código) | controlado | DESACTIVADO (a GUI não o usa) |
| `/v1/agents` (`api_routes.py:77`; spawn/message com `tools` arbitrárias, `:151-196`) | Agentes com ferramentas | **CONTORNA** | DESACTIVADO |
| `/v1/managed-agents`, `/v1/templates`, `/v1/tools`, `/v1/channels/sendblue` (`agent_manager_routes.py:1641-2416`) | Agentes geridos, credenciais, mensagens | **CONTORNA** | DESACTIVADO |
| `POST /api/research` (`research_router.py:569`) | Agente de pesquisa com web | **CONTORNA** (Internet) | DESACTIVADO (Internet não autorizada) |
| `/v1/connectors/*`, `/v1/connectors/upload/ingest*` (`connectors_router.py:131`, `upload_router.py:18`) | OAuth, sync de dados pessoais, ficheiros | **CONTORNA** | DESACTIVADO |
| `/webhooks/*`, `POST /v1/channels/send` | Mensagens externas | **CONTORNA** | DESACTIVADO |
| `/api/digest/*`, scheduler (`app.py:174,301`; "Scheduler: active") | Tarefas agendadas com ferramentas | **CONTORNA** | DESACTIVADO (o scheduler não arranca) |
| `POST /v1/models/pull`, `DELETE /v1/models/*`, `/v1/cloud/reload` | Descarga ou remoção de modelos; fornecedores cloud pagos | efeito no anfitrião | DESACTIVADO |
| `/v1/memory/store|index`, `/v1/skills`, `/v1/learning/*`, `/v1/optimize/*`, `/v1/feedback`, `PUT /v1/budget/limits`, `POST /v1/telemetry/reset` | Escritas locais (memória, skills, aprendizagem) | escrita | DESACTIVADO (a memória fica NÃO INTEGRADA) |
| `POST /v1/approvals/{id}/approve|deny` | Aprova acções de agentes proactivos do upstream | aprovação fora do RIGHTWARE | DESACTIVADO (a autorização é do ControlPlane) |
| `/v1/speech/*` | STT/TTS local | sem efeito externo (faster-whisper não instalado) | DESACTIVADO até haver gate de voz |
| `POST /v1/analytics/preference` + `posthog-js` | Envio de analytics para a PostHog | saída à Internet se activado | DESACTIVADO (forçado `enabled=false`) |
| Verificação de versão no arranque (`cli/__init__.py:77-86`) | Pedido à Internet | saída | DESACTIVADO no arranque RIGHTWARE |
| GET de leitura (`/health`, `/v1/info`, `/v1/models`, `/v1/savings`, `/v1/telemetry/*`, `/v1/approvals/pending` vazio) | Nenhum | — | PERMITIDO |

**Conclusão:** a configuração por omissão do upstream tem vários caminhos **CONTORNA**. Na execução local usou-se só a conversa sem agente; nenhum outro caminho foi exercido. **A GUI não pode ser usada pelo Issa antes do adaptador de política (§5).**

## 5. Proposta G-IMPL (aguarda autorização do operador)

**Branch:** uma branch curta `integration/jrv-ui01-gui-20261123`, a partir de `develop` (depois do merge do P3A, se for autorizado) e com uma única PR para `develop`.

**Ficheiros**, todos **fora do vendor**:
- `rightware/gui/__init__.py`
- `rightware/gui/server.py`: constrói `openjarvis.server.app.create_app` com o engine Ollama, **sem agente e sem scheduler**; bind só em `127.0.0.1`; sem verificação de versão.
- `rightware/gui/route_policy.py`: middleware ASGI **deny-by-default**, com allowlist de método e caminho (só os GET de leitura da §4 e `POST /v1/chat/completions`). Tudo o resto recebe 403 com o JSON `{"error":"BLOQUEADO_PELA_POLITICA_RIGHTWARE","path":…}`, que fica registado e é visível na GUI como erro.
- `rightware/gui/chat_bridge.py`: as mensagens de conversa vão para o caminho sem ferramentas (remove `tools`). As mensagens `/tarefas`, `/tarefa`, `/autorizar`, `/estado` e `/cancelar` vão para o `ControlPlane` existente, incluindo a capacidade P1 e a missão goose quando o anfitrião as activa. A resposta sai em SSE no formato que a GUI já consome.
- `rightware/gui/analytics_off.py`: força analytics desligado e devolve uma identidade sem chave.
- `configs/gui/openjarvis-gui.toml`: configuração RIGHTWARE.
- `jarvis.py`: subcomando `gui` (launcher).
- `tests/test_ui01_gui_policy.py`: a allowlist, todas as rotas CONTORNA negadas e o encaminhamento de comandos.
- `labs/ui01/gui_e2e.py`: ensaio Playwright pela GUI real.
- `docs/engineering/UI01_OPENJARVIS_GUI.md`.

**Frontend:** usar o build do pin tal como está. Nenhum fork do frontend.

**Fora do âmbito:** i18n PT da GUI (exigiria alterar o frontend do vendor ou criar um overlay). Fica NÃO INTEGRADO até haver decisão.

## 6. Estado das capacidades (sem simulação)

| Capacidade | Existe no OpenJarvis (prova) | Integrada com RIGHTWARE | Testada | Estado | Bloqueio / próxima acção |
|---|---|---|---|---|---|
| Pesquisa financeira | Só genérica: `/api/research` com web (`research_router.py:569`) | Não | Não | NÃO INTEGRADA | Exige Internet autorizada e fontes datadas; ordens e efeitos financeiros não autorizados |
| Internet | `web_search` em `_DEFAULT_TOOLS`, research, browser (`ToolsConfig.browser`) | Não (TE-P2D parcial) | Não | BLOQUEADA | Política de rede da plataforma e TE-P2D; gate próprio |
| Voz | `/v1/speech/*` (`api_routes.py:990-1177`), extra `desktop` (faster-whisper) | Não | Não | NÃO INTEGRADA | Extra `desktop` não instalado; validação em hardware real |
| Memória | `/v1/memory/*` (`api_routes.py:204`), injecção de contexto em `routes.py:175-180` | Não | Não | NÃO INTEGRADA | Consentimento e persistência privada (SIC/IAM) |
| Acesso ao computador | Ferramentas de ficheiros e shell do upstream, agentes | Não | Não | BLOQUEADA | Companion Windows autorizado; nunca acesso genérico a shell |
| Conversa real | `/v1/chat/completions` | Não (upstream directo) | **Sim, pela GUI** | PARCIAL | Adaptador §5 |
| Tarefas supervisionadas (P1, goose) | Não existe no upstream | Na consola, sim; na GUI, não | Consola: sim (P1/P2/P3A); GUI: não | NÃO INTEGRADA NA GUI | Adaptador §5 + G-IMPL |

## 7. Acesso

- **Local, verificado:** `http://127.0.0.1:8000/` no ambiente remoto de engenharia. Não é acessível ao operador nem ao Issa fora deste ambiente.
- **Acesso remoto ao Issa:** não autorizado. Opções para decisão:
  1. correr localmente no PC do Issa (exige instalação autorizada);
  2. túnel autenticado (exposição de rede, autenticação e TLS por decidir);
  3. host privado HTTPS com autenticação e runtime persistente.

  Todas exigem decisão do operador e um gate próprio.

---

# Parte II — G-IMPL implementado (23/11/2026, branch `integration/jrv-ui01-gui-20261123`)

A Parte I descreve a investigação feita antes da implementação, quando a GUI original corria sem a camada RIGHTWARE. **Esta parte é o estado actual.**

## 8. Arquitectura implementada

```
browser ──127.0.0.1:8000──> PolicyApp (rightware/gui/policy.py, camada EXTERNA deny-by-default)
   │  allowlist exacta (método, caminho canónico) + build estático do frontend ORIGINAL (pin, inalterado)
   ├─ GET /health, GET /v1/info ─────────────> app OpenJarvis ORIGINAL (create_app, sem agente/scheduler/…)
   ├─ GET /v1/models, POST /v1/chat/completions, analytics (só "não partilhar") ─> ChatBridge (rightware/gui/bridge.py)
   │       conversa  → TaskEntry/TextFacade RIGHTWARE (sem ferramentas; o anfitrião é dono do histórico)
   │       /tarefas /tarefa /autorizar /estado /cancelar → o MESMO ControlPlane (P1 + goose/Gateway P3A)
   └─ tudo o resto → 403 JSON / WebSocket 1008 + audit.jsonl (sem conteúdo)
```

**Como se corre:**

```bash
python jarvis.py gui setup
python jarvis.py gui serve --model qwen3.5:2b --model qwen3.5:4b [--tarefa-ensaio] [--missao-goose --goose-bin B --goose-ollama-dir O --goose-models-dir D]
```

- `setup` corre uma vez: cria um venv isolado com `uv sync --frozen --extra server` a partir do lock do pin e faz o build do frontend original com `npx npm@11.19.0`. Tudo fica em `.runtime/gui`.
- O vendor não é tocado.

**Frontend:** o build do pin sem alterações. Não há fork, nem segundo frontend, nem segundo backend, nem um segundo mecanismo de autorização.

## 9. Inventário deny-by-default (B1)

Ficheiro: `docs/evidence/ui01/route_inventory.json`. Lista **114** rotas do servidor no pin, cada uma com `ficheiro:linha` e a decisão:
- **6 PERMITIDAS**:
  - `GET /health` e `GET /v1/info` (app original);
  - `GET /v1/models`, `POST /v1/chat/completions`, `GET /v1/analytics/identity` e `POST /v1/analytics/preference` (bridge RIGHTWARE). A preferência de analytics só aceita `enabled:false`.
- **7 páginas SPA** (`/`, `/dashboard`, `/settings`, `/get-started`, `/data-sources`, `/agents`, `/logs`): servem o `index.html` do build. As rotas originais com o mesmo caminho, como o `/dashboard` HTML do upstream, ficam inacessíveis.
- **Todas as outras são NEGADAS**:
  - agentes e agentes geridos, ferramentas e credenciais;
  - aprovações, pesquisa (`/api/research`), upload e conectores;
  - memória, skills, scheduler/digest, webhooks, canais;
  - operações sobre modelos (pull, delete, `cloud/reload`);
  - telemetria, learning, optimize, feedback, budget;
  - WebSockets (`/v1/chat/stream`, `/v1/agents/events`);
  - `/docs` e `/openapi.json`.

O teste `test_every_route_of_the_pinned_openjarvis_server_is_denied_except_the_allowlist` percorre o mesmo inventário.

**Formas alternativas recusadas, nunca normalizadas** (testes e browser):
- maiúsculas, `//`, barra final, `./` e `../`, percent-encoding, backslash e não-ASCII;
- métodos `HEAD`, `OPTIONS` e `PUT` sobre rotas permitidas;
- `Host` que não seja loopback ou que venha duplicado;
- `Origin` cruzado num POST;
- `Upgrade` WebSocket.

Um erro dentro da política dá 403 (fail-closed).

**Browser:** CSP `connect-src 'self'`, de modo que PostHog e Supabase ficam bloqueados pelo próprio browser. Também `X-Frame-Options: DENY`, `nosniff` e `no-store`.

**Startup limpo** (`labs/ui01/startup_audit.py`, processo real com proxy-isco; `docs/evidence/ui01/startup_audit.json`):
- 0 tentativas de saída;
- 0 sockets fora de loopback;
- 0 processos-filho;
- 0 ficheiros criados em `HOME`/`OPENJARVIS_HOME`;
- 2 threads.

Não há version check, porque nunca se passa por `jarvis serve`. Scheduler, canais, memória, speech, MCP e webhooks não são construídos. Telemetria, traces e analytics estão `false`; a config é recusada se não estiverem.

## 10. Conversa real (B2)

| Item | Resultado (FACTO) |
|---|---|
| Modelo | `qwen3.5:2b` (digest `0689d44085e0…`), Ollama 0.40.15, CPU com 4 vCPU e sem GPU, `num_ctx` 4096, `num_predict` 256 |
| PT (B5.2) | "A capital de Moçambique é Maputo, e a língua oficial é o português." Acentos e UTF-8 correctos |
| EN (B5.3) | "The capital of Japan is Tokyo." |
| Continuidade e isolamento (B5.4) | Na mesma conversa a resposta foi "ZEBRA-41"; numa conversa nova foi "NENHUM". O histórico é do anfitrião: um turno de assistente forjado pelo cliente não é aceite (teste) |
| Ferramentas | Não são oferecidas ao modelo. Um pedido com `tools`, `functions` ou `tool_choice` recebe 403 `TOOLS_NOT_ALLOWED` e fica registado |
| Ollama parado (B5.10) | Erro visível e accionável: `[Erro de inferência] … (código: MODEL_UNAVAILABLE) Acção: confirme que o Ollama está a correr em 127.0.0.1:11434…`. Nenhuma resposta inventada. Depois do reinício responde "OK". Antes da correcção, a GUI original mostrava só "Pick a model first" |
| Desempenho, N=10 por condição, pelo mesmo endpoint da GUI (`perf_qwen3.5-2b.json`) | **A frio** (modelo descarregado antes de cada pedido): p50 4,18 s, p95 15,6 s. **A quente**: p50 0,87 s, p95 1,76 s. **Modelo** (Ollama directo): 16,0 tokens/s (p50). 10/10 somas correctas e 10 respostas distintas |
| Limites de desempenho (sem esconder) | 1. A bridge **não faz streaming de tokens**: a resposta chega inteira, por isso TTFT = tempo total. 2. Perguntas abertas demoram mais: 13–55 s com o 2B nos testes de browser. 3. Num caso o 2B gerou durante 4 min e foi cortado pelo prazo de 240 s (`TIMEOUT`, mostrado como erro). 4. Mitigações propostas, ainda não aplicadas: streaming no adaptador; `think`/`num_predict` configuráveis com registo; modelo 4B ou GPU no host de produção |

## 11. Tarefas supervisionadas (B3)

- Os comandos são os da consola, sobre o **mesmo** ControlPlane.
- **A autorização é só o código do operador:**
  - qualquer tentativa consome o código (fail-closed);
  - `/autorizar` sem código é recusado sem consumir;
  - um código expirado é recusado (teste com relógio);
  - `POST /v1/approvals/*/approve` (o clique da UI original) recebe 403 e não inicia nada.
- `/autorizar` lança a execução em background. `/estado` mostra o progresso e o resultado final decidido pelo verificador. `/cancelar` cancela através do ControlPlane.
- **Distinção visual:** os rótulos de estado vêm em negrito. O comentário do modelo aparece como citação `⚠️ Comentário do modelo — NÃO verificado (não é evidência)`. As respostas de conversa levam o rodapé "NÃO verificada · sem ferramentas".
- P1, goose, Gateway, verificador e recibos estão **inalterados**: o `git diff` contra `develop` desses ficheiros é vazio.

## 12. Validação no browser original (B5): 10/10 cenários executados

Evidência: `docs/evidence/ui01/b5_results.json` e `docs/evidence/ui01/gui/*.png`.

| # | Acção | Obtido (FACTO) | Resultado |
|---|---|---|---|
| 1 | Abrir | Interface original: Chat, Dashboard, Data Sources, Agents, Logs, Settings | PASS |
| 2 | PT real | Maputo/português, rótulo NÃO verificada, id `rw-fb75…` | PASS |
| 3 | EN real | Tokyo, id `rw-17b2…` | PASS |
| 4 | Sessão | ZEBRA-41 na mesma conversa; NENHUM noutra | PASS |
| 5 | Pedido | `/tarefa comparar-versoes-ensaio` dá "Autorização necessária" e um código | PASS |
| 6 | Autorizações | sem código, código errado e código consumido: recusados; clique na aprovação: 403; código válido: execução; reutilização com tarefa activa: recusada | PASS |
| 7 | Execução e recibos | **P1**: `Resultado verificado por evidência`, COMPARISON_VERIFIED, 3 recibos (`fixture_read`, `fixture_read`, `fixture_compare`), 3 objectivos VERIFIED, alterações calculadas pelo código, comentário do modelo marcado NÃO verificado (99,9 s) | PASS |
| 7b | Missão goose/Gateway P3A pela GUI (3 tentativas) | Ver abaixo | **não verificada** |
| 8 | Cancelamento | `/cancelar` dá "Pedido cancelado". Estado final `Tarefa cancelada` (HALTED), pedidos de ferramenta seguintes DENIED | PASS |
| 9 | Contornar | 20 sondas (rotas, métodos, `//`, barra final, `/docs`, `/openapi.json`, webhooks, `PUT` no chat, `tools` no chat, modelo não permitido) e WebSocket: tudo recusado e registado; tarefa não activada recusada | PASS |
| 10 | Ollama parado | Erro explícito `MODEL_UNAVAILABLE` e recuperação após o reinício | PASS |

**Missão goose pela GUI (FACTO; nenhuma terminou verificada):**
- Isolamento verificado nas três: fixture e internet BLOCKED, 403 para clientes que não são o goose, imagem `sha256:fe85afae…`.
- Em todas: cadeia válida, HTTP↔recibos exactos, 0 violações e chamadas = recibos.

| Tentativa | Fim | Recibos e objectivos | Estado |
|---|---|---|---|
| 1 | `TIMED_OUT` aos 900 s | 5 recibos (5↔5) | EXECUCAO_PARCIAL `PROCESS_TIMED_OUT` |
| 2 | `TIMED_OUT` aos 900 s | 5↔5 | EXECUCAO_PARCIAL |
| 3 | goose terminou com código **1** aos 793 s, sem submeter o relatório | 4/4 objectivos observados, 503 recuperado, 6↔6 | **EXECUCAO_FALHADA `PROCESS_EXIT_NONZERO`** |

Os gates R1 funcionaram: nunca houve "verificado" com timeout ou com saída diferente de 0. A latência por turno do 4B foi de 131–332 s, contra 15–83 s na corrida P3A real. A causa não foi determinada (NÃO VERIFICADO; provável contenção de CPU no anfitrião partilhado). **A missão goose fica sem resultado verificado pela GUI nesta entrega.**

**Prova de backend real** (`docs/evidence/ui01/correlation.json`):
- **Correlação:** cada id `rw-…` mostrado na GUI aparece no `audit.jsonl` do servidor (modelo, segundos, `facade_request_id`) e corresponde a um único `POST /api/chat` do Ollama, com a mesma hora UTC e a mesma duração (diferença ≤ 0,03 s; por exemplo, 54,856 s no servidor e 54,83 s no Ollama).
- **Controlo:** com o Ollama parado não há nenhum pedido ao Ollama e aparece o erro explícito.
- **Varrimento:** a bridge só tem textos fixos de **rótulos, recusas e erros**; não há respostas de cortesia. Entradas distintas dão respostas distintas (10/10).

## 13. Regressões e integridade

- Suite completa no venv fixado: **680 OK, 0 skipped**.
- `tests/test_ui01_gui.py`: 20 testes FAKE/offline.
- P1, P2, P3A e TE-P2A verdes.
- Vendor (`f21d902`) e os seus ficheiros inalterados.
- O build do frontend é o `vite build` do pin. O lint e o typecheck do frontend original não foram corridos: o `tsc -b` do script `build` foi substituído por `vite build` directo para o `outDir` externo. O typecheck do frontend fica NÃO VERIFICADO.

## 14. Acesso

- **Verificado:** `http://127.0.0.1:8000/` no ambiente de engenharia.
  - `bash labs/ui01/start_and_verify.sh 8000 --tarefa-ensaio` arranca e verifica o bind só em 127.0.0.1, as rotas permitidas e as negações.
- **Host privado HTTPS:** só preparação, em `docs/engineering/UI01_PRIVATE_HOST.md`. Nada foi instalado, publicado ou tunelado.

## 15. INTEGRADO vs PENDENTE

| Capacidade | Existe no OpenJarvis | Integrada com RIGHTWARE | Testada | Estado | Bloqueio / próxima acção |
|---|---|---|---|---|---|
| Interface original + conversa real PT/EN | sim | **sim** (bridge → TextFacade) | sim, no browser | **INTEGRADA** | streaming de tokens; i18n PT da UI (a UI está em inglês) |
| Tarefa supervisionada P1 | n/a | **sim** (ControlPlane) | sim, verificada no browser | **INTEGRADA** | — |
| Missão goose/Gateway P3A | n/a | **sim** (ControlPlane) | executada no browser, não verificada (3/3) | **PARCIAL** | desempenho do 4B no host; repetir em host com GPU/CPU dedicado |
| Market Intelligence | pesquisa genérica (`/api/research`) | não | não | NÃO INTEGRADA | Internet autorizada, fontes datadas e verificador próprio; sem ordens financeiras |
| Internet pública | `web_search`, research, browser | não (rotas negadas) | não | BLOQUEADA | política de rede da plataforma; TE-P2D parcial |
| Voz | `/v1/speech/*` | não (negada) | não | NÃO INTEGRADA | extra `desktop` não instalado; hardware real |
| Windows (acções locais) | ferramentas upstream | não | não | BLOQUEADA | companion autorizado no dispositivo; nunca shell genérica |
| Shared Intelligence Core (SIC) | não | não | não | NÃO INTEGRADA | repositório separado; IAM e consentimento |
| Router multi-IA | `cloud_router` (fornecedores pagos) | não (negado) | não | NÃO INTEGRADA | decisão de produto; sem despesas autorizadas |

Na UI original, as páginas Data Sources, Agents, Dashboard (dados) e Settings (memória, cloud) continuam visíveis, mas as suas chamadas recebem 403 "não está integrada no JARVIS (RIGHTWARE)". **Nada é simulado.**

## 16. Limitações e riscos

- **Interface original:** em inglês. Mostra páginas de funções não integradas e um modal de opt-in (analytics e giveaway) na primeira visita. "Continue without sharing" funciona e qualquer opt-in é recusado e bloqueado pelo CSP. Removê-los exigiria alterar o frontend do vendor ou criar um overlay; decisão do operador.
- **Desempenho:** a resposta não é streamed (sem tokens incrementais). O 2B pode gerar respostas longas até ao prazo. As missões goose 4B não terminaram verificadas neste host.
- **Autenticação local:** não existe. A protecção é o bind só em loopback, a verificação de Host e Origin e o CSP. Qualquer processo local do mesmo utilizador pode usar a API permitida.
- **Uma tarefa de cada vez para todo o processo:** o ControlPlane é global, portanto várias conversas partilham o mesmo estado de tarefa.
- **Dependências de setup:** `uv`, `npx` e acesso ao PyPI e ao npm; linux/amd64 verificado.
