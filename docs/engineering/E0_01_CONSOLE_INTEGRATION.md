# JRV-E0-01 — Integração do produto: consola textual unificada (E0)

**Branch:** `develop` (produto). **Base:** `1e0c0aa82d6e2f220b6acac4c8afd79a1d1fab79`. **Data:** 20/11/2026.

**Fronteira com o laboratório:** os checkpoints BP-036 a BP-054 (investigação TE-P1/P2A/P2B/P2C/P2D) vivem na branch experimental `exp/te-p1-kaggle-goose` (PR #27, Draft, último estado `TE_P2D_PARTIAL` em `a1b88ef`). Nada disso está em `develop` e nada é integrado aqui: nem Gateway MCP, nem goose, nem contratos te-p2*.

## 1. Matriz real de componentes em `develop` (FACTO, por inspecção do código)

| Componente | Implementado? | Caminho | Interface actual | Reutilização na E0-01 |
|---|---|---|---|---|
| Conversação textual | Sim (WP-04/D02) | `rightware/text_adapter.py` | `LocalSimpleTextAdapter.reply(text, history)` → `SimpleAgent` fixado do OpenJarvis via Ollama local; sem ferramentas nem memória; injectável para FAKE | **Reutilizar** sem alterações |
| Sessão e contexto | Sim (WP-04/D01) | `rightware/text_facade.py` | `TextFacade.open_session/submit/cancel/close_session/history_snapshot/close`. Histórico efémero limitado (6 turnos, 6000 chars). Rotas `Route` (ANSWER/CLARIFY/PLAN/TASK/CONTROL/MEMORY_INTENT) e estados `Status` (ANSWER_ONLY/PLAN_ONLY/WAITING_INPUT/UNAVAILABLE/ERROR) com códigos de diagnóstico (CANCELLED, TIMEOUT, MODEL_BUSY, MODEL_UNAVAILABLE, INVALID_MODEL_REPLY, UNVERIFIED_EFFECT_CLAIM…). `TextResult` recusa por construção efeitos, recibos, verificação factual e persistência | **Reutilizar** como único caminho da consola |
| Entrada de tarefas confiáveis | Sim (TE-02…TE-06A) | `rightware/task_entry.py` | `TaskEntry.submit_text` delega no `TextFacade`. Os presets confiáveis (fixture, IANA, ficheiro) só correm por fábricas fornecidas pelo host | **Reutilizar `submit_text`**. A consola NÃO liga nenhuma fábrica: sem elevação de permissões |
| Política | Sim | `rightware/agent/policy.py` | `AgentPolicy` (capacidade, orçamentos, auditoria) | **Preservar**, não usada nem alterada pela consola (sem ferramentas) |
| Recibos | Sim | `rightware/agent/receipts.py` | `ReceiptLedger`/`ExecutionReceipt` | **Preservar**. A consola não mostra "verificado" sem recibos e não tem caminho que os produza |
| Completion | Sim | `rightware/agent/completion.py` | `evaluate(contract, receipts)` | **Preservar**, não usada |
| Agente A1/A2/A3 | Sim (WORK-05/07) | `rightware/agent/session.py`, `cli.py` | `python jarvis.py agent` (opt-in por flags) | **Inalterado**; continua comando separado |
| Tarefa pública TE-03 | Sim | `rightware/task_cli.py` | `python jarvis.py task` (opt-in) | **Inalterado**; não exposto na consola |
| Voz | Sim (canal separado) | `rightware/voice.py` | `python jarvis.py voice` | **Não alterar** |
| Windows | Sim (acções limitadas, `authorized=`) | `rightware/windows_actions.py` | `WindowsActions` | **Não executar nem ligar** |
| Chat upstream | Sim | `rightware/runtime.py` `chat_command` | `python jarvis.py chat` (CLI OpenJarvis) | **Inalterado** |
| Goose/Gateway/egress | Investigação | `labs/` na PR #27 (não está em `develop`) | Experimental | **Não integrar** |

**Lacuna identificada:** o `TextFacade`/`TaskEntry` (o caminho seguro e testado) não tem nenhum ponto de entrada para o utilizador. O `chat` lança o CLI upstream, que fica fora da facade e não usa os estados RIGHTWARE. Não há duplicação a remover; falta apenas a ligação.

## 2. Proposta mínima (GATE 1)

- **Novo** `rightware/console.py`: REPL fino sobre `TaskEntry(TextFacade(adapter=LocalSimpleTextAdapter(model)))`, só com `submit_text`. Mostra identidade e limitações e traduz `Route`/`Status`/diagnóstico em estados explícitos. Comandos `/ajuda`, `/estado`, `/capacidades`, `/cancelar` e `/sair`, reconhecidos apenas como linha completa e exacta. Ctrl+C durante a inferência usa o `TextFacade.cancel` existente. No fim fecha a sessão e liberta o adaptador, sem escrever nada em disco.
- **Edição mínima** de `rightware/runtime.py`: acrescentar o comando `console` (corre no venv fixado, como `agent`/`task`; `--model` repassado, com o modelo por omissão da configuração). O comportamento dos comandos existentes não muda.
- **Novo** `tests/test_e0_console.py` (FAKE/offline).
- **Novo** `labs/e0/mutation_e0.py`, com resultados em `docs/evidence/e0/`.
- **Documentação:** este ficheiro e o HANDOFF (append-only).
- **Proibido tocar:** `text_facade.py`, `text_adapter.py`, `task_entry.py`, `agent/*`, `voice.py`, `windows_actions.py`, `vendor/openjarvis` e workflows.
- **Critérios de aceitação técnica (não aceitação de E0):**
  - comando `python jarvis.py console` funcional com modelo FAKE;
  - todos os estados mapeados a partir de resultados reais da facade;
  - pedidos hostis sem aumento de privilégios;
  - nenhum ficheiro escrito e nenhum processo nem rede;
  - regressão completa verde;
  - mutações nos invariantes novos mortas.

Não exige alterar políticas, o submódulo nem interfaces congeladas: GATE 1 passado.
