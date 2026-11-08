"""Read-only Windows readiness diagnostics for Jarvis do Issa.

Never installs, never launches applications, never records audio and never
creates the runtime profile. Prints one line per check and writes a sanitized
JSON report under .runtime/logs/ (no environment values, user or host names).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import platform
import sys
import urllib.request

from rightware import runtime

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


def sanitize(text: str) -> str:
    """Replace home path, user and computer names with placeholders."""
    text = str(text)
    for value, token in ((str(Path.home()), "<HOME>"),
                         (os.environ.get("USERNAME") or os.environ.get("USER"), "<USER>"),
                         (os.environ.get("COMPUTERNAME") or platform.node(), "<HOST>")):
        if value and len(value) > 1:
            text = text.replace(value, token)
    return text


def check_python():
    v = sys.version_info
    ok = (3, 10) <= (v.major, v.minor) <= (3, 13) and sys.maxsize > 2**32
    return (PASS if ok else FAIL), f"{platform.python_version()} {platform.architecture()[0]}"


def check_upstream():
    try:
        runtime.verify_source()
        return PASS, f"pin {runtime.PIN[:12]}"
    except Exception as exc:
        return FAIL, f"{exc} -> git submodule update --init --recursive"


def check_venv():
    if runtime.python_executable().is_file():
        return PASS, "upstream .venv present"
    return FAIL, "missing -> python jarvis.py setup --voice (needs authorization)"


def check_profile():
    import tomllib
    reference = tomllib.loads((runtime.ROOT / "configs/local.toml").read_text(encoding="utf-8"))
    path = runtime.STATE / "openjarvis" / "config.toml"
    if not path.is_file():
        return WARN, "runtime profile not created yet (created by the first setup/voice run)"
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    problems = []
    if config.get("engine", {}).get("default") != "ollama":
        problems.append("engine is not ollama")
    if config.get("engine", {}).get("ollama", {}).get("host") != "http://127.0.0.1:11434":
        problems.append("ollama host is not loopback")
    if config.get("analytics", {}).get("enabled", False):
        problems.append("analytics enabled")
    prompt = config.get("agent", {}).get("default_system_prompt", "")
    if "Issa" not in prompt or "RIGHTWARE" not in prompt:
        problems.append("identity prompt is not Jarvis do Issa/RIGHTWARE")
    if problems:
        return FAIL, "; ".join(problems)
    if prompt != reference["agent"]["default_system_prompt"]:
        return WARN, "identity prompt differs from configs/local.toml (older profile)"
    return PASS, f"local Ollama, analytics off, model {config['intelligence']['default_model']}"


def _ollama(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:11434" + path, timeout=5) as response:
        return json.load(response)


def check_ollama(model: str):
    try:
        version = _ollama("/api/version").get("version")
        names = {m.get("name") for m in _ollama("/api/tags").get("models", [])}
    except Exception as exc:
        return FAIL, f"not reachable on 127.0.0.1:11434 ({type(exc).__name__}) -> start: ollama serve"
    if model not in names:
        return FAIL, f"Ollama {version}; model {model} missing -> ollama pull {model}"
    return PASS, f"Ollama {version}; model {model} installed"


def check_stt_libraries():
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        return FAIL, f"{exc.name or exc} missing -> python jarvis.py setup --voice"
    except OSError as exc:  # DLL load failure on Windows
        return FAIL, f"DLL load failed ({exc}); install Microsoft Visual C++ Redistributable x64"
    return PASS, f"faster-whisper {faster_whisper.__version__ if hasattr(faster_whisper, '__version__') else ''}".strip()


def check_whisper_cache(size="small"):
    home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    if (home / "hub" / f"models--Systran--faster-whisper-{size}").is_dir():
        return PASS, f"Whisper '{size}' cached"
    return WARN, f"Whisper '{size}' not cached: first voice start downloads it from Hugging Face"


def check_microphone():
    try:
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        return FAIL, f"sounddevice unavailable ({type(exc).__name__}: {exc}) -> python jarvis.py setup --voice"
    try:
        device = sd.query_devices(kind="input")
    except Exception as exc:
        return FAIL, f"no default input device ({type(exc).__name__}); connect/enable a microphone"
    return PASS, f"default input: {device.get('name')} ({device.get('max_input_channels')} ch)"


def check_portuguese_voice():
    if os.name != "nt":
        return SKIP, "Windows SAPI only"
    from rightware.voice import SapiTTS, VoiceUnavailable
    try:
        voices = SapiTTS().voices()
    except VoiceUnavailable as exc:
        return FAIL, str(exc)
    pt = [f"{c} {n}" for c, n in voices if c.lower().startswith("pt-")]
    if pt:
        return PASS, "; ".join(pt)
    return WARN, (f"no Portuguese SAPI voice ({len(voices)} other voices). Settings > Time & "
                  "language > Language > add Portuguese (Portugal) with speech")


def check_action_executables():
    if os.name != "nt":
        return SKIP, "Windows only"
    from rightware.windows_actions import ACTIONS, WindowsActions
    acts = WindowsActions(authorized=False, audit_dir=runtime.STATE / "logs")
    missing = [a.executable for a in ACTIONS.values() if not Path(acts.executable_path(a)).is_file()]
    if missing:
        return FAIL, "missing " + ", ".join(missing)
    return PASS, "notepad.exe and calc.exe present (not launched)"


def run_checks(model: str | None = None):
    if model is None:
        model = "qwen3.5:2b"
        path = runtime.STATE / "openjarvis" / "config.toml"
        if path.is_file():
            import tomllib
            model = tomllib.loads(path.read_text(encoding="utf-8"))["intelligence"]["default_model"]
    checks = [
        ("python", check_python), ("upstream", check_upstream), ("venv", check_venv),
        ("profile", check_profile), ("ollama", lambda: check_ollama(model)),
        ("stt_libraries", check_stt_libraries), ("whisper_model", check_whisper_cache),
        ("microphone", check_microphone), ("portuguese_voice", check_portuguese_voice),
        ("action_executables", check_action_executables),
    ]
    results = []
    for name, fn in checks:
        try:
            status, detail = fn()
        except Exception as exc:
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        results.append({"check": name, "status": status, "detail": sanitize(detail)})
    return results


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Jarvis do Issa — diagnóstico só de leitura")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    results = run_checks(args.model)
    for r in results:
        print(f"[{r['status']}] {r['check']}: {r['detail']}")
    report = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
              "python": platform.python_version(), "results": results}
    try:
        import subprocess
        report["repo_sha"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=runtime.ROOT, text=True).strip()
    except Exception:
        report["repo_sha"] = None
    logs = runtime.STATE / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = logs / f"diagnostic-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"REPORT: {sanitize(out)}")
    failed = [r["check"] for r in results if r["status"] == FAIL]
    print("SUMMARY: " + ("READY FOR REAL VALIDATION" if not failed else "NOT READY: " + ", ".join(failed)))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
