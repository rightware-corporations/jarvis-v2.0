# Revisão de merge — PR #30 (UI-01), HEAD revisto `d50e946`

Data: 23/11/2026.

Legenda: **FACTO** = medido ou executado; **INFERÊNCIA** = deduzido do código. Correcção aplicada nesta revisão: R-11 (ver §2).

## 1. Estado verificado

- **PR #30:** Draft, base `develop` `9e22f6a` (P3A integrado), head `d50e946`. `develop` está contido no branch: sem conflitos.
- **CI no head:** 5/5 success, a saber WORK-05 `product` (run 45154911708) e foundation `launcher`, `lab-tests`, `runner-capacity`, `windows-compat` (run 45154911933).
- **Pin, `main` e PR #27:** pin `f21d902` (inalterado), `main` `0cac8e8`, PR #27 intacta.
- **Frontend original no pin** (nunca tinha sido corrido): `tsc -b` termina com rc 0, e `vitest` passa com 23 ficheiros e 117 testes. Isto testa só código upstream, porque a PR não tem código frontend próprio.
- **Testes Python:** suite completa 681 OK, 0 skipped, já com o teste R-11 novo.

## 2. Riscos concretos

| ID | Área | Severidade | Evidência | Estado / recomendação |
|---|---|---|---|---|
| R-1 | Autorização | **Alta** fora do modo local | O código de uso único é devolvido na resposta HTTP a quem fez `/tarefa`. Qualquer cliente com acesso à API (outro processo ou utilizador local; no futuro, qualquer utilizador autenticado no host HTTPS) pode pedir e autorizar a sua própria tarefa (INFERÊNCIA, pelo fluxo do código). Na consola o modelo de confiança é o mesmo, mas lá o terminal é o operador. | Aceitável **só** para um operador único em loopback. Antes de qualquer acesso não-local: código entregue fora da banda (consola do anfitrião ou dispositivo do operador) **ou** sessão autenticada do operador. Decisão do operador. |
| R-2 | Autenticação | **Alta** fora do modo local | Não há autenticação nem token CSRF. A protecção é o bind em loopback, o Host em loopback, o Origin no POST e o CSP (FACTO, testes). Num host multi-utilizador, qualquer utilizador local chega à API. | Antes do B6: token de sessão local emitido pelo launcher (cookie `HttpOnly; SameSite=Strict`) e verificado pela PolicyApp. Bloqueante para o B6. |
| R-3 | Concorrência | Média | **FACTO**: duas conversas simultâneas são servidas em série (0,77 s e 1,44 s). O adaptador tem um único lock por modelo. | Aceitável para um operador. UI-02: fila visível ("a aguardar o modelo") e limite por conversa. |
| R-4 | Cancelamento e desconexão | **Média-alta** | **FACTO**: um pedido longo cancelado pelo cliente continua a gerar até ao fim (16,29 s), e um pedido curto **de outra conversa** esperou 13,97 s em vez de 0,65 s. O botão "Stop" da GUI não pára o modelo, e um `TIMEOUT` deixa a geração órfã a ocupar o lock. | Corrigir em UI-02 (backend): propagar a desconexão para `facade.cancel` e o cancelamento para o adaptador, fechando o pedido HTTP ao Ollama. Hoje o modelo pode bloquear-se até 240 s. |
| R-5 | Sessões | Média | A continuidade depende de a GUI devolver **exactamente** o texto de assistente emitido (hash do transcript). Se o frontend normalizar o texto, a conversa perde o contexto em silêncio (sessão nova). Funciona nos testes de browser (FACTO). Limites do facade: 6 trocas, 6000 caracteres de contexto, 2048 caracteres de entrada. | UI-02: id de conversa explícito, emitido pela bridge e devolvido pela GUI, e aviso visível de contexto truncado. |
| R-6 | Estado de tarefa | Média | O ControlPlane é global: `/estado` e `/cancelar` de qualquer conversa ou separador actuam sobre a mesma tarefa, e o resultado anterior é substituído. | Aceitável para um operador. UI-02: painel de missões único e explícito (não por conversa) e histórico de missões em memória. |
| R-7 | Desempenho | **Alta** para missões goose na mesma máquina | **FACTO** (ver `GOOSE_GUI_PERF_INVESTIGATION.md`): com a GUI original aberta num browser sem GPU, o browser consome 1,3–2,4 núcleos e a geração do 4B cai de 4,6 para 1,0 tokens/s. | UI-02: orçamento de CPU para a interface (sem animação contínua durante a inferência; respeitar `prefers-reduced-motion`) e `num_thread = núcleos − 1` para o Ollama da missão. Não bloqueia o merge da conversa e do P1. **Bloqueia declarar o goose pela GUI como concluído.** |
| R-8 | Páginas upstream | Média (UX) | Data Sources, Agents, Settings e Dashboard mostram funções não integradas, cujas chamadas recebem 403. Há um modal de opt-in na primeira visita, e a UI está em inglês (FACTO). | UI-02: overlay RIGHTWARE (§ plano). |
| R-9 | Testes | Média | Os testes de browser (`labs/ui01/gui_e2e.mjs`) não correm na CI. Os testes do frontend original não estão na CI. | UI-02: job de frontend (build, vitest dos componentes RIGHTWARE, verificação de deriva do overlay) e E2E reduzido. Exige decisão sobre a alteração de workflows. |
| R-10 | Auditoria | Baixa | `audit.jsonl` cresce sem rotação. | Rotação por tamanho (UI-02 ou B6). |
| R-11 | Recurso (DoS local) | Média | A bridge continuava a acumular o corpo depois de exceder 256 KB, sem limite de memória (FACTO, leitura do código). | **Corrigido nesta revisão**: o excesso é drenado, não guardado. Teste `test_oversized_body_is_drained_not_buffered`. |
| R-12 | Service worker | Baixa | O PWA (workbox) faz cache da UI e pode servir uma versão antiga depois de uma actualização (INFERÊNCIA). | UI-02: desactivar o registo do SW no overlay ou versionar o cache. |
| R-13 | Cadeia de build | Baixa | `npx npm@11.19.0` e o backend de build do vendor não estão fixados por hash (o `package-lock` e o `uv.lock` estão). | Fica para o P3B ou para um pacote de build. |

## 3. Recomendação

**Merge da PR #30 em `develop`: RECOMENDADO como base UI-01 para uso local de um único operador**, com os limites de R-1 a R-8 documentados. Isso cobre:
- conversa real PT/EN;
- tarefa P1 verificada pela GUI;
- política deny-by-default provada;
- startup limpo;
- correcção R-11;
- CI verde.

O merge **não** declara a missão goose pela GUI concluída. Ela continua **PARCIAL/FALHADA**: 4 tentativas pela GUI, nenhuma verificada, com a causa agora medida (R-7).

**Bloqueantes:**
- para qualquer acesso não-local (B6): R-1 e R-2;
- para declarar o goose pela GUI: R-7, mais uma corrida verificada com a mitigação.

O merge exige a aprovação explícita do operador. Esta revisão não faz merge.
