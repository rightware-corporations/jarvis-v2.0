"""WEB-01 W2: supervised ``pesquisa-publica`` capability for the ControlPlane.

The executor is a DETERMINISTIC read plan defined by the host spec (no model decides anything in W2):
for each objective → ``web_search_public(query)`` → open up to N allowlisted results → stop as soon as the
verifier confirms the objective. Everything goes through ``EgressGuard`` (fixture mode: no socket). The result is
decided by ``research.verify`` from receipts + kept bytes; it lists the sources (URL, fetched_at, SHA-256, bytes)
that support each claim. Evidence goes to ``.runtime/web01-missions/<run>/`` (never committed).

Authorisation (single-use operator code), one-task-at-a-time, cancellation and the HUD timeline come from the
SAME ControlPlane as every other supervised capability.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from rightware.control_plane import State, TaskOutcome
from rightware.web01 import fixture as FX
from rightware.web01.egress import EgressGuard, EgressPolicy, build_fetcher
from rightware.web01.research import MissionSpec, ResearchToolkit, verify

CAPABILITY = "pesquisa-publica"
ROOT = Path(__file__).resolve().parents[2]
STATE_OF = {"RESEARCH_VERIFIED": State.RESULTADO_VERIFICADO, "RESEARCH_PARTIAL": State.EXECUCAO_PARCIAL,
            "RESEARCH_NOT_VERIFIED": State.RESULTADO_DESCONHECIDO,
            "RESEARCH_INVALID_EVIDENCE": State.EXECUCAO_FALHADA}


class ResearchMission:
    capability = CAPABILITY

    def __init__(self, policy: EgressPolicy | None = None, spec: MissionSpec | None = None, *, fetcher_factory=None,
                 runtime: Path | None = None, clock=time.monotonic):
        self.policy = policy or EgressPolicy.load()
        self.spec = spec or MissionSpec.load()
        if self.policy.mode == "fixture":
            self._search_url = FX.search_url
        else:                                    # W3: the public search endpoint is part of the authorisation
            raise NotImplementedError("WEB-01 W3 (rede pública) não está implementado nem autorizado")
        build_fetcher(self.policy)               # fail at host start-up, not mid-mission, if the mode is refused
        self._fetcher_factory = fetcher_factory or (lambda cancel: build_fetcher(self.policy))
        self.runtime = runtime or ROOT / ".runtime" / "web01-missions"
        self.clock = clock
        self._cancel = threading.Event()
        self.description = (f"Pesquisa pública de LEITURA (modo {self.policy.mode.upper()}: corpus local de ensaio, "
                            f"sem acesso à Internet). Pergunta: {self.spec.question} Cada leitura passa pela política "
                            "de egress e gera um recibo (URL, data, SHA-256, bytes); o resultado é decidido pelo "
                            "verificador RIGHTWARE só com fontes designadas.")

    def cancel(self) -> bool:
        self._cancel.set()
        return True

    def run(self, cancelled: threading.Event, on_start=None) -> TaskOutcome:
        started = self.clock()
        self._cancel.clear()
        stop = _Either(cancelled, self._cancel)
        guard = EgressGuard(self.policy, self._fetcher_factory(stop), cancelled=stop, clock=self.clock)
        kit = ResearchToolkit(guard, self._search_url)
        if on_start:
            on_start()
        done: set[str] = set()
        opened: set[str] = set()
        for obj in self.spec.objectives:
            if stop.is_set():
                break
            if obj.id in done:
                continue
            _, results = kit.web_search_public(obj.query)
            for url in results[: self.spec.max_open]:
                if stop.is_set() or obj.id in done:
                    break
                if url in opened or not self.policy.host_allowed(urlsplit(url).hostname or ""):
                    continue                     # off-allowlist results are never requested
                opened.add(url)
                kit.web_open_public(url)
                v = verify(kit.receipts, kit.kept, self.spec, self.policy.host_allowed)
                done = {oid for oid, st, _ in v["objectives"] if st == "VERIFIED"}
        v = verify(kit.receipts, kit.kept, self.spec, self.policy.host_allowed)
        seconds = round(self.clock() - started, 2)
        self._write_evidence(kit, guard, v, seconds)
        state = State.TAREFA_CANCELADA if stop.is_set() else STATE_OF[v["verdict"]]
        verified = state == State.RESULTADO_VERIFICADO
        lines = [f"Pergunta: {self.spec.question}"] + [
            f"{oid}: {v['claims'][oid]} (recibo #{seq})" if st == "VERIFIED" else f"{oid}: NÃO verificado"
            for oid, st, seq in v["objectives"]]
        return TaskOutcome(state=state, capability=CAPABILITY,
                           operational_state="CANCELLED" if stop.is_set() else v["verdict"] + f"_{self.policy.mode.upper()}",
                           verified=verified, changes=None, objectives=tuple(v["objectives"]),
                           receipts_count=len(kit.receipts),
                           receipt_events=tuple((r["seq"], r["tool"], r["status"]) for r in kit.receipts),
                           halt_reason_code="CANCELLED" if stop.is_set() else "NONE",
                           error_code="NONE" if not v["problems"] else "EVIDENCE_INVALID",
                           model_commentary_unverified="", seconds=seconds,
                           findings=tuple(lines), sources=tuple(v["sources"]))

    def _write_evidence(self, kit, guard, v, seconds) -> None:
        run = self.runtime / f"{self.spec.id}-{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"
        try:
            (run / "pages").mkdir(parents=True, exist_ok=False)
            (run / "receipts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kit.receipts))
            (run / "egress_audit.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in guard.audit))
            for seq, raw in kit.kept.items():
                (run / "pages" / f"{seq}.bin").write_bytes(raw)
            (run / "verification.json").write_text(json.dumps(
                {**v, "objectives": [list(o) for o in v["objectives"]], "mode": self.policy.mode,
                 "policy_version": self.policy.version, "seconds": seconds}, ensure_ascii=False, indent=1))
        except OSError:
            pass                                 # evidence is best-effort; the verdict never depends on it
        self.last_run = run


class _Either:
    """is_set() if either event is set; wait() for the fixture transport's cancellable delay."""

    def __init__(self, a: threading.Event, b: threading.Event):
        self.a, self.b = a, b

    def is_set(self) -> bool:
        return self.a.is_set() or self.b.is_set()

    def wait(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.is_set():
                return True
            time.sleep(min(0.05, max(0.0, end - time.monotonic())))
        return self.is_set()
