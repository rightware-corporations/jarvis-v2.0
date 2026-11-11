# RIGHTWARE JARVIS v2.0 — GOVERNANÇA DE BRANCHES

**Decisão institucional, 11/11/2026:** modelo de **três branches de referência**. Esta decisão organiza a engenharia; não altera o estado de aceitação do produto.

## 1. Estrutura oficial

| Branch | Responsabilidade | Regra |
|---|---|---|
| `main` | Versões aprovadas / referência de release | Não receber automaticamente todo o trabalho de `develop`; PR de release, testes e aprovação explícita. |
| `develop` | **Linha única de desenvolvimento diário e integração** | Novos checkpoints e desenvolvimento ordinário decorrem aqui. CI obrigatório; HANDOFF persistido. |
| `demo/issa-20261111` | Cópia contextual de demonstração | Deriva de `develop` quando autorizado, sem se tornar linha paralela de produto. Não confundir com aceitação real em Windows, voz ou Qwen. |

Para trabalho de alto risco ou desenvolvimento simultâneo, branches temporárias continuam possíveis com justificação explícita, dono, prazo de vida e plano de merge/arquivo. Não criar uma nova branch por cada subfase menor.

## 2. Integração verificada em 11/11/2026

| PR / commit | Movimento | Efeito |
|---|---|---|
| PR #4 — `929fa945166ad4515498aba35a41a6eff3d2b4c9` | WORK-05 R1 → `develop` | Agente de produto e endurecimento de segurança; código testado em CI; **Qwen real não executado**. |
| PR #5 — `63986b9a563fa11ca7430e466bdfaceaeecb4645` | `main` → `develop` | Preserva os dois workflows exclusivamente existentes em `main`, de execução manual. `main` inalterada. |
| `671bdb2e733fe47009a28792047e4404afd68065` | Documento único de investigação → `develop` | Preserva o radar open-source original. |
| PR #2 — `1d4661556bc12527e7dead495917b103c8fe090f` | WORK-04 R2 → `develop` | Históricos, testes e evidências do R2 integrados. Conflito em HANDOFF reconciliado de forma append-only; testes WORK-04 e WORK-05 passaram em `5798c70e`. **Benchmark histórico 0/35 continua NOT ACCEPTED.** |
| `7200b123dd8d775db064c942cdd711e0384fc87f` | Commit de arquivo de ascendência (`-s ours` conceptual) | Liga o histórico do WORK-05-A alternativo e da investigação a `develop` **sem alterar ficheiros**; nenhum runtime alternativo foi integrado. |
| PR #6 — `ccac84ec75e907ec709242dee7bfff745df41295` | `develop` → `demo/issa-20261111` | Preserva os dois commits da demo e incorpora histórico consolidado. Não comprova funcionalidades reais. |
| PR #3 | Fechado SEM MERGE | Protótipo alternativo WORK-05-A não seleccionado; código e commits preservados via ascendência de `develop`. |

**CI relevante:** `43105709812` WORK-05 R1 success; `43107964069` WORK-04 R2 success; `43107975121` WORK-05 success. O workflow WORK-05 foi configurado para também correr em `develop` e nos PRs para `develop`.

**Repositório de produto:** o HEAD operacional é `develop`; o HEAD da `main` ainda é `0cac8e8d828d91cb9d849c67a33f62eb701bdb94`, sem promoção de release.

## 3. Branches temporárias ainda visíveis no GitHub

A verificação `compare/<branch>...develop` confirmou **behind_develop=0** para todas as quatro referências abaixo. O seu histórico é alcançável por `develop`, mas a API de mutação deste conector **não permite apagar branches**. O número físico de branches só descerá de 7 para 3 após eliminação administrativa das referências.

| Branch física temporária | Último SHA conhecido | Estado / recuperação |
|---|---|---|
| `feat/work05-product-agent` | `ff46a027b5756718441d0ab070af3457114885f1` | PR #4 integrado; conteúdo no produto. |
| `feat/work04-r2-semantic-safety` | `5798c70ee5843c8a21945d4f2279dd2b2f2efd10` | PR #2 integrado; 0/35 histórico ainda não aprovado. |
| `feat/work05-product-agent-foundation` | `5499bdbe4994606258e70ec9ea2bc60d7ee8c111` | História arquivada no merge de ascendência; ficheiro alternativo `rightware/agent_tools.py` **não** integra o runtime activo; recuperável por SHA. |
| `research/jarvis-agent-survey-20261111` | `5864036773f1818848dab01a8e35937718bbe7ff` | História arquivada; documento único copiado com SHA de blob idêntico. |

**Checklist antes de apagar estas quatro branches:** confirmar mais uma vez que o HEAD remoto corresponde à tabela, que `develop` contém cada SHA (`git merge-base --is-ancestor`), que não existem workers/PRs em execução nessas referências e que PRs/evidências ficam acessíveis. Não usar force-push. Não apagar a branch da demo.

## 4. Protecção técnica pendente

Na auditoria, todas as branches tinham `protected=false`. O conector GitHub disponível não possui operações de criação/alteração de rulesets, de branch protection, nem de exclusão de branch. **Não declarar estas acções concluídas.**

A conta com administração do repositório deverá configurar nas definições do GitHub: protecção de `main` e `develop`; proibir force pushes e exclusão; checks obrigatórios adequados; revisão de PR em `main`. O processo de `develop` pode permitir commits directos do operador após CI, de acordo com a decisão de desenvolvimento diário.

## 5. Continuidade e segurança

- Antes de qualquer tarefa, consultar `docs/HANDOFF.md`, este documento, HEAD remoto e CI.
- Antes de cada output de progresso substantivo, gravar checkpoint técnico sanitizado em HANDOFF, fazer commit/push, verificar HEAD e citar SHA; se falhar, declarar não persistido.
- Não guardar segredos, dados pessoais, conversas privadas nem pesos de modelos no repositório público.
- Não executar testes Qwen reais sem autorização explícita, incluindo HEAD, cenário e limites. Testes FAKE e determinísticos não são evidência de aceitação do produto.
- Manter OpenJarvis fixado e a separação entre `rightware/` (produto) e `labs/` (investigação).
