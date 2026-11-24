"""python -m rightware.gui setup|serve|check (UI-01). See rightware/gui/server.py."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m rightware.gui", description="JARVIS — interface gráfica (OpenJarvis "
                                "original) sobre o runtime RIGHTWARE, só em 127.0.0.1")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="prepara .runtime/gui a partir do pin (venv isolado + build do frontend original)")
    sub.add_parser("check", help="mostra o manifesto do runtime preparado")
    sub.add_parser("frontend-check", help="TypeScript + Vitest do overlay HUD sobre o frontend do pin")
    s = sub.add_parser("serve", help="arranca a interface em http://127.0.0.1:PORT/")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--model", action="append", default=[],
                   help="modelo Ollama local permitido (repetível; o primeiro é o predefinido)")
    s.add_argument("--deadline", type=float, default=240.0, help="limite por resposta, em segundos (1–300)")
    s.add_argument("--tarefa-ensaio", action="store_true", help="ANFITRIÃO: activa a comparação sintética P1")
    s.add_argument("--missao-goose", action="store_true", help="ANFITRIÃO: activa a missão goose sintética (Docker)")
    s.add_argument("--goose-bin", type=Path)
    s.add_argument("--goose-ollama-dir", type=Path)
    s.add_argument("--goose-models-dir", type=Path)
    s.add_argument("--goose-model", default="qwen3.5:4b")
    s.add_argument("--public-origin", help="B6: origem HTTPS exacta de um túnel privado autenticado (ex.: "
                   "https://<id>-8000.euw.devtunnels.ms); activa o modo de acesso privado temporário")
    s.add_argument("--public-minutes", type=float, default=60.0, help="B6: duração máxima do acesso privado (1–60)")
    s.add_argument("--ambiente", choices=("cloud", "local", "unknown"), default="unknown",
                   help="OP01: onde este servidor corre (declarado pelo anfitrião; o JARVIS di-lo com verdade)")
    s.add_argument("--pesquisa-sites", default="",
                   help="OP01 ANFITRIÃO: hosts EXACTOS (separados por vírgula) que a ferramenta de pesquisa pode ler; "
                        "exige --pesquisa-autorizacao")
    s.add_argument("--pesquisa-modelo", default="",
                   help="OP01: URL de pesquisa com {q} (ex.: https://host/search?q={q}), dentro de --pesquisa-sites")
    s.add_argument("--pesquisa-entradas", default="",
                   help="OP01: páginas https de entrada (separadas por vírgula), dentro de --pesquisa-sites")
    s.add_argument("--pesquisa-autorizacao", default="", help="OP01: referência da autorização de rede do operador")
    a = p.parse_args(argv)
    from rightware.gui import runtime as R
    if a.cmd == "setup":
        print(json.dumps(R.setup(), indent=2))
        return 0
    if a.cmd == "frontend-check":
        res = R.frontend_check()
        for name, r in res.items():
            print(f"== {name}: rc={r['rc']}\n{r['tail']}")
        return 0 if all(r["rc"] == 0 for r in res.values()) else 1
    if a.cmd == "check":
        m = R.paths()["manifest"]
        if not m.is_file():
            print("Runtime da interface não preparado: corra `python -m rightware.gui setup`.", file=sys.stderr)
            return 2
        print(m.read_text())
        return 0
    if not 1024 <= a.port <= 65535 or not 1.0 <= a.deadline <= 300.0:
        p.error("porta 1024–65535 e --deadline 1–300")
    if not R.paths()["static"].joinpath("index.html").is_file():
        print("Runtime da interface não preparado: corra `python -m rightware.gui setup`.", file=sys.stderr)
        return 2
    if a.public_origin is not None and (a.missao_goose or not 1 <= a.public_minutes <= 60):
        p.error("modo de acesso privado: sem --missao-goose e --public-minutes entre 1 e 60")
    goose = None
    if a.missao_goose:
        if not (a.goose_bin and a.goose_ollama_dir and a.goose_models_dir):
            p.error("--missao-goose exige --goose-bin, --goose-ollama-dir e --goose-models-dir (anfitrião)")
        from rightware.goose_adapter import GooseMission, GooseRuntime
        goose = GooseMission(GooseRuntime(a.goose_bin, a.goose_ollama_dir, a.goose_models_dir, a.goose_model))
    sites, fetcher, label, entries = (), None, "", ()
    if a.pesquisa_sites:
        if not a.pesquisa_autorizacao.strip():
            p.error("--pesquisa-sites exige --pesquisa-autorizacao (autorização de rede específica do operador)")
        sites = tuple(h.strip().lower() for h in a.pesquisa_sites.split(",") if h.strip())
        if not sites or any(not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", h) for h in sites):
            p.error("--pesquisa-sites: só hosts exactos (sem esquema, porta, caminho ou wildcard)")
        entries = tuple(u.strip() for u in a.pesquisa_entradas.split(",") if u.strip())
        if any(not u.startswith("https://") or u.split("/")[2].lower() not in sites for u in entries):
            p.error("--pesquisa-entradas: https e dentro de --pesquisa-sites")
        if a.pesquisa_modelo and not (a.pesquisa_modelo.startswith("https://") and "{q}" in a.pesquisa_modelo
                                      and a.pesquisa_modelo.split("/")[2].lower() in sites):
            p.error("--pesquisa-modelo: https, com {q}, num host de --pesquisa-sites")
    from rightware.gui.server import build_app, serve
    app, _ = build_app(port=a.port, models=a.model or ["qwen3.5:2b"], deadline=a.deadline, trial=a.tarefa_ensaio,
                       goose=goose, public_origin=a.public_origin,
                       public_minutes=a.public_minutes if a.public_origin else None, environment=a.ambiente,
                       tool_sites=sites, browser_fetcher=fetcher, tool_label=label,
                       tool_search_template=a.pesquisa_modelo if sites else "",
                       tool_entry_urls=entries if sites else ())
    if sites:
        print(f"OP01: pesquisa activada só para {', '.join(sites)}"
              + (f" (autorização {a.pesquisa_autorizacao})" if a.pesquisa_autorizacao else f" [{label}]"), flush=True)
    print("JARVIS (RIGHTWARE JARVIS HUD sobre a interface OpenJarvis original), só em 127.0.0.1.", flush=True)
    if a.public_origin:                          # never print the login link: it would land in logs
        import time
        print(f"ACESSO PRIVADO B6 activo para {a.public_origin} até "
              f"{time.strftime('%H:%M:%S UTC', time.gmtime(app.public_until))}. Ligação de uso único (15 min) em "
              f"{R.paths()['runtime'] / 'session-url'} (0600); não é impressa.", flush=True)
    else:
        print(f"Abra esta ligação de sessão local (uso pelo operador; não partilhar): {app.session_url}", flush=True)
    serve(app, a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
