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
