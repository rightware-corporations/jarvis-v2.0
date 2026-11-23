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
