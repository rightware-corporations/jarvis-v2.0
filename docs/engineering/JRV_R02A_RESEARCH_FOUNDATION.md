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

RESULTADOS: ver secção 5 (preenchida com a execução real).

## 5. Resultados
(preenchido abaixo)
