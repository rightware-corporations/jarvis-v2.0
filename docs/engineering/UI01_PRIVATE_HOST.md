# UI-01 B6 — preparação de um host privado HTTPS (só preparação; nada instalado, publicado ou aberto)

**Estado:** especificação. Não existe infraestrutura persistente autorizada. Nada deste documento foi instalado em computadores de terceiros, e não foi aberto nenhum túnel nem porta pública. A execução verificada é a do ambiente de engenharia em `127.0.0.1` (ver `UI01_OPENJARVIS_GUI.md` §8).

## 1. Topologia alvo

```
utilizador (browser) ──HTTPS + autenticação──> reverse proxy (TLS)  ──http://127.0.0.1:8000──> JARVIS GUI
                                                                       (rightware.gui serve, loopback only)
                                                                    ──> Ollama 127.0.0.1:11434 (mesma máquina)
```

- O processo JARVIS continua a escutar **só** em `127.0.0.1`. O reverse proxy é o único ponto exposto, e só numa rede privada ou VPN da organização.
- A política RIGHTWARE exige que o `Host` seja `127.0.0.1:PORT` ou `localhost:PORT`. O proxy tem de **reescrever o Host** para `127.0.0.1:8000` e **não** encaminhar o `Origin` externo. Em alternativa, numa alteração própria e testada, acrescenta-se o hostname privado à lista de hosts e origens da política. Nunca usar `*`.

## 2. Configuração (variáveis sem valores)

| Variável / ficheiro | Finalidade |
|---|---|
| `configs/gui/openjarvis-gui.toml` | Configuração do OpenJarvis (sem agente, telemetria, traces nem analytics); copiada para `.runtime/gui/home/config.toml` |
| `JARVIS_GUI_PORT` | Porta em loopback (por omissão 8000) |
| `JARVIS_GUI_MODELS` | Modelos permitidos, por ordem (o primeiro é o predefinido) |
| `JARVIS_GUI_DEADLINE` | Limite por resposta, em segundos (por omissão 240) |
| `JARVIS_TASKS` | Capacidades activadas pelo anfitrião (`--tarefa-ensaio`, `--missao-goose` e os caminhos goose) |
| `OLLAMA_HOST=127.0.0.1:11434`, `OLLAMA_MODELS` | Motor local |
| Credenciais do proxy (utilizadores, hashes) | **Fora do repositório**, num cofre do host |

## 3. Serviço supervisionado (modelo de unidade systemd; não instalado)

```ini
[Unit]
Description=JARVIS GUI (RIGHTWARE runtime, loopback)
After=network-online.target ollama.service
[Service]
User=jarvis
WorkingDirectory=/opt/jarvis-v2.0
Environment=PYTHONPATH=/opt/jarvis-v2.0 NO_PROXY=127.0.0.1,localhost
ExecStart=/opt/jarvis-v2.0/.runtime/gui/venv/bin/python -m rightware.gui serve --port 8000 --model qwen3.5:4b
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/jarvis-v2.0/.runtime
PrivateTmp=true
ProtectHome=true
[Install]
WantedBy=multi-user.target
```

## 4. Reverse proxy com TLS e autenticação (exemplo nginx; não instalado)

```nginx
server {
  listen 443 ssl; server_name jarvis.<rede-privada>;
  ssl_certificate /etc/ssl/<cert>; ssl_certificate_key /etc/ssl/<key>;   # CA interna ou ACME privado
  auth_basic "JARVIS"; auth_basic_user_file /etc/nginx/jarvis.htpasswd;    # ou SSO/OIDC da organização
  client_max_body_size 256k; limit_req zone=jarvis burst=10;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host 127.0.0.1:8000;
               proxy_set_header Origin ""; proxy_buffering off; proxy_read_timeout 600s; }
}
```

O SSE das respostas exige `proxy_buffering off` e um timeout maior do que o `--deadline`.

## 5. Limites, backup e observabilidade

- **Limites:**
  - uma tarefa supervisionada de cada vez (ControlPlane);
  - pedidos de 256 KB no máximo;
  - 64 mensagens por pedido;
  - 12 sessões de conversa no máximo (LRU);
  - rate limit no proxy.
- **Backup:** não há dados persistentes de conversa. As sessões são efémeras, por directiva. Faz-se backup apenas da configuração e de `.runtime/gui/audit.jsonl` (registo de decisões, sem conteúdo de conversas). Não se faz backup de modelos nem de evidência pessoal.
- **Observabilidade:**
  - `audit.jsonl`: decisões ALLOW/DENY/ANSWER com o id `rw-…`, tempos e códigos;
  - `serve.log`;
  - `GET /health` (estado do motor) como sonda de vida no proxy.
- **Arranque automático:** a unidade da §3 com `Restart=on-failure`. O `python -m rightware.gui setup` é corrido só em deploy controlado, porque descarrega dependências do lock.

## 6. Checklist de segurança antes de qualquer exposição

1. O processo JARVIS escuta só em `127.0.0.1` (`ss -ltn`).
2. TLS válido, autenticação obrigatória, sem acesso anónimo.
3. Exposição só em rede privada ou VPN; nenhum DNS público; nenhum túnel.
4. O proxy reescreve `Host` e remove `Origin` externos. A política RIGHTWARE devolve 403 a qualquer outro host.
5. `bash labs/ui01/start_and_verify.sh` passa no host.
6. `labs/ui01/startup_audit.py` está limpo no host: sem tráfego de saída, sem processos-filho, sem escritas fora de `.runtime`.
7. Nenhuma credencial no repositório. Credenciais do proxy guardadas no cofre do host.
8. Missões goose só com Docker local e a imagem verificada da Gateway (P3A).
9. Decisão escrita do operador antes de abrir o acesso, incluindo quem acede e onde.
