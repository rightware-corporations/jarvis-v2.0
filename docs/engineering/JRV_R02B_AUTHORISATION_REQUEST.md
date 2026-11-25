# JRV-R02-B — Pedido de autorização delimitado e solução para a verificação de destinos

Estado: **PROPOSTA. Nada está activado.** A política versionada mantém `network_enabled=false`. Data: 25/11/2026.

## 1. O problema
- O transporte de produção (`HttpxFetcher`) verifica o destino real em três passos:
  1. resolve o DNS ele próprio;
  2. liga-se a um IP público fixado (pinned);
  3. confirma o IP do peer antes de ler.
- Neste ambiente cloud **não há DNS directo**. A única saída é o proxy HTTPS da sessão, que resolve o DNS e escolhe o IP ele próprio. O nosso código vê apenas o nome do servidor; não consegue provar a que IP o pedido chegou.
- Isto é aceitável para uma **lista fechada** de servidores conhecidos, revista pelo operador. **Não é aceitável para leitura aberta**: qualquer servidor que apareça num resultado de pesquisa.
- Nenhuma técnica dentro do contentor resolve isto de forma honesta. Uma resolução DoH separada não prova o IP que o proxy usa (divergência no tempo e entre resolvedores). Por isso **não é proposta como verificação**.

## 2. A solução proposta, em duas vias

### Via 1 — R02-B1 (cloud, já possível): avaliação real com lista fechada, em duas camadas de controlo
- **Camada RIGHTWARE:**
  - `ResearchToolkit` com `verifies_destination=False`, portanto só a lista fechada é legível (testado: `ProvenanceRules`, `Security`);
  - todos os saltos de redireccionamento verificados contra a mesma lista;
  - orçamentos, recibos e auditoria em `.runtime/`.
- **Camada do ambiente:**
  - o operador muda a rede do ambiente cloud para **"limitada"**, apenas com os servidores da lista;
  - o próprio proxy recusa qualquer outro destino, mesmo que o código RIGHTWARE falhasse;
  - a alteração faz-se nas definições do ambiente e precisa da aprovação explícita do operador;
  - o JARVIS só a propõe e não a faz sozinho.
- **Limite declarado:** o IP de destino e o TLS até à origem continuam delegados ao proxy e são registados em cada recibo, como em OP01-FX-REAL-PROXY. A pesquisa é geral (o DuckDuckGo devolve qualquer resultado), mas a **leitura** fica restrita à lista.

### Via 2 — R02-B2: leitura aberta onde o destino é verificável
- A leitura aberta corre **no computador do operador** (Windows), onde há DNS directo e o `HttpxFetcher` faz a verificação completa.
- **Arquitectura:** é o mesmo produto, local-first, sem novo motor: `ToolChatAdapter` → `AgentSession` + `ResearchToolkit(HttpxFetcher())`. Com esse fetcher, `verifies_destination=True`, e a provenance permite ler resultados da pesquisa, sempre sujeitos às regras estáticas e ao SSRF em cada salto.
- **Pré-requisitos:**
  - executar o JARVIS localmente (procedimento Windows existente);
  - `pdftotext` (Poppler para Windows) ou equivalente. **NÃO VERIFICADO no Windows.** Sem ele, `doc_read` falha fechado com "conversor indisponível".
  - autorização específica de leitura aberta (secção 3).

## 3. Pedido de autorização delimitado

### R02-B1 — `JRV-R02-B1-EVAL-<data>` (cloud, lista fechada)
**Servidores:**

| Classe | Servidores exactos | Estado |
|---|---|---|
| Pesquisa | `html.duckduckgo.com` | Novo. Formato real do markup **NÃO VERIFICADO**. Se divergir, o parser falha fechado ("sem resultados"); o primeiro pedido serve de verificação. |
| Já autorizados antes | `www.bancomoc.mz`, `bancomoc.mz`, `pt.wikipedia.org`, `en.wikipedia.org`, `api.frankfurter.dev` | Renovação para a janela. |
| A propor pelo operador | Domínios oficiais de Moçambique: INE, Autoridade Tributária, Portal do Governo, Boletim da República e outros que o operador escolher | Os nomes exactos ficam a confirmar pelo operador. **Não os invento.** |

**Limites:**
- 10 pedidos por pergunta;
- 120 pedidos por janela;
- 1 MB por página e 5 MB por PDF;
- 15 s por pedido;
- janela de 60 minutos;
- 30 perguntas.

**Condições:**
- **Transporte:** o proxy de sessão experimental, autorizado só para esta janela e com as delegações declaradas.
- **Rede do ambiente:** passa a "limitada", com exactamente esta lista, durante a janela, com aprovação explícita.
- **Revogação:** no fim, revogar e repor.
- **Exclusões:** sem APIs pagas, sem contas, sem chaves, sem túnel e sem leitura aberta.

### R02-B2 — `JRV-R02-B2-OPEN-<data>` (computador do operador, leitura aberta)
- **Leitura aberta com provenance:** qualquer servidor público que apareça nos resultados desta pergunta, ou numa ligação de uma página lida (profundidade ≤ 2).
- **Regras:** só https e porta 443; sem login, conta ou administração; sem executáveis; SSRF e IP público em **cada salto**, com IP fixado.
- **Limites:** os mesmos de B1, mais 6 leituras por pergunta.
- Exige o JARVIS a correr localmente e a confirmação do operador nesse computador.

## 4. O que permanece fora
- Execução de JavaScript.
- Playwright, Crawl4AI, Firecrawl e SearXNG.
- Formulários, POST e cookies.
- Envio do perfil ou de dados pessoais nas pesquisas: as consultas derivam só do pedido.
