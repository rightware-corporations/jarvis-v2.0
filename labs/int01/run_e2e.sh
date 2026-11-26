#!/usr/bin/env bash
# JRV-INT01 integrated E2E: starts the integrated JARVIS (B6 private mode, voice, owners, documents, memory; offline
# finance replay; NO tunnel, NO network) + a local TLS front, then drives it with real Chromium. Synthetic data only.
# Usage: bash labs/int01/run_e2e.sh <workdir with cert.pem key.pem fala.wav> <out.json>
set -euo pipefail
W=$1; OUT=$2
PY=.runtime/gui/venv/bin/python
ORIGIN=https://jarvis-e2e.example
rm -f "$W"/mem.sqlite3* "$W"/docs.sqlite3*
$PY -c "from labs.k01.fixtures import make_pdf, REPORT_2025; open('$W/relatorio-anual-2025.pdf','wb').write(make_pdf(REPORT_2025))"
$PY -m labs.presentation.serve --offline --hoje 2026-11-26 --voz --port 8000 --public-origin "$ORIGIN" \
    --public-minutes 30 --donos operador=lab:operador,issa=lab:issa --documentos \
    --memoria-ficheiro "$W/mem.sqlite3" --documentos-ficheiro "$W/docs.sqlite3" > "$W/serve.log" 2>&1 &
SRV=$!
$PY -m labs.int01.tls_forward "$W/cert.pem" "$W/key.pem" 443 8000 > "$W/tls.log" 2>&1 &
TLS=$!
trap 'kill $SRV $TLS 2>/dev/null || true' EXIT
for i in $(seq 1 60); do curl -s --noproxy '*' -o /dev/null 127.0.0.1:8000/ && break; sleep 1; done
sleep 4   # voice preload
node labs/int01/e2e.mjs "$ORIGIN" "$W/fala.wav" "$W/relatorio-anual-2025.pdf" "$OUT" \
     "$PY -m rightware.gui emitir-ligacao issa"
