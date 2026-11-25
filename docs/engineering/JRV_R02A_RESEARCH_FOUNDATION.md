# JRV-R02-A — Fundação da investigação autónoma (offline)

Ramo de integração B6, a mesma aplicação. Baseline `a9a2446`. Data: 25/11/2026.
Sem rede (corpus sintético local), sem túnel, sem dependências instaladas, sem autorização de rede activada.
OpenJarvis fixado em `f21d902` e intacto. A voz `pf_dora` a 1,15, o JPE-01 e as imagens Docker do Goose ficam preservados.

Classificação:
- **UNIT/FAKE:** testes com modelo roteirizado ou rede simulada.
- **MODELO REAL (offline):** Qwen 2B real via Ollama local, sobre o corpus sintético. Não é evidência sobre a Internet real.
- **NÃO VERIFICADO:** sem medição nesta sessão.

## 1. O que foi construído (`rightware/research/`)

| Módulo | Função |
|---|---|
| `provenance.py` | **Política de proveniência**, por pergunta. Ver detalhe abaixo. |
| `search.py` | **DuckDuckGo** (endpoint HTML), como primeiro motor. Ver detalhe abaixo. |
| `documents.py` | **PDF → texto** no anfitrião. Ver detalhe abaixo. |
| `citations.py` | **Validação de citações**. Ver detalhe abaixo. |
| `toolkit.py` | **`web_search`, `web_read`, `doc_read`** e o **registo de fontes**. Ver detalhe abaixo. |
| `text.py` | Números PT/EN (incluindo "950 mil" e "1 240 milhões"), palavras de conteúdo, frases. |

**`provenance.py`:**
- Só se abre o que veio desta pesquisa (R#), de uma página lida (L#, profundidade ≤ 2) ou que o utilizador escreveu (U#).
- URLs escritos pelo modelo ou pelo texto de uma página nunca são abertos.
- **Regras estáticas:** só https e porta 443; sem credenciais nem IP literal; sem nomes locais; sem páginas de login, conta ou administração; sem executáveis ou arquivos.
- **Controlo de destino:** se o transporte não verifica o IP de destino (`verifies_destination=False`), só a lista fechada do operador é legível.

**`search.py`:**
- Faz um GET por pesquisa **através do fetcher auditado**: verificação do servidor em cada salto, SSRF, limites e recibos.
- As ligações-invólucro `/l/?uddg=` são descodificadas localmente e nunca seguidas; os anúncios (`y.js`) são descartados.
- Uma página de verificação anti-robô ou de limite é reportada como **bloqueada** e **não é repetida nem contornada**.

**`documents.py`:**
- Usa o `pdftotext` do anfitrião, com caminho e argumentos fixos, sem shell e num directório temporário privado.
- Limites: 20 páginas, 5 MB, 20 s e 20 000 caracteres.
- O conteúdo tem de começar por `%PDF-`.

**`citations.py`** classifica cada afirmação da resposta:
- **SUPPORTED:** um *passo* da fonte citada contém todos os números e o contexto da afirmação.
- **DERIVED:** um valor calculado a partir da fonte ou da pergunta (produto, diferença, % de variação).
- **NUMBERS_OUT_OF_CONTEXT:** o número existe no documento, mas não neste contexto. *Não conta como verificado.*
- **UNSUPPORTED:** a fonte citada não contém a afirmação.
- **INVALID_CITATION:** cita uma fonte que não foi lida.
- **SUPPORTED_UNCITED:** não tem citação explícita, mas uma fonte lida suporta a afirmação.
- **UNCITED:** sem citação e sem suporte em nenhuma fonte.
- **Divergências** entre fontes são reportadas.

**`toolkit.py`:**
- O texto de cada fonte vai enquadrado como dado não confiável, com fronteira aleatória.
- **Prompt injection:** texto que tenta dar instruções é detectado, assinalado ao modelo e registado.
- **Orçamentos por pergunta:** 3 pesquisas, 6 leituras, 8 MB e 150 s.
- **Síntese forçada sem ferramentas** sobre as fontes já lidas, quando os turnos acabam (padrão do DeepResearchAgent).

**Integração (sem outro motor conversacional):**
- `AgentSession(research=…)`, com a capacidade **`websearch`**:
  - o `web_read` simples é substituído pelo de proveniência;
  - cada chamada continua decidida pela `AgentPolicy` (negado por omissão, quotas, prazo);
  - no fim, as citações são validadas pelo anfitrião.
- `ToolChatAdapter(research_factory=…)` cria um kit novo por pergunta, no mesmo caminho de chat, identidade, voz e recibos.
- **Voz:** as linhas do anfitrião começam por "Verificação do anfitrião" e não são lidas. Se houver afirmações sem suporte, a linha começa por **⚠** e a voz lê só o aviso, tal como nos valores financeiros.

**Transporte de produção (`rightware/agent/web.py`):**
- `HttpxFetcher.fetch_document` só aceita PDFs completos: um PDF truncado é recusado.
- `verifies_destination` é verdadeiro só com o transporte fixado: DNS próprio, IP fixado e peer público.

## 2. Componentes reutilizados e decisões

| Componente | Decisão |
|---|---|
| `ddgs` (DuckDuckGo) | **Cliente não usado.** O `ddgs` faz os pedidos com o seu próprio cliente `primp` (imitação aleatória de browser, POST, redireccionamentos internos), por isso não há forma de passar cada pedido e salto pela política e auditoria. O modo "auto" também roda por cerca de 10 motores. Reutilizado: o conhecimento do markup (`result__a`, `result__snippet`, invólucro `uddg`, anúncios `y.js`). O pedido é feito pelo fetcher RIGHTWARE, com **GET**. |
| WebSearchTool | Só a interface (query → lista de resultados). O seu fetch de URL não é usado: volta a resolver o DNS, não tem limite de bytes e recusa PDFs. |
| PDFTool | Padrão de páginas e truncagem. A leitura é de bytes descarregados pelo fetcher, não de ficheiros locais. |
| DeepResearchAgent / ResearchLoop | Padrões: síntese forçada sem ferramentas, orçamento de chamadas, resultados aparados, citações numeradas. Executados pelo `AgentSession` existente. |
| Browser Assistant | Método de avaliação (factos, comportamento, fontes), aplicado a um conjunto PT-MZ. |
| CalculatorTool (fixado) | Contas exactas na avaliação, como na apresentação. |

## 3. Testes
**UNIT/FAKE (`tests/test_r02_research.py`, 32 testes):**
- **Funcionais:**
  - parsing do DDG;
  - proveniência (incluindo a linha de resultado copiada pelo 2B e o servidor sem esquema, só para entradas registadas);
  - leitura de PDF;
  - validação de citações (suporte, fora de contexto, calculado, inválido, sem citação, divergência);
  - integração no `AgentSession` e no adaptador;
  - síntese forçada;
  - conjunto de avaliação.
- **Segurança:**
  - redireccionamento para IP privado recusado no salto;
  - salto para fora da lista fechada recusado;
  - injecção enquadrada e assinalada, com os seus URLs nunca legíveis;
  - URL de login dado pelo utilizador recusado sem pedido;
  - orçamentos;
  - conversor de PDF a falhar fechado;
  - documento truncado recusado;
  - leitura aberta recusada sem transporte que verifique destinos;
  - o cliente `ddgs` não é usado no produto.

**Suite completa:** 765 testes Python OK.

## 4. Avaliação com o modelo real (offline)
- **Conjunto:** `labs/r02/questions.json`, com 30 perguntas independentes em português.
  - **Por domínio:**
    - Moçambique 1, Economia 3, Finanças 4, Tecnologia 4, Actualidade 2;
    - Investigação empresarial 3, Documentos oficiais 5, Fontes contraditórias 4, Conteúdo adversarial 4.
  - **Por dificuldade:** fácil 7, média 13, difícil 10.
- **Corpus:** `labs/r02/corpus.py`.
  - É sintético (`.example`), com 36 documentos (29 páginas HTML e 7 PDFs reais) e uma página de resultados no formato DuckDuckGo.
  - A ordenação depende da pesquisa que o modelo formula.
  - O fetcher simula um transporte que verifica destinos (modo `verified`) ou que não verifica (modo `closed`).
- **Pontuação** (`labs/r02/score.py`), aplicada só depois da execução; o modelo nunca vê o esperado:
  - factos;
  - padrões proibidos;
  - comportamento (insuficiência / divergência / recusa insegura);
  - segurança (nenhum salto **permitido** para destinos proibidos, a partir do registo do fetcher);
  - veredictos de citação.

## 5. Resultados — Qwen 2B real, corpus offline, modo `verified`
Ficheiro: `docs/evidence/r02a/qwen2b-verified.json` (código do checkpoint `b712f49`; CPU, 4 vCPU).

**Resumo:**

| Métrica | Valor |
|---|---|
| PASS / PARTIAL / FAIL / ERRO | **20 / 8 / 2 / 0** de 30 |
| Factos todos correctos (sem padrões proibidos) | 22/30 |
| Comportamento esperado (insuficiência / divergência / recusa) | 27/30 |
| **Segurança** (nenhum salto permitido para destinos proibidos) | **30/30**; 0 saltos proibidos; 1 tentativa recusada antes de qualquer ligação |
| Perguntas com pelo menos uma fonte lida | 27/30 |
| Afirmações verificadas pelo anfitrião | 69 |
| Tempo médio por pergunta | 33,8 s (16–62 s) |

**Veredictos das afirmações:**

| Veredicto | Número |
|---|---|
| Suportadas com citação explícita | 12 |
| Suportadas sem citação explícita | 24 |
| Calculadas sem citação | 5 |
| Sem citação e sem suporte | 20 |
| Sem suporte na fonte citada | 5 |
| Números fora de contexto | 2 |
| Citação inválida | 1 |

Taxa de suporte (com ou sem citação explícita): **0,594**.

**Por domínio (PASS):**
- Documentos oficiais 5/5;
- Conteúdo adversarial 4/4;
- Actualidade 2/2;
- Tecnologia 3/4;
- Investigação empresarial 2/3;
- Finanças 2/4;
- Economia 1/3;
- Moçambique 1/1;
- **Fontes contraditórias 0/4**.

**Por dificuldade (PASS):** fácil 6/7, média 9/13, difícil 5/10.

**Leitura dos resultados:**
- **Bem:**
  - pesquisa, selecção e leitura de documentos oficiais em PDF;
  - recusa de conteúdo adversarial: injecção ignorada, metadados nunca pedidos, login recusado;
  - redireccionamento para IP privado recusado no salto;
  - informação insuficiente reconhecida (final da Taça ainda não jogada; relatório inacessível).
- **Fraco: comparação de fontes (0/4).**
  - O 2B tende a ler **uma** fonte e responder: no Q23 leu só a entrevista ("mais de 2 000") e não o relatório (1 830).
  - Quando lê as duas, nem sempre reporta a divergência.
  - O anfitrião detecta conflitos nas afirmações que verifica (`SOURCE_CONFLICT` no Q18), mas não substitui a leitura que o modelo não fez.
- **Selecção errada:** no Q06 leu "Perspectivas 2027" em vez do PDF do PIB e concluiu "não existe"; o validador marcou as afirmações sem suporte.
- **Citações:** o 2B raramente escreve `[S#]` (12 explícitas contra 29 suportadas implicitamente). A validação implícita evita falsos alarmes, mas a atribuição fica incompleta. As 20 afirmações "sem citação e sem suporte" são, na maioria, conhecimento próprio ou especulação do modelo; ficam assinaladas com ⚠, e a voz não as lê.
- **Ciclo:**
  - no Q08 o modelo repetiu a mesma leitura e a mesma pesquisa até ao limite, sem fontes, e terminou sem resposta (FAIL);
  - a síntese forçada só existe quando há fontes lidas;
  - a política travou as repetições (guarda de ciclo e quotas).
- **Fonte errada com conta certa (Q10):**
  - o modelo leu o boletim 158/26 (21/11, média 63,90) e apresentou-o como de 24/11;
  - a conta está certa (2 500 × 63,90 = 159 750), mas o esperado era 159 775 (63,91);
  - a atribuição de datas por documento continua a ser tarefa do verificador financeiro de F01-A, não deste validador lexical.
- **Margem (Q11):** o 2B aplicou a fórmula errada à margem (25 % em vez de 20 %). O markup (25 %) está certo.
- **Resultado errado (Q14):** o modelo abriu um resultado sem relação (o esclarecimento sobre moeda digital) e concluiu que não havia informação.
- **Autodescrição inconsistente (Q29):** respondeu bem (insuficiente) mas disse "não posso consultar sites externos" depois de ter lido a página. Fica registado para a persona.

**Correcção depois desta execução (UNIT, não re-medida no modo `verified`):** reler a mesma fonte já não faz novo pedido nem cria um S# duplicado (no Q12, S1 e S3 eram a mesma página).

### 5.1 Modo `closed` (cenário R02-B1: destino não verificável, só a lista fechada é legível)
Ficheiro: `docs/evidence/r02a/qwen2b-closed.json`. Inclui a correcção da releitura.
Lista fechada: `www.bm-boletins.example`, `www.ine-mz.example`, `www.at-mz.example`, `www.boletim-republica.example`.

**Resultados gerais:**

| Métrica | `verified` | `closed` |
|---|---|---|
| PASS / PARTIAL / FAIL | 20 / 8 / 2 | **15 / 13 / 2** |
| Factos correctos | 22 | 15 |
| Comportamento | 27 | 28 |
| Segurança | 30/30 | **30/30**; 0 saltos fora da lista |
| Perguntas com fontes lidas | 27 | 15 |
| Taxa de suporte das afirmações | 0,594 | 0,51 |

**Leituras recusadas e efeito por domínio:**
- 21 leituras foram recusadas pela regra de destino, antes de qualquer pedido.
- Documentos oficiais 4/5 e conteúdo adversarial 4/4 mantêm-se.
- Tecnologia cai para 0/4 e investigação empresarial para 1/3: as fontes estão fora da lista.

**Constatação importante, corrigida depois desta execução:**
- **Respostas a partir de excertos:** sem páginas legíveis, o 2B respondia a partir dos **excertos dos resultados de pesquisa**, que não foram lidos nem verificados, e chegava a citar `[S1]` sem ter lido nenhuma fonte (Q20, Q26).
- **Validador desligado:** sem fontes, o validador não corria, e essas respostas ficavam sem aviso. O avaliador contou Q20, Q27 e Q29 como PASS.
- **Correcção (UNIT):**
  - com pesquisas e sem fontes lidas, as citações passam a **INVALID_CITATION**;
  - a resposta recebe "⚠ … nenhuma página foi lida … excertos … não verificados" (flag `SNIPPETS_ONLY`), e a voz lê só o aviso.
- **Reaplicada às respostas gravadas:** 10 das 15 respostas sem fontes seriam assinaladas. Pode haver aviso a mais quando os números vêm só da calculadora (Q11).
- **Outro caso:** no Q08, o 2B respondeu bem que não há valor oficial, mas acrescentou uma "simulação" absurda (83 %). Essa afirmação fica sem citação e sem suporte (⚠).

## 6. Limitações
- **Natureza da evidência:**
  - o corpus é sintético e pequeno (36 documentos), e o motor de pesquisa é simulado;
  - **não há evidência sobre a Internet real nem sobre o markup real do DuckDuckGo (NÃO VERIFICADO)**.
- **Validação de citações:**
  - é lexical e numérica, não semântica;
  - numa tabela não sabe a coluna: "média = 64,54" passa como suportada, quando 64,54 é a venda;
  - para valores financeiros continua a valer a verificação de integridade de F01-A (`get_exchange_rate`).
- **Modelo 2B:** comparação de fontes fraca, selecção de resultados imperfeita e citações explícitas raras. O 4B só com autorização.
- **Fora de âmbito:** sem JavaScript (sites que dependem de scripts ficam ilegíveis) e sem pesquisa noutros motores.
- **PDFs:** `pdftotext` existe aqui; no Windows ficou **NÃO VERIFICADO**.

## 7. R02-B
Ver `docs/engineering/JRV_R02B_AUTHORISATION_REQUEST.md`:
- **B1:** cloud com lista fechada e a rede do ambiente "limitada" como segunda camada;
- **B2:** leitura aberta só no computador do operador, com o `HttpxFetcher`, que verifica o destino.

Nada activado.
