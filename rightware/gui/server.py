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


def build_inner(model: str, home: Path, voice: bool = False):
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
    speech = None
    if voice:                                      # VOICE (opt-in): upstream STT backend + Kokoro TTS, local only
        from rightware.gui import voice as V
        speech = V.whisper_backend()
    app = create_app(engine, model, agent=None, engine_name="ollama", agent_name="", config=config,
                     channel_bridge=None, memory_backend=None, speech_backend=speech, agent_manager=None,
                     agent_scheduler=None, mcp_tools=None, mcp_clients=None, webhook_config=None,
                     cors_origins=[])
    if voice:
        app.state.tts_backend, app.state.tts_resolved = V.make_tts(), True
        V.preload(speech, app.state.tts_backend)          # models loaded before the first interaction
    return app


def build_entries(models: list[str], deadline: float, adapter_factory=None) -> dict:
    from rightware.console import build
    return {m: build(m, adapter_factory(m) if adapter_factory else None, deadline) for m in models}


def build_app(*, port: int, models: list[str], deadline: float = 240.0, trial: bool = False, goose=None,
              runtime: Path | None = None, inner=None, adapter_factory=None, session_factory_builder=None,
              auth: LocalAuth | None = None, static_dir: Path | None = None, public_origin: str | None = None,
              public_minutes: float | None = None, environment: str = "unknown", tool_sites: tuple[str, ...] = (),
              browser_fetcher=None, tool_label: str = "", tool_search_template: str = "",
              tool_entry_urls: tuple[str, ...] = (), voice: bool = False, owners: dict | None = None,
              memory=None, documents=None, link_ttl_minutes: float = 15.0,
              public_deadline: float | None = None):
    """INT01: ``owners`` = {label: owner_id} declared by the operator; the launch link belongs to the FIRST label,
    further links (e.g. "issa") are minted on demand (``app.issue_link(label)``) and never consumed by GET.
    ``memory``/``documents``: their routes exist only when given."""
    if public_deadline is not None and public_origin is None:
        raise ValueError("absolute deadline requires private-access origin")
    if public_origin is not None:
        from rightware.gui.recovery import absolute_expiry
        public_until = absolute_expiry(public_minutes or 0, public_deadline)
    else:
        public_until = None
    p = paths(runtime) if runtime is not None else paths()
    audit = AuditLog(p["audit"])
    adapters: dict = {}
    if adapter_factory is None:                   # OP01: every GUI model gets the host-built JARVIS persona
        from rightware.persona import RuntimeFacts, system_prompt
        tools = (("pesquisa e leitura de páginas web nas fontes autorizadas" + (f" ({tool_label})" if tool_label else ""),)
                 if tool_sites else ())

        def adapter_factory(m):
            prompt = system_prompt(RuntimeFacts(model=m, environment=environment, tools=tools, sites=tuple(tool_sites),
                                                search_template=tool_search_template,
                                                entry_urls=tuple(tool_entry_urls)))
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
    if voice:
        from rightware.gui import voice as V
        ok, why = V.available()
        if not ok:
            raise RuntimeError(f"VOZ_INDISPONIVEL: {why}")
    inner = inner if inner is not None else build_inner(models[0], p["home"], voice=voice)
    bridge.voice = voice
    if public_origin is not None:                 # B6 private access: single-use link, expiring sessions and access
        import time as _time
        if public_until <= _time.time():
            raise ValueError("private access expired during startup")
        first = next(iter(owners.items())) if owners else ("principal", None)
        auth = auth or LocalAuth(single_use=True, token_ttl=link_ttl_minutes * 60, session_ttl=public_minutes * 60,
                                 max_failures=20, owner=first[1], label=first[0])
    if auth is None:
        first = next(iter(owners.items())) if owners else ("principal", None)
        auth = LocalAuth(owner=first[1], label=first[0])
    from rightware.gui.policy import ALLOW, DOCUMENT_ALLOW, MEMORY_ALLOW, VOICE_ALLOW
    allow = {**ALLOW, **(VOICE_ALLOW if voice else {}), **(DOCUMENT_ALLOW if documents is not None else {}),
             **(MEMORY_ALLOW if memory is not None else {})}
    app = PolicyApp(inner=inner, bridge=bridge, static_dir=static_dir or p["static"], port=port, audit=audit,
                    auth=auth, public_origin=public_origin, public_until=public_until, allow=allow)
    bridge.memory, bridge.documents = memory, documents
    try:
        from rightware.gui import runtime as RT
        bridge.build = RT.build_stamp(runtime) if runtime is not None else RT.build_stamp()
    except Exception:
        bridge.build = None
    app.public_until = public_until
    app.session_url = auth.write_url(p["runtime"] / "session-url", port, base=public_origin)
    declared = dict(owners or {})

    def issue_link(label: str) -> str | None:
        """Mint a NEW single-use link for a declared owner label; written only to a 0600 file, never printed."""
        if label not in declared:
            return None
        tok = auth.issue(declared[label], label)
        return auth.write_url(p["runtime"] / f"session-url-{label}", port, base=public_origin, token=tok)
    app.issue_link = issue_link
    return app, bridge


def install_link_issuer(app, runtime: Path) -> None:
    """INT01: mint an additional owner link WITHOUT an HTTP admin route: a local operator writes the label to
    ``.runtime/gui/issue-request`` and sends SIGUSR1 (``python -m rightware.gui emitir-ligacao <label>``). The new link
    goes to ``.runtime/gui/session-url-<label>`` (0600); nothing is printed."""
    import os
    import signal
    req = runtime / "issue-request"
    pid = runtime / "server.pid"
    runtime.mkdir(parents=True, exist_ok=True)
    pid.write_text(str(os.getpid()))

    def handler(signum, frame):
        try:
            label = req.read_text(encoding="utf-8").strip()[:32]
            req.unlink()
        except OSError:
            return
        issue = getattr(app, "issue_link", None)
        url = issue(label) if callable(issue) else None
        (runtime / "issue-result").write_text("OK " + label if url else "RECUSADO " + label)
    signal.signal(signal.SIGUSR1, handler)


def serve(app, port: int) -> None:
    import uvicorn
    try:
        install_link_issuer(app, paths()["runtime"])
    except (ValueError, OSError):            # not the main thread (tests) or read-only runtime: no issuer
        pass
    uvicorn.run(app, host=LOOPBACK, port=port, log_level="info", access_log=False, proxy_headers=False,
                server_header=False, ws="none", lifespan="on")
