#!/usr/bin/env bash
# UI-01: start the JARVIS GUI (original OpenJarvis interface on the RIGHTWARE runtime) on 127.0.0.1 and verify it.
# Usage: bash labs/ui01/start_and_verify.sh [PORT] [extra `serve` flags, e.g. --tarefa-ensaio]
# Requires: python jarvis.py gui setup (once), Ollama on 127.0.0.1:11434 with the configured models.
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT="${1:-8000}"; shift || true
PY=.runtime/gui/venv/bin/python
[ -x "$PY" ] || { echo "Runtime não preparado: python jarvis.py gui setup"; exit 2; }
curl -s --noproxy '*' -m 3 http://127.0.0.1:11434/api/tags >/dev/null || echo "AVISO: Ollama não responde em 127.0.0.1:11434 (a interface mostrará erro explícito)."
PYTHONPATH="$PWD" NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  "$PY" -m rightware.gui serve --port "$PORT" "$@" > .runtime/gui/serve.log 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 1; done
fail=0
check() { local want="$1" method="$2" path="$3"; local got
  got=$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' -X "$method" -H 'Content-Type: application/json' \
        ${4:+-d "$4"} "http://127.0.0.1:$PORT$path"); [ "$got" = "$want" ] && echo "ok   $method $path -> $got" \
        || { echo "FAIL $method $path -> $got (esperado $want)"; fail=1; }; }
check 200 GET /
check 200 GET /v1/models
check 200 GET /v1/info
check 403 POST /v1/agents '{}'
check 403 POST /api/research '{}'
check 403 GET /v1/approvals/pending
check 403 POST /v1/chat/completions '{"messages":[{"role":"user","content":"x"}],"tools":[{}]}'
ss -ltn 2>/dev/null | grep ":$PORT " | grep -q "127.0.0.1:$PORT" && echo "ok   escuta só em 127.0.0.1:$PORT" || { echo "FAIL bind"; fail=1; }
echo "JARVIS: http://127.0.0.1:$PORT/   (PID $PID; parar: kill $PID)"
exit $fail
