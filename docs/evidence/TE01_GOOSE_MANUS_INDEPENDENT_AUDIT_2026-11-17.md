# TE-01 — Auditoria independente dos logs goose/Manus (2026-11-17)

**Estado:** EVIDENCIA OBSERVADA, nao aceitacao de integracao, recuperacao autonoma ou seguranca de producao.

**Ficheiros recebidos do operador:** `goose_test_run.log`, `goose_test_retry.log`, `GOOSE_TE01_RESULTS.json`, `GOOSE_TE01_COMMANDS.txt`, `Project codename_ JARVIS.md`, `identical=false.md`. Inspeccionados directamente. Os logs originais NAO foram committados (evitar armazenar transcricoes no repo publico). SHA-256 abaixo permite correlacao com os artefactos originais.

| Artefacto | SHA-256 |
|---|---|
| goose_test_run.log | `8fbcdcd6305582b4b3d70d5f9363a7208555f6adc5778cc780b6d00c3cb5bbdc` |
| goose_test_retry.log | `8567f6c8621087ea744cf069ef4d9d9c8e812a0764c9fc7e5a69f1aa1f078ef9` |
| GOOSE_TE01_RESULTS.json | `619deb66bf2d9998128b5b7951b7a62a94b4d2da33e6fbb6750f4314bd566b9c` |
| GOOSE_TE01_COMMANDS.txt | `0b6d0a3d18e6f5a87b813404f8a31e9b6d6eeeb0d125e62506f8cb817f9f8935` |

## Execucao real

- O resumo de Manus informa goose `1.59.2`, Ollama `0.40.16`, modelo **`qwen2.5:3b`** em Ubuntu 24.04.5 x86_64 CPU-only (6 CPU, 7.8 GiB RAM). Estes valores sao relatorio do agente externo; o modelo/provedor estao tambem explicitamente nos metadata de inferencia em ambos os logs.
- Primeiro log: **2 tool requests `shell`, 2 respostas de ferramenta**. Primeiro comando fez `cat alpha.txt && cat beta.txt > comparison_report.md && echo ... >> ...`, o que concatena conteudo para o ficheiro mas NAO calcula nem relata a diferenca. A segunda chamada `test -f ... && cat` demonstrou que existe o ficheiro errado. **FAIL na tarefa**, embora exit status = 0 para as chamadas shell.
- Segundo log: **3 tool requests `shell`, 3 respostas**. Os comandos incluem `cat alpha.txt && cat beta.txt && diff -u alpha.txt beta.txt`, `printf 'identical=false...'> comparison_report_retry.md`, e `cat comparison_report_retry.md`. A leitura final coincide com o esperado e com o artefacto `identical=false.md`. **PASS na tarefa especifica apos repeticao dirigida externamente**.
- **Correcao importante:** `diff -u` terminou com exit code **1** porque encontrou uma diferenca. Isto e esperado para `diff`, nao falha do programa.
- **Recuperacao autonoma NAO provada:** a segunda tentativa ocorreu depois de correcao/prompt externos, nao por auto-recuperacao do goose. Os 3 toolRequests no segundo log aparecem no MESMO conjunto emitido pelo modelo antes das toolResponses. Logo, nao esta demonstrado que o modelo tenha lido a saida do diff antes de propor o `printf` com valores correctos; a execucao nao demonstra um ciclo observe -> replan -> act nesse ponto.
- **Seguranca NAO provada:** `--no-profile` e builtin `developer` nao demonstram impossibilidade de acesso directo ao shell. Os logs mostram ferramenta `shell` efectivamente chamada. Nao houve ligacao ao `AgentPolicy` da RIGHTWARE, nem teste de bypass negativo.
- **Modelos desejados NAO provados:** Qwen3.5 2B/4B do projecto RIGHTWARE nao foram testados pelo Manus. `qwen2.5:3b` e outro modelo, nao se deve extrapolar fidelidade ou custos.
- O comando de `goose doctor` ficou interactivo e foi terminado por Manus; nao e evidencia de sucesso completo desse diagnostico.
- Nao ha evidencia de testes Windows, memoria persistente, checkpoint/restart, aprovacao humana real, limite de credits, nem integracao JARVIS.

## Veredicto por requisito

| Requisito | Estado | Evidencia |
|---|---|---|
| Goose consegue comunicar com motor Ollama local | OBSERVADO | metadata de inferencia `ollama/qwen2.5:3b` em ambos os logs |
| Goose chama ferramenta concreta e grava ficheiro | OBSERVADO | toolRequest `shell` + toolResponse com stdout/exit_code |
| Primeiro pedido compara correctamente | FAIL | comando apenas concatena |
| Segundo pedido compara correctamente | PASS LIMITADO | `diff -u`, criacao e leitura de report coerente |
| Replan autonomo apos falha | NAO TESTADO | retry foi separado e dirigido |
| Restricao de shell pelo Harness RIGHTWARE | NAO TESTADO | shell e ferramenta disponivel e usada |
| Compatibilidade Qwen3.5:2b/4b | NAO TESTADO | foi qwen2.5:3b |
| Integracao com OpenJarvis/AgentSession | NAO TESTADO | projecto RIGHTWARE intacto |
| Fiabilidade estatistica | NAO TESTADO | apenas duas tentativas dirigidas |

## Decisao de engenharia — TE-02

A evidência TE-01 justifica **manter goose como candidato**, nao importá-lo. A forma mais barata de medir a lacuna actual e um experimento restrito com o **executor existente** `rightware.agent.session.AgentSession`, que ja tem `AgentPolicy`, A1 contracts, A2 receipts e A3 completion gate. A nova `rightware/task_entry.py` e apenas um ponto de entrada opt-in host-owned para um preset sintetico de browser, sem shell, ferramentas de ficheiros, Windows, memoria, nem modelo real. Essa implementacao nao substitui o modulo goose e **nao** prova a entrega de tarefas gerais.

**Criterio de decisao posterior:** caso o executor actual demonstre uma lacuna concreta apos tarefas sinteticas de varios passos e testes reais aprovados, avaliar sidecar goose sob um proxy unico de ferramentas RIGHTWARE; nunca incorporar o builtin `developer/shell` com acesso irrestrito.

**Status de implementacao:** candidato TE-02 em branch isolada, independente de aceitação comercial. Consultar testes `tests/test_te02_task_entry.py`; sem chamadas Ollama neste incremento.
