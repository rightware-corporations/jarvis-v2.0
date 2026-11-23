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
