# B6 — Procedimento exacto do túnel HTTPS privado (para a apresentação)

Estado: **preparado; túnel NÃO aberto.** A abertura só ocorre por instrução posterior do operador. Data: 24/11/2026.
Ferramenta: Microsoft Dev Tunnels CLI 1.0.2115 (gratuita, sem contas novas, sem despesas). Login com a conta Microsoft
do operador, por device code. Um túnel privado tem `Access control: {}`: só o dono entra, e o pedido anónimo
recebe um 302 para o login Microsoft.

## Garantias preservadas
| Requisito | Como |
|---|---|
| Autenticação obrigatória | 1.º Dev Tunnels privado (identidade Microsoft do dono antes da app). 2.º B6: sessão exigida em todas as rotas, estáticos incluídos |
| Código de acesso de uso único | Ligação `/rw-login?t=` de uso único, válida 15 min, escrita só em `.runtime/gui/session-url` (0600), nunca impressa nem colada em logs ou chat |
| Máximo 60 min | Túnel `--expiration 1h` + `timeout 3540` no host + prazo B6 `--public-minutes ≤ 58` (`PUBLIC_ACCESS_EXPIRED` revoga todas as sessões) |
| Ollama só em loopback | `OLLAMA_HOST=127.0.0.1:11434`; verificar com `/proc/net/tcp` antes de abrir |
| Só a porta da UI | `devtunnel port create -p 8000` (única porta); nunca 11434, Docker ou SSH |
| Sem acesso anónimo | Túnel sem `--allow-anonymous`; B6 recusa sem sessão (401) e Host/Origin errados (403) |

## Passos (executar só após a instrução "ABRIR_TUNEL")
```bash
DT=<scratchpad>/b6/cli/devtunnel
$DT user login -d                       # o operador introduz o código em login.microsoft.com/device
$DT create --expiration 1h --json       # anotar o tunnelId (sem --allow-anonymous)
$DT port create <tunnelId> -p 8000
$DT update <tunnelId> --origin-header unchanged --host-header unchanged   # OBRIGATÓRIO (ver abaixo)
$DT show <tunnelId>                      # confirmar "Host request header: unchanged" e "Origin request header: unchanged"
                                         # e usar o URL REAL indicado (não deduzir o cluster)
```
**Porque é obrigatório (FACTO, 24/11/2026):**
- Por omissão, o Dev Tunnels **reescreve** o `Origin` para `http(s)://localhost` e o `Host` para `localhost` antes de entregar o pedido ao anfitrião.
- O B6 exige um Origin exacto em pedidos que alteram estado. Com a reescrita, todos os `POST /v1/chat/completions` foram recusados pela política RIGHTWARE com `CROSS_ORIGIN`, e o browser mostrou `Chat request failed: 403`. Os GET funcionavam.
- Passar `--origin-header/--host-header` só ao `devtunnel host` **não teve efeito** (medido). A configuração tem de ser **persistente no túnel** (`devtunnel update`), como em microsoft/dev-tunnels#284; depois, reiniciar o `host`.
- Isto não relaxa nenhuma protecção: o JARVIS passa a receber os cabeçalhos **reais** do browser e continua a compará-los exactamente com a origem configurada. Sem wildcards e sem confiar em cabeçalhos `X-Forwarded-*`.
1. Verificar: Ollama só em 127.0.0.1, sem nenhum processo na porta 8000.
2. Arrancar o JARVIS em modo B6 com a origem exacta:
   `.runtime/gui/venv/bin/python -m rightware.gui serve --port 8000 --model qwen3.5:2b --public-origin https://<tunnelId>-8000.<cluster>.devtunnels.ms --public-minutes 58`
3. Expor: `timeout --kill-after=10 3540 $DT host <tunnelId>`.
4. Verificação externa anónima: `curl -sI https://<url>/` deve dar **302 para o login Microsoft** (nunca 200).
4b. Validação em duas fases (24/11):
   - Primeiro, o operador abre o URL base **sem token**. Tem de passar o login Microsoft e ver "Sessão local necessária". O audit regista `AUTH_REQUIRED`, o que prova que o pedido chegou ao JARVIS.
   - Só depois se gera a ligação de uso único.
   - Uma ligação gerada no arranque expira em 15 min. Para emitir uma nova, reinicia-se o JARVIS com `--public-minutes` ajustado ao fim do túnel.
5. Entregar a ligação de uso único ao operador **fora do chat e de capturas** (o operador lê o ficheiro localmente
   ou pelo método privado combinado). Na apresentação: entra o operador (conta Microsoft dona do túnel) e depois a ligação.

## Fecho (instrução "FECHAR_TUNEL" ou fim dos 60 min)
```bash
pkill -f "devtunnel host"; pkill -f "rightware.gui serve"
$DT delete <tunnelId> -f
$DT user logout && rm -rf /root/.local/share/DevTunnels
rm -f .runtime/gui/session-url
```
Verificar: o URL antigo deixa de responder (404 ou erro de túnel inexistente), e `devtunnel user show` mostra "Not logged in".

## Limites honestos
- Quem vê a HUD tem de usar a conta Microsoft dona do túnel. O túnel privado não suporta convidados anónimos, por desenho.
- O modelo continua NÃO verificado nas respostas livres. Pesquisa pública (WEB-01), voz, memória, finanças e Windows **não** fazem parte desta versão.

## Registo da janela de 24/11/2026 (apresentação) — FACTO
- Túnel privado `silent-ant-n61dpz7.use` (`use`), só a porta 8000, `Access control: {}`, expiração de 1 h. Hosting iniciado às 15:21:20 UTC, com limite rígido às 16:19:50 UTC. JARVIS em B6 com `--public-origin https://24thldvf-8000.use.devtunnels.ms`, prazo às 16:16:59 UTC.
- Anónimo: 302 → `login.microsoftonline.com`; 0 pedidos anónimos no JARVIS. A porta 11434 não está exposta (404). Ollama e JARVIS escutam só em 127.0.0.1.
- Fase 1 (sem token): o operador passou o login Microsoft; o audit regista `GET / DENY AUTH_REQUIRED` às 15:28–15:29 UTC.
- Fase 2: ligação de uso único entregue em privado ao operador. A HUD abriu.
- **Falha:** `POST /v1/chat/completions` → `DENY CROSS_ORIGIN` às 15:32:24, 15:32:42, 15:35:41 e 15:36:14 UTC. A opção só no `host` não resolveu.
- **Correcção:** `devtunnel update <id> --origin-header unchanged --host-header unchanged`; depois, reiniciar o `host`. O JARVIS não foi reiniciado e a sessão manteve-se.
- **Evidência após a correcção:** um observador de loopback, que regista só Host e Origin, viu às 15:39:50 UTC `POST /v1/chat/completions Host=24thldvf-8000.use.devtunnels.ms Origin=https://24thldvf-8000.use.devtunnels.ms`. Audit: `ALLOW ALLOWLISTED` às 15:39:50, seguido de `ANSWER RESPOSTA_DO_MODELO qwen3.5:2b 17,2 s ANSWER_ONLY` às 15:40:07.
- **Confirmação do operador:** o Qwen respondeu através da HUD externa.
- **Inconsistência de identidade (por corrigir; não corrigida nesta sessão):**
  - Pela GUI, o modelo apresentou-se como "OpenJarvis", em inglês, em vez de RIGHTWARE JARVIS em português.
  - `configs/local.toml` define `default_system_prompt` com a identidade RIGHTWARE.
  - **Hipótese:** o percurso de chat da GUI (bridge → TextFacade → SimpleAgent) não aplica esse prompt, ou um prompt do frontend/servidor upstream tem precedência.
  - A causa exacta está por demonstrar. Já tinha sido observado em UI-02 como defeito conhecido.
