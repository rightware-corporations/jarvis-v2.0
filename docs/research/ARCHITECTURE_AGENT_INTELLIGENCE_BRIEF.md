# RIGHTWARE — Arquitectura do agente Jarvis do Issa (brief explicativo)

**Data:** 09/11/2026 (Africa/Maputo). **Estado:** análise do código existente e arquitectura **RECOMENDADA**, não implementação aprovada. **Base auditada:** RIGHTWARE `develop@6bac396a5c9db65879feccfb064fdb502d814c7e`; submódulo OpenJarvis `f21d902f4d3bd7f0f3f138f1a4613019a394b549`. Consultar sempre HEAD antes de actuar. Relatório de investigação base: [WORK01_ACTIVE_ASSISTANT_AUDIT.md](WORK01_ACTIVE_ASSISTANT_AUDIT.md).

## 1. Vocabulário: seis peças diferentes

1. **Modelo (Qwen3.5)** — prevê texto, interpreta linguagem e pode propor chamadas de ferramentas. Os pesos não são um assistente completo.
2. **Engine (Ollama)** — hospeda/serve localmente o modelo, tipicamente em `127.0.0.1:11434`. É um servidor **no próprio PC**, não uma cloud obrigatória.
3. **Agente (OpenJarvis)** — código Python que gere o ciclo entre pedido, modelo, ferramentas, observações e resposta. Não é um segundo modelo autónomo: utiliza Qwen através de Ollama.
4. **Tools/Skills** — operações invocáveis (ler documentos, cálculo, pesquisa, escritas limitadas, APIs, UI Windows). Ter o módulo no repositório não o torna automaticamente activo.
5. **Política RIGHTWARE** — decide se determinada chamada, com aqueles parâmetros, naquele contexto, foi autorizada; pode exigir preview/consentimento. O agente/modelo não concede a si próprio privilégios.
6. **Verificador/observabilidade** — confirma efeitos fora da narrativa do modelo (ficheiro existe e está íntegro, fonte, processo/pedido realmente concluído) e regista receipts sanitizados.

## 2. Situação REAL, verificada no código RIGHTWARE

- `configs/local.toml`: `engine.default="ollama"`, `default_model="qwen3.5:2b"`, `default_agent="simple"`, `context_from_memory=false`. **O 4B foi recomendado após K03, mas não substituiu ainda o default do ficheiro.** Pode ser seleccionado explicitamente por parâmetro no teste.
- `[agent].default_system_prompt` fixa identidade («Jarvis, assistente pessoal do Issa, desenvolvido pela RIGHTWARE»), português, distinção factos/hipóteses e proibição de alegar acções sem confirmação. Isto **não treina** o modelo nem lhe fornece ferramentas.
- `rightware/runtime.py` verifica PIN, valida Ollama loopback e configura o processo; `chat_command` passa explicitamente `-a simple`.
- `rightware/voice.py` usa `OpenJarvisBrain` com `SimpleAgent` + `AgentContext`; a memória conversacional é mantida **dentro da sessão**. Voz: Whisper local + SAPI/Kokoro, em código; voz portuguesa num PC Windows do Issa ainda sem aceite real.
- `rightware/windows_actions.py` reconhece comandos de abertura de Notepad e Calculadora por regras determinísticas em português; exige autorização de sessão/confirmacão por acção e verifica o PID. **Não** é um catálogo de tools seleccionado pelo modelo.
- K03 Kaggle: Qwen3.5 2B e 4B produziram conversa real e um `NativeReActAgent` separado chamou `CalculatorTool` e confirmou 3973.0. Ambos em `full_gpu`; não prova Orchestrator multi-tool. Hardware do PC Issa por confirmar.
- OpenJarvis fixado inclui `orchestrator`, `native_react`, `operative`, memória, scheduler, tools e frontend React/Tauri, mas **não há demonstração integrada do Jarvis activo nesta camada RIGHTWARE**.

## 3. Arquitectura ALVO recomendada — NÃO implementada

```text
Issa (texto, microfone, desktop)
   |
   v
INTERFACE RIGHTWARE / UI OpenJarvis adaptada
  STT Whisper → texto; resposta → SAPI/Kokoro; aprovação visível
   |
   v
CONTEXTO + INTENÇÃO + LIMITES (perfil, task_id, pastas, consentimento)
   |
   v
AGENTE OpenJarvis Orchestrator
   |                 \
   |                  -> Ollama local -> Qwen3.5 (interpreta/propõe)
   v
CATÁLOGO DE FERRAMENTAS (schemas; conjunto mínimo aprovado por tarefa)
   |
   v
POLÍTICA RIGHTWARE FAIL-CLOSED (por chamada, parâmetros e risco)
   |   + preview, confirmação humana, negação e cancelamento
   v
EXECUTOR RESTRITO Python/APIs/Windows/browser
   |
   v
VERIFICAÇÃO INDEPENDENTE DO ARTEFACTO OU EFEITO
   |
   +--> audit receipt / logs sanitizados
   +--> memória consentida / tarefa recorrente (quando aprovados)
   |
   v
RESULTADO REAL → resposta por voz e interface
```

Um pedido pode exigir várias rondas: agente propõe `read_file`; política autoriza a leitura; tool devolve conteúdo; o modelo analisa e propõe `write_report`; a política pede confirmação; após escrita, ferramenta independente `verify_report` reabre e valida saída; só então o sistema comunica êxito.

O modelo **propõe** qual ferramenta usar e que parâmetros; o **executor** validado faz operações. Um `system prompt` isolado não impede comportamento indevido nem cria acesso a disco/rede.

## 4. Que agentes existem e quando interessam?

| Agente upstream | Função | Estado para RIGHTWARE |
|---|---|---|
| `simple` | Conversa sem tools | **Utilizado actualmente**; inadequado para tarefas de execução |
| `native_react` | Loop de acção/observação | Calculadora real em ensaio Kaggle **separado**; multi-tool não validado |
| `orchestrator` | Multi-turn e selecção de tools com hooks de governação | **Candidato preferencial** para WORK-02; ainda não integrado nem provado com Qwen multi-tool |
| `operative` | Estado/sessões persistentes e tarefas recorrentes | Código upstream existe; não activado/aceite |
| `monitor_operative` | Monitorização mais longa e recuperação de contexto | Futuro, maior complexidade |
| `deep_research` | Pesquisa multi-hop e síntese | Existe; pesquisa real/atribuição a validar |
| `native_openhands` | Executa código para tarefas | Alto risco no PC pessoal; fora do primeiro slice |

Não precisamos de começar com uma equipa complexa de vários agentes. **Um Orchestrator com 3–5 ferramentas e um verificador** é suficiente para demonstrar o princípio. Só depois considerar agentes especializados e delegação.

## 5. System prompt: o que é e o que não é

No estado actual, a configuração `[agent].default_system_prompt` fornece regras de identidade/estilo. O OpenJarvis compõe mensagens de sistema, histórico e pedido através do runtime; o Orchestrator também pode incluir descrições de ferramentas e formato de chamadas.

O prompt pode dizer: «És o Jarvis do Issa; responde em português; pede autorização antes de escrever». **Não pode** por si só abrir ficheiros, validar permissões, impor sandbox ou executar tarefas. As capacidades dependem de `tools` instanciadas, executor e política testados. A regra de autorização deve sobreviver a respostas erradas do modelo, documentos externos e prompts maliciosos.

## 6. Qual é a base de dados?

**Hoje não existe uma única base de dados de produto configurada pela RIGHTWARE para o Jarvis do Issa.** Há vários mecanismos no upstream, com funções diferentes:

| Estado/dado | Tecnologia | Situação |
|---|---|---|
| Conversa corrente | Objectos `AgentContext` / `Conversation` em RAM | Utilizado por `rightware/voice.py`; termina com a sessão; persistência entre arranques não provada |
| Factos pessoais persistentes | `LocalFactStore` upstream usa ficheiro `memory_facts.jsonl` no directório de configuração | **Disponível no upstream**, não activado como memória automática RIGHTWARE; scanner de injecção tem falha fail-open identificada |
| Pesquisa documental / RAG | SQLite + FTS5 (e backends adicionais de recuperação, dependendo do setup) | **Disponível no upstream**; o backend inspeccionado exige extensão **Rust** mesmo com SQLite Python presente; não testado no PC Issa |
| Tarefas e histórico de execuções agendadas | `SchedulerStore` usa SQLite local via `sqlite3` | Disponível, não integrado/validado na experiência RIGHTWARE |
| Evidência de acções/diagnósticos | `.runtime/logs/` JSONL e JSON locais | Implementado parcialmente na camada RIGHTWARE, com dados operacionais e auditoria, não conversa integral por omissão |
| Modelos e pesos | Ficheiros geridos pelo Ollama | **Não** armazenados em SQLite/JSONL |
| Traces e telemetria upstream | Mecanismos upstream sujeitos à configuração | Não assumir retenção zero nem segurança de dados sem auditoria; `analytics/telemetry` RIGHTWARE desactivadas no perfil inicial |

**Não é obrigatório PostgreSQL nem um servidor de base de dados externo** para o primeiro produto local. Persistência de dados só deve entrar com política de retenção, proveniência, acesso, exportação/apagamento e backup. O `context_from_memory=false` da configuração actual significa que a recuperação automática de memória não foi activada no perfil inicial.

## 7. Exemplo de tarefa útil WORK-02

Pedido de prova sintética: «Lê `a.txt` e `b.txt`, cria um relatório sobre o projecto Orion com datas, responsável, indicação de orçamento desconhecido e cita as duas fontes.»

Resultado aceite **somente** quando: duas leituras reais, síntese genuína pelo modelo, consentimento específico para criar ficheiro, `resultado.md` novo dentro de workspace autorizado, verificação independente de conteúdo/hash, nenhum original modificado, logs e resposta condizentes. Tentativas sem autorização, caminho externo, injecção, cancelamento e timeout devem bloquear efeitos.

O WORK01 anterior testou essa sequência **com provider FAKE**, 30 cenários e 4 recusas; não provou OpenJarvis/Qwen real. O WORK02 é para resolver exactamente essa lacuna, primeiro num laboratório isolado. No ambiente do Claude pode não existir Ollama/GPU; marcar `REAL_NOT_RUN` e preparar execução Kaggle/Windows sem inventar resultado.

## 8. PC local, Internet e futuro

O núcleo pode correr no PC: UI + Python + Ollama + agentes + base local. APIs externas e pesquisa web podem ser chamadas a partir do próprio PC mediante Internet e consentimento, sem contratar um servidor cloud. Quando o PC está desligado, as automações locais param. Servidor externo só se justificar no futuro por disponibilidade contínua, acesso remoto ou hardware insuficiente. O equipamento Issa ainda precisa de medição.

## 9. Próximas decisões e execução

- **Requisito explícito:** a prova do MVP **não pode terminar na abertura de apps**; precisa de executar uma tarefa útil multi-etapa. Jarvis do Issa = piloto; RIGHTWARE = desenvolvedor e proprietário da camada própria.
- **Recomendação, não aprovação final:** Orchestrator + Qwen3.5 4B + tools de ficheiros restritas + guarda e verificador; sem shell, sem escrita fora da área autorizada, sem dependências cloud obrigatórias.
- **Claude / WORK02:** confirmar contratos JAR-*, pin/modelo/Rust, construir prova restrita, testar com Qwen real quando runtime existir, resultados e handoff. Não integrar voz/UI antes de observar tool-loop real. Preservar `main`.
- **Depois da prova:** escolher próxima capacidade de alto valor: Internet pública com fontes, ficheiros/Office, aplicações Windows, conectores consentidos, memória e automação agendada. A UI React/Tauri upstream deve ser avaliada antes de redesenhar tudo.
- **Nunca atribuir à RIGHTWARE funções upstream que não foram integradas e testadas.**

**Fontes no código:** `configs/local.toml`, `rightware/runtime.py`, `rightware/voice.py`, `rightware/windows_actions.py`, `docs/HANDOFF.md`; no pin upstream: `src/openjarvis/agents/{simple,orchestrator,native_react,operative}.py`, `src/openjarvis/memory/store.py`, `src/openjarvis/tools/storage/sqlite.py`, `src/openjarvis/scheduler/store.py`. A documentação publicada no website do OpenJarvis pode corresponder a commits posteriores e não prevalece sobre o PIN.
