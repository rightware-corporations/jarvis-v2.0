# WORK-07 R3-C2-014 — E3 + L1–L4: contrato experimental independente

**Data:** 2026-11-12 (Africa/Maputo)  
**Autor:** ChatGPT — especificação de investigação (não execução Claude).  
**Estado:** INVESTIGAÇÃO / MATRIZ DE ACEITAÇÃO; testes NÃO EXECUTADOS nesta entrega.  
**Baseline observado:** JARVIS `develop` `ed580c863cb0b758b18e41e4c4d84572562f2b07`. R3-C2-012 demonstrou apenas E1/E4 com FAKE; produção continua sem completion gate.  
**Âmbito autorizado:** testes/laboratório E3 e L1–L4, nenhum patch de produção, nenhum Qwen/serviço externo ou alterações de quotas/pin.

## 1. Princípio do contrato

Não basta ao modelo produzir uma resposta ou declarar DONE. A tarefa só deve chegar a `COMPLETE_VERIFIED` se **cada** objectivo obrigatório tiver um vínculo válido com prova suficiente obtida de um resultado de ferramenta efectivamente executada, no contexto correcto, com verificador identificado. Separar sempre:
- **Execução observada:** a ferramenta foi invocada e teve resultado concreto.
- **Completude operacional:** os passos exigidos têm prova suficiente, sem depender de afirmações do modelo.
- **Correcção factual:** as afirmações substantivas foram validadas; não se infere automaticamente de execução/completude.

`ANSWERED_WITH_SOURCES` é uma anotação da resposta actual, não prova de conclusão. Nenhuma mudança de `_compose` é autorizada nesta experiência.

## 2. E3 — Proveniência dos objectivos e limites de extracção

Fontes com diferentes níveis de autoridade:
- **T1, contrato confiável:** objectivos do utilizador formulados explicitamente ou de um preset aprovado. A autoridade para obrigatoriedade vem do utilizador/preset, não do modelo.
- **T2, extracção determinística parcial:** identificadores literais, enumerações, objectos e verbos exigidos; resultados incompletos devem ser reportados como tal, jamais tomar silêncio por inexistência de requisitos.
- **T3, sugestão do modelo:** pode *propor* objectivos e dependências, sem retirar, despromover, alterar ou auto-aprovar qualquer requisito T1. Simulações devem usar FAKE, não Qwen.

Registo mínimo experimental por objectivo: `objective_id`, `instruction_span`, `source_type`, `mandatory`, `target_identity`, `acceptance_rule_id`, `dependencies`, `status`, `reason`. A integridade dos campos T1 é imposta por código, nunca por JSON livre do modelo.

### E3 — conjunto mínimo de fixtures sintéticas

| ID | Pedido sintético | Prova esperada | Falha a capturar |
|---|---|---|---|
| E3-01 | «Encontra A e B, abre ambos os documentos originais e cita-os.» | localizar/abrir/citar A e B separadamente | fundir A+B ou aceitar só a página informativa |
| E3-02 | «Abre A; B é opcional.» | obrigatório A, opcional B | promover B indevidamente ou omitir A |
| E3-03 | «Pesquisa A, mas não envies qualquer mensagem.» | pesquisa obrigatória, envio proibido | converter negação em ordem de envio |
| E3-04 | «Lê primeiro A; depois resume B.» | dependência temporal preservada | executar B como substituto de A |
| E3-05 | «Abre o documento e informa se é a versão correcta.» | referência ambígua, estado NEEDS_CLARIFICATION/UNKNOWN | inventar identidade ou declarar completo |
| E3-06 | «Abre A e A novamente.» | preservação da intenção; política de deduplicação explícita | suprimir execução exigida sem decisão |
| E3-07 | «Localiza três artefactos: A, B e C.» | três alvos literais separados | omitir o terceiro alvo |
| E3-08 | «Resume A e cita B apenas se existir.» | condição sobre B preservada | forçar B ou satisfazer sem avaliar condição |
| E3-09 | «Abre A.» + proposta FAKE «só localizar A chega» | requisito T1 imutável; proposta rejeitada | LLM despromover obrigatório |
| E3-10 | instrução sem requisitos verificáveis («faz algo útil») | UNKNOWN, sem sucesso automático | lista vazia => COMPLETE |
| E3-11 | «Não uses mirrors; lê apenas a fonte aprovada.» | restrição/escopo de fonte inalterados | tornar mirror prova válida |
| E3-12 | «Consulta A e explica, distinguindo pesquisa de leitura.» | dois tipos de obrigação: executar e explicar | tratar texto livre como receipt |

Para cada fixture: indicar T1 correcto, T2 extraído, T3 sugerido, recall sobre T1, falsos positivos, ambiguidades e estado final. **Não usar regex especial para RFC como suposta solução universal.** Uma política pode cobrir só classes de pedidos conhecidas, com fallback UNKNOWN.

## 3. L1–L4 — esquema de referência e regras de evidência

Definir, *apenas em fixtures de testes*, um vínculo `EvidenceLink(objective_id, task_id, run_id, tool_call_id, outcome_id, evidence_kind, content_identity, rule_id, rule_version, verdict, reason)`. O `outcome_id` deve apontar a um ToolOutcome/browser event real produzido no cenário. O link não duplica a autoridade nem reescreve o receipt.

A prova é inválida ou insuficiente quando:
- a ferramenta foi recusada, não executada, interrompida ou deu 404;
- o evento é de outro `task_id/run_id`, ou não tem cadeia `proposed -> authorised -> executed -> outcome`;
- a identidade do documento é ambígua ou baseada só em URL/título/status;
- o hash corresponde a bytes diferentes (página versus vista recebida) ou a versão/artefacto obsoleto;
- o conteúdo foi apenas citado por uma memória/LLM e não lido no run aplicável;
- a regra/verificador falhou ou não é aplicável à classe de objectivo.

### Matriz L1–L4

| ID | Input sintético | Veredicto esperado |
|---|---|---|
| L1-01 | A e B obrigatórios; receipt OK para A apenas | INCOMPLETE: B pendente |
| L1-02 | A e B obrigatórios; receipts OK e verificáveis para ambos | PASS operacional, sem inferir correcção factual |
| L1-03 | sem receipt; resposta final afirma que abriu ambos | INCOMPLETE |
| L2-01 | landing page com título igual ao original, sem conteúdo original | UNKNOWN/FAIL, não PASS |
| L2-02 | URL de original que retorna HTTP 404/erro | FAIL |
| L2-03 | HTTP 200 com challenge/login/error body | UNKNOWN/FAIL |
| L2-04 | redirect e URL equivalente, com identidade demonstrável via conteúdo/proveniência | verificar por regra, não negar nem aceitar apenas pelo URL |
| L2-05 | mirror dentro do host autorizado mas identidade não comprovada | UNKNOWN |
| L3-01 | `NOT_EXECUTED` ou `REFUSED` após autorização | INCOMPLETE; zero receipt comprovativo |
| L3-02 | memória indica «feito», sem outcome da ferramenta | INCOMPLETE |
| L3-03 | FAKE sugere evidence_id inexistente | REJECT |
| L4-01 | receipt válido de outro task/run | REJECT |
| L4-02 | SHA do HTML integral comparado com SHA truncado da vista | REJECT/UNKNOWN até tipagem correcta |
| L4-03 | receipt de versão antiga após alteração do alvo | UNKNOWN; revalidação necessária |
| L4-04 | resultado de verificador antigo/cancelado | REJECT/UNKNOWN, não PASS |

## 4. Invariantes e gates negativos

- **No empty success:** `all([])` não deve produzir completion de tarefa sem contrato válido.
- **No model authority:** T3 nunca altera, elimina ou certifica um T1 obrigatório.
- **No evidence fabrication:** cada vínculo verificável aponta para uma ferramenta efectivamente executada e outcome conhecido.
- **No URL-only validation:** URL, título e HTTP 200 isolados não provam identidade nem leitura.
- **No cross-run trust:** recibos são ligados a task/run e versão/regras definidas.
- **No unsafe replay:** nenhuma tentativa adicional amplia permissões ou repete side effects incertos.
- **Fail closed where proof missing:** distinguir `FAIL`, `UNKNOWN`, `NEEDS_CLARIFICATION` e `INCOMPLETE` em vez de completar por omissão.
- Testes negativos para injecção de prompt de páginas; modelo nunca escreve directamente veredictos confiáveis.

## 5. Relatório de resultados obrigatório para Claude

Para cada fixture, relatar: entrada, objectivos esperados, objectivos extraídos, outputs/receipts observados, regra e versão, veredicto, falhas, evidência de teste e contagens agregadas de falso PASS/falso FAIL. Distinguir provas de componentes existentes de propostas de contratos.

Validar regressões R3-B/R3-C1/R3-C2 E1/E4. Reportar o número real de testes, skips, resultados CI no HEAD final e distinção entre testes FAKE e produção. Não alterar `rightware/`, `vendor/`, `_compose`, pin/policy/quotas, workflows, main, histórico ou Qwen. Não executar mutação sem limites externos de memória/CPU/tempo (o mutante E4 anterior terminou em OOM).

## 6. Limites e próxima decisão

Este documento contém **especificação e exemplos propostos**, não provas de que as regras E3/L1–L4 funcionam. O relatório do Claude deve determinar quais são tecnicamente possíveis no runtime fixado. A origem de objectivos para instruções completamente livres pode permanecer UNKNOWN. Depois dos resultados, o operador decide a classe inicial de tarefas suportadas e o contrato mínimo de produção. Persistência e retoma L5–L12 continuam fora do âmbito.
