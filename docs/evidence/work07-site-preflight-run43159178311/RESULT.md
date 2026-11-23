# WORK-07 Fase 4 — Evidência real, request_id 3

**Veredicto: READY / ACEITE**, sem modelo. Este teste comprova o funcionamento do navegador semântico no website real, não a autonomia do Qwen.

- Run: https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43159178311
- Run attempt: 1
- Artefacto original: https://github.com/rightware-corporations/jarvis-v2.0/actions/runs/43159178311/artifacts/13916523822
- Código aprovado: `2db6df5d183df3a171d29b15982b351285fbc67e`
- Commit de autorização: `756d0d504599109c009100c036b856c8b6cabc4d`
- Plano SHA256: `b0e4ac7849b7ad14d19ca4c61da7f0929fa1ef351c5b0a5f633419eba6178ef4`
- Execução técnica: `COMPLETED`, exit 0
- Aceitação: `READY`, `accepted=true`, `reasons=[]`
- Authorisation: `ok=true`, problemas `[]`; Qwen não foi executado (`models_called=false`).
- Pedidos reais: 7 GET, todos HTTP 200, todos para `www.rfc-editor.org` (ligação TCP `104.18.20.81:443`).
- Documento RFC 9110: `https://www.rfc-editor.org/rfc/rfc9110.txt`, HTTP 200, título `RFC 9110: HTTP Semantics`, `validated=true`.
- Documento RFC 9112: `https://www.rfc-editor.org/rfc/rfc9112.txt`, HTTP 200, título `RFC 9112: HTTP/1.1`, `validated=true`.
- Ambos os documentos foram truncados ao limite da vista; não invalida a verificação de título/URL nesta tarefa.
- Os parâmetros `x-typesense-api-key` aparecem como `REDACTED` na evidência examinada.
- ZIP SHA256: `f00894211b1741d87d9095709e2df2e882669568d1aaba58e305bcb9d954416e`; corresponde ao digest GitHub.
- Verificação interna de integridade: **8/8 ficheiros conferem com SHA256SUMS**.
- Retenção do ZIP original: 30 dias pelo GitHub Actions. Este documento é um índice persistente; não substitui o arquivo original.

**Histórico preservado:** request_id 1 e 2 resultaram NOT_READY; request_id 3 READY. O pedido 3 foi consumido.

**Seguinte:** Fase 5 — Qwen3.5:4b real, exige autorização nova, separada e explícita. Não confundir o preflight determinístico com validação de decisões autónomas do Qwen.
