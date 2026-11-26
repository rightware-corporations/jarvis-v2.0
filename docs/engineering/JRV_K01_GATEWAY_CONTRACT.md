# JRV-K01 — Contrato de gateway para o upload de documentos (para o responsável do B6)

Estado: **PROPOSTA, não aplicada.** `rightware/gui/policy.py` e `rightware/gui/auth.py` pertencem à correcção B6 (Manus) e não foram alterados. Data: 26/11/2026.

## Porquê
- O gateway só despacha pares exactos (método, caminho) listados em `ALLOW`. Por isso o upload não tem rota.
- Não se usa o chat (`/v1/chat/completions`) para transportar ficheiros: seria contornar os limites e a política do gateway.

## Handlers prontos (não ligados)
`rightware/knowledge/http_api.py` (`handle(library, scope, receive, send)`), testados directamente:

| Método | Caminho | Corpo | Resposta |
|---|---|---|---|
| POST | `/v1/rightware/documents/upload` | Bytes do ficheiro; cabeçalho `X-Rightware-Filename` (só rótulo) | 200 `{status: OK\|DUPLICATE, document_id, name, kind, units, segments, injection_suspected}` / 422 `{status: REFUSED, reason}` / 413 |
| GET | `/v1/rightware/documents` | — | 200 `{documents: [...]}` (só os do dono) |
| POST | `/v1/rightware/documents/delete` | JSON `{"document_id": "d-…"}` | 200 / 404 |

O dono vem **sempre** do anfitrião (contrato de identidade M01), nunca do pedido.

## Alteração proposta em `rightware/gui/policy.py` (a aplicar pelo responsável do B6, se aprovada)
```python
ALLOW.update({
    ("POST", "/v1/rightware/documents/upload"): "bridge",
    ("GET", "/v1/rightware/documents"): "bridge",
    ("POST", "/v1/rightware/documents/delete"): "bridge",
})
BODY_LIMITS["/v1/rightware/documents/upload"] = 5 * 1024 * 1024
BODY_LIMITS["/v1/rightware/documents/delete"] = 1024
```
- **Rota activa só com documentos:** idealmente, como `VOICE_ALLOW`, estas entradas só valem quando o processo arranca com documentos activos.
- **Protecções que se mantêm:**
  - sessão B6 obrigatória;
  - `Origin` exacto nos POST;
  - CSP;
  - nenhum recurso externo.
- **Bridge:** depois disso, chama `http_api.handle` no `__call__` quando `(method, path)` está em `http_api.ROUTES` (alteração em `bridge.py`, fora dos ficheiros reservados, a fazer quando o contrato for aceite).

## Frontend (depois do contrato)
- Um botão "Anexar documento" junto ao microfone envia o ficheiro para a rota de upload.
- Mostra o resultado (aceite ou recusado, com o motivo) e a lista de documentos.
- Sem reformular a interface. Exige recompilar o frontend.

## Enquanto isso
O carregamento faz-se pelo anfitrião:

```bash
python -m rightware.knowledge add --owner lab:alfa FICHEIRO
```

As perguntas fazem-se na conversa normal do JARVIS (launcher com `--memoria-dono` e `--documentos`).
