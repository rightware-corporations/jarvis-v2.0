# JRV-P3A — productização do RIGHTWARE Tool Gateway

**Branch temporária:** `integration/jrv-p3a-gateway-20261123`, a partir de `develop` `5ae4ddf` (estado `JRV_P2_MERGED_VERIFIED`). Destina-se a uma única PR para `develop`; a branch é apagada depois do merge ou do fecho.

## 1. Gate 0: reconciliação e matriz de dependências (antes de alterar código)

**Reconciliação:**
- HEAD local = remoto = `5ae4ddf29ec52a67a6c589bfca1bb7ad8ebdbc66`, árvore limpa.
- CI no HEAD: WORK-05 45121050993 e foundation 45121051050, ambos success.
- PR #28 merged (`9a0eadb`); PR #27 Draft (`a1b88ef`); pin OpenJarvis `f21d902`.

**Imagem actual `jrv-gateway:te-p2a`:** foi criada no TE-P2A com `docker run` + `docker commit` (instalação do vendor com `uv sync --frozen` num contentor). Não tem Dockerfile versionado nem manifesto, e a imagem base foi referida pela tag `python:3.12-slim`. A sua construção não é reprodutível a partir do repositório.

**Como o produto usa hoje o Gateway (P2):**
- **Contentores:**
  - `gateway`: corre `labs.te_p2a_gateway.mcp_http` com o repositório inteiro montado em `/app:ro`.
  - `ollama-tap`: corre `labs.te_p2a_gateway.model_tap` com `labs/` montado.
  - `fixture`: corre `labs.te_p1_bakeoff.site` com `labs/` montado.
- **Anfitrião:** `rightware/goose_adapter.py` importa `labs.te_p2a_gateway.{verify,report_contract}`.

**Dependências reais, por import:**
- **Gateway** (`gateway.py`) importa:
  - `rightware.agent.browser.PublicBrowser/Step`
  - `rightware.agent.policy.AgentPolicy/Budgets/ToolDef/canonical`
  - `rightware.agent.receipts.ReceiptLedger`
  - `rightware.agent.session.TOOLS`, que importa OpenJarvis (`openjarvis.agents/core/tools`)
  - `report_contract`
  - lazy, TE-P2D: `labs.te_p2d_public.research_contract`, que **não existe** em develop.
- **`mcp_http`** importa:
  - `rightware.agent.policy.Budgets`
  - `fixture_transport`
  - `gateway`
  - lazy, TE-P2D: `labs.te_p2d_public.{egress,transport}`, também ausentes.
- **`fixture_transport`** importa `httpx` e `rightware.agent.web.HttpxFetcher`, que usa `openjarvis.security.ssrf` de forma lazy.
- **`verify`** importa:
  - `labs.te_p1_bakeoff.score_semantic.check`
  - `rightware.agent.completion.evaluate`
  - `rightware.agent.task_contract`
  - `fixture_transport.BASE_URL/SYNTHETIC_HOST`
- **Só stdlib:** `model_tap`, `report_contract`, `site` e `score_semantic`.

| Módulo actual | Classificação | Destino P3A |
|---|---|---|
| `labs/te_p2a_gateway/gateway.py` | **Runtime de produto** (Gateway MCP: AgentPolicy + ReceiptLedger + contrato) | `rightware/gateway/gateway.py` |
| `labs/te_p2a_gateway/mcp_http.py` | **Runtime de produto** (transporte MCP, allowlist de clientes, evidência) | `rightware/gateway/mcp_http.py` |
| `labs/te_p2a_gateway/model_tap.py` | **Runtime de produto** (filtro de ferramentas na fronteira do modelo) | `rightware/gateway/model_tap.py` |
| `labs/te_p2a_gateway/report_contract.py` | **Runtime de produto** (contrato `te-p2b.report.v1` e cadeia) | `rightware/gateway/report_contract.py` |
| `labs/te_p2a_gateway/verify.py` | **Runtime de produto** (verificador RIGHTWARE) | `rightware/gateway/verify.py` |
| `labs/te_p2a_gateway/fixture_transport.py` | **Fixture**: material de ensaio usado em runtime **só** pela capacidade sintética | `rightware/gateway/synthetic/fixture_transport.py` |
| `labs/te_p1_bakeoff/site.py` | **Fixture** (servidor do catálogo sintético) | `rightware/gateway/synthetic/site.py` |
| `labs/te_p1_bakeoff/score_semantic.py` | **Fixture** (valores esperados do catálogo sintético, usados pelo verificador) | `rightware/gateway/synthetic/score_semantic.py` |
| `labs/te_p2a_gateway/fake_model.py` | **Teste** | fica em `labs/` |
| `labs/te_p2a_gateway/*.py`, `labs/te_p1_bakeoff/{site,score_semantic}.py` | **Investigação histórica**: os nomes continuam a ser importáveis | ficam como aliases (`sys.modules`) para o módulo `rightware.gateway.*`, sem segunda implementação |
| referências a `labs.te_p2d_public.*` | **Investigação histórica** (TE-P2D, fora de develop) | substituídas por recusa explícita (fail-closed), com o mesmo resultado que hoje (antes ImportError) |
| `rightware/agent/{policy,receipts,browser,session,web,completion,task_contract,diagnostics,trace}.py` | **Dependência partilhada** | inalterados |
| `vendor/openjarvis` (`f21d902`) | **Dependência partilhada** (pin) | inalterado; instalado na imagem a partir do `uv.lock` do pin |
| `tests/test_te_p2a_gateway.py` | **Teste histórico** | inalterado; continua a passar através dos aliases |
| `labs/p2/*` | **Investigação** (harness real, mutação) | caminhos actualizados só onde é necessário |

## 2. Arquitectura antes e depois

```
ANTES (P2, develop 5ae4ddf)
  goose_adapter ──import──> labs.te_p2a_gateway.{verify,report_contract}
  contentor gateway:  jrv-gateway:te-p2a (docker commit, origem desconhecida), corre como root,
                      com o repositório inteiro montado em /app:ro e `python -m labs.te_p2a_gateway.mcp_http`
  contentores tap/fixture:  python:slim + labs/ montado + `python -m labs.…`

DEPOIS (P3A)
  goose_adapter ──import──> rightware.gateway.{verify,report_contract}
                ──GI.local_image()──> só o id sha256 de uma imagem local cujas etiquetas correspondem a ESTA árvore
  contentores gateway / tap / fixture:  rightware/jarvis-gateway:p3a, arrancados POR ID, uid 10001, --read-only,
                      --cap-drop ALL, no-new-privileges, /tmp em tmpfs, único mount = directório de evidência
                      `python -m rightware.gateway.{mcp_http, model_tap, synthetic.site}`
  labs.te_p2a_gateway.* / labs.te_p1_bakeoff.{site,score_semantic}  =  aliases sys.modules (o MESMO objecto)
```

Inalterados:
- Control Plane, consola, AgentPolicy, ReceiptLedger e verificador (só mudaram de sítio);
- o contrato te-p2b, a topologia de redes `--internal`, a propriedade de recursos (R1), a readiness, a evidência obrigatória, o estado do processo, o cancelamento e a limpeza;
- o goose (sem mounts, IP fixo, só a extensão MCP da Gateway).

A missão continua **OFF por omissão** e exige activação pelo anfitrião e o código do operador.

## 3. Matriz de módulos migrados (paridade)

`rightware/gateway/PARITY.json` regista, para cada ficheiro movido:
- a origem;
- o blob git validado em `a1b88ef`;
- o cabeçalho acrescentado;
- as substituições declaradas.

O teste `Parity` reconstrói cada original a partir do ficheiro novo e exige o **mesmo blob git**.

| Ficheiro novo | Origem | Alterações declaradas |
|---|---|---|
| `rightware/gateway/gateway.py` | `labs/te_p2a_gateway/gateway.py` | import do contrato; removido o ramo TE-P2D (`labs.te_p2d_public`, ausente): um contrato desconhecido continua a falhar fechado, agora com ValueError em vez de ImportError |
| `rightware/gateway/mcp_http.py` | `labs/te_p2a_gateway/mcp_http.py` | 2 imports; docstring; `--egress-socket` (TE-P2D) passa a dar SystemExit explícito em vez de ImportError |
| `rightware/gateway/model_tap.py` | `labs/te_p2a_gateway/model_tap.py` | docstring |
| `rightware/gateway/report_contract.py` | `labs/te_p2a_gateway/report_contract.py` | nenhuma |
| `rightware/gateway/verify.py` | `labs/te_p2a_gateway/verify.py` | 2 imports |
| `rightware/gateway/synthetic/fixture_transport.py` | `labs/te_p2a_gateway/fixture_transport.py` | nenhuma |
| `rightware/gateway/synthetic/site.py` | `labs/te_p1_bakeoff/site.py` | docstring |
| `rightware/gateway/synthetic/score_semantic.py` | `labs/te_p1_bakeoff/score_semantic.py` | nenhuma |

**Novos ficheiros:**
- `rightware/gateway/image.py`: build, verificação e sonda de segurança.
- `configs/gateway/{Dockerfile,build-requirements.txt}`.
- `tests/test_p3a_gateway_component.py`.
- `labs/p3a/mutation_p3a.py`.

**Paridade em evidência real:** a evidência guardada da corrida real 4 do P2 (código `1b292bb`) foi reavaliada com `rightware.gateway` em `719137d`. Os 14 campos (veredicto, objectivos, 503, correspondência, cadeia, violações, estado…) são idênticos (`docs/evidence/p3a/parity_p2_run4_reevaluation.json`).

## 4. Imagem e procedimento de build

```bash
vendor/openjarvis/.venv/bin/python -m rightware.gateway.image build [--ca <bundle do proxy>] [--network host] [--no-cache]
vendor/openjarvis/.venv/bin/python -m rightware.gateway.image check
```

**Entradas fixadas:**
- base `mirror.gcr.io/library/python@sha256:5e2bdb1b…` (o mesmo digest dos restantes contentores);
- `uv==0.11.32` com `--require-hashes`;
- dependências de runtime **só** do `uv.lock` do vendor no pin `f21d902` (`uv sync --frozen --no-dev --no-editable`);
- vendor obtido por `git archive` no pin, depois de verificar que o gitlink corresponde ao pin.

**Contexto mínimo:** 995 ficheiros, a saber:
- o fecho de imports RIGHTWARE (`RUNTIME_FILES`, verificado por teste);
- `configs/gateway/*`;
- os caminhos do vendor necessários ao build.

Sem `labs/`, testes, docs, `.git` ou `.runtime/`.

**Execução:**
- utilizador 10001;
- sem binários setuid/setgid;
- `/app` não gravável;
- os contentores correm com `--read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp`.

**Identificação:** a imagem leva as etiquetas `org.rightware.gateway.{source_digest,vendor_pin,base_image,uv_lock_sha256}`. O adaptador só aceita o **id** de uma imagem cujas etiquetas correspondem à árvore actual:
- sem imagem: `GATEWAY_IMAGE_MISSING`;
- imagem sem etiquetas (por exemplo, a antiga `jrv-gateway:te-p2a`): `GATEWAY_IMAGE_UNVERIFIED`;
- imagem de outras fontes ou com utilizador privilegiado: `GATEWAY_IMAGE_STALE`.

Em qualquer destes casos a preparação pára antes de criar qualquer recurso. **Nenhuma imagem foi publicada em registos.**

**Reprodutibilidade:** dois builds `--no-cache` a partir de `719137d` produziram o **mesmo id de imagem**, `sha256:fe85afaed08f48918ff26d71f59f17b3b2331a9f12cae19e002b36ec4bceca6c`, e a mesma árvore de runtime. Foram precisas quatro iterações; os resultados negativos estão registados em `docs/evidence/p3a/gateway_image_build_2026-11-23.json`:
1. `.pyc` e `uv_cache.json` traziam timestamps;
2. os mtimes das camadas;
3. os directórios-pai criados pelo COPY e os whiteouts;
4. idêntico bit a bit.

A sonda de segurança `--network none` passou: uid 10001, 0 ficheiros setuid, `labs` não importável, `/app` só de leitura, 59 distribuições. O histórico da imagem não contém proxy nem CA; o CA entra como secret de build e não fica em nenhuma camada.

## 5. Validação

- **Testes:**
  - `tests/test_p3a_gateway_component.py`: 15 testes (paridade, aliases, ausência de imports de `labs`, fecho de imports, identidade da imagem, falhas de build e de arranque, utilizador não-root);
  - P2: 43 (actualizados para a imagem verificada e o endurecimento);
  - TE-P2A históricos: 32, inalterados, a passar através dos aliases.
- **Suite completa no venv fixado:** **660 OK, 0 skipped**. Python simples: OK.
- **Mutação:** P3A **19/19**; P2 repetida **44/44**.
- **Real (corrida P3A-1, `719137d`, mesma consola, mesmo catálogo, qwen3.5:4b):** **RESULTADO_VERIFICADO** (TASK_VERIFIED_LIMITED).
  - Processo: goose terminou com código 0 em 271,9 s (281,8 s no total).
  - Recibos e objectivos: 7 recibos = 7 chamadas observadas; 4/4 objectivos; 503 recuperado.
  - Verificação: HTTP↔recibos 6↔6, cadeia válida contra a auditoria, semântica PASS, 0 violações.
  - Isolamento: fixture e internet BLOCKED, 403 para clientes que não são o goose, só a rede da missão, 0 mounts.
  - Contentores da imagem: gateway, tap e fixture correram pelo id `sha256:fe85afae…`, como `10001:10001`, read-only, `CapDrop=[ALL]`, no-new-privileges, com o único mount em `/evidence`.
  - Limpeza: 0 contentores e 0 redes da missão no fim.
  - Evidência: `docs/evidence/p3a/p3a_real_goose_mission_2026-11-23.json`.

## 6. Diferenças de segurança

| Aspecto | Antes (P2) | Depois (P3A) |
|---|---|---|
| Origem da imagem da Gateway | `docker commit` desconhecido, referida por tag mutável | Dockerfile versionado, entradas fixadas, etiquetas ligadas à fonte, arranque por id |
| Utilizador | root | 10001 (não-root); anfitrião não-root → uid do anfitrião |
| Sistema de ficheiros | gravável | `--read-only`, `/tmp` tmpfs noexec |
| Capacidades | por omissão do Docker | `--cap-drop ALL`, no-new-privileges |
| Mounts | repositório inteiro (`/app:ro`) e `labs/` | só o directório de evidência da missão |
| Código de laboratório no produto | importado de `labs/` | nenhum import de `labs` em `rightware/` (teste AST) |
| TE-P2D | ImportError por omissão | recusa explícita |

## 7. Riscos e limites

- **Ferramentas de build sem hash:** as dependências de build do pacote vendor (`hatchling`, `hatch-vcs`) são resolvidas pelo `uv` no build e **não** estão fixadas por hash. As de runtime estão, pelo `uv.lock`.
- **Plataforma:** só linux/amd64 (a hash do `uv` é da wheel amd64).
- **Tamanho:** a imagem tem cerca de 472 MB, porque leva o conjunto completo de dependências do lock do OpenJarvis (o Gateway importa `rightware.agent.session`, que importa OpenJarvis).
- **Dependência de rede:** o build exige acesso ao PyPI. Não há mirror offline nem a imagem está publicada; cada anfitrião constrói localmente.
- **Reprodutibilidade:** demonstrada num único anfitrião (Docker 29.9.2, BuildKit 0.34). Noutros anfitriões ou versões não foi verificada.
- **Material sintético:** o catálogo sintético e os valores esperados (`synthetic/`) estão em `rightware/`, mas só são usados pela capacidade sintética e pelos testes.
- **Amostra:** N=1 real neste pacote.
- **Outros riscos do P2 que continuam:** cliente MCP autenticado por IP, colisão de sub-redes entre missões simultâneas (falha fechada), Windows não testado, sem Internet pública, não é produção.

## 8. Próximo passo P3B (proposta, requer autorização)

> **Prioridade de produto decidida (JRV-PRODUCT-DIRECTION-UI-REUSE, 23/11/2026):** a próxima prioridade é reutilizar e integrar a GUI existente do OpenJarvis, e não desenvolver outra interface. O P3B abaixo fica como proposta e **não** é iniciado automaticamente.


- Tornar o build da imagem independente da rede: wheelhouse local verificado por hash, incluindo as ferramentas de build.
- Reduzir a imagem a um conjunto mínimo de dependências: extrair de `rightware.agent.session` o que o Gateway usa.
- N≥3 missões reais pré-registadas através do produto, com a imagem P3A.
- Decidir a publicação da imagem num registo interno autorizado, com assinatura e SBOM.
