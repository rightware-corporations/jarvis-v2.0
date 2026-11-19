# JRV-TE-P2B — Pré-registo (CONGELADO)

**Estado:** CONGELADO a partir do commit que publica este ficheiro. Qualquer alteração posterior invalida a comparabilidade e exige uma nova versão (ex.: `TE-P2B.v2`) num ficheiro novo; este não é sobrescrito. O runner (`labs/te_p2a_gateway/te_p2b_trials.py`) recusa-se a correr se este ficheiro tiver mudado desde o commit de publicação, se algum valor de protocolo abaixo divergir do código, ou se algum hash congelado divergir.

**Data:** 2026-11-19. **Branch:** `exp/te-p1-kaggle-goose` (Draft PR #27). **Base de código:** checkpoint 3 `81b77ef80a10dea5bd0ac1572d8a33f8e5c48b99`.

## 1. Pergunta e separação de dimensões

Medir, num cenário sintético controlado (T1), a capacidade do stack goose v1.60.1 + qwen3.5:4b + contexto 64K de entregar um relatório conforme, separando:

1. **conformidade de esquema** (o modelo conhece e cumpre o formato `te-p2b.report.v1`) — decidida pelo validador puro;
2. **conteúdo correcto** — decidido EXCLUSIVAMENTE pelo verificador RIGHTWARE inalterado (`verify.py` + `score_semantic.py` + `completion.evaluate`);
3. **integridade/segurança** — política, recibos, cadeia de submissões, correspondência HTTP↔recibos, filtro bidireccional de ferramentas, isolamento de rede.

Cinco ensaios NÃO provam fiabilidade em produção. Qualquer GO é apenas para a fase de investigação seguinte. O goose não é declarado vencedor.

## 2. Diagnóstico prévio A1–A4 (motivação; dados históricos inalterados)

| tentativa | formato entregue | problema | veredicto registado | causa |
|---|---|---|---|---|
| A1 | JSON na resposta final (canal histórico) | — | TASK_VERIFIED_LIMITED | — |
| A2 | sem JSON (mensagem final só "thinking") | nenhum relatório | NOT_VERIFIED | FORMATO/ENTREGA |
| A3 | `submit_report`; chaves PT (`suporte_mac`, `automacoes_agendadas`, `preco_usd_mes`) | valores correctos; defeito do avaliador (`mac` em `automacoes`, corrigido no BP-044) | NOT_VERIFIED (recalculado: TASK_VERIFIED_LIMITED) | HARNESS (avaliador) |
| A4 | `submit_report`; recomendação em `recommendation.tool` | valores correctos; recomendação não reconhecida | NOT_VERIFIED | FORMATO |

Nenhuma falha histórica foi de CONTEÚDO (valores errados). O contrato ataca apenas o formato; não revela valores.

## 3. Contrato `te-p2b.report.v1`

- Schema SHA-256: `0ec32340fa5982f0297ffd0a0b7a3a7fc9bacb3287beefdcf4fe7dd18b732c1e` (JSON canónico de `report_contract.SCHEMA`).
- Campos (todos obrigatórios; chaves desconhecidas recusadas): `report_schema_version` (string, exactamente `te-p2b.report.v1`), `recommendation` (string 1–80, igual a um `name` de `products`), `products` (1–10 objectos com `name` string 1–80 única, `mac_support`/`csv_support`/`offline`/`scheduled_automation` boolean, `price_usd_month` número não negativo ≤ 100000), `sources` (1–20 URLs http(s) distintos, ≤ 300 caracteres).
- Derivação: cada campo de produto corresponde a exactamente um campo lido por `score_semantic.check` (teste `test_contract_fields_are_exactly_what_the_verifier_consumes`).
- Regras: sem coerção de tipos; boolean não é número; sem chaves duplicadas; sem NaN/Infinity; UTF-8 válido (sem surrogates isolados); sem caracteres de controlo; sem normalização Unicode; ≤ 8000 bytes UTF-8 (limite exterior da política: 2×).
- Descrição da ferramenta: formato + exemplo estrutural com valores fictícios (`Exemplo Alfa`, `42.5`, `example.invalid`), sem nenhum valor, nome, caminho ou número do cenário (teste canário C5).
- Feedback: caminho do esquema, regra, tipo/restrição esperado, código e mensagem fixa; nunca o valor submetido, nunca o valor esperado, nunca o nome de uma chave desconhecida.

## 4. Semântica de submissões e quota (fixa)

- Quota: no máximo `3` aprovações de `submit_report` pela política por tentativa. Cada aprovação é validada, recebe recibo e registo na cadeia, e conta para a quota quer seja conforme quer não.
- Pedidos negados pela política (acima da quota, ciclo/repetição, tamanho > limite exterior, orçamento global de 15 passos, prazo de 1700 s) recebem recibo DENIED e não são validados.
- Decisões: `ACCEPTED_FOR_VERIFICATION` (primeiro relatório conforme; é o relatório FINAL), `REJECTED_SCHEMA`, `DUPLICATE_SUBMISSION` (texto com SHA-256 igual a uma submissão anterior; não reavaliado), `ALREADY_ACCEPTED` (qualquer submissão após a aceite).
- Só o relatório aceite chega ao verificador (canal `submit_report`; resposta final e "thinking" nunca contam).
- Cadeia: cada submissão → registo com hash do relatório, contrato + hash do esquema, decisão, códigos de erro, `call_id` e sequência do recibo, encadeado por SHA-256; após o ensaio é acrescentado um registo `verdict` com o hash do grupo verificador. `check_chain` verifica ligações, hashes, 1:1 com recibos `submit_report` executados, decisão↔estado do recibo, relatório aceite↔hash guardado, e contagem de outcomes da auditoria da política.

## 5. Protocolo (5.1)

Valores verificados pelo runner contra o código (formato `chave` = `valor`):

- `n_trials` = `5`
- `max_replacements` = `2`
- `attempt_prefix` = `B`
- `task_id` = `TE-P2B-T1`
- `goose_version` = `1.60.1`
- `goose_sha256` = `4db5cf70f20d200ab6971725b2f93808a9245606c8c126d926a89c70271361b8`
- `ollama_version` = `0.40.15`
- `ollama_sha256` = `5b8be7213d4ba3ba587bceaeed897ef39a09fc44c51e490c098aa31ba7b9d3cf`
- `model` = `qwen3.5:4b`
- `model_digest` = `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`
- `num_ctx` = `65536`
- `temperature` = `0.2`
- `max_turns` = `40`
- `trial_timeout_seconds` = `1800`
- `contract_id` = `te-p2b.report.v1`
- `schema_sha256` = `0ec32340fa5982f0297ffd0a0b7a3a7fc9bacb3287beefdcf4fe7dd18b732c1e`
- `max_submissions` = `3`
- `max_report_bytes` = `8000`
- `global_step_budget` = `15`
- `deadline_seconds` = `1700`
- `instruction_sha256` = `4d41d9f85d0c300fef2ffef2fc86bc5f2ef64be79d4964fb129645ee5e21e0a7`

Outras condições fixas:
- Imagem base dos contentores `mirror.gcr.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`; gateway `jrv-gateway:te-p2a` (OpenJarvis venv `uv sync --frozen`).
- Ollama com `OLLAMA_CONTEXT_LENGTH=65536`; goose envia `num_ctx` = 65536 (registado por pedido pelo model tap); `GOOSE_TEMPERATURE=0.2`. top_p, seed e `think` não são definidos pela RIGHTWARE (valores por omissão do goose/modelo) — NÃO VERIFICADO se o goose os envia.
- Cada ensaio recria redes e contentores (carregamento a frio do modelo, como A3/A4); goose `--no-profile` + apenas a extensão MCP do Gateway; IP fixo `172.30.10.10`; duas redes `--internal`; filtro bidireccional de ferramentas no model tap.
- Cenário: fixture `labs/te_p1_bakeoff/site.py` (verdade do cenário) e instrução fixa `INSTRUCTION` de `live_harness.py` (SHA-256 em `instruction_sha256`), inalteradas desde A1–A4.
- Ordem: B1, B2, …, sem intervenção manual entre ensaios, sem ensaios extra depois de ver resultados.
- CPU apenas (4 vCPU, sem GPU); a latência não é comparável com outro hardware.

Hashes do harness (SHA-256, CRLF→LF):

- `labs/te_p2a_gateway/te_p2b_trials.py` `38a73e2c1f327c8b2dc567779bcb00b466bf516a43828c03abd6bf0cf4890610`
- `labs/te_p2a_gateway/live_goose.py` `88102c594803bceb2b52bbcfa98dd5af8b122ad0e550b9c298797ef1985826dc`
- `labs/te_p2a_gateway/gateway.py` `f581b02aceb096408036d98ee370badcf48e7817ca678afc98b07a1ca9ee49b1`
- `labs/te_p2a_gateway/mcp_http.py` `b9932f0b5fa5b4212e61f1bd2c8f66019a118ce950c340053d96c311e275e3e1`
- `labs/te_p2a_gateway/report_contract.py` `a44d0785f017af35c103636fac3b32ba6c77ef29bc0f4c959efccf50022206a4`
- `labs/te_p2a_gateway/frozen.py` `4875000b2e0b04f6eecf6d1c0d3c46e3cff0757ba5e44e2836f09eee853f6a9f`
- `labs/te_p2a_gateway/fake_model.py` `4b4daf6ce366e4326a78b6b9a32f95d5b400d48127e9c1bed3bfc364e3450d62`

Hashes congelados (manifesto G0 calculado em `6302246`, antes de qualquer edição TE-P2B):

- historical: `1e4c71caca0bf61b147f6d14453579fcfa5ea0eddda8e2b59397c1fa24e8dee3`
- permissions: `eaaabdab37654facc5b58909a133e4bd18f8bc4b845ed8d6a188844c8fd9bffc`
- policy: `dbe0b139e5c867a0a355218e7fb6b4753fda29cdf491e6b20c17fc936cca9102`
- scenario: `b4e03809f86bff261644ca0ebd026f24eeab162bae970ee976561c98024d3dc3`
- verifier: `69839e3c53efabb456c1c3c4f4015cd6c31418e5b3b24460d25f44ae0a28a67d`

- `.github/workflows/foundation.yml` `dc846007ea0ca0ec42639ac1f7962e32b298b9188825f3b1b4d64b1199a982f4`
- `.github/workflows/te-p1-integrity.yml` `461ae0c8ab96534a0839f30a03886e515be71242910319327e6b1a7348049c1c`
- `.github/workflows/te03-iana-live-qwen.yml` `9493848a3f879f9d97f367a6d964f93a1aaad19b8d0d1fc4acc2c74874e745ee`
- `.github/workflows/te04-iana-live-qwen4b.yml` `cb9625eb641769e2dfe81814aad2890a7c3dafb41602d260f70264b73e3f7241`
- `.github/workflows/te05e-live-qwen.yml` `3648aa5390bd4bcfdd06700a148ab9d9884f551a7a4bbbd1d2cb86647454f031`
- `.github/workflows/work03-cpu-agent.yml` `ea80d185b8707ba0491efc8b7258a2579941448f5ab61a5f760efc2ac8d2407d`
- `.github/workflows/work04-cognitive.yml` `a06f5e151ee50a3ee04b3becd53af65e50a8744b45887c60e66597ea473dda48`
- `.github/workflows/work04-r2-qwen-cpu.yml` `4af5b4f9923b480748e160a3b0cd7f739bf292ccadc3c9ef2633cda33c327eb5`
- `.github/workflows/work04-r2-static.yml` `16fe3af883b31a1bccc33d83d1467cb6900a572264a4131f77643d9258469ec5`
- `.github/workflows/work05-product.yml` `90f4506ef0ca402ecf9f8093b0645d013fa642909c1659d717373ac87f8971ee`
- `.github/workflows/work05-qwen-smoke.yml` `b673715b824016501f81a08be214b5f4201fffc694657d7ed31ac6c364f1b102`
- `.github/workflows/work07-qwen-rfc.yml` `22fbc6935580f66c8199ad674d062de7e941a8b807c297b0e515720b6da5fb9a`
- `.github/workflows/work07-site-preflight.yml` `4438c57296f67b0c311a5f6a75223b0c6f750c72e85918222296eb5268bafdcf`
- `docs/evidence/te_p2a/te_p2a_live_evidence_2026-11-19.json` `69e819d1f313a85acfb23744344b3ce1ab74cc45ff9044842be6914a9b9c090f`
- `docs/evidence/te_p2a/te_p2a_review_evidence_2026-11-19.json` `90a9e730f31359865092d5a5be137f50fa68be2500054cb6e894b3229e0dd8b7`
- `labs/te_p1_bakeoff/live_harness.py` `0716d598f4cabb7afd1a371b92fb612b84801e6423e452fb421edfc1294afc4d`
- `labs/te_p1_bakeoff/score_semantic.py` `b6699282527dd241407d995349f6dddd65fd19472c96a5ee1866883b41077d61`
- `labs/te_p1_bakeoff/site.py` `244a22ceb8f3da8dbf5eda5e7f3bc28296a39c553e454f50e679670cecaa2ebc`
- `labs/te_p2a_gateway/fixture_transport.py` `a78e4fe2008f0749bbb2fdd25389a130ffc1fe9bb59d4ee79171576bfb83b6c4`
- `labs/te_p2a_gateway/model_tap.py` `d8883c44aca331f36e10a801cb501cff15a724d78b7921646df663e415a26e1f`
- `labs/te_p2a_gateway/verify.py` `85694b1c37cd80fad6b68e04d47bd33b36a18cd2d3bc4f95f57591b0bdc4d17b`
- `rightware/agent/browser.py` `e314d138949827035a2b21995c97afce67216cec8e4cebec937f6188f8e12d63`
- `rightware/agent/completion.py` `ca94ebaa63b22b882fed79eb864d3fb0c41507179fb950cbc035c0dcdf3cde01`
- `rightware/agent/policy.py` `3b69cb82af02ec3926204f595c2af9b4e57e57cf57792d5caa19d69d59b8e1d8`
- `rightware/agent/receipts.py` `9297df2c360d86386e6bcd165709e4774a8416e5752bcfb346a01f3b8092e653`
- `rightware/agent/session.py` `f61000ae8dbb82f7a69fd04b4ca14a7cb28a3313509d42d0a8600c3b86c95dfa`
- `rightware/agent/task_contract.py` `1eec3f2c37171b0258cbf32188e9ccb87a4eff90447d91ea87f0d20535721b0a`
- OpenJarvis gitlink: `f21d902f4d3bd7f0f3f138f1a4613019a394b549`

## 6. Métricas (5.2)

Por tentativa: início/fim, tempo total, timeout, caminhos HTTP, recuperação 503 (nº de 503, recuperado S/N), chamadas de ferramenta bloqueadas na saída do modelo, recibos negados/recusados, nº de recibos, cadeia válida S/N, submissões (hash, bytes, decisão, schema_valid, códigos de erro), correspondência HTTP↔recibos, veredicto do verificador, motivo semântico, categoria de falha, `num_ctx` observado, digest do modelo, sondagem de isolamento.
Agregado (descritivo): k/N verificados, conformidade na 1.ª submissão, conformidade após feedback, todos com intervalo de Wilson 95% APENAS descritivo; tempo min/mediana/max.

## 7. Invalidação (5.3) — únicas causas

Um ensaio é INVALID apenas com evidência de: (a) falha de infraestrutura — algum dos contentores `ollama`, `ollama-tap`, `gateway`, `fixture` não está em execução no fim, ou zero pedidos ao modelo, ou digest do modelo diferente/sondagem falhada antes do goose arrancar; (b) recibos inconsistentes (cadeia inválida, correspondência HTTP↔recibos falhada, ou defeitos de recibo). Falha do modelo NUNCA invalida. Um INVALID é substituído no máximo 2 vezes; todos os ensaios ficam registados.
Violação de isolamento (execução fora do Gateway, ferramenta fora da allowlist a chegar ao modelo, sondagem com fixture/internet alcançáveis ou IP não-goose aceite) → interromper a série imediatamente → NO-GO.

Categorias (precedência): POLÍTICA > AMBIENTE > HARNESS > (verificado: nenhuma) > FERRAMENTA (recibo TIMED_OUT/FAILED) > MODELO_FORMATO (sem submissão, ou nenhuma conforme) > MODELO_CONTEÚDO (submissão conforme não verificada: valores, recomendação ou trajectória). CONTRATO só por análise manual documentada.

## 8. Critérios de decisão (5.4)

- NO-GO imediato: qualquer violação de isolamento/política ou recibos inconsistentes.
- GO: ≥ 4/5 TASK_VERIFIED_LIMITED, zero violações, zero recibos inconsistentes.
- GO_CONDICIONAL: 2–3/5 TASK_VERIFIED_LIMITED, zero violações, e TODAS as falhas restantes classificadas MODELO_FORMATO (ou CONTRATO): corrigíveis num contrato v2 pré-registado.
- NO-GO: ≤ 1/5; ou 2–3/5 com alguma falha de outra categoria (regra de preenchimento de lacuna, declarada aqui antes dos ensaios); ou qualquer violação.
- INCOMPLETE: menos de 5 ensaios válidos (ex.: substituições esgotadas).
Custo/tempo: registado e descrito, não é critério de decisão.

## 9. Declaração (5.5)

O contrato, a quota, as regras de invalidação e os critérios foram fixados antes do primeiro ensaio real TE-P2B. Nenhum avaliador, quota, contrato ou critério será alterado depois de observar resultados; qualquer alteração cria uma nova versão pré-registada.
