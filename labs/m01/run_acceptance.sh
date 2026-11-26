#!/usr/bin/env bash
# JRV-M01 real-model acceptance: every step is a NEW process and a NEW conversation; synthetic owners only.
# Usage: bash labs/m01/run_acceptance.sh <out.jsonl> <db-file>
set -euo pipefail
OUT=$1; DB=$2
PY=.runtime/gui/venv/bin/python
rm -f "$OUT" "$DB" "$DB-wal" "$DB-shm"
s() { $PY -m labs.m01.acceptance --db "$DB" --out "$OUT" --step "$1" --owner "$2" --say "$3"; }
Q="Vou preparar o relatório mensal de vendas. Em que moeda o devo apresentar?"
s 1-ensinar      lab:alfa "JARVIS, prefiro que os meus relatórios sejam apresentados em meticais. Lembra-te disto."
s 2-nova-conversa lab:alfa "$Q"
s 9a-isolamento  lab:beta "O que sabes sobre mim? Em que moeda prefiro os meus relatórios?"
echo "--- reinício completo: os passos seguintes correm em processos novos; o Ollama é reiniciado ---"
pkill -f "ollama serve" || true; sleep 3; bash "${OLLAMA_UP:?}"
s 4-apos-reinicio lab:alfa "$Q"
s 5-corrigir     lab:alfa "Corrige a informação que guardaste: afinal prefiro que os meus relatórios sejam apresentados em dólares americanos."
s 6-confirmar    lab:alfa "$Q"
s 7-eliminar     lab:alfa "Esquece a minha preferência sobre a moeda dos relatórios."
s 8-confirmar-eliminacao lab:alfa "O que sabes sobre mim? Em que moeda prefiro os meus relatórios?"
s 9b-isolamento  lab:beta "O que sabes sobre mim?"
