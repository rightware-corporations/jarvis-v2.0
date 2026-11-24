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
$DT show <tunnelId>                      # usar o URL REAL indicado (não deduzir o cluster)
```
1. Verificar: Ollama só em 127.0.0.1, sem nenhum processo na porta 8000.
2. Arrancar o JARVIS em modo B6 com a origem exacta:
   `.runtime/gui/venv/bin/python -m rightware.gui serve --port 8000 --model qwen3.5:2b --public-origin https://<tunnelId>-8000.<cluster>.devtunnels.ms --public-minutes 58`
3. Expor: `timeout --kill-after=10 3540 $DT host <tunnelId>`.
4. Verificação externa anónima: `curl -sI https://<url>/` deve dar **302 para o login Microsoft** (nunca 200).
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
