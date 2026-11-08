# RIGHTWARE Jarvis v2 — continuidade

## Decisão desta sessão

O utilizador forneceu `rightware-corporations/jarvis-v2.0` para concretizar a implementação separada baseada no OpenJarvis. O projecto anterior `rightware-corporations/jarvis` deve ser preservado. Branches: main e develop. Produto independente do Claude no runtime; modelo local ou auto-hospedado, sem API paga obrigatória.

## Evidência anterior, não reexecutada por esta fundação

Ensaio OpenJarvis/Qwen3.5 2B/Ollama 0.40.15 em CPU: conversa, resposta Maputo, recordação parcial de Orion e ferramenta calculator real (137 × 29 = 3973). Personalização de identidade funcionou com agent.default_system_prompt. Houve invenções sobre Orion; fidelidade não aprovada. O ensaio anterior resolveu dependências no momento; esta fundação usa uv.lock upstream com --frozen, pelo que uma nova prova real é necessária.

Mark XXXIX-OR foi investigado: Gemini Live/OpenRouter, sem percurso Ollama encontrado e README com uso não comercial. Não foi importado.

## Implementado

- Upstream fixado em submódulo, atribuição e licença.
- Camada RIGHTWARE de setup/doctor/chat; configuração portuguesa.
- Logs de instalação e remoção de credenciais cloud do ambiente filho.
- Quatro testes dirigidos de configuração/encaminhamento.
- Workflow leve para estes testes; não é CI de inferência nem suite upstream.

## Limites

Sem migração da camada Wyzer. Sem voz, GUI, wake word, acções Windows ou memória persistente validados. Não chamar esta etapa release. OLLAMA_NO_CLOUD no cliente não reconfigura um daemon já existente. O Kaggle é laboratório temporário. Não instalar no PC do destinatário por inferência.

## Próxima execução

1. Clonar develop com submódulos; executar setup e doctor com Ollama local.
2. Executar o corpus curto com modelo real e preservar respostas/tempos por SHA.
3. Comparar uma alternativa de modelo no mesmo ambiente; escolher pelo resultado, não apenas tamanho.
4. Só depois integrar voz e tarefas no Windows autorizado.

Consultar docs/VALIDATION.md para o que foi efectivamente validado nesta entrega. Actualizar este ficheiro após cada resultado material.


## ADENDA — 08/11/2026: execução em 48 horas e disciplina obrigatória de handoff

### Direcção explícita da RIGHTWARE (CONFIRMADA)
- **Prazo e prioridade:** dispor de um Jarvis v2 utilizável dentro de dois dias de trabalho/48 horas de execução. Parar ciclos intermináveis de QA; corrigir bloqueadores do percurso real. O prazo é meta de execução, não declarar sucesso antes do aceite.
- **Handoff contínuo:** após **cada output material** (ensaio, alteração, CI, erro, decisão), actualizar este handoff **no mesmo ciclo de trabalho**, com SHA, ambiente, comando/cenário, resultado observado, PASS/FAIL/REVIEW/NOT RUN, evidência sanitizada, bloqueio, responsável e próxima acção. Não substituir histórico, não inventar resultados; manter PR Draft até critérios cumpridos.
- **Motor em operação:** independente de Claude/serviços pagos obrigatórios. Kaggle é laboratório transitório, não runtime do produto.
- **Repositórios:** desenvolver apenas neste `rightware-corporations/jarvis-v2.0` na `develop`; preservar `rightware-corporations/jarvis` como referência histórica. Apenas `main` e `develop`.

### Estado verificado antes desta adenda
- Base `develop@8d92705c30f965e4e344427604a8500bab45d388`; PR #1 Draft; duas execuções do workflow de fundação em 08/11 PASS (runs `42492070438` e `42492070280`), cada uma contendo apenas testes unitários do launcher no Linux. Não são validação de inferência.
- Upstream fixado em `f21d902f4d3bd7f0f3f138f1a4613019a394b549`; launcher português com `agent=simple` e modelo inicial `qwen3.5:2b`. O agente `simple` do upstream **não aceita ferramentas**, embora aceite histórico de mensagens: a prova da calculadora exige um caminho de agente distinto, com resultados de ferramenta auditados.
- O relato final do Work confirma Ollama 2B descarregado/carregado e conversa real iniciada, mas **não inclui transcrição completa das seis perguntas, resultado da ferramenta na nova base, avaliação do 4B ou ZIP Kaggle**. Esses resultados continuam NOT RUN/NOT VERIFIED para a v2.0.
- `child_environment()` continua a herdar variáveis proxy para o subprocesso da CLI; `doctor()` ignora proxies nas suas próprias consultas. Rever bloqueio proxy na CLI antes da prova de inferência. Não atribuir ao modelo falhas de transporte.
- Consola desta sessão: Linux x86_64/Python 3.13.5, RAM total ~5.8 GiB, sem nvidia-smi nem Ollama instalado. Não tem acesso garantido ao Kaggle do utilizador ou Windows físico.

### Plano de entrega (RECOMENDAÇÃO DE IMPLEMENTAÇÃO; nenhuma fase abaixo foi validada por esta adenda)
| Janela de trabalho | Entrega exigida | Gate e regra de paragem |
|---|---|---|
| H0–H4 | Baseline reprodutível: revisão de SHA, transporte sem proxy indevido, setup/doctor, corpus curto, script/notebook de ensaio e artefactos de prova sanitizados | CI unitário PASS; nenhuma credencial ou transcript pessoal no git. Não apresentar o doctor como prova de inferência. |
| H4–H12 | Teste GPU Kaggle ou host equivalente: 2B vs 4B, **mesmas seis perguntas**, contexto Orion conhecido/desconhecido, identidade e aritmética. Ferramentas **num cenário separado** com agente habilitado | Respostas completas e métricas (modelo, SHA, GPU, tempos, RAM/VRAM); proibir invenção de dados críticos, falsas afirmações de execução ou ferramenta sem autorização. |
| H12–H20 | Escolher modelo e corrigir até **dois bloqueadores de maior impacto** identificados na prova real, com reteste focalizado | Decisão documentada com evidência; não iniciar treino, refactor ou memória vectorial por rotina. |
| H20–H36 | Integrar STT/TTS PT básicos e **duas acções Windows permitidas** (ex.: abrir Bloco de Notas e Calculadora), confirmação e cancelamento, em host autorizado | Provas com microfone/áudio e efeitos Windows reais; sem autorização explícita, reportar BLOQUEADO, nunca PASS. |
| H36–H48 | Integração, regressão limitada, arranque/reinício e empacotamento de instruções; demonstração de ponta a ponta | Entregar comando de arranque, evidência reproduzível, falhas residuais, aceite ou NO-GO. |

### Critérios mínimos de aceitação do MVP (objectivo)
1. Iniciar Jarvis com procedimento documentado, sem API paga; responde em português e identifica-se como Jarvis da RIGHTWARE.
2. Mantém contexto básico durante seis turnos de uma sessão, incluindo mudança de tópico e retorno. Sobre Orion, só afirma factos fornecidos e assume desconhecer orçamento/equipamentos.
3. Executa uma ferramenta **real** com resultado auditável, distingue resposta calculada pelo modelo de `tool_results`.
4. Numa máquina Windows autorizada, STT reconhece um pedido PT, TTS reproduz resposta; duas acções permitidas só ocorrem com pedido/autorização, confirmação e possibilidade de cancelamento; execução observável.
5. Segurança P0: zero operações não solicitadas, zero segredos publicados; rejeita execução não autorizada e nunca diz que executou algo sem `tool_result` verificado.
6. Repetir arranque após reinício e guardar instruções de uso. UI/HUD cinematográfico, wake word, memória durável, treino de pesos, instalação comercial e arquitectura distribuída **fora do escopo** inicial, salvo funcionalidade pronta comprovada.

**Ponto de corte dos testes:** parar depois de uma comparação controlada e de um reteste dirigido por falha, seguido de smoke final. Não repetir baterias completas sem alteração material. Se P0 continuar, reduzir âmbito e registar NO-GO explícito, sem fingir MVP aceite.

### Protocolo de registo para as próximas saídas
```text
[DATA/HORA UTC+02] [WORK-PACKAGE] [SHA] [AMBIENTE]
OBJECTIVO / COMANDO OU CENÁRIO:
RESULTADO OBSERVADO (PASS | FAIL | REVIEW | BLOCKED | NOT RUN):
EVIDÊNCIA (link, run ID, ficheiro sanitizado):
CAUSA/INCERTEZA:
PRÓXIMA ACÇÃO E CRITÉRIO DE ACEITAÇÃO:
```

**Próxima acção:** corrigir/validar transporte e preparar o harness de comparação versionado no repositório. Executar Kaggle somente com artefactos de execução suficientes; usar GPU para teste, não treino de pesos. Priorizar funcionalidade real, não número de testes.


## ADENDA — 08/11/2026: identidade do destinatário (DECISÃO EXPLÍCITA)

**Correcção confirmada pela RIGHTWARE:** o produto é **JARVIS DO ISSA** (Jarvis — Issa Edition), assistente pessoal **destinado ao Issa**. **RIGHTWARE é a organização desenvolvedora**, não a pessoa a quem o assistente se destina. Esta decisão prevalece sobre a frase histórica «Jarvis da RIGHTWARE» presente nos critérios de aceitação anteriores. Não confundir Issa com o operador da RIGHTWARE nem com a entidade empresarial.

- Identidade esperada em todos os ensaios e no produto: «Sou o Jarvis, assistente pessoal do Issa, desenvolvido pela RIGHTWARE», em português natural; outras formulações correctas são permitidas.
- O prompt inicial em `configs/local.toml` foi alinhado nesta mudança. **Limite:** `prepare_config()` só copia a configuração para `.runtime/openjarvis/config.toml` caso ela ainda não exista. Sessões previamente configuradas **não recebem automaticamente o prompt novo**: actualizar o arquivo runtime com preservação de preferências e sem apagar dados do utilizador.
- Actualizar o corpus do benchmark 2B/4B para avaliar especificamente a identidade do Issa. A referência Orion continua sendo **dado sintético de teste**; não afirmar que é um projecto real do Issa.
- Estado: **DECISÃO REGISTADA / CONFIGURAÇÃO DE REPOSITÓRIO ALTERADA / INFERÊNCIA REAL NÃO REEXECUTADA**. Os testes anteriores não provam que o modelo respeitará a identidade.
- Próxima acção: validar o prompt pela sessão real; em seguida prosseguir a comparação de modelos, voz e ferramentas Windows no prazo do MVP.

## ADENDA — 08/11/2026: H0–H4 transporte, comparador e laboratório Kaggle

**Produto:** JARVIS DO ISSA, desenvolvido pela RIGHTWARE.
**Estado:** preparação e testes unitários no GitHub concluídos; execução de modelos na GPU Kaggle AINDA NÃO EFECTUADA.

### Evidências de cada output material (branch develop)

| Marco | Commit | Evidência / status |
|---|---|---|
| H0-01 Transporte loopback sem proxies herdados | 2ef812ff | Código de rightware/runtime.py alterado; CI PASS |
| H0-02 Regressão de proxies | 4218f416 | tests/test_runtime.py com asserts novos; CI PASS |
| H0-03 Corpus + comparador real OpenJarvis | 6929f0b6 | qa/compare_models.py publicado; execução real NOT RUN |
| H0-04 Testes de preflight | af29fe72 | Casos sintéticos, modelo cloud rejeitado, evidências JSON; CI PASS |
| H0-05 Notebook para GPU | 40617014 | qa/JARVIS_ISSA_KAGGLE.ipynb publicado; Kaggle NOT RUN |
| H0-06 Sintaxe e contrato do notebook | bfbfa841 | CI runs 42498924112 e 42498930402 PASS |
| H0-07 Instruções no README | 1aae7109 | Guia de utilização e limitações publicado |
| H0-08 Ambiente realmente saneado no benchmark | 2d3fcd73 | Usar os.environ.clear() + update(), pois só update preservava proxies; CI run 42499026517 PASS |

### Decisões técnicas aplicadas

- Seis perguntas idênticas em sessões separadas por modelo Qwen3.5 2B e 4B. As respostas completas, latência por turno, SHA, ambiente e utilização de GPU entram num JSON escrito progressivamente.
- Os dados Orion são inteiramente fictícios; o orçamento e os equipamentos não são fornecidos. O modelo não pode inventá-los.
- A identidade correcta é Jarvis pessoal do Issa, desenvolvido pela RIGHTWARE. A configuração existente de uma sessão antiga não é sobrescrita sem revisão.
- O agente simple mantém histórico mas não tem ferramentas. A prova da calculadora é feita separadamente por native_react com CalculatorTool original; só se considera execução se tool_results mostrar success=true e 3973.
- O notebook utiliza o upstream fixado, Ollama 0.40.15 com hash oficial do artefacto Linux, GPU do Kaggle, repositório privado via Kaggle Secret GITHUB_TOKEN e ZIP de evidências. Não faz actualização silenciosa de um checkout já existente.
- Não interpretar testes de CI como demonstração com LLM, voz, microfone, Windows ou produto pronto.

### Próximo gate imediato — H4–H12

1. Abrir qa/JARVIS_ISSA_KAGGLE.ipynb no Kaggle com Internet e GPU, definir GITHUB_TOKEN com acesso read-only ao repositório privado em Kaggle Secrets.
2. Executar as três células por ordem; confirmar o SHA impresso antes de comparar.
3. Guardar o ZIP JARVIS_ISSA_QWEN_EVIDENCE_*.zip e analisar separadamente cada resposta e tool_results, sem atribuir percentagem automática.
4. Actualizar este handoff com tempos, recursos, SHA, respostas, falhas e veredicto, imediatamente após receber o output. Modelo definitivo continua PENDENTE.
5. Passar para voz e acções Windows até ao limite H20 para avaliação do motor, salvo falha crítica documentada.

**Bloqueio:** sem acesso à sessão privada Kaggle a partir deste chat, os testes GPU e a comparação real continuam NOT RUN. Ferramentas Windows e áudio continuam NOT RUN.
