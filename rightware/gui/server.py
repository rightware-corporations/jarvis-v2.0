"""UI-01: assemble and run the GUI process — original OpenJarvis app + original frontend behind RIGHTWARE.

    .runtime/gui/venv/bin/python -m rightware.gui serve [--port 8000] [--model qwen3.5:2b] [--tarefa-ensaio]
        [--missao-goose --goose-bin B --goose-ollama-dir O --goose-models-dir D]

Layers, outermost first: ``PolicyApp`` (deny-by-default, loopback only) → either the ORIGINAL OpenJarvis FastAPI
app built by ``openjarvis.server.app.create_app`` (only its allowlisted read routes are reachable) or the
RIGHTWARE ``ChatBridge`` (conversation + Control Plane). The original app is built WITHOUT agent, scheduler,
channel bridge, memory, speech, MCP or webhooks, with telemetry/traces/analytics off, and the CLI's version check
is never run (we never go through ``jarvis serve``). Bound to 127.0.0.1 only.
"""
from __future__ import annotations

import os
from pathlib import Path

from rightware.gui.bridge import ChatBridge
from rightware.gui.policy import AuditLog, PolicyApp
from rightware.gui.runtime import paths

LOOPBACK = "127.0.0.1"


def build_inner(model: str, home: Path):
    """The original OpenJarvis application with every effect-capable component absent."""
    os.environ["OPENJARVIS_HOME"] = str(home)
    from openjarvis.core.config import load_config
    from openjarvis.engine.ollama import OllamaEngine
    from openjarvis.server.app import create_app

    config = load_config(home / "config.toml")
    for section, attr in (("telemetry", "enabled"), ("traces", "enabled"), ("analytics", "enabled")):
        if getattr(getattr(config, section), attr):
            raise RuntimeError(f"GUI_CONFIG_UNSAFE: {section}.{attr}")
    if config.server.agent:
        raise RuntimeError("GUI_CONFIG_UNSAFE: server.agent")
    engine = OllamaEngine(host=config.engine.ollama.host)
    return create_app(engine, model, agent=None, engine_name="ollama", agent_name="", config=config,
                      channel_bridge=None, memory_backend=None, speech_backend=None, agent_manager=None,
                      agent_scheduler=None, mcp_tools=None, mcp_clients=None, webhook_config=None,
                      cors_origins=[])


def build_entries(models: list[str], deadline: float, adapter_factory=None) -> dict:
    from rightware.console import build
    return {m: build(m, adapter_factory(m) if adapter_factory else None, deadline) for m in models}


def build_app(*, port: int, models: list[str], deadline: float = 240.0, trial: bool = False, goose=None,
              runtime: Path | None = None, inner=None, adapter_factory=None, session_factory_builder=None):
    p = paths(runtime) if runtime is not None else paths()
    audit = AuditLog(p["audit"])
    entries = build_entries(models, deadline, adapter_factory)
    control = None
    if trial or goose is not None or session_factory_builder is not None:
        from rightware.control_plane import ControlPlane
        control = ControlPlane(entries[models[0]].text_facade, enable_trial_compare=trial or
                               session_factory_builder is not None, model=models[0],
                               session_factory_builder=session_factory_builder, goose=goose)
        entries[models[0]] = control.entry
    bridge = ChatBridge(entries=entries, default_model=models[0], control=control, audit=audit)
    inner = inner if inner is not None else build_inner(models[0], p["home"])
    return PolicyApp(inner=inner, bridge=bridge, static_dir=p["static"], port=port, audit=audit), bridge


def serve(app, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host=LOOPBACK, port=port, log_level="info", access_log=False, proxy_headers=False,
                server_header=False, ws="none", lifespan="on")
