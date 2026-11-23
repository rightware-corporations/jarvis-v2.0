# WEB-01 — Pesquisa web pública de leitura pelo RIGHTWARE Gateway (plano incremental)

Estado: **plano de implementação; acesso externo à rede NÃO habilitado.** Data: 23/11/2026. Base: UI-02 (HUD) e P3A (Gateway). Abrir a rede pública exige uma **autorização específica do operador**, separada desta.

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
