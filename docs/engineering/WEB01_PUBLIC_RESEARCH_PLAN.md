# WEB-01 — Pesquisa web pública de leitura pelo RIGHTWARE Gateway (plano incremental)

Estado: **W0–W2 implementados sem rede (23/11/2026, ramo `integration/jrv-web01-w0w2-20261123`); W3–W4 por autorizar. Acesso externo à rede NÃO habilitado.** Data: 23/11/2026. Base: UI-02 (HUD) e P3A (Gateway). Abrir a rede pública exige uma **autorização específica do operador**, separada desta.

## Princípios (não negociáveis)
- **Só leitura.** Nesta fase não há formulários, login, POST para terceiros, downloads executáveis nem pagamentos.
- **Egress explícito.** O Gateway RIGHTWARE é o único caminho para a rede. Cada pedido passa por uma política declarada: allowlist de domínios, métodos `GET`/`HEAD`, limites de bytes, tempo e redirecionamentos, e bloqueio de IPs privados, link-local e metadata (anti-SSRF, também depois da resolução DNS). Tudo é auditado.
- **Fontes verificáveis.** Cada afirmação apresentada tem o URL, a data e hora de obtenção e o hash do conteúdo observado (um recibo do Gateway). O verificador RIGHTWARE decide `VERIFIED` a partir dos recibos, nunca a partir do texto do modelo.
- **Market Intelligence apenas informativa.** Mostra dados datados e com a fonte. Não faz recomendações de investimento nem ordens, e não toca em contas.
- O modelo continua local (Ollama + Qwen). Não há APIs pagas.

## Incrementos

| Fase | Entrega | Rede | Evidência exigida |
|---|---|---|---|
| W0 | Política de egress (`configs/web01/egress.json`): allowlist, limites e bloqueios. Testes unitários da política, incluindo SSRF, DNS rebinding, redireccionamentos para fora da allowlist e tamanho máximo. | Nenhuma (só fixture) | Testes FAKE/unit, marcados como tal |
| W1 | Ferramentas do Gateway `web_search_public` / `web_open_public` em modo **fixture** (servidor local com páginas reais congeladas), com recibos `url + fetched_at + sha256 + bytes`. | Nenhuma | Recibos e verificador sobre a fixture |
| W2 | Capacidade `pesquisa-publica` no ControlPlane (código do operador, cancelamento, timeline na HUD), com estado PARCIAL. | Nenhuma | E2E da HUD (FAKE em CI, real em local) |
| W3 | **Com autorização específica:** egress real para uma allowlist curta de fontes públicas e estáveis (por exemplo, Wikipedia e sites institucionais). Uma pesquisa de leitura de ponta a ponta. | **Sim (autorizado)** | Recibos reais, auditoria do Gateway e resultado do verificador |
| W4 | Market Intelligence informativa. O painel "Inteligência financeira" passa de NÃO INTEGRADA a PARCIAL e mostra valores **só** com fonte, data e recibo. Sem fonte verificada, mostra "Sem dados". | Sim (allowlist ampliada e autorizada) | Valores com recibo, testes de "nunca mostrar sem recibo" |

## Pedido de autorização (a apresentar antes de W3)
1. Lista exacta de domínios iniciais.
2. Limites: pedidos por missão, bytes por resposta e tempo total.
3. Onde corre o egress: o host local do operador. Sem túneis nem deploy público.
4. O que fica guardado: recibos e hashes. As páginas completas ficam só em `.runtime/`, nunca no repositório.

## Fora de âmbito
Navegação com sessão iniciada, compras, envio de dados pessoais, scraping massivo, contornar paywalls ou robots, voz, acções Windows e escrita de ficheiros (cada um com a sua própria autorização).

## Estado da implementação W0–W2 (23/11/2026)
Classificação: **FACTO** (testado neste host ou em CI); nenhum teste abriu um socket de rede (verificado por asserção).

| Fase | Código | Testes / evidência |
|---|---|---|
| W0 | `configs/web01/egress.json` (modo `fixture`, `network_enabled=false`, `authorization_ref=null`); `rightware/web01/egress.py`: `EgressPolicy` (validação estrita), `build_fetcher` (o modo `public` é **recusado** sem autorização W3), `EgressGuard` (allowlist por salto, só GET, limites por resposta, orçamentos por missão, cancelamento, auditoria). `HttpxFetcher.fetch` recebeu limites por chamada que só podem **apertar** os máximos existentes, mais `Page.raw` (alteração aditiva). | `tests/test_web01.py::W0Policy`: políticas inválidas, recusa do modo público, recusa antes do fetch, orçamentos, limite de bytes, redireccionamento permitido e para fora da allowlist, e, com transporte injectado, IP privado, DNS misto (rebinding), redireccionamento para 169.254.169.254, re-verificação do peer. |
| W1 | `rightware/web01/fixture/`: corpus local escrito pela RIGHTWARE em `*.fixture.example` (cada página declara ser fixture), motor de pesquisa determinístico, página de fórum com injecção de instruções. `rightware/web01/research.py`: `web_search_public` e `web_open_public` com **recibos encadeados por hash** (URL, `fetched_at` UTC, SHA-256, bytes, estado HTTP, recusa); o verificador re-hasheia os bytes guardados e aceita um objectivo **só** de fontes designadas. | `W1ToolsReceiptsVerifier`: cadeia, fórum (diz "Beira") nunca suporta a capital, adulteração de bytes, URL ou cadeia → `RESEARCH_INVALID_EVIDENCE`, especificação estrita. |
| W2 | `rightware/web01/mission.py` (`ResearchMission`, capacidade `pesquisa-publica`, estado **PARCIAL**), registada no **mesmo** ControlPlane (`missions=`), com código do operador, uma tarefa de cada vez e cancelamento. `TaskOutcome.findings/sources` aparecem na consola, na bridge e na timeline da HUD (secção "Fontes"). CLI do anfitrião: `python -m rightware.gui serve --missao-pesquisa`. Evidência em `.runtime/web01-missions/` (fora do repositório). | `W2Mission` (verificado, cancelamento < 1,5 s, ControlPlane, bridge). Browser E2E **U8** (CI com `serve_fake.py` + executor WEB-01 real sobre o corpus) e no anfitrião via CLI: `docs/evidence/web01/`. |

**Limites (honestos):**
- O executor W2 é um plano de leitura **determinístico** definido pelo anfitrião: pesquisa, abertura de até N resultados permitidos, verificação. Nenhum modelo decide.
- A exposição destas ferramentas ao goose via Gateway MCP fica para depois (com o mesmo `EgressGuard`).
- O corpus é **fixture**: prova a política, os recibos, o verificador e a integração na HUD, não a qualidade de pesquisa na Internet real.
- A capacidade `internet-publica` continua **BLOQUEADA** na HUD.

**Para avançar para W3, o operador tem de autorizar especificamente:**
1. a lista exacta de domínios;
2. o motor de pesquisa público e as suas condições de uso;
3. os limites;
4. a execução apenas no anfitrião local.

Depois disso, `authorization_ref` e `network_enabled=true` entram na política e o código W3 passa `allow_public=True` num ponto único e auditado.

## W3 — estado (24/11/2026): `W3_IMPLEMENTED_AWAITING_NETWORK_APPROVAL`
**Código (FACTO, testado offline com transporte injectado):**
- `rightware/web01/providers.py`: `WikipediaSearch` (uma única língua, por exemplo `pt.wikipedia.org`).
  - Usa a página HTML `Especial:Pesquisar` com `fulltext=1&ns0=1`.
  - Os URLs saem **apenas** dos títulos de resultado (`mw-search-result-heading`) e só para `/wiki/<Artigo>` no mesmo servidor.
  - São ignorados: navegação, páginas especiais e links externos.
- `configs/web01/egress.public.json` sai com `network_enabled=false` e `authorization_ref=null`, e o arranque é recusado. Allowlist proposta: `pt.wikipedia.org`.
- `configs/web01/missions/ficha-mocambique-publica.json`: os mesmos três objectivos, com a fonte designada `pt.wikipedia.org`.
- `ResearchMission` é o único ponto `allow_public`. O fetcher só é construído com `network_enabled=true` e `authorization_ref` na política.
  - O resultado traz `operational_state` `RESEARCH_VERIFIED_PUBLIC` ou `_FIXTURE`, e a primeira linha diz `Modo: INTERNET PÚBLICA` ou `Modo: FIXTURE`.
  - Na HUD, o rótulo e o estado de `internet-publica` vêm da política em vigor.
- Transporte `direct` (o caminho do produto no computador do operador): DNS local, IP global, DNS pinning e verificação do peer.
- Transporte `session_proxy`, só para validação numa sandbox cuja única saída é um proxy aprovado:
  - o proxy resolve o DNS, por isso a garantia é mais fraca e está declarada;
  - mantém-se: allowlist exacta em cada salto, só https:443, sem IPs literais, redireccionamentos re-validados e orçamentos.
- User-Agent definido pela política e validado (`RIGHTWARE-Jarvis/<v> (<contacto>)`). A política da Wikimedia exige contacto.

**Testes:** `tests/test_web01_w3.py` (9) cobre:
- missão pública verificada e rotulada PUBLIC, e fixture nunca rotulada PUBLIC;
- SSRF (redireccionamento para 169.254.169.254, IP literal, DNS privado);
- redireccionamento para fora da allowlist;
- prompt injection: a página é aberta como não confiável e nunca suporta um objectivo;
- extracção só dos títulos de resultado;
- guardas do `session_proxy` e do User-Agent;
- estado da HUD.

**Ainda não validado com rede real.** Ver o pedido de autorização no HANDOFF.

**Factos do ambiente Claude Cloud:**
- o contentor **não tem DNS local**, e toda a saída passa pelo proxy da sessão, que re-termina o TLS;
- a verificação SSRF do OpenJarvis resolve o DNS localmente e falha de forma fechada, por isso não pode correr em `session_proxy`.

## W3 — validação real (24/11/2026): `W3_REAL_RESEARCH_VERIFIED` (missão predefinida, transporte experimental)
Autorização `OP-W3-20261124`:
- só `pt.wikipedia.org`, GET;
- limites: 10 pedidos, 512 KB por resposta, 3 MB no total, 90 s, 2 redireccionamentos, concorrência 1;
- User-Agent com o URL de issues do projecto (definido pelo operador);
- `session_proxy` só para esta validação.

A política experimental ficou só no scratchpad e foi apagada no fim; a política versionada continua com `network_enabled=false`.

| Execução | Resultado (FACTO) | Evidência |
|---|---|---|
| 1 (HUD) | **PARCIAL**: CAPITAL (`/wiki/Maputo`) e MOEDA (`/wiki/Metical`) verificados; BANCO_CENTRAL **não**. A pesquisa genérica devolveu "Banco Central do Paraguai" e "Banco Mundial". | `docs/evidence/web01/w3-real/run1-partial/` |
| 2 (HUD) | Pergunta do BANCO_CENTRAL ajustada para a frase exacta `"Banco de Moçambique"` (especificação do anfitrião). **VERIFICADO 3/3**: `/wiki/Maputo`, `/wiki/Metical`, `/wiki/Banco_de_Mo%C3%A7ambique`; 6 recibos; cadeia e hashes OK. | `run2-verified/` |
| 2 (re-verificação offline) | O padrão de MOEDA tinha casado com uma entrada do índice da página. O padrão passou a exigir a frase definidora e o verificador passou a guardar o **excerto** exacto. Re-verificação dos mesmos bytes reais, sem novos pedidos: **VERIFICADO 3/3**. | `run2-verified/verification.strict.json` |
| 3 (HUD, confirmação) | **VERIFICADO 3/3** em 4,9 s; a HUD mostra o modo, o transporte experimental, os excertos e as fontes (URL, UTC, SHA-256, bytes). | `run3-hud-confirm/` (captura de ecrã incluída) |

**Excertos reais** (execução 2/3):
- «Maputo é a capital e a maior cidade de Moçambique»;
- «O metical (ISO 4217: MZN, abreviado como MT), é a unidade monetária oficial da República de Moçambique»;
- «O Banco de Moçambique (abreviadamente BM) é o banco central da República de Moçambique».

**Testes adversariais** (`w3-real/adversarial-real.txt`):
- **Reais, com a política autorizada:**
  - recusados antes de qualquer pedido HTTP: URL fora da allowlist (`en.wikipedia.org`), IP literal, `http://` e porta 8443;
  - esgotamento do orçamento (2 pedidos reais, depois `orçamento de pedidos da missão esgotado`);
  - cancelamento a meio (`TAREFA_CANCELADA` em 1,8 s, nada verificado).
- **Simulados** (transporte injectado ou fixture, por segurança ou por não serem provocáveis na rede real): redireccionamento para 169.254.169.254, redireccionamento para fora da allowlist, DNS privado e página com prompt injection (lida como não confiável; nunca suporta um objectivo).

**Limites (declarados):**
- **Transporte:** `session_proxy` delega o DNS e a ligação ao proxy da sessão. O IP e o peer **não** foram verificados localmente, e não é equivalente ao `direct`, que é o caminho do produto e não foi exercido com rede real.
- **Execução:** é uma missão **predefinida e determinística**. O JARVIS ainda **não** é um agente que pesquisa autonomamente qualquer assunto, e o modelo não decide nem acede à rede.
- **Fornecedor:** a Wikipédia depende do ranking da pesquisa (execução 1) e de páginas grandes cortadas a 512 KB (Maputo); é enciclopédica e editável, não institucional.

## W3.1 — pesquisa orientada por perguntas livres (24/11/2026): `W3_1_IMPLEMENTED_AWAITING_REAL_VALIDATION`
**Percurso** (reutiliza EgressGuard, providers, ResearchToolkit, recibos, ControlPlane, ChatBridge e HUD; sem novo motor nem frontend):
1. **Pergunta na conversa** → `planner.route`. O anfitrião decide:
   - `/pesquisar …` é um pedido explícito;
   - regras do anfitrião classificam como fora de âmbito finanças, cotações, acções locais, mensagens e credenciais;
   - o modelo só **propõe** "research" para uma pergunta, e só se a capacidade estiver activa;
   - tudo o resto é conversa.

   Uma mensagem **nunca** abre a rede.
2. **Plano** pelo Qwen local (`llm.ollama_json`, só loopback, JSON):
   - validação estrita: chaves exactas, tipos, sem URLs nem operadores `site:`;
   - a pergunta vem do anfitrião;
   - o modelo não pode tocar em domínios, orçamentos, política ou veredicto;
   - uma nova tentativa com o erro do anfitrião; depois disso, plano de fallback do anfitrião, rotulado.
3. **Código de uso único ligado a ESTE plano** (`ControlPlane.request(cap, params)`). Sem plano, a capacidade é recusada.
4. **Execução** (`free_research.FreeResearchMission`):
   - as consultas do plano dentro dos orçamentos da política;
   - no máximo uma reformulação por consulta, por regra determinística do anfitrião, quando nada relevante voltou;
   - cancelamento.
5. **Síntese fundamentada** (`grounding`), com verificações separadas:
   - **A. integridade:** recibo OK, os bytes re-hasheiam e a passagem existe no documento;
   - **B. relevância:** léxica, contra a pergunta ou uma subpergunta validada;
   - **C. correspondência:** a citação é um substring exacto da passagem e os termos da afirmação estão na citação;
   - **D. síntese do modelo:** mostrada como texto NÃO verificado;
   - **E. incerteza e abstenção.**

   Referências e citações inventadas são **removidas**; contradições indicadas limitam o resultado a PARCIAL.
   Estados possíveis: `RESPOSTA_FUNDAMENTADA` ("afirmações NÃO verificadas semanticamente"), `EXECUCAO_PARCIAL`, `RESULTADO_DESCONHECIDO` (abstenção) ou `TAREFA_CANCELADA`. **Nunca `RESULTADO_VERIFICADO`.**

**Avaliação com o Qwen REAL local** (`labs/web01/w31_eval.py`):
- corpus FIXTURE, **sem rede**;
- 9 perguntas reservadas (fora de qualquer especificação, prompt ou código) e 10 mensagens reservadas para o routing;
- evidência em `docs/evidence/web01/w31-eval/`.

| versão | modelo | intent | planos válidos | casos | afirmações | grounded | weak | removidas | s/pergunta | pedidos |
|---|---|---|---|---|---|---|---|---|---|---|
| v1-baseline | qwen3.5:2b | 10/10 | 3/9 | 5/9 | 11 | 5 | 6 | 0 | 35.5 | 5.0 |
| v1-baseline | qwen3.5:4b | 10/10 | 8/9 | 5/9 | 10 | 6 | 4 | 5 | 92.2 | 9.8 |
| v2 | qwen3.5:2b | 10/10 | 9/9 | 8/9 | 18 | 10 | 8 | 0 | 29.8 | 9.8 |
| v2 | qwen3.5:4b | 10/10 | 9/9 | 8/9 | 23 | 14 | 9 | 0 | 90.5 | 10.7 |

**Correcções entre v1 e v2:** todas genéricas; nenhuma regra por pergunta.
- **Selecção de passagens:** aceita frases curtas e usa stemming leve.
- **Plano:** a nova tentativa leva o erro de validação; as listas informativas longas são truncadas, com registo.
- **Relevância B:** passa a medir também contra as subperguntas validadas. A re-validação offline dos mesmos outputs de v2 levou o Q4/4b a GROUNDED (`v2/revalidated-B-fix.json`).

**Observações reais:**
- **Referências inventadas:** em v1, o 4b inventou referências de passagens em Q3. As 3 afirmações foram removidas e o JARVIS absteve-se.
- **Prompt injection (Q9):** nenhum modelo obedeceu.
  - o 4b atribuiu a afirmação ao fórum;
  - o 2b tratou o fórum como fonte equivalente e indicou a contradição, ficando em PARCIAL.
- **Contradição (Q6):** os dois modelos responderam Maputo com fontes fiáveis.
- **Informação inexistente (Q7, Q8):** abstenção correcta nas duas versões.
- **Latência:** o 2b é cerca de 3× mais rápido (≈30 s contra ≈90 s por pergunta nesta máquina de 4 vCPU).
- **Routing:** com o prompt revisto, 10/10 nas mensagens reservadas, nos dois modelos.

**Testes offline** (`tests/test_web01_w31.py`, modelo **FAKE** com guião):
- routing;
- o modelo não toca na política;
- referência ou citação inventada removida;
- bytes adulterados;
- abstenção;
- injecção e conflito limitados a PARCIAL;
- orçamento, cancelamento e allowlist;
- fluxo conversa → plano → código → execução.

**HUD (U9, Qwen 2b real, fixture):** pergunta → plano legível com código → `/autorizar` → `RESPOSTA_FUNDAMENTADA` em 11,7 s com 2 citações GROUNDED. Evidência em `docs/evidence/web01/w31-hud/`.

**Limites (honestos):**
- **Sem rede real:** sem pesquisa real na Internet com W3.1. Exige uma **nova autorização específica**; `OP-W3-20261124` foi só para a validação W3.
- **Relevância e suporte léxicos:** uma citação literal de uma fonte errada (o fórum) é texto real, não verdade. Daí o estado nunca ser VERIFICADO.
- **Fixture pequeno:** 5 páginas; os números de qualidade não se transferem directamente para a Wikipédia real.
- **Proposta de intenção:** cada pergunta na conversa custa uma chamada extra ao modelo (≈1–4 s) quando a capacidade está activa.
- **Não é autónomo:** não é um agente aberto. O plano é limitado, o anfitrião executa, e o modelo não escolhe URLs nem domínios.
