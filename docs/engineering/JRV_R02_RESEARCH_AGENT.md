# JRV-R02 — Agente de pesquisa na Internet: investigação técnica e proposta

Ramo de integração B6. Baseline `69dfe13` + aprovação final da voz. Data: 25/11/2026.
Fase: **investigação e proposta**. Sem código de produto novo, sem dependências instaladas e sem rede usada.
OpenJarvis fixado em `f21d902`; não foi alterado.

Classificação:
- **FACTO**: lido no código fixado ou medido aqui.
- **NÃO VERIFICADO**: depende de documentação externa não consultada nesta sessão.

## 1. Situação actual
- A pesquisa geral do JARVIS é `labs/f01/research_tool.py` (`web_research`): só lê a Wikipédia, através de um modelo de URL de pesquisa e de anfitriões exactos.
- **Câmbio:** `get_exchange_rate`, com o Banco de Moçambique e o BCE.
- **Transporte de produção:** `rightware/agent/web.py` (`HttpxFetcher`, FACTO):
  - DNS próprio e IP fixado (pinned), contra o DNS rebinding;
  - verificação do peer, IP público obrigatório, só GET;
  - 5 redireccionamentos, 15 s, 1 MB, HTML ou texto;
  - o texto é enquadrado como dado não confiável.
- **Neste ambiente não há DNS directo.** Só o transporte experimental `labs/op01/proxy_transport.py` funciona: proxy de sessão, allowlist exacta por salto, orçamentos, auditoria e bytes guardados.
- **Navegação:** `rightware/agent/browser.py` (`PublicBrowser`) faz navegação sem JavaScript (formulários GET de pesquisa, seguir ligações) dentro da allowlist exacta, com recibos.
- **Política:** `AgentPolicy` decide cada chamada (negado por omissão); o modelo só propõe.

## 2. Componentes do OpenJarvis fixado (inspecção do código, FACTO)

| Componente | Ficheiro | O que é realmente | Reutilização proposta |
|---|---|---|---|
| **WebSearchTool** | `tools/web_search.py` (823 linhas) | Ver detalhe abaixo. | **Parcial:** reutilizar só a formatação de resultados e a interface; a pesquisa passa por um adaptador RIGHTWARE sobre `ddgs` com motor fixo, e a leitura pelo nosso fetcher. Não activar o modo "auto". |
| **Browser** (`browser_navigate/click/type/screenshot/extract`) | `tools/browser.py`, `browser_axtree.py` | Playwright com Chromium completo e JavaScript. SSRF verificado só no `navigate`, não nos cliques, redireccionamentos nem sub-recursos. Sem allowlist. Sessão partilhada com cookies. `playwright` (Python) **não está instalado**. | **Não agora.** Exigiria dependência pesada e uma política nova (JavaScript, cookies, sub-recursos). O nosso `PublicBrowser` sem JS cobre a navegação de leitura. Fica como fase futura isolada (contentor), com autorização própria. |
| **PDFTool** (`pdf_extract`) | `tools/pdf_tool.py` | Lê **ficheiros locais** com `pdfplumber` (não instalado). Não descarrega. | **Padrão sim, dependência não.** Os PDFs descarregados pelo fetcher auditado são convertidos com `pdftotext` (já usado e testado em F01), com limites de páginas, bytes e tempo. |
| **DeepResearchAgent** | `agents/deep_research.py` | Ciclo `ToolUsingAgent` com chamadas nativas a ferramentas sobre a **base de conhecimento pessoal** (email, Slack, documentos). As fontes só são extraídas de `knowledge_search`. Prompt "You are Jarvis…" próprio, em inglês. | **Só ideias:** síntese forçada sem ferramentas quando acaba o orçamento; fontes numeradas. O nosso `AgentSession` já é este ciclo, com política, recibos e persona. Usar o agente directamente perderia a política e a identidade. |
| **ResearchLoop** (`ResearchAgent`) | `agents/research_loop.py` (885 linhas), `server/research_router.py` | Planeador-executor sobre `HybridSearch` (conectores pessoais) e `clarify`. Planeador por omissão `gemma4:31b`, demasiado pesado aqui. **Não pesquisa na Web.** | **Ideias:** limite de iterações, resultados aparados antes de voltarem ao contexto, renumeração de citações (`renumber_citations`), `clarify` só depois de uma pesquisa. Reimplementar no nosso ciclo, sem importar o conector. |
| **Browser Assistant** | `evals/datasets/browser_assistant.py`, `evals/scorers/browser_assistant.py` | **Não é um componente de execução:** é um conjunto de avaliação (30 perguntas em inglês: fáceis, médias, difíceis) e um avaliador (facto exacto 35 %, semântico 35 %, qualidade 15 %, fontes 15 %). | **Sim, como método de avaliação.** Criar um conjunto PT-MZ equivalente (Moçambique, finanças, tecnologia, actualidade) com o mesmo esquema de pontuação, mais verificação de citações contra os recibos. |

**Detalhe do WebSearchTool:**
- **Motor por omissão ("auto"):** You.com **sem chave**, um serviço externo de terceiros; Tavily, Serply e Firecrawl na nuvem exigem chave.
- **Recurso de último caso:** DuckDuckGo, pela biblioteca `ddgs`.
- **Leitura de URLs:**
  - `httpx` com `check_ssrf` por salto, mas com nova resolução DNS no socket, por isso vulnerável a DNS rebinding;
  - sem allowlist e sem limite de bytes (`resp.text` inteiro);
  - limpeza do HTML por regex;
  - **PDFs recusados**.

**Conclusão:** nenhum dos seis componentes pode ser ligado tal como está sem enfraquecer as políticas. O valor está em três peças:
1. a interface de pesquisa;
2. os padrões de ciclo e de citações;
3. o conjunto de avaliação.

A execução continua a passar pelo `AgentSession`, pela `AgentPolicy`, pelo fetcher auditado e pelas verificações de integridade.

## 3. Motores externos considerados (recursos: cerca de 430 MB livres; imagens Docker do goose intocáveis)

| Opção | Estado aqui | Recursos | Rede necessária | Avaliação |
|---|---|---|---|---|
| **DuckDuckGo via `ddgs` 9.16.0** | **Já instalado** no venv da GUI (196 KB; FACTO) | Nenhum adicional | Ver detalhe abaixo. | **Recomendado para a fase 1**, com motor fixo e anfitriões exactos. Contra: são raspagens HTML não oficiais, sujeitas a bloqueio ou CAPTCHA e a mudanças. Termos de uso **NÃO VERIFICADOS**. |
| **SearXNG self-hosted** | Não instalado | Imagem Docker de cerca de 150–200 MB (**NÃO VERIFICADO**) e Redis opcional. Cabe à justa, sem margem. | O SearXNG consulta ele próprio motores a montante (Google, Bing, DDG…): a allowlist teria de incluir esses anfitriões **na saída do contentor**, que não passa pelo nosso fetcher auditado. | **Fase 2**, se houver disco. Agrega bem, mas o tráfego de pesquisa fica fora dos nossos recibos por salto. |
| **Crawl4AI** | Não instalado | Python + Playwright + Chromium; imagem de cerca de 1–2 GB (**NÃO VERIFICADO**) | Qualquer anfitrião visitado e sub-recursos | **Não cabe.** Também executa JavaScript de terceiros, o que exige isolamento. Rejeitado nesta fase. |
| **Firecrawl self-hosted** | Não instalado | Vários serviços (API, worker, Redis, serviço Playwright); vários GB (**NÃO VERIFICADO**) | Idem; a pesquisa usa um motor configurado | **Não cabe.** O cliente já existe no WebSearchTool (`FIRECRAWL_API_URL`), por isso é viável no futuro numa máquina com recursos. Firecrawl na nuvem é pago: excluído. |
| You.com sem chave, Tavily, Serply | — | — | APIs de terceiros | **Excluídos:** pagos, com chave ou serviço externo não autorizado. |

**Detalhe da rede necessária para `ddgs`:**
- Com motor fixo `duckduckgo`: `html.duckduckgo.com` (e eventualmente `duckduckgo.com`).
- O modo "auto" roda por bing, brave, google, mojeek, startpage, yahoo, yandex, grokipedia, wikipedia e annas-archive. **Proibido.**

## 4. Arquitectura proposta
Um ciclo de agente, as ferramentas existentes reforçadas e uma política nova de "leitura aberta com proveniência".

**Ferramentas propostas ao modelo, todas decididas pela `AgentPolicy`:**
1. **`web_search(query, lang)`:**
   - um adaptador RIGHTWARE sobre `ddgs` com backend **fixo** `duckduckgo`;
   - o tráfego HTTP do `ddgs` só é aceite para os anfitriões de pesquisa autorizados (validado no adaptador; o `ddgs` usa o seu próprio cliente, por isso cada pedido é envolvido e registado — **a validar na implementação**; se não for possível interceptar, usa-se o `PublicBrowser` sobre `html.duckduckgo.com` com o nosso fetcher);
   - devolve até 8 resultados {título, URL, excerto}, cada um com um **id de proveniência**.
2. **`web_read(url | result_id)`:**
   - lê com o fetcher auditado: GET, HTTPS, limites, tipos HTML/texto/PDF, recibo com sha256;
   - **regra de proveniência:** só abre URLs que vieram de um resultado de pesquisa desta pergunta, ou de uma ligação numa página já lida nesta pergunta (profundidade ≤ 2);
   - nunca abre URLs inventados pelo modelo, a não ser os que o utilizador escreveu.
3. **`doc_read(url)`:** PDF via `pdftotext` no anfitrião (binário e argumentos fixos), até 20 páginas, 5 MB e 20 s; o texto é dado não confiável.
4. **Ferramentas existentes:** `web_research` (Wikipédia), `get_exchange_rate` e a calculadora.

**Ciclo (ideias do ResearchLoop e do DeepResearchAgent aplicadas ao `AgentSession`):**
- planear → pesquisar → ler 2 a 4 fontes → comparar → sintetizar;
- no máximo 10 chamadas a ferramentas por pergunta;
- os resultados são aparados antes de voltarem ao contexto (o modelo 2B tem pouco contexto);
- síntese forçada sem ferramentas quando acaba o orçamento;
- clarificação só depois de uma pesquisa.

**Fundamentação e verificação (anfitrião, não modelo):**
- citações numeradas renumeradas contra os **recibos reais**: uma citação sem recibo é removida e assinalada;
- números na resposta verificados contra o texto lido (extensão da integridade de F01-A);
- divergência entre fontes: mostrada, não escolhida em silêncio;
- data de recolha em cada fonte;
- a voz continua a não ler valores não confirmados.

**Segurança:**
- **Perímetro:** sem JavaScript, sem cookies, sem POST, sem formulários de login, sem downloads executáveis.
- **Fetcher e sinais de alerta:**
  - lista de bloqueio de domínios sensíveis (bancos com sessão, email, redes internas);
  - o SSRF do fetcher mantém-se;
  - o conteúdo das páginas é sempre dado e nunca instrução; tentativas de injecção registadas.
- **Orçamentos:** por pergunta (pedidos, bytes, tempo) e por janela.
- **Auditoria:** em `.runtime/` (nunca no git).

**Onde fica o código:**
- O adaptador de pesquisa e a política de proveniência vão para `rightware/agent/` (sem `subprocess`).
- A conversão de PDF fica num componente fora da fronteira do agente, como em F01.
- Enquanto só existir o transporte pelo proxy de sessão, tudo fica marcado como EXPERIMENTAL em `labs/`. A promoção a produto exige o transporte com DNS próprio (`HttpxFetcher`) numa máquina com DNS directo, por exemplo a máquina Windows do operador.

**Avaliação antes de qualquer demonstração:**
- conjunto PT-MZ de 30 perguntas, inspirado no Browser Assistant (10 fáceis, 10 médias, 10 difíceis);
- pontuação: facto exacto, semântico, qualidade, fontes e **citação verificada contra o recibo**;
- comparação com o estado actual (só Wikipédia), no modelo 2B e, com autorização, no 4B.

## 5. Plano por fases
- **R02-a (offline, sem rede):**
  - adaptador de pesquisa, política de proveniência, `doc_read` e verificação de citações;
  - testes UNIT/FAKE com páginas e PDFs locais;
  - criação do conjunto de avaliação.
- **R02-b (rede autorizada, janela única):** avaliação real com o pedido da secção 6; relatório de métricas.
- **R02-c (opcional, recursos):** SearXNG self-hosted, se houver disco e autorização; Browser com JavaScript em contentor isolado, só com autorização própria.

## 6. Pedido consolidado de autorização de rede (a decidir pelo operador; NADA activado)
**Identificador proposto:** `JRV-R02-EVAL-<data>`, de uso único e com revogação no fim.

**Anfitriões e regras:**

| Classe | Anfitriões | Regra |
|---|---|---|
| Pesquisa | `html.duckduckgo.com` (e `duckduckgo.com` se o adaptador o exigir) | Exactos. Só GET ou o formulário de pesquisa. |
| Fontes já autorizadas antes | `www.bancomoc.mz`, `bancomoc.mz`, `pt.wikipedia.org`, `en.wikipedia.org`, `api.frankfurter.dev` | Renovação para esta janela. |
| **Leitura aberta com proveniência** (nova) | Qualquer anfitrião público **que apareça nos resultados de pesquisa da mesma pergunta**, ou numa ligação de uma página lida (profundidade ≤ 2) | HTTPS 443, GET, HTML/texto/PDF, sem JavaScript nem cookies. Lista de bloqueio aplicada. |

**Limites propostos:**
- 10 pedidos por pergunta;
- 150 pedidos por janela;
- 1 MB por página e 5 MB por PDF;
- 15 s por pedido;
- janela de 90 minutos;
- 30 perguntas de avaliação.

**Transporte e autorização:**
- **Transporte:** o proxy de sessão experimental (único disponível aqui: não há DNS directo). Delega DNS, IP público e TLS de ponta a ponta, como em OP01-FX-REAL-PROXY, e isso é declarado em cada recibo.
- **Autorização do proxy de sessão** para esta janela.
- **Nenhuma API paga, nenhuma conta, nenhuma chave.**

**Alternativa mais restrita**, se a leitura aberta não for aceite: uma lista fechada de domínios de referência, por exemplo:
- governo e reguladores de Moçambique;
- INE;
- bancos centrais;
- agências noticiosas escolhidas pelo operador.

Contra: a pesquisa deixa de ser geral.

**Fica explicitamente de fora:**
- túnel;
- execução de JavaScript;
- Playwright;
- SearXNG, Crawl4AI e Firecrawl;
- envio de dados pessoais em pesquisas: as consultas são geradas a partir do pedido, sem o perfil.

## 7. Riscos
- `ddgs` é raspagem não oficial: pode falhar, devolver CAPTCHA ou mudar.
- O 2B tem contexto curto e falha na síntese com várias fontes. A avaliação vai medir isto; o 4B só com autorização.
- A leitura aberta alarga a superfície de injecção de instruções. É mitigada pelo enquadramento como dado, pela política negada por omissão e por nenhuma ferramenta com efeitos.
- O transporte pelo proxy não verifica o IP do destino: aceitável só como avaliação experimental, não como produto.
