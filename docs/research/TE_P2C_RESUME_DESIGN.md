# JRV-TE-P2C — Especificação da retoma supervisionada (GATE 1)

Data: 2026-11-19. Branch `exp/te-p1-kaggle-goose`, Draft PR #27. Base `c06624c`.

## 1. Quem detém que estado (diagnóstico)

| Estado | Dono | Onde vive | Confiança para autorizar |
|---|---|---|---|
| Conversa do agente (mensagens, pedidos e resultados de ferramentas) | goose | `~/.local/share/goose/sessions/sessions.db` no contentor do goose | **nenhuma**: pode ser adulterada; serve só para o goose saber onde estava |
| Sessão de transporte MCP (`Mcp-Session-Id`) | Gateway | memória do processo `mcp_http` | identifica uma ligação, não autoriza nada |
| Identidade da tarefa e da tentativa (`task_id`, `attempt_id`) | host RIGHTWARE | fixadas em código na criação do Gateway | autoridade |
| Identidade de cada operação (sequência do recibo, `call_id`, assinatura efectiva) | Gateway (ReceiptLedger) | memória do Gateway, despejada em `receipts.jsonl` | autoridade |
| Política (orçamento global, quotas por ferramenta, prazo, guarda de ciclos, auditoria) | Gateway (AgentPolicy) | memória do Gateway + `audit.jsonl` | autoridade |
| Estado do navegador (ligações L#, página actual) | Gateway (PublicBrowser) | memória do Gateway | — |
| Submissões e cadeia `te-p2b.report.v1` | Gateway | memória + `submission_chain.jsonl` | autoridade |
| Estado do 503 da fixture | fixture | memória da fixture | verdade do cenário (não muda) |

Consequência: só o processo goose é interrompido. O Gateway e a fixture continuam vivos, e todo o estado autorizado permanece no host RIGHTWARE. A conversa do goose é a única coisa persistida fora do Gateway, num volume Docker dedicado e descartável por ensaio, sem directórios do host.

## 2. Problemas que a versão TE-P2B teria numa retoma

1. Um segundo `initialize` dá 409 (sessão única), pelo que o goose reiniciado não conseguiria ligar-se. Não se resolve desligando a verificação.
2. Os ids JSON-RPC recomeçam no novo processo goose, o que gera `call_id` duplicados (`DUPLICATE`), recibos defeituosos e veredicto NOT_VERIFIED.
3. Uma operação já executada antes da interrupção pode ser pedida de novo pelo goose retomado; seria executada outra vez.
4. Uma operação em curso no momento da interrupção não pode ficar órfã nem coexistir com outra.
5. Os ids de pedidos cancelados (`notifications/cancelled`) de um processo poderiam colidir com os do processo seguinte.

## 3. Estratégia

**Separação explícita:** transporte (`Mcp-Session-Id`, efémero, um por processo goose), sessão do agente (goose, sem autoridade), tarefa (host) e operações (recibos). A geração de transporte `g` é um contador do Gateway: `g=0` no arranque e `+1` por cada religação autorizada.

**Canal de controlo do supervisor (host apenas):**
- `POST /control/{status,suspend,authorize-resume}` no mesmo servidor, aceite só de `127.0.0.1`, ou seja, via `docker exec` no contentor do Gateway pelo supervisor. O goose está noutro contentor e nunca tem origem loopback.
- Cabeçalho `X-Rightware-Control` igual a um token aleatório passado por variável de ambiente na criação do Gateway, comparado em tempo constante. Sem token configurado, o canal não existe (404).
- O modelo e o goose nunca o alcançam.

**Suspensão (`suspend`):**
- espera, sob o mesmo lock que serializa as chamadas, que nenhuma operação esteja em curso;
- se uma ferramenta ainda corre após timeout, a suspensão devolve `in_flight=true` e a retoma fica recusada até terminar (fail-closed: nunca duas operações activas);
- invalida a sessão de transporte actual: o id antigo passa a dar 404;
- devolve um resumo: tarefa, tentativa, geração, nº de recibos, última sequência, digest SHA-256 de todos os recibos, cabeça da cadeia de submissões, quotas.

**Autorização da retoma (`authorize-resume`):**
- o supervisor tem de devolver exactamente o resumo actual (tarefa, tentativa, geração, última sequência, digest de recibos, cabeça da cadeia); qualquer diferença (tarefa errada, resumo antigo ou adulterado) dá recusa;
- emite uma concessão única com TTL de no máximo 300 s.

**Religação:**
- o único `initialize` aceite após a suspensão é o primeiro vindo do IP autorizado do goose com concessão válida;
- esse `initialize` consome a concessão, faz `g += 1`, cria um novo `Mcp-Session-Id` e limpa os cancelamentos da geração anterior;
- concessão expirada dá 403; segundo `initialize` dá 409; pedidos sem `initialize` dão 400.
- Os `call_id` passam a `<task>:<attempt>:g<g>:<id>` quando `g ≥ 1` (formato de `g=0` inalterado).

**Anti-replay e deduplicação (por assinatura efectiva, não por id do modelo):**
- uma operação **executada numa geração anterior** que seja pedida de novo com a mesma assinatura efectiva não é executada outra vez;
- o Gateway devolve o resultado registado e cria um recibo próprio: não autorizado e não executado, com `reason_code = REPLAYED_FROM_RECEIPT` e motivo que cita a sequência original;
- este recibo não consome política nem gera tráfego HTTP.

| Classe | Ferramentas | Regra de reenvio |
|---|---|---|
| Leitura com rede | `web_open`, `web_follow` | só operações concluídas OK; servido uma vez por operação, depois a política normal decide; leituras falhadas, por exemplo o 503, podem ser tentadas de novo pela política |
| Efeito | `submit_report` | qualquer operação executada (OK ou recusada); servido sempre, nunca re-executado |
| Local, sem rede | `web_find` | sem reenvio |

A ausência de duplicados em leitura **não** prova segurança para escrita; os testes tratam as duas classes separadamente com um executor de efeitos contado.

**Quotas e orçamento** acumulam entre gerações: é o mesmo `AgentPolicy`, que não é reiniciado.

**Verificação:**
- inalterada: o verificador congelado decide a partir dos recibos executados;
- os recibos de reenvio não têm tráfego HTTP nem contam como observação;
- a correspondência HTTP↔recibos mantém-se exacta.

## 4. Riscos e limites declarados

- O estado RIGHTWARE vive na memória do Gateway: se o Gateway cair, a retoma é impossível. Fail-closed: nova tentativa, nunca reconstrução a partir do goose.
- A autenticação do cliente continua a ser IP fixo numa rede interna mais a concessão única; o goose CLI não envia cabeçalhos próprios.
- A conversa do goose persistida pode estar adulterada; não autoriza nada, apenas pode levar o agente a errar, o que o verificador apanha.
- `load_skill` continua a existir no goose; o filtro bidireccional mantém-se igual.
- Navegação apenas de leitura; a regra de efeitos é demonstrada com `submit_report` e com um executor contado nos testes, não com escrita real.

## 5. Ficheiros editáveis (lista fechada)

`labs/te_p2a_gateway/gateway.py`, `labs/te_p2a_gateway/mcp_http.py`, `labs/te_p2a_gateway/live_goose.py` (parâmetros opcionais, comportamento por omissão igual). Novos ficheiros:
- `labs/te_p2a_gateway/frozen_p2c.py`
- `labs/te_p2a_gateway/te_p2c_resume.py`
- `labs/te_p2a_gateway/mutation_p2c.py`
- `tests/test_te_p2c_resume.py`
- `docs/research/TE_P2C_*.md`
- `docs/evidence/te_p2c/*`
- `docs/HANDOFF.md` (append-only)

Congelados: manifesto `docs/evidence/te_p2c/frozen_manifest_p2c_g0.json`, que cobre o verificador, a política, o cenário, A1–A4, as permissões, `report_contract.py`, a evidência e o pré-registo TE-P2B, `live_t2.py` e a evidência T2 histórica. OpenJarvis permanece em `f21d902`.

Esta estratégia não enfraquece nenhuma verificação: GATE 1 passado.
