# F01-A — Inteligência de ferramentas e fiabilidade operacional

Estado: investigação delimitada, **offline**. Nenhum pedido à Internet. A autorização OP01-FX-REAL-PROXY está revogada e não foi reutilizada. Todos os componentes novos são **EXPERIMENTAIS**, em `labs/f01/`. Data: 24/11/2026.
Classificação: **FACTO** (medido), **MECANISMO** (testes unitários), **EXECUÇÃO REAL** (Qwen local), **AVALIAÇÃO INDEPENDENTE** (pontuador com registos-ouro próprios).

## 1. Princípio
O modelo interpreta, raciocina e **escolhe** ferramentas. As ferramentas executam operações especializadas e devolvem **registos estruturados**. A política controla e a evidência confirma.

`get_exchange_rate` é uma ferramenta genérica (qualquer moeda e data), não uma resposta programada: não fixa valores, datas, números de boletim nem perguntas.

## 2. Ferramenta estruturada `get_exchange_rate(base_currency, quote_currency, reference_date)` — `labs/f01/bm_fx.py`
- **Localiza** o boletim pedido (ou o mais recente) no índice do BM. A data vem do texto da ligação ou do nome do ficheiro; ligações não diárias (por exemplo, relatórios) são ignoradas.
- **Extrai** as tabelas genericamente: país, moeda, unidade (por 1 ou por 1000), compra, venda e média. O número é convertido de pt (`3.629,39`).
- Usa ISO 4217 por (país, moeda), com **CNH ≠ CNY**. Moedas desconhecidas ou linhas duplicadas dão AMBIGUOUS, nunca adivinhação.
- **Devolve** um registo estruturado:
  - estado: `OK / DERIVED / NOT_LISTED / NOT_RETRIEVED / STALE / AMBIGUOUS / UNSUPPORTED / PARSE_ERROR`;
  - par, data de referência *impressa no documento*, data pedida, valores e unidade, tipo de taxa;
  - **proveniência**: URL, sha256, nº do boletim, linha de assinatura, hora de obtenção, data no índice;
  - valores derivados (inverso, taxa cruzada) com a fórmula.
- **Fontes injectadas:**
  - *offline replay* dos bytes reais recolhidos em OP01-FX-REAL-PROXY; um documento não recolhido dá `NOT_RETRIEVED`, nunca um substituto;
  - *fixtures fictícias independentes* com armadilhas: milhares, linha duplicada, data do documento diferente da do índice, boletim antigo e moeda desconhecida.
- **Mecanismo (FACTO, `tests/test_f01_fx.py`):** o boletim real 159/26 é lido **sem problemas de parsing**, com as 20 moedas (USD, ZAR, BWP, SZL, MUR, ZMW, JPY/1000, MWK/1000, TZS/1000, ZWG/1000, BRL, CAD, CNH, CNY, DKK, GBP, NOK, SEK, CHF, EUR).
  - 20/11: `NOT_RETRIEVED` (listado, não recolhido).
  - 22/11: `NOT_LISTED` (domingo).
  - XAU: `UNSUPPORTED`.
  - Inverso e cruzada: `DERIVED`.

## 3. Integridade financeira — `labs/f01/integrity.py`
- Um número financeiro só é **sustentado** se corresponder, *em conjunto*, a um registo estruturado do mesmo turno:
  - moeda dita na frase igual à do registo;
  - atributo (compra, venda ou média) igual ao campo;
  - valor igual após normalização (vírgula ou ponto decimal, milhares) e arredondamento à precisão escrita;
  - unidade correcta.
- Ou a um **derivado reproduzível**: diferença venda−compra, montante do utilizador × taxa, inverso ou cruzada da ferramenta.
- As datas têm de ser a data de referência do registo, ou a de consulta ou assinatura identificadas.
- Montantes dados pelo utilizador são entrada, não afirmação.
- Resultados: `UNSUSTAINED`, `WRONG_ATTRIBUTE_OR_CURRENCY`, `WRONG_DATE`.
- **Não é** verificação semântica da resposta inteira: verifica apenas figuras financeiras.
- **A atribuição de fontes é construída pelo anfitrião** a partir dos registos e guardada à parte do texto do modelo.

## 4. Data de referência (24/11/2026) vs assinatura (25/11/2026) — FACTO, sem presunções
- O documento diz "TAXAS … DO DIA **24 Novembro** de 2026" e está assinado "Maputo, **25.11.2026**". O índice lista-o como "24-11-2026".
- Foi **obtido em 24/11/2026 às 16:40:44 UTC (18:40 em Maputo)**, ou seja, *antes* da data da assinatura. Portanto, **a data da assinatura não é a data de publicação**: o documento já estava publicado a 24/11.
- A nota (a) diz que a taxa média USD/MZN "é apurada às 15H30 com base na informação cambial reportada pelos Bancos Comerciais ao longo do dia".
- **Hipótese (NÃO verificada):** a assinatura indica a data de aplicação ou validade do boletim (o dia seguinte). Confirmá-la exige documentação do BM ou mais boletins.
- **Regra adoptada:** a ferramenta devolve a **data de referência impressa** como data dos dados, e a assinatura, a hora de obtenção e a data do índice como proveniência, separadas. Nunca apresenta a assinatura como data de publicação.

## 5. F01-A — comparação controlada
Perguntas, critérios e configurações foram **congelados no commit `311be5a`** (`labs/f01/frozen_eval.json`, sha256 `d508e671…`), antes de qualquer execução. São 13 turnos em 3 conversas (8 financeiros e 5 gerais), com continuidade (F2–F4 e G4).

| Configuração | Descrição |
|---|---|
| A | Qwen + persona, sem ferramentas (SimpleAgent fixado) |
| B | AgentSession/Orchestrator + `browse` + `web_search` sobre a reprodução offline das páginas reais do BM e o fixture OP01 |
| C | Tool calling nativo do Ollama com **só** `get_exchange_rate` (ciclo mínimo de laboratório, não é motor de produto) |
| D | AgentSession/Orchestrator + `browse` + `web_search` + `get_exchange_rate` (ferramenta extra declarada pelo anfitrião, `extra_tools`) |

RESULTADOS: ver §6 (preenchido depois da execução).

## 6. Resultados (Qwen 3.5 2B real, offline; pontuação independente) — **F01-A SUSPENSO** pelo operador (prioridade: apresentação)
| Config | Correctas | Financeiras | Gerais | Selecção de ferramentas | Figuras inventadas/mal atribuídas | Latência média | Tokens de prompt médios |
|---|---|---|---|---|---|---|---|
| A — sem ferramentas | 4/13 | 1/8 (só reconhece indisponibilidade) | 5/5 | 3/3 | 0 | 7,2 s | 665 |
| B — browse genérico | 5/13 | 1/8 | 4/5 | 6/11 (sobre-uso em G1/G2/G5) | 2 | 22,9 s | 9 021 |
| **C — ferramenta estruturada** | **10/13** | **7/8** | 5/5 | 8/9 | 3 (uma só resposta, F8: venda do **euro** 70,75 apresentada como a do **dólar**) | **9,2 s** | 1 549 |
| D — Orchestrator + browse + estruturada | **NÃO EXECUTADO** (suspenso ao início; sem resultados) | | | | | | |

- **Nota:** G3/G4 sem web (A e C) contam como correctas quando reconhecem que não têm a informação. O 4B (comparação delimitada) **não correu**.
- **Conclusões (FACTO, N=1 por pergunta):**
  1. A ferramenta estruturada multiplica a correcção financeira (1/8 → 7/8), reduz a latência (22,9 → 9,2 s) e o contexto (9 021 → 1 549 tokens) face à navegação genérica.
  2. O modelo continua a poder trocar atributos entre turnos (F8); a verificação de integridade do anfitrião detectou-o.
  3. Sem ferramentas, o 2B não inventou valores nesta execução (diferente da 4B em OP01).
- **Recomendação:** ferramentas estruturadas para domínios com dados (câmbio, ouro), web_search/leitura para o resto, e verificação de integridade ligada às respostas financeiras.
- **Generalização (proposta, não implementada):** o mesmo Agent Runtime (AgentSession + `extra_tools` declarados pelo anfitrião + AgentPolicy + recibos) pode receber ferramentas de análise de ficheiros (só leitura no workspace), de produção de artefactos (escrita só num workspace isolado com verificador, como TE-06A) e de programação (execução em contentor isolado sem rede, nunca shell no anfitrião). Cada uma exige autorização própria.
