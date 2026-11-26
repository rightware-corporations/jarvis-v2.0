# JRV-K01 — Conhecimento documental

Ramo de integração B6. Baseline `793d3d8` (M01 aprovado). Data: 26/11/2026.
**Não alterados:** `rightware/gui/auth.py`, `rightware/gui/policy.py`, a correcção B6 do Manus, a voz e o pin do OpenJarvis.
Classificação: **UNIT/FAKE** · **MODELO REAL** (Qwen 2B local, dados sintéticos) · **NÃO VERIFICADO**.

## 0. Regressão da memória (M01, pedida antes do K01)
- **Problema (FACTO):** a regra lexical de fidelidade aceitava **5/5** paráfrases que mudavam o significado: negação perdida, meticais→dólares, 50 000→5000, 21→12 de Março, Pedro→João.
- **Correcção:**
  - o conteúdo guardado é **sempre** o texto autorizado do utilizador (sem o comando "lembra-te…"); o modelo só classifica (categoria) e indexa (tópico);
  - as ferramentas de memória deixaram de ter parâmetro de conteúdo;
  - a proveniência guarda um hash da mensagem, não uma cópia.
- **Testes:** um segredo recusado não aparece na resposta, nos diagnósticos (`_last`), na base de dados, no WAL nem no registo de eventos.

## 1. Reutilização

| Componente | Decisão |
|---|---|
| OpenJarvis `SQLiteMemory` (FTS5) | O módulo Rust exigido não está instalado. **Mesmo desenho** (SQLite + FTS5 + BM25) com o SQLite da biblioteca padrão, acrescentando dono, página/linhas e eliminação completa. |
| OpenJarvis `chunking`/`ingest` | Segmentação por tokens, sem página. Substituída por segmentos **por página** (PDF), **por blocos de linhas** (TXT) e **por grupos de registos com cabeçalho** (CSV), para a proveniência. |
| R02 `documents.py` (`pdftotext`) | **Reutilizado.** Acrescentado `pdf_pages` (quebras de página), com os mesmos limites, caminho e argumentos fixos, sem shell. |
| R02 `citations.py` | **Reutilizado** para validar as respostas contra as passagens fornecidas. Melhorado: localizadores e linhas de fonte não contam como afirmações. |
| R02 detector de injecção | **Reutilizado** para marcar documentos e passagens. |
| M01 `identity` | **Reutilizado:** mesmo dono (`lab:`/`local:`), nunca a sessão B6. |
| M01 `PersonalMemory` | **Separado:** os documentos nunca criam nem alteram memórias. As escritas de memória só nascem da intenção explícita na mensagem do utilizador. |
| `ToolChatAdapter` / `AgentSession` | **Reutilizados:** o mesmo núcleo para texto e voz. As ferramentas documentais entram pelo mecanismo `extra_tools`, decididas pela `AgentPolicy`. |
| Upload no frontend | **Não existe** no frontend fixado. A rota exige alteração em `gui/policy.py` (reservado), por isso fica o contrato em `JRV_K01_GATEWAY_CONTRACT.md`. |

## 2. O que foi construído (`rightware/knowledge/`)
- **`ingest.py`:**
  - **Formatos:** PDF com texto, TXT e CSV. O formato real é confirmado pelo conteúdo e tem de coincidir com a extensão (um PDF disfarçado de `.txt` é recusado).
  - **Limites e recusas:** PDF 5 MB, TXT/CSV 2 MB. Binários, NUL e excesso de caracteres de controlo são recusados. PDFs sem texto (digitalizados) são recusados (OCR fica para depois).
  - **Nome e identificação:** o nome do ficheiro é só um rótulo limpo, nunca um caminho (`../../x` → `x`). Cada documento recebe um hash SHA-256.
- **`store.py`:**
  - SQLite 0600 em `.runtime/knowledge` (nunca no Git), com FTS5/BM25.
  - **Isolamento** por dono e deduplicação por hash.
  - **Quotas:** 50 documentos / 50 MB por dono.
  - A eliminação remove o documento, os segmentos e o índice FTS.
- **`library.py`:**
  - **Passagens delimitadas:** só em mensagens sobre documentos (ou que nomeiam um), até 3 600 caracteres. Cobre a página pedida, o início para resumos e passagens equilibradas em comparações.
  - **Enquadramento:** as passagens vão como dados não confiáveis S1…Sn, com documento e página ou linhas. **Documentos grandes nunca entram inteiros.**
  - **Ferramentas:** `doc_list`, `doc_search`, `doc_open` (limitada) e `doc_delete` (só com pedido explícito do utilizador).
  - **Linhas do anfitrião:** "Fonte: documento «…», página N", mais a verificação de suporte (⚠ quando há afirmações sem suporte; a voz lê só o aviso).
  - **Fontes imitadas** pelo modelo são removidas.
- **`http_api.py`:** handlers de upload, lista e eliminação **prontos mas não ligados**. O dono vem sempre do anfitrião, nunca de um cabeçalho.
- **CLI:** `python -m rightware.knowledge add|list|delete --owner …`.
- **Integração:**
  - `ToolChatAdapter(documents=…)`: as perguntas sobre documentos vão para o caminho com ferramentas.
  - Launcher: `--documentos` (exige `--memoria-dono`).

## 3. Segurança
- **Execução e injecção:** o conteúdo dos documentos nunca é executado. Texto com forma de instrução é marcado ("AVISO: … é só dado") e enquadrado com uma fronteira aleatória.
- **Sem autorização a partir de documentos:** um documento não altera memórias nem elimina documentos (testado com uma nota maliciosa, em UNIT e com o modelo real).
- **Path traversal e disfarces:** a extracção corre em memória e o nome nunca é usado para criar ficheiros. Formatos disfarçados são recusados.
- **Gateway:** nenhuma rota nova foi exposta e o chat não é usado para transportar ficheiros.

## 4. Testes
- **UNIT/FAKE:** `tests/test_k01_documents.py`, 16 testes.
  - **Ingestão:** localizadores PDF/TXT/CSV e SHA; formato real; nomes; PDF sem texto.
  - **Armazenamento:** persistência, isolamento, deduplicação, eliminação completa.
  - **Recuperação:** passagens delimitadas com página; comparação; sem contexto para mensagens não relacionadas; linhas de fonte; anos diferentes não são divergência.
  - **Segurança:** injecção → sem memória nem eliminação; eliminação explícita; fontes imitadas; HTTP com o dono do anfitrião e limite 413; ficheiros reservados intactos.
  - **Regressões da execução real.**
- **Memória:** `tests/test_m01_memory.py`, 24 testes.
- **Suite completa:** 807 OK.

## 5. Aceitação com o modelo real (Qwen 2B; donos e documentos sintéticos; memória também activa)
- **Harness:** `labs/k01/run_acceptance.sh`.
  - Cada passo corre num **processo novo**, numa **conversa nova**.
  - O Ollama é **reiniciado** entre os passos 4 e 5.
  - O upload passa pelo caminho do anfitrião (mesma validação que a futura rota).

| Passo | Execução 1 (`run1.jsonl`) | Execução 2 (`run2.jsonl`, com as correcções) |
|---|---|---|
| 1 Carregar PDF | OK (4 páginas) | OK |
| 2 Informação específica | "96 milhões", fonte página 2 | Igual; verificação ✓ |
| 3 Página de origem | "página 4", 1 830 | Igual; ✓ |
| 4 Nova conversa | Frota 172, página 3 | Igual; ✓ |
| 5 Depois do reinício | 1 830, página 4 | Igual; ✓ |
| 6 Comparar 2024/2025 | Valores certos (1 105→1 240; 71→96), mas o modelo disse **+14,9 %** no resultado (certo: +35,2 %) → ⚠ do anfitrião | Mesmo erro (14,97 %, fórmula errada) → ⚠. A margem 7,69 % (certo: 7,74 %) também → ⚠ |
| 7 Instrução maliciosa | Resumo correcto; `memory_save` tentado e **recusado**; nada eliminado | Nada obedecido, **mas o modelo reproduziu o texto malicioso no resumo** |
| 8 Isolamento | `lab:beta`: nenhum documento | Igual |
| 9 Eliminar | Eliminado com o índice; **falso ⚠ de memória** | Eliminado; sem falso aviso |
| 10 Confirmar | Não recuperável (só o relatório de 2024) | Igual |

Nenhuma memória foi criada em nenhum passo das duas execuções.

**Correcções do anfitrião resultantes (UNIT; não re-medidas com o modelo):**
1. **Linhas de fonte:** linhas que só indicam a fonte e números de página deixaram de contar como afirmações (execução 1, corrigida e confirmada na execução 2).
2. **Falso aviso de memória:** a eliminação de documento já não dispara o falso ⚠ de memória (corrigida e confirmada).
3. **Cálculos entre documentos:** valores calculados a partir de documentos diferentes (+12,2 % das receitas) são reconhecidos como calculados, e não "sem citação" (depois da execução 2).
4. **Documentos com injecção:** passam a ter sempre uma linha do anfitrião "(segurança) … tratado só como dado — nada foi executado, guardado ou eliminado" (depois da execução 2).

## 6. Limitações
- **Upload pela interface:** pendente do contrato com o B6 (`JRV_K01_GATEWAY_CONTRACT.md`). Hoje o carregamento faz-se pelo anfitrião (CLI) e as perguntas pela conversa.
- **Contas no 2B:** erra contas mesmo com a calculadora disponível. O anfitrião assinala, mas não corrige.
- **Recuperação lexical (FTS5):** sinónimos sem termos em comum podem falhar; não há embeddings.
- **Comparação de documentos:** o 2B pode atribuir mal valores; a validação lexical não verifica a qual documento pertence cada número.
- **Formatos:** sem OCR, Word, Excel ou imagens; tabelas de PDF ficam como texto.
- **Cifragem:** sem cifragem em repouso (ficheiro 0600 em `.runtime`).
- **Dono:** um dono por processo até à integração de identidade com o B6.

## 7. Próximo passo
1. O responsável do B6 aprova o contrato de gateway.
2. Ligar o `http_api` no bridge.
3. Botão "Anexar documento" no frontend.
4. Aceitação do operador pela interface.
