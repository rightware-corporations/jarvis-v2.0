# JRV-P2 — goose como segundo executor supervisionado (candidato a integração)

**Branch temporária:** `integration/jrv-p2-goose-20261122`, criada a partir de `develop` `b3e45ec`. Destina-se a uma única PR para `develop`; a branch é apagada depois do merge ou do fecho.
**Origem experimental:** `exp/te-p1-kaggle-goose@a1b88efc9db00f501d7c6772c31d01ce69622dff` (PR #27, Draft, intacta).

## 1. Percurso integrado

```
consola (python jarvis.py console --missao-goose …)  →  ControlPlane (autoridade: capacidade activada pelo anfitrião
  + código de uso único do operador)  →  GooseMission (rightware/goose_adapter.py)  →  Docker isolado:
  goose 1.60.1 --no-profile, só a extensão MCP do Gateway  →  model_tap (filtro bidireccional de ferramentas)
  →  RIGHTWARE Tool Gateway (AgentPolicy + ReceiptLedger + te-p2b.report.v1)  →  recibos  →
  labs.te_p2a_gateway.verify (verificador RIGHTWARE)  →  estado do ControlPlane
```

- O goose só **propõe** operações. A AgentPolicy decide cada uma e cada uma gera recibo; nenhuma conclusão vem de texto do modelo.
- **Isolamento verificado, não declarado:**
  - **antes de o goose arrancar:** uma sonda feita da posição de rede do goose tem de encontrar a fixture e a internet bloqueadas, o Gateway acessível e uma recusa 403 para qualquer cliente que não seja o goose; o `docker inspect` do contentor tem de mostrar só a rede `jrv-agent` e zero mounts;
  - **depois:** o registo de sessão do próprio goose tem de conter só chamadas ao Gateway, e só as 4 ferramentas do Gateway podem ter chegado ao modelo;
  - **qualquer violação** dá EXECUCAO_FALHADA e nunca "verificado".
- **Estado:** RESULTADO_VERIFICADO só com `TASK_VERIFIED_LIMITED` e evidência consistente (correspondência HTTP↔recibos exacta, sem defeitos, cadeia de submissões válida). Os outros estados são:
  - EXECUCAO_PARCIAL: há objectivos observados, mas não verificados;
  - RESULTADO_DESCONHECIDO: inclui EVIDENCE_INCONSISTENT;
  - TAREFA_CANCELADA;
  - EXECUCAO_FALHADA.
- **Limites fixos:**
  - goose: 20 turnos, 900 s;
  - Gateway: 15 chamadas, 1700 s, quota de 3 submissões;
  - uma tarefa de cada vez, controlada pelo ControlPlane.
- **Retoma (TE-P2C) não é oferecida.** O estado do Gateway vive só em memória, por isso não se promete durabilidade entre reinícios. O cancelamento pára o goose e fecha a execução.

## 2. Lista fechada de ficheiros

| Ficheiro | Tipo | Origem |
|---|---|---|
| `labs/te_p2a_gateway/{__init__,gateway,mcp_http,fixture_transport,model_tap,verify,report_contract,fake_model}.py` | **reutilizado** (blob idêntico) | `a1b88ef` |
| `labs/te_p1_bakeoff/{__init__,site,score_semantic}.py` | **reutilizado** (blob idêntico) | `a1b88ef` |
| `tests/test_te_p2a_gateway.py` | **reutilizado** (blob idêntico) | `a1b88ef` |
| `rightware/goose_adapter.py` | **novo**; orquestração adaptada de `labs/te_p2a_gateway/live_goose.py@a1b88ef` | — |
| `rightware/control_plane.py` | **adaptado**: registo de executores, `Refusal`, correcções P1 | P1 `b3e45ec` |
| `rightware/console.py` | **adaptado**: flags do anfitrião, apresentação | P1 `b3e45ec` |
| `tests/test_p2_goose_integration.py` | **novo** | — |
| `tests/test_p1_control_plane.py` | **adaptado**: as recusas passam a afirmar o motivo exacto | P1 |
| `labs/p2/{mutation_p2,real_mission_trial}.py`, `docs/evidence/p2/*`, este documento, `docs/HANDOFF.md` | **novo** | — |

**Não trazidos:**
- runners de ensaio (`live_goose`, `te_p2b_trials`, `te_p2c_resume`);
- manifestos congelados e scripts de mutação TE;
- harnesses do bake-off;
- TE-P2D (egress público e contrato de investigação).

Há duas referências preguiçosas a `labs.te_p2d_public` no `gateway.py` e no `mcp_http.py`. Nenhuma é alcançável no percurso integrado e, se fosse, falharia fechada (ImportError).

**Inalterados:** `text_facade.py`, `task_entry.py`, `agent/*`, vendor (`f21d902`) e workflows.

## 3. Correcções P1 (GATE 1)

1. As linhas de estado que o executor acrescenta ("Estado: …", "Estado da tarefa (…)") são retiradas do comentário não verificado. O estado mostrado é o determinado pelo código; o verificador não foi alterado.
2. A pasta de ensaio é criada dentro do bloco de limpeza e é removida mesmo que a preparação falhe. O estado de execução é sempre reposto.
3. O banner e `/capacidades` mostram o modo realmente activo.
4. Erros internos aparecem como EXECUCAO_FALHADA e nunca como "código inválido". As recusas passam a trazer o motivo (CODE_INVALID, BUSY ou ENVELOPE_REFUSED).
5. Corre uma tarefa de cada vez, com verificação atómica (BUSY).

## 4. Execução real (GATE 5)

**Condições:** goose 1.60.1 (`4db5cf70…`), qwen3.5:4b (`d8b0f5e9…`), Ollama 0.40.15 num contentor da rede interna, Docker 29.9.2, CPU sem GPU. Mesmo comando de produto em todas as corridas. Nenhuma corrida foi apagada.

| Corrida | Código | Resultado | Observação |
|---|---|---|---|
| 1 | `179af9c` | **Execução falhada**, NOT_STARTED (12,6 s) | A sonda de isolamento não alcançou o Gateway: corrida de um `sleep 6` fixo num arranque a frio. O sistema falhou fechado sem arrancar o goose. Corrigido em `4feba0e` (espera pelo arranque do Gateway). |
| 2 | `4feba0e` | **Resultado verificado** (TASK_VERIFIED_LIMITED, 7 recibos, 257,5 s) | A consola rebentou **depois** de mostrar o resultado, porque assumia que um resultado verificado traz alterações (`changes=None`). Corrigido em `23330c7`. |
| 3 | `23330c7` | **Resultado verificado** (TASK_VERIFIED_LIMITED, 7 recibos, 217,2 s), saída 0 | Percurso de produto completo e limpo. |

**Corrida 3 em detalhe:**
- recibos: #1 web_open OK, #2 web_follow OK, #3 web_follow HTTP_ERROR (o 503), #4–#6 web_follow OK, #7 submit_report OK;
- objectivos CATALOG, ATLASBOARD, NOVAVIEW e TERRALENS_FACTSHEET observados por recibo;
- recuperação do 503 confirmada;
- correspondência HTTP↔recibos 6↔6;
- cadeia válida;
- verificação semântica PASS;
- violações: 0;
- o goose só executou ferramentas do Gateway, e ao modelo só chegaram as 4 ferramentas do Gateway;
- isolamento verificado (fixture e internet BLOCKED, 403 para clientes que não são o goose, só `jrv-agent`, zero mounts).

Evidência: `docs/evidence/p2/p2_real_goose_mission_2026-11-22.json`. Os registos de sessão e de pedidos ficam locais; o ficheiro guarda os respectivos hashes.

## 5. Comparação com as garantias TE-P2C

| Garantia TE-P2C | Neste pacote |
|---|---|
| Sessão MCP única, IP fixo, `Mcp-Session-Id` | Mantido: `mcp_http.py` igual |
| Ids por geração, anti-replay (leituras uma vez, efeitos nunca), canal de controlo do anfitrião | O código existe e é testado (`tests/test_te_p2a_gateway.py` trazido). A **retoma não é exposta** pelo produto: não há suspensão nem religação no adaptador. |
| Recibos, correspondência HTTP exacta, cadeia te-p2b | Mantidos e exigidos pelo mapeamento de estados |
| Filtro de ferramentas na entrada e na saída do modelo (`load_skill`) | Mantido: allowlist do tap com as 4 ferramentas e auditoria do inventário depois de cada corrida |
| Durabilidade entre reinícios | **Não existe** (estado em memória); não é prometida |

## 6. Riscos e limites que permanecem

- **Amostra pequena:** uma missão sintética e uma corrida limpa (N=1). Com o 4B em CPU, uma missão demora entre 3,5 e 4,5 min.
- **Isolamento dependente do Docker:** o laboratório tem de estar disponível no host. A imagem `jrv-gateway:te-p2a` tem de existir; foi construída localmente a partir do lockfile e **não** está publicada. Sem ela, a execução falha com `GATEWAY_IMAGE_MISSING`.
- **Código de laboratório no produto:** o produto importa código de `labs/`, só quando o anfitrião activa a capacidade. Isto deve ser decidido na revisão, mantendo-o como está ou promovendo-o para `rightware/` num pacote próprio.
- **`load_skill`:** continua a existir dentro do goose e está contido pelo filtro e pela auditoria. Nesta corrida houve 0 tentativas.
- **Autenticação do cliente MCP:** é feita por IP numa rede interna.
- **Windows:** nada foi testado em Windows.
- **Âmbito:** não há Internet pública (TE-P2D_PARTIAL) e não é produção.

## 7. Próximo passo exacto

Revisão humana desta PR. Se for aprovada e o merge verificado, segue-se um pacote próprio para decidir:
- a promoção do subconjunto do Gateway de `labs/` para `rightware/`;
- a publicação reprodutível da imagem do Gateway;
- N≥3 missões reais pré-registadas através do produto.
