# JRV-M01 — Memória pessoal persistente

Ramo de integração B6. Baseline `61db386`. Data: 26/11/2026.
**Não alterados:** `rightware/gui/auth.py`, `rightware/gui/policy.py`, o mecanismo B6 e a voz.
Classificação: **UNIT/FAKE** (testes) · **MODELO REAL** (Qwen 2B local, dados sintéticos) · **NÃO VERIFICADO**.

## 1. Auditoria de reutilização

| Componente | O que é | Decisão |
|---|---|---|
| OpenJarvis `memory/` (FactStore + MemoryService) | JSONL de "factos", **extraídos automaticamente** por LLM em segundo plano. Sem dono, categoria, id estável, correcção ou confirmação. | Não usado como armazenamento: a extracção automática contraria o consentimento. Reutilizada a ideia de proveniência e de quarentena (`trusted_for_recall`). |
| `memory_manage` / `user_profile_manage` | Ficheiros Markdown (`MEMORY.md`/`USER.md`) que o **modelo** altera directamente, por substituição de texto. | Não usado: sem controlo do anfitrião nem dono. |
| `tools/storage/sqlite.py` (knowledge) | Índice de documentos para pesquisa. | Mesma tecnologia (SQLite, stdlib). A base de dados é separada, porque memória ≠ documentos (JRV-K01). |
| `security/scanner.py` | `SecretScanner` / `PIIScanner`. O módulo Rust não está instalado, por isso as classes não instanciam. | **Reutilizados os `PATTERNS`** (chaves, tokens, cartões, padrões críticos). |
| `security/injection_scanner.py` | Só padrões em inglês. | **Reutilizado** e complementado com o detector PT/EN do R02. |
| `AgentSession` | Ferramentas do anfitrião com `extra_tools`, decididas pela `AgentPolicy`. | **Reutilizado** sem alterações: as ferramentas de memória entram por aqui. |
| `ToolChatAdapter` | O núcleo conversacional (router → conversa directa ou ferramentas), comum a texto e voz. | **Integração aqui**: a memória entra nos dois caminhos. |
| `persona` / `configs/profile.json` | Identidade JARVIS; perfil autorizado (nome, língua, voz). | Mantidos. A persona declara a memória só quando está activa. O perfil continua a ser configuração do operador, não memória aprendida. |
| Histórico de conversa (`TextFacade`, bridge) | Em memória, por sessão, limitado. | Mantido. A memória persistente é uma camada separada e explícita. |

## 2. O que foi construído (`rightware/memory/`)
- **`store.py` — SQLite** em `.runtime/memory/jarvis-memory.sqlite3` (modo 0600; `.runtime/` nunca vai para o git).
  - **Campos:** `id` (`m-` + 8 hex), `owner`, `category` (preferência / facto / objectivo / contexto), `topic`, `content`, `provenance` (fonte, canal, citação do pedido, correcções), `created_at`, `updated_at`, `status`, `superseded_by`.
  - **Estados de `status`:**
    - `confirmed`: é recuperada;
    - `pending`: reservado para aprendizagem sugerida no futuro; nunca é recuperada;
    - `superseded`: substituída por uma versão mais recente; fica guardada com a proveniência, mas não é recuperada.
  - **Contradições:** uma nova memória com o mesmo dono, categoria e tópico substitui a anterior.
  - **Correcção:** mantém o id e acrescenta a proveniência da correcção.
  - **Eliminação:** apaga a linha e as versões substituídas. O registo de eventos guarda só id, acção e hora, nunca o conteúdo.
- **`policy.py` — o que pode alterar a memória (determinístico, no anfitrião):**
  - **Intenção do utilizador:** escrever exige um pedido explícito na **mensagem do utilizador** (lembra, aprende, prefiro, corrige, a partir de agora…); esquecer exige "esquece", "apaga", "elimina"… O texto de páginas, documentos, resultados de ferramentas ou do próprio modelo **nunca** autoriza alterações.
  - **Fundamentação:** a maior parte das palavras do conteúdo tem de estar no que o utilizador disse, tolerando conjugações (prefere/prefiro). Isto impede o modelo de guardar invenções ou conteúdo externo.
  - **Recusa:** credenciais, senhas, tokens, chaves, NUIT, BI, passaporte, IBAN e números de conta ou cartão (sequências longas de dígitos), padrões críticos do OpenJarvis, e texto com forma de instrução.
- **`personal.py` — `PersonalMemory`:**
  - **Recuperação antes da inferência:** só memórias **relevantes** (sobreposição lexical) e até 3 preferências recentes. O conjunto alargado (até 15) só aparece quando o utilizador pergunta "o que sabes sobre mim". Nunca carrega a base inteira.
  - **Bloco de contexto:** enquadrado como dado consentido, não instruções, com ids para corrigir ou esquecer.
  - **Ferramentas:** `memory_save`, `memory_update`, `memory_forget`, `memory_list`. A confirmação vem **só** do resultado da escrita na base.
  - **Anotações do anfitrião:** "✓ Verificação do anfitrião (memória): guardada [id] …".
  - **Confirmações falsas:** linhas do modelo que imitam a confirmação do anfitrião são removidas. Se o modelo diz "guardei" sem escrita real, a resposta recebe "⚠ … nada foi guardado" e a voz lê só o aviso.
- **`identity.py` — contrato de dono:** `lab:`, `local:` ou `user:<nome>`. **Nunca** o id temporário da sessão B6. Hoje é um dono por processo (`StaticOwner`), declarado pelo operador.

**Integração:**
- **Núcleo conversacional:** `ToolChatAdapter(memory=…)`, o mesmo para texto e voz, porque a voz entra no mesmo chat.
- **Caminhos:** a recuperação vai para os **dois** caminhos (conversa directa e ferramentas). Os pedidos de memória passam directamente às ferramentas verificadas pela política, sem depender da decisão do router.
- **Launcher:** `labs/presentation/serve.py --memoria-dono <dono> [--memoria-ficheiro …]`.

## 3. Identidade — integração pendente
O B6 prova a posse de um link de uso único, não **quem** é a pessoa. Por isso:
- **Hoje:** um processo do JARVIS tem **um** dono (o computador do Issa → `local:issa`). Num servidor partilhado, pessoas diferentes **não** podem usar o mesmo processo com memória.
- **A coordenar com o responsável do B6** (não feito aqui, porque toca em `auth.py`):
  - emitir links de uso único **por dono declarado**;
  - na troca do link, ligar a sessão a esse dono;
  - expor ao `ToolChatAdapter` um fornecedor de dono por pedido.
  - O contrato `Owner(owner_id, verified_by)` já existe para isso.

## 4. Testes
- **UNIT/FAKE:** `tests/test_m01_memory.py`, 18 testes.
  - **Armazenamento:** campos, persistência entre instâncias (reinício), substituição, correcção com proveniência, eliminação, isolamento entre donos, contrato de dono.
  - **Política:** intenções, dados sensíveis, injecção, fundamentação.
  - **Ferramentas:** sem intenção → recusa; invenção ou conteúdo externo → recusa; dono alheio → não encontrado.
  - **Recuperação:** só o relevante, mais as preferências.
  - **Adaptador:** ensinar → nova conversa → reinício → corrigir → eliminar → isolamento; conversa directa com memória; confirmação falsa assinalada; ficheiros protegidos intocados.
- **Suite completa:** 787 OK (20 testes de memória).

## 5. Aceitação com o modelo real (Qwen 2B local, donos sintéticos `lab:alfa`/`lab:beta`)
- **Harness:** `labs/m01/run_acceptance.sh`.
  - Cada passo corre num **processo novo**, numa **conversa nova** (sem histórico), pelo núcleo do produto: router → conversa directa ou ferramentas, com `PersonalMemory`.
  - O **Ollama é reiniciado** a meio.
  - A base SQLite fica no scratchpad (nunca no git).

| Execução | Resultado | Causa / correcção |
|---|---|---|
| 1 (`run1.jsonl`) | **FALHA** no passo 1: nada guardado | O 2B parafraseou ("O utilizador prefere… moçambicanos"); a fundamentação recusou. "Guardado"/"MEMÓRIA GUARDADA" não foram assinalados (o detector só conhecia "guardei"). → palavras-meta ignoradas; detector de particípios; conteúdo proposto registado. |
| 2 (`run2.jsonl`) | **FALHA** no passo 1 | O 2B embelezou ("financeiros e de desempenho… em vez de outras moedas") e não repetiu a chamada. → **Desenho corrigido:** o modelo decide guardar; se o texto não for fiel, o anfitrião guarda as **palavras do próprio utilizador** (sem o comando), com os mesmos filtros. |
| 3 (`run3.jsonl`) | **PASSA nos 9 passos** | Ver a tabela seguinte. |

**Execução 3 (FACTO):**

| Passo | Processo | Resultado |
|---|---|---|
| 1 Ensinar | 13363 | O modelo propôs uma paráfrase não fiel. O anfitrião guardou `m-75ba45f4` «Prefiro que os meus relatórios sejam apresentados em meticais». Confirmação do anfitrião baseada na escrita real. |
| 2 Nova conversa | 14088 | Recuperou `m-75ba45f4` (caminho de conversa directa) e respondeu "meticais". |
| 9a Isolamento (antes de eliminar) | 14708 | O dono `lab:beta` não recuperou nada; `memory_list` devolveu vazio para beta. |
| 3 Reinício completo | — | Ollama reiniciado; todos os passos em processos novos. |
| 4 Depois do reinício | 15402 | Recuperou `m-75ba45f4` e respondeu "Meticais". |
| 5 Corrigir | 16024 | `memory_list` → `memory_update` `m-75ba45f4` (o id mantém-se). Base de dados: «… em dólares americanos». |
| 6 Confirmar | 16652 | Respondeu "dólares americanos (USD)". |
| 7 Eliminar | 17274 | `memory_forget` `m-75ba45f4`; base de dados vazia. |
| 8 Confirmar a eliminação | 17906 | Nada recuperado; "memória pessoal vazia". |
| 9b Isolamento | 17915 | O dono `lab:beta` continua sem memórias. |

**Observações do modelo, não da memória:**
- **Embelezamento:** o 2B acrescenta texto ao responder ("relatórios financeiros e de desempenho" no passo 1), embora o que fica guardado sejam as palavras do utilizador.
- **Alucinação sem relação com a memória:** no passo 6 disse "tenho acesso a dados financeiros reais".
- **Dono vs. nome de perfil:** chama "Issa" ao dono sintético, porque a persona usa o nome do perfil autorizado (`configs/profile.json`). A persona e o perfil não estão ligados ao dono da memória. Fica pendente com a integração de identidade.
- **Aviso correcto no passo 7 da execução 2:** o modelo disse "tem apagado" sem nenhuma eliminação real (não havia memória), e o anfitrião acrescentou correctamente ⚠ "nada foi … eliminado". Na execução 3 a eliminação foi real e confirmada pela base de dados.

## 6. Limitações
- **Identidade:** um dono por processo. Não há ligação sessão B6 ↔ dono (ver secção 3).
- **Recuperação:** é lexical; sinónimos sem palavras em comum podem não ser recuperados (por isso as preferências entram sempre, até 3).
- **Detecção de intenção:** usa expressões em português. Pedidos implícitos ("o meu fornecedor agora é X") não são guardados sem "lembra-te", "prefiro", "corrige"… É deliberado: só se guarda com consentimento explícito.
- **Palavras literais:** quando o anfitrião guarda as palavras do utilizador, o conteúdo fica na 1.ª pessoa e em bruto, sem normalização.
- **Interface:** não há ainda ecrã para ver, editar ou apagar memórias; isso faz-se por conversa (`memory_list`, corrigir, esquecer).
- **Base de dados:** sem cifragem em repouso (ficheiro 0600 em `.runtime`).

## 7. Próximo passo
- Coordenar com o responsável do B6 a ligação sessão ↔ dono, depois do JRV-ID01-A.
- Ecrã de memórias na HUD (ver, editar, apagar), com aprovação do design.
- Activar `--memoria-dono local:issa` só no computador do Issa, depois da aceitação do operador.
