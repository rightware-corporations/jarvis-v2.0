"""python -m rightware.gui setup|serve|check (UI-01). See rightware/gui/server.py."""
from __future__ import annotations

import argparse
import json
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
    s.add_argument("--missao-pesquisa", action="store_true",
                   help="ANFITRIÃO: activa a pesquisa pública de leitura WEB-01 (modo fixture, sem rede)")
    s.add_argument("--pesquisa-modelo", help="ANFITRIÃO: modelo local do planeador/síntese W3.1 (predefinido: o 1.º)")
    s.add_argument("--pesquisa-politica", type=Path,
                   help="ANFITRIÃO: política de egress WEB-01 (ex.: configs/web01/egress.public.json, W3 autorizado)")
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
    goose = None
    if a.missao_goose:
        if not (a.goose_bin and a.goose_ollama_dir and a.goose_models_dir):
            p.error("--missao-goose exige --goose-bin, --goose-ollama-dir e --goose-models-dir (anfitrião)")
        from rightware.goose_adapter import GooseMission, GooseRuntime
        goose = GooseMission(GooseRuntime(a.goose_bin, a.goose_ollama_dir, a.goose_models_dir, a.goose_model))
    missions = []
    if a.missao_pesquisa:
        from rightware.web01.mission import ResearchMission
        from rightware.web01.egress import EgressPolicy
        policy = EgressPolicy.load(a.pesquisa_politica) if a.pesquisa_politica else None
        missions.append(ResearchMission(policy))  # refuses at start-up unless fixture or W3-authorised policy
        from rightware.web01.free_research import FreeResearchMission
        missions.append(FreeResearchMission(policy, model=a.pesquisa_modelo or (a.model or ["qwen3.5:2b"])[0]))
    from rightware.gui.server import build_app, serve
    app, _ = build_app(port=a.port, models=a.model or ["qwen3.5:2b"], deadline=a.deadline, trial=a.tarefa_ensaio,
                       goose=goose, missions=missions)
    print("JARVIS (RIGHTWARE JARVIS HUD sobre a interface OpenJarvis original), só em 127.0.0.1.", flush=True)
    print(f"Abra esta ligação de sessão local (uso pelo operador; não partilhar): {app.session_url}", flush=True)
    serve(app, a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
