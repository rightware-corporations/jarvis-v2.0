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

from rightware.gui.auth import LocalAuth
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
              runtime: Path | None = None, inner=None, adapter_factory=None, session_factory_builder=None,
              auth: LocalAuth | None = None, static_dir: Path | None = None, public_origin: str | None = None,
              public_minutes: float | None = None, environment: str = "unknown", tool_sites: tuple[str, ...] = (),
              browser_fetcher=None, tool_label: str = "", tool_search_template: str = ""):
    p = paths(runtime) if runtime is not None else paths()
    audit = AuditLog(p["audit"])
    adapters: dict = {}
    if adapter_factory is None:                   # OP01: every GUI model gets the host-built JARVIS persona
        from rightware.persona import RuntimeFacts, system_prompt
        tools = (("pesquisa e leitura de páginas web nas fontes autorizadas" + (f" ({tool_label})" if tool_label else ""),)
                 if tool_sites else ())

        def adapter_factory(m):
            prompt = system_prompt(RuntimeFacts(model=m, environment=environment, tools=tools, sites=tuple(tool_sites),
                                                search_template=tool_search_template))
            if tool_sites:
                from rightware.assistant_tools import ToolChatAdapter
                adapters[m] = ToolChatAdapter(m, sites=tuple(tool_sites), persona=prompt, browser_fetcher=browser_fetcher,
                                              timeout_seconds=deadline,
                                              search_template=tool_search_template or None)
            else:
                from rightware.text_adapter import LocalSimpleTextAdapter
                adapters[m] = LocalSimpleTextAdapter(m, timeout_seconds=min(deadline, 300.0), system_prompt=prompt)
            return adapters[m]
    entries = build_entries(models, deadline, adapter_factory)
    control = None
    if trial or goose is not None or session_factory_builder is not None:
        from rightware.control_plane import ControlPlane
        control = ControlPlane(entries[models[0]].text_facade, enable_trial_compare=trial or
                               session_factory_builder is not None, model=models[0],
                               session_factory_builder=session_factory_builder, goose=goose)
        entries[models[0]] = control.entry
    bridge = ChatBridge(entries=entries, default_model=models[0], control=control, audit=audit)
    bridge.adapters = adapters                    # OP01: live activity of tool-using turns (HUD)
    inner = inner if inner is not None else build_inner(models[0], p["home"])
    public_until = None
    if public_origin is not None:                 # B6 private access: single-use link, expiring sessions and access
        if not (public_minutes and 1 <= public_minutes <= 60):
            raise ValueError("private access needs 1..60 minutes")
        import time as _time
        public_until = _time.time() + public_minutes * 60
        auth = auth or LocalAuth(single_use=True, token_ttl=15 * 60, session_ttl=public_minutes * 60,
                                 max_failures=20)
    auth = auth or LocalAuth()
    app = PolicyApp(inner=inner, bridge=bridge, static_dir=static_dir or p["static"], port=port, audit=audit,
                    auth=auth, public_origin=public_origin, public_until=public_until)
    app.public_until = public_until
    app.session_url = auth.write_url(p["runtime"] / "session-url", port, base=public_origin)
    return app, bridge


def serve(app, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host=LOOPBACK, port=port, log_level="info", access_log=False, proxy_headers=False,
                server_header=False, ws="none", lifespan="on")
