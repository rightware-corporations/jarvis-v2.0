# WEB-01 W3.2-R — Fiabilidade da pesquisa e recuperação de regressões

Estado: implementado no ramo da PR #32 (Draft). **Sem rede.** `network_enabled=false`. OP-W31 consumida e não reutilizada. Data: 24/11/2026.
Classificação: **FACTO** (medido aqui), **INFERÊNCIA**, **NÃO VERIFICADO**.

## Decisões arquitecturais
1. **R01 — Cobertura só por afirmações aceites.** A avaliação e a síntese passaram a ser **uma única chamada estruturada por iteração** (`STEP_SYSTEM`).
   - O modelo devolve, numa só resposta: afirmações `{part, evidence_id, quote, answer, text}`, as partes em falta (`missing`) e a próxima consulta (`next_query`).
   - O anfitrião valida cada afirmação. A cobertura de uma parte resulta **exclusivamente** de afirmações aceites.
   - A paragem antecipada só acontece quando todas as partes estão cobertas desta forma. Um "nada em falta" do modelo sem afirmações aceites é registado e ignorado.
   - Afirmações aceites acumulam entre iterações.
   - Máximo de 4 chamadas ao modelo por missão (antes: 5).
2. **R02 — Correspondência afirmação↔parte, com verificações registadas em separado por afirmação.**
   - **Relevância documental, suporte textual, correspondência com a parte.** Esta última verifica:
     - o atributo pedido, sem as entidades nomeadas da pergunta;
     - o tipo de resposta: ano, número ou nome próprio;
     - o contexto temporal (ano pedido presente) e a relação temporal (antes vs desde);
     - que nenhuma outra parte corresponde melhor;
     - que um mesmo valor de resposta não responde a duas partes;
     - o campo `answer`, que tem de estar na citação e na afirmação.
   - **Correcção semântica: `NAO_VERIFICADA`**, declarada como tal. São heurísticas lexicais.
   - A falha esperada das relações invertidas com as mesmas palavras mantém-se (`expectedFailure`).
3. **R03 — Fontes e atribuição.**
   - A **classe da fonte** vem de política (`configs/web01/sources.json`, por host exacto), nunca do modelo e nunca por tema.
   - Só `reference`, `institutional` e `news` sustentam **factos**. `user_generated` e hosts não listados produzem **alegações atribuídas**, que nunca entram em `accepted` e nunca cobrem uma parte factual.
   - Quando a parte pergunta o que essa fonte diz (por exemplo, "o que dizem no fórum"), a alegação é mostrada como *"alegação NÃO sustentada"* e o resultado é no máximo PARCIAL.
   - Cada linha da resposta tem `[fonte #n · host]`.
   - As **contradições são detectadas pelo anfitrião**: na mesma parte, fontes diferentes com quantidades ou valores diferentes. Um conflito torna o resultado PARCIAL.
   - As notas `part=-1` foram eliminadas: eram o canal de G7.
   - O texto das afirmações rejeitadas **nunca** é mostrado; só o número e os motivos.
   - Os "conflitos" em texto livre do modelo já não são mostrados; ficam só como evidência marcada como não verificada.
4. **R04 — Unidades canónicas completas.**
   - `UNITS`: identificador → (dimensão, factor). Aliases completos, sem truncatura (`_unit()[:4]` fazia colidir quilómetro e quilograma).
   - A comparação distingue: unidades equivalentes, conversão exacta, mesmo número com unidade diferente da mesma dimensão (rejeitado: *exige conversão*) e dimensões incompatíveis.
   - Moedas nunca são convertidas. Os multiplicadores (mil, milhões) são suportados.
   - O separador decimal deixou de colidir com o de milhares: 1,5 ≠ 15.
   - Palavras desconhecidas depois de um número não contam como unidades.
5. **R05 — Autonomia do planeamento.** Diagnóstico **FACTO**, medido com o Qwen 2B real, sem rede:
   - no contrato `answer_parts`, o modelo escreve **respostas** (muitas vezes inventadas): "1975", "Maputo", "Maria Helena Barreto", "São Paulo, no Brasil";
   - a validação estava correcta ao rejeitá-las;
   - a causa estava no **contrato e no prompt**: um campo chamado "answer_parts" convida a responder;
   - **novo contrato**: `{subperguntas, consultas}`. O anfitrião filtra cada subpergunta: tem de ser uma pergunta, sem números ou nomes ausentes da pergunta, e sem termos novos para além de um pequeno conjunto genérico;
   - a decomposição do anfitrião é **só contingência**, marcada `parts_source`, e as métricas separam proposta, aceitação e intervenção;
   - o contrato antigo continua a ser aceite, por compatibilidade.
6. **R06 — Custos.** Cada chamada regista tokens e tempos do Ollama (`load_s`, `prompt_s`, `generate_s`). A missão regista as fases: recuperação, selecção, passo do modelo e validação. A classificação de intenção é medida à parte, no conjunto H.

## Avaliação (Qwen 3.5 2b real, local, SEM rede)
Ver §Resultados abaixo e `docs/evidence/web01/w32r-eval/`.

## Resultados (FACTO; código `9d6d316`; conjunto H congelado em `ac7aa29`)

| Conjunto | W3.1 | W3.2 | **W3.2-R** | Meta |
|---|---|---|---|---|
| S1 Q1–Q9 (regressão) | 8/9 | 5/9 | **6/9** | ≥ 8/9 ✗ |
| H1–H10 (independente, 1 execução) | — | — | **5/10** | ≥ 8/10 ✗ |
| S3 R1–R5 (revalidação offline dos bytes reais) | 3/5 | 4/5 | **3/5** | ≥ 4/5 ✗ |
| Latência média S1 | 29,8 s | 49,7 s | **48,4 s** (H: 49,0 s) | < 49,7 s: só marginal |
| Pedidos médios S1 | 9,8 | 4,9 | **6,1** | eficiência face ao W3.1: preservada |
| Partes do plano vindas do modelo | — | 0/17 | **S1 9/9, H 9/10** (1 contingência) | autonomia: recuperada |
| Referências inventadas aceites | | | **0** | ✓ |
| Colisões de unidades | | | **0** | ✓ (testes) |
| Alegação de fórum apresentada como facto | | G7: 1 | **0** (H6, Q9) | ✓ |
| Associações erradas aceites | | Q3, Q4 | **3** (H8, Q7, R5) | 0 ✗ |

**Falhas de segurança (FACTO, divulgadas):**
- **H8:** "Amon Ferrel nasceu em 1894" foi aceite para "Em que ano ganhou o Nobel?". O tipo (ano) e o sujeito batiam, mas não há verificação da relação.
- **Q7:** a subpergunta do modelo **perdeu "em 2031"**, e uma frase sobre taxas de câmbio foi aceite para "taxa de inflação" (GROUNDED).
- **R5:** a subpergunta **perdeu "da Química"** (a premissa falsa), e "Nobel da Física em 1921" ficou GROUNDED.

O juiz original (inalterado) marcou estes três casos como adequados. Este relatório não os conta como sucesso.

**Causas medidas:**
1. O filtro de subperguntas aceita partes que **perdem restrições** da pergunta (anos, qualificadores). O limiar de cobertura 0,6 é permissivo.
2. Falta verificar a **relação (predicado)** entre a parte e a afirmação.
3. A verificação do valor `answer` é **estrita demais**: rejeitou valores correctos em R2, R4, H4 e H9.
4. A aceitação com uma só fonte não deixa ver contradições: H5 aceitou a estimativa do jornal sem consultar o censo.

**Custo (R06):**
- Por passo: ≈ 490 tokens de entrada (2,6 s) e ≈ 200 de saída (≈ 13 s). **A geração domina.**
- O planeamento desceu para cerca de 6 s.
- A latência só baixa se o número de iterações baixar. As iterações sobem quando as afirmações são rejeitadas (causa 3).
- Classificação de intenção: 1,5 s.

## Próximo passo proposto
1. Impedir que uma subpergunta perca restrições: todos os números, anos e nomes próprios da pergunta têm de estar em pelo menos uma parte.
2. Verificar a relação (verbo ou predicado) da parte na afirmação ou na chave da evidência.
3. Tornar a verificação de `answer` tolerante à forma, mantendo a verificação de quantidades.
4. Para valores numéricos, exigir uma segunda fonte ou indicar "fonte única".
5. Criar um **novo** conjunto independente H2, congelado antes de executar, e só depois pedir uma validação real com nova autorização.
