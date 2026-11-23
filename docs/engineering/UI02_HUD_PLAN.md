# UI-02 — RIGHTWARE JARVIS HUD sobre a interface React original do OpenJarvis (plano)

Estado: **plano, por autorizar.** Base: PR #30 (UI-01). Regra de produto: a interface apresentada ao Issa é o produto que continua. Não haverá outra aplicação, demonstração descartável, mocks ou capacidades simuladas.

## 1. Estratégia de personalização reproduzível (fora do vendor)

**Problema.** O frontend original importa módulos por caminho relativo (`./components/Layout`), por isso não basta um `alias`. Editar `vendor/openjarvis` não é permitido.

**Solução: overlay declarado, aplicado no build isolado do UI-01** (`rightware/gui/runtime.py`):
1. A cópia do frontend continua a vir do `git archive` do pin. O vendor nunca é escrito.
2. **`rightware/gui/frontend/overlay.manifest.json`** lista cada módulo upstream substituído:
   - `upstream`: o caminho no pin;
   - `upstream_sha256`: o hash do ficheiro no pin;
   - `replacement`: o ficheiro RIGHTWARE;
   - `reason`: o motivo.

   No build, se o hash upstream não coincidir (por exemplo, numa mudança de pin), **o build falha**. Não há deriva silenciosa.
3. **`rightware/gui/frontend/vite.rightware.ts`** importa a `vite.config.ts` do pin com `mergeConfig` e acrescenta:
   - o plugin `rightwareOverlay()`: um hook `resolveId` que, *depois* da resolução normal, troca o id resolvido de cada módulo listado pelo substituto;
   - o alias `@rw` → `rightware/gui/frontend/src`;
   - `outDir` → `.runtime/gui/static`.
4. As substituições são **poucas e pequenas** (tabela §3). Componentes novos ficam em `@rw/…`, importados pelos módulos substituídos.
5. Testes de componentes RIGHTWARE em **vitest**, com a config do pin mais o overlay. Os 117 testes upstream continuam a correr, excepto os dos módulos substituídos, que são listados no manifesto e trocados pelos testes RIGHTWARE equivalentes.

**Alternativas rejeitadas:**
- fork do frontend, porque seria um segundo frontend;
- patches `git apply` sobre ficheiros grandes, frágeis numa mudança de pin;
- iframe ou app nova, porque seria outra aplicação.

## 2. Backend RIGHTWARE necessário (sem segundo backend: rotas na bridge existente, allowlist da PolicyApp)

| Rota (nova na allowlist) | Função | Contrato |
|---|---|---|
| `GET /v1/rightware/state` | Estado único da HUD | Motor (saúde, modelos permitidos); capacidades com estado (INTEGRADA, PARCIAL, NÃO INTEGRADA, BLOQUEADA) e motivo; tarefa activa (capacidade, início, fase); último resultado estruturado (estado, `verified`, recibos, objectivos, comentário NÃO verificado); fila do modelo. Vem só do ControlPlane e do facade, nunca do modelo. |
| `POST /v1/rightware/tasks/request` | Pedir uma missão | `{capability}` → `AUTORIZACAO_NECESSARIA` com o código, ou o código fora da banda conforme R-1 |
| `POST /v1/rightware/tasks/authorize` | Autorizar | `{code}`. Mesma semântica do `/autorizar`: só o código; qualquer tentativa o consome |
| `POST /v1/rightware/tasks/cancel` | Cancelar | via `ControlPlane.cancel` |
| `GET /v1/rightware/events` (SSE) **ou** polling de 1 s | Mudanças de estado | Sem WebSocket: o `ws` continua `none` |

Os comandos `/tarefa…` no chat continuam a funcionar. A HUD é outra vista do **mesmo** ControlPlane.

**Correcções de backend incluídas (da revisão):**
- R-4: cancelamento propagado (desconexão → `facade.cancel` → fecho do pedido ao Ollama);
- R-5: id de conversa explícito;
- R-10: rotação do audit;
- R-7: `num_thread = núcleos − 1` para o Ollama da missão (declarado em PARITY se for no `model_tap`).
- **Opcional:** streaming de tokens no adaptador, para que o primeiro token chegue antes da resposta completa.

## 3. Componentes permanentes (`rightware/gui/frontend/src/`)

| Componente | Dados reais de que depende | Comportamento |
|---|---|---|
| `hud/JarvisCore.tsx` | `state.engine`, estado do stream de conversa, `state.task`, `state.last` | Núcleo animado em SVG ou canvas com estados `offline`, `pronto`, `a pensar`, `a executar missão`, `verificado`, `não verificado`, `falha`. **Só muda de estado com sinal do backend.** Orçamento de CPU: animação pausada com o separador oculto, durante inferência e durante missões (R-7); respeita `prefers-reduced-motion`; no máximo 30 fps. |
| `hud/ExecutionTimeline.tsx` | recibos e objectivos estruturados | Linha temporal de recibos (`#seq ferramenta estado`), objectivos e veredicto do verificador. O comentário do modelo aparece separado e rotulado NÃO verificado. |
| `hud/MissionsPanel.tsx` | `/v1/rightware/state`, `tasks/*` | Lista de capacidades activadas pelo anfitrião, pedido, **campo de código do operador** (sem botão "aprovar" sem código), progresso, cancelamento e histórico em memória. Mostra o tempo por turno e o aviso de contenção quando a geração está lenta. |
| `hud/VoicePanel.tsx` | `state.capabilities.voice` | Hoje "Voz — NÃO INTEGRADA", com o motivo (extra `desktop`, validação em hardware). O microfone upstream (`MicButton`) é substituído por um estado desactivado com explicação. Integração futura via gate próprio. |
| `hud/FinanceIntelPanel.tsx` | `state.capabilities.finance` | Hoje "Inteligência financeira — NÃO INTEGRADA" e os requisitos: Internet autorizada, fontes datadas, verificador, sem ordens. **Nenhum número, gráfico ou cotação exibidos** até haver dados verificados. O contrato de dados está definido (fonte, carimbo temporal, hash da observação, estado de verificação) para a integração futura. |
| `hud/CapabilityBadge.tsx` | estado da capacidade | Badge uniforme: INTEGRADA, PARCIAL, NÃO INTEGRADA ou BLOQUEADA, com o motivo |
| `lib/rightware-api.ts`, `lib/rightware-store.ts` | rotas §2 | Cliente tipado e slice zustand separado da store upstream |
| `i18n/pt-MZ.ts` | — | Textos da HUD e dos módulos substituídos em PT-MZ, com EN como secundário |
| `theme/rightware.css` | — | Tokens visuais RIGHTWARE JARVIS (cores, tipografia) sobre os tokens shadcn do pin |

**Módulos upstream substituídos** (manifesto com hash do pin):

| Upstream (pin) | Linhas | sha256 (16) | Substituto e motivo |
|---|---|---|---|
| `src/main.tsx` | 46 | `df88421e94d95f7a` | Importar o tema RIGHTWARE, desactivar o registo do service worker (R-12) e não chamar `initAnalytics` |
| `src/components/Chat/SystemPanel.tsx` | 315 | `404b54e39dac9693` | Painel direito → JarvisCore, ExecutionTimeline e resumo de missões (sai a comparação de custos e o leaderboard) |
| `src/components/OptInModal.tsx` | 266 | `9e0afa3f480428a6` | Componente nulo: sem modal de analytics e giveaway (R-8) |
| `src/lib/analytics-invitation.ts` | 33 | `d1595b2491836912` | No-op |
| `src/components/Chat/MicButton.tsx` | 80 | `d6beeb361f770b55` | Estado "Voz não integrada" |
| `src/pages/AgentsPage.tsx` | 4007 | `6a61edc5b1821eec` | A rota `/agents` passa a mostrar a página **Missões** (MissionsPanel completo) |
| `src/pages/DataSourcesPage.tsx` | 2399 | `4ae97b561a8fdf1f` | A rota `/data-sources` passa a mostrar a página **Capacidades** (estado honesto de cada capacidade) |
| `src/pages/DashboardPage.tsx` | 35 | `332fd0a8f7965f0b` | HUD de ecrã inteiro: JarvisCore, missões, voz e finanças com o estado real |
| `src/components/Sidebar/Sidebar.tsx` | 235 | `f4871004311825cc` | Navegação PT-MZ: Conversa, HUD, Missões, Capacidades, Registos, Definições |

`App.tsx`, a conversa (`ChatArea`, `InputArea`, `MessageBubble`), a store e a API upstream **não** são substituídos.

## 4. Ficheiros afectados

**Novos:**
- `rightware/gui/frontend/{overlay.manifest.json, vite.rightware.ts, package.json*}`
- `rightware/gui/frontend/src/{hud/*, lib/*, i18n/*, theme/*, overrides/*}`
- `tests/test_ui02_overlay.py`: hashes do manifesto contra o pin, contrato das rotas e política
- `rightware/gui/frontend/src/**/*.test.tsx`: vitest
- `labs/ui02/hud_e2e.mjs`
- `docs/engineering/UI02_HUD.md`

\* O `package.json` fica só para scripts; usa o `node_modules` do pin, sem dependências novas sem autorização.

**Alterados:**
- `rightware/gui/runtime.py`: aplica o overlay e verifica o manifesto;
- `rightware/gui/bridge.py`: rotas §2, R-4, R-5;
- `rightware/gui/policy.py`: allowlist §2;
- `rightware/goose_adapter.py` ou `rightware/gateway/model_tap.py`: `num_thread` (R-7, declarado);
- `tests/test_ui01_gui.py`: allowlist;
- `docs/HANDOFF.md`.

**Inalterados:** `vendor/` (pin), ControlPlane e contratos P1, goose, Gateway, verificador e recibos (hashes verificados por teste).

## 5. Critérios de aceitação (UI-02)

1. O build do overlay é reprodutível a partir do pin: dois builds dão a mesma árvore estática. Uma mudança no hash de qualquer módulo upstream substituído faz o build falhar (teste).
2. `vendor/` não muda (gitlink e working tree). Nenhum segundo frontend ou backend. Toda a função nova passa pela PolicyApp e pela allowlist testada.
3. A HUD mostra **apenas** estados que vêm de `/v1/rightware/state`. Teste: com o backend parado, o núcleo fica `offline`, sem animação de actividade nem dados.
4. Uma missão só é autorizada com o código do operador. Não existe nenhum caminho de clique sem código (teste E2E). O cancelamento tem efeito real e fica visível.
5. Resultados verificados e comentários NÃO verificados são visualmente distintos (teste de componente e E2E).
6. Voz e finanças aparecem **NÃO INTEGRADAS**, com o motivo. Nenhuma cotação ou número é mostrado (teste que procura dígitos ou preços no painel de finanças sem fonte).
7. **Orçamento de CPU:** com a HUD aberta em Chromium sem GPU, idle mais de 30 s, o browser consome **≤ 10% de um núcleo**. Durante uma missão, a geração do 4B fica a **≥ 85%** dos tokens/s sem browser (método E0/E1).
8. **Uma missão goose real pela HUD termina VERIFICADA** neste host (com a mitigação R-7). Até lá, o goose continua PARCIAL.
9. R-4: depois de abortar um pedido longo, um pedido curto de outra conversa responde em menos de 2× o tempo isolado (método da revisão).
10. A interface está em PT-MZ por omissão (EN disponível). As páginas upstream não integradas deixam de aparecer na navegação.
11. Testes: suite Python 100% sem skips; vitest dos componentes RIGHTWARE e upstream não substituídos verdes; E2E HUD com todos os cenários da tabela B5 mais missões pela HUD; CI verde no head exacto.
12. HANDOFF actualizado; PR única Draft; sem merge sem aprovação; `main` e PR #27 intactos; P3B não iniciado.

## 6. Decisões do operador necessárias

1. **R-1:** onde aparece o código do operador (na GUI, no modo local actual, ou fora da banda).
2. **R-2:** token de sessão local já em UI-02 ou só no B6.
3. **CI:** autorizar um job de frontend (Node) nos workflows (R-9).
4. **R-7:** aplicar `num_thread` no `model_tap` (alteração declarada em PARITY) ou limitar o CPU do contentor.
5. Identidade visual: aprovar o tema e o nome "RIGHTWARE JARVIS".
6. Ordem: merge da PR #30 primeiro (recomendado), depois uma branch UI-02 única a partir de `develop`.
