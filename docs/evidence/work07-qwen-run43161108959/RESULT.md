# WORK-07 — Primeira execução real Qwen3.5:4b no RFC Editor

**Resultado histórico: FAIL (execução técnica COMPLETED, aceitação rejeitada).** Não alterar este veredicto por revisão posterior ou por testes simulados. Pedido único, `request_id: 1`, consumido em 12/11/2026.

## Identidade da execução

- GitHub Actions: [run 43161108959](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43161108959)
- Artefacto original: [13917784091](https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43161108959/artifacts/13917784091), retenção de 30 dias
- HEAD de código aprovado: `a2a7a2ac110b04860d78bb61224929a4a98a3cc6`
- Commit único de pedido: `15bb4a514b31a768728f7387f24176b322c42d2f` (apenas `ops/work07_qwen_request.json`)
- Plano SHA256: `44d9664812cd98648f17691508f4adf9710463ef20354b09ed4d12e144a02d94`
- `request_id`: 1, `run_attempt`: 1, `authorisation.ok`: true
- Ambiente real: Ollama 0.40.15, Qwen3.5:4b, digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`; sem API paga
- Restrições: `browse` exclusivamente em `www.rfc-editor.org`, 14 turnos, 14 tool calls, 768 tokens por resposta, 900 segundos; sem shell, filesystem, Windows actions ou outras capacidades
- GATE 0, 1, 2 e 3: PASS; runner técnico exit 0 (COMPLETED); `ACCEPTANCE: FAIL`, `accepted=false`
- ZIP SHA256: `baecf5f0bba58bf998e73ac1e3da37c4bd3b46c07bd9f8b37439250ca69cec69` (igual ao digest GitHub), 11/11 ficheiros do `SHA256SUMS` íntegros.

## Trajectória real do modelo (extraída da fronteira de inferência)

O Qwen emitiu **9 propostas de chamadas de ferramenta**, nesta ordem:

| # | Ferramenta/argumento proposto | Evidência |
|---|---|---|
| 1 | `web_open` `https://www.rfc-editor.org/search/` | OK, HTTP 200 |
| 2 | `web_type` `F1`, texto `RFC 9110` | OK |
| 3 | `web_submit` `F1` | OK, resultados HTTP 200 |
| 4 | `web_open` `https://www.rfc-editor.org/info/rfc9110/` | OK, HTTP 200, página de metadados |
| 5 | `web_type` `F1`, texto `RFC 9112` | OK |
| 6 | `web_submit` `F1` | OK, resultados HTTP 200 |
| 7 | `web_open` `https://www.rfc-editor.org/info/rfc9112/` | Proposta aprovada na auditoria, **sem outcome associado** no artefacto; precisa de investigação read-only |
| 8 | `web_open` novamente `https://www.rfc-editor.org/info/rfc9112/` | Negado: quota máxima de 3 chamadas `web_open` |
| 9 | `web_follow` `L37` | OK, HTTP 200, página de metadados RFC 9112 |

Total: **5 pedidos de página bem-sucedidos** nos eventos (2 open, 2 submit, 1 follow), todos do domínio autorizado. A pesquisa e navegação **não foram simuladas**. O modelo efectivamente abriu as páginas oficiais de informação das duas RFC (`/info/`), mas **não abriu os documentos canónicos** `/rfc/rfc9110(.html|.txt)` e `/rfc/rfc9112(.html|.txt)`, exigidos pela aceitação.

## Resposta do Qwen

A resposta final indicou correctamente (em termos semânticos) que a RFC 9110, `HTTP Semantics`, trata da semântica HTTP e que a RFC 9112, `HTTP/1.1`, trata da sintaxe de mensagens e gestão das ligações. Citou estes links oficiais, mas **apenas de metadados**, não os links canónicos exigidos pelo plano:

- `https://www.rfc-editor.org/info/rfc9110/`
- `https://www.rfc-editor.org/info/rfc9112/`

A resposta do produto terminou `ANSWERED_WITH_SOURCES` e listou as cinco fontes lidas; `answer_factually_verified=false`, porque a verificação factual de cada afirmação não foi realizada. A flag `TOOL_REFUSALS` assinala uma chamada recusada pela quota. A conclusão do produto **não equivale** a PASS do avaliador.

## Motivos reais do FAIL

O avaliador automático devolveu cinco motivos:

1. `RFC 9110 was not actually opened` — refere-se à **versão canónica do documento**, não à página /info/.
2. `RFC 9112 was not actually opened` — mesma distinção.
3. `official title of RFC 9110 missing or not paired with it` — **falso negativo de associação textual em Markdown**: o título está na linha seguinte ao cabeçalho RFC 9110. A rubrica `spans()` separa por linhas e perde o contexto. Não significa que o título esteja errado.
4. `official URL of RFC 9110 not attributed in the answer` — o Qwen citou /info/, não o canónico /rfc/.
5. `official URL of RFC 9112 not attributed in the answer` — mesma distinção.

**Diagnóstico:** a infraestrutura, pesquisa, acesso real ao site, isolamento de rede e modelo fixado funcionaram. A execução ficou curta na etapa *índice/página de informação → documento original*, e houve uso ineficiente de `web_open`/quota. Separadamente, a rubrica automática precisa de um teste negativo/positivo para associação de cabeçalhos Markdown com os respectivos títulos.

## Recomendações (NÃO aprovadas nem implementadas)

- **R1:** investigar porque uma proposta `web_open` foi aprovada, mas não teve outcome associado na evidência; reforçar observabilidade/contagem de quota se confirmado. Não atribuir uma causa sem testes.
- **R2:** orientar genericamente o agente para distinguir páginas de índice/metadados de documentos originais, e para utilizar links `L#` observados por `web_follow` sem depender de URLs imaginados; não escrever navegação RFC codificada nem injectar os títulos/respostas.
- **R3:** adicionar testes de regressão à rubrica para documentos com cabeçalhos e bullets Markdown; preservar a exigência de documento canónico, não converter o FAIL histórico em PASS.
- **R4:** executar a suite determinística/CI e o protocolo de aprovação novamente antes de qualquer **novo** Qwen real. O pedido 1 foi consumido, **não reexecutar** sem autorização específica para request_id 2.

## Governança e proveniência

Os resultados históricos anteriores permanecem: preflight Fase 4 request_id 1 `NOT_READY`, request_id 2 `NOT_READY`, request_id 3 `READY`; Fase 5 Qwen request_id 1 `FAIL`. `main`, demo, OpenJarvis pin e modelo não foram alterados nesta operação. Este documento é um índice e relatório inspectável, não substitui o ZIP original retido pelo GitHub. Ver `PROVENANCE.txt` para os digests de cada ficheiro.
