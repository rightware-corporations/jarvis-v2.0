# Divulgação de independência (avaliação W3.2-R)
- O conjunto H1–H10 (páginas fictícias novas e critérios) foi **congelado e publicado no commit `ac7aa29`, antes de qualquer código W3.2-R**.
- A implementação (`9d6d316`) foi feita sem executar H. Por limitação de tempo, o H correu **uma única vez**, com o código final. Nenhuma alteração foi feita depois de ver os resultados de H.
- O autor da implementação também escreveu o conjunto H. Isto limita a independência: as perguntas não são cegas para o implementador.
- S1 (Q1–Q9) e S3 (R1–R5) **não são independentes**: foram usados no diagnóstico do W3.2.
- O juiz é `labs/web01/w32_eval.judge`, **inalterado**. Lê só as afirmações aceites como FACTO e as contradições do anfitrião. As alegações atribuídas (fórum) ficam fora de `accepted`, por desenho do R03; são mostradas ao utilizador como "alegação NÃO sustentada".
- O juiz original aceitou 3 casos com associação errada (H8, Q7, R5). Constam como falhas de segurança em `METRICS.json`, apesar de o juiz os marcar adequados.
- Qualquer correcção futura que resulte desta análise exige um **novo** conjunto independente (H2), congelado antes de executar.
