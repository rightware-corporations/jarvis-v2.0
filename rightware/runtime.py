"""Small, explicit launcher for the pinned OpenJarvis text baseline."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "openjarvis"
PIN = "f21d902f4d3bd7f0f3f138f1a4613019a394b549"
STATE = ROOT / ".runtime"


def child_environment(source=None):
    env = dict(os.environ if source is None else source)
    # httpx/urllib can inherit HTTP(S)_PROXY and ALL_PROXY even when the
    # Ollama address is loopback. Do not route local inference to a proxy.
    proxy_names = {"http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
                   "no_proxy"}
    for key in list(env):
        if (key.upper().endswith(("API_KEY", "AUTH_TOKEN"))
                or key.upper().startswith("ANTHROPIC_")
                or key.lower() in proxy_names):
            env.pop(key, None)
    env.update(OPENJARVIS_HOME=str(STATE / "openjarvis"),
               OLLAMA_HOST="http://127.0.0.1:11434", OLLAMA_NO_CLOUD="1",
               JARVIS_NUM_CTX="4096",
               NO_PROXY="127.0.0.1,localhost,::1",
               no_proxy="127.0.0.1,localhost,::1")
    return env


def verify_source():
    if not (UPSTREAM / "pyproject.toml").is_file():
        raise RuntimeError("Missing upstream. Run: python jarvis.py setup")
    sha = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if sha != PIN:
        raise RuntimeError(f"Upstream revision differs: {sha}; expected {PIN}")
    dirty = subprocess.check_output(["git", "-C", str(UPSTREAM), "status", "--porcelain", "--untracked-files=no"], text=True)
    if dirty.strip():
        raise RuntimeError("Upstream has tracked edits. Review them before launching.")


def prepare_config():
    path = STATE / "openjarvis" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        shutil.copyfile(ROOT / "configs" / "local.toml", path)
    # The initial launch profile deliberately accepts only local Ollama.
    import tomllib
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    if config.get("engine", {}).get("default") != "ollama":
        raise RuntimeError("This baseline requires engine.default = ollama")
    host = config.get("engine", {}).get("ollama", {}).get("host")
    if host != "http://127.0.0.1:11434":
        raise RuntimeError("This baseline requires local Ollama at 127.0.0.1:11434")
    if config.get("analytics", {}).get("enabled", False):
        raise RuntimeError("Disable analytics for the local baseline")
    return config


def executable():
    folder = UPSTREAM / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    return folder / ("jarvis.exe" if os.name == "nt" else "jarvis")


def run_logged(command, env=None):
    """Log setup/diagnostics, never interactive conversation text or env values."""
    logs = STATE / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with (logs / f"setup-{stamp}.log").open("w", encoding="utf-8") as log:
        log.write(json.dumps(command) + "\n")
        proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
        code = proc.wait()
    if code:
        raise RuntimeError(f"Command failed with exit {code}; see {logs}")


def sync_command(voice=False, kokoro=False):
    """Frozen upstream lockfile only; voice uses upstream extras (no new deps)."""
    cmd = ["uv", "sync", "--project", str(UPSTREAM), "--frozen", "--no-dev",
           "--python", sys.executable]
    if voice:
        cmd += ["--extra", "speech"]
    if kokoro:
        cmd += ["--extra", "voice"]
    return cmd


def setup(voice=False, kokoro=False):
    if not shutil.which("git") or not shutil.which("uv"):
        raise RuntimeError("Install Git and uv first. See README.md.")
    run_logged(["git", "submodule", "update", "--init", "--recursive"])
    verify_source()
    run_logged(sync_command(voice, kokoro))
    prepare_config()
    print("Core installed. Start Ollama, run 'ollama pull qwen3.5:2b', then python jarvis.py doctor")
    if voice:
        print("Voice extras installed (faster-whisper). Next: python jarvis.py voice")


def doctor():
    verify_source()
    config = prepare_config()
    if not executable().is_file():
        raise RuntimeError("Python dependencies missing. Run python jarvis.py setup")
    run_logged([str(executable()), "--help"], child_environment())
    # Direct localhost request; no dependency on proxy configuration.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:11434/api/tags", timeout=5) as response:
        data = json.load(response)
    wanted = config["intelligence"]["default_model"]
    if wanted not in {m.get("name") for m in data.get("models", [])}:
        raise RuntimeError(f"Model unavailable. Run: ollama pull {wanted}")
    print(f"READY: pinned upstream, CLI, local Ollama, model {wanted}. Inference/voice not validated by doctor.")


def python_executable():
    folder = UPSTREAM / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    return folder / ("python.exe" if os.name == "nt" else "python")


def voice_command(extra):
    """Voice loop runs in the upstream venv; flags are passed through."""
    return [str(python_executable()), "-m", "rightware.voice", *extra]


def voice_environment():
    """child_environment() plus UTF-8 stdio: on Windows a redirected/logged
    console would otherwise use cp1252 and fail on Portuguese text."""
    env = child_environment()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return env


def chat_command(model):
    if not model or any(x in model.lower() for x in ("cloud", "://")):
        raise RuntimeError("Choose a downloaded local model, not a cloud model")
    return [str(executable()), "--quiet", "chat", "-e", "ollama", "-m", model,
            "-a", "simple", "--num-ctx", "4096", "--skip-runtime-panel"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="RIGHTWARE Jarvis v2 — local text baseline")
    parser.add_argument("command", choices=("setup", "doctor", "chat", "voice", "diagnose"))
    parser.add_argument("--model", help="Installed local Ollama model (chat/voice)")
    parser.add_argument("--voice", action="store_true",
                        help="setup: also install local speech-to-text (upstream 'speech' extra)")
    parser.add_argument("--kokoro", action="store_true",
                        help="setup: also install Kokoro TTS (upstream 'voice' extra; large, needs espeak-ng)")
    args, extra = parser.parse_known_args(argv)
    if extra and args.command not in ("voice", "diagnose"):
        parser.error("unrecognized arguments: " + " ".join(extra))
    try:
        if args.command == "setup":
            setup(voice=args.voice or args.kokoro, kokoro=args.kokoro)
        elif args.command == "voice":
            verify_source()
            prepare_config()
            if not python_executable().is_file():
                raise RuntimeError("Run python jarvis.py setup --voice first")
            if args.model:
                extra = ["--model", args.model, *extra]
            return subprocess.call(voice_command(extra), cwd=ROOT, env=voice_environment())
        elif args.command == "diagnose":
            # Read-only. Prefer the upstream venv so speech libraries are checked.
            if args.model:
                extra = ["--model", args.model, *extra]
            if python_executable().is_file():
                return subprocess.call([str(python_executable()), "-m", "rightware.diagnose", *extra],
                                       cwd=ROOT, env=voice_environment())
            from rightware import diagnose
            return diagnose.main(extra)
        elif args.command == "doctor":
            doctor()
        else:
            verify_source()
            config = prepare_config()
            cmd = chat_command(args.model or config["intelligence"]["default_model"])
            if not executable().is_file():
                raise RuntimeError("Run python jarvis.py setup first")
            return subprocess.call(cmd, cwd=UPSTREAM, env=child_environment())
        return 0
    except KeyboardInterrupt:
        return 130
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
