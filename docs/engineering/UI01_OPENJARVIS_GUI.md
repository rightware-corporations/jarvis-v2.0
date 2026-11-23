# UI-01 — interface original do OpenJarvis com o runtime RIGHTWARE

Estado: **investigação e execução local concluídas; integração por implementar** (aguarda os gates G-MERGE e G-IMPL). Data: 23/11/2026. Base: `develop` `ba85c2a85d8290685eba9cd78dfe371eb3e29cc2`; vendor `f21d902f4d3bd7f0f3f138f1a4613019a394b549` (inalterado).

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
