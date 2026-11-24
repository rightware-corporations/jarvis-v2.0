"""WEB-01 W3.1: user-driven research (``pesquisa-livre``) on the SAME stack as W2/W3: EgressGuard + provider +
ResearchToolkit receipts + ControlPlane (single-use code bound to the exact question and plan) + HUD timeline.

Flow: question → host intent routing → local-model PLAN (validated) → operator types the code → executor runs the
plan's queries (≤ policy budgets; each query may be reformulated ONCE by a host rule when nothing relevant came back)
→ host picks relevant passages → local-model SYNTHESIS (validated: A integrity, B relevance, C quote/claim) → result.
The model never touches the network, the policy, the budgets or the verdict. Result states: RESPOSTA_FUNDAMENTADA
(all claims grounded), EXECUCAO_PARCIAL, RESULTADO_DESCONHECIDO (abstention) or TAREFA_CANCELADA — never
RESULTADO_VERIFICADO (semantic truth of free claims is not machine-verified here)."""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from rightware.control_plane import State, TaskOutcome
from rightware.web01 import grounding as G
from rightware.web01 import providers as PV
from rightware.web01.egress import EgressGuard, EgressPolicy, build_fetcher, guarantees
from rightware.web01.llm import ModelError, local_model
from rightware.web01.mission import MODE_LABEL, _Either
from rightware.web01.planner import Plan, content_terms, make_plan
from rightware.web01.research import ResearchToolkit

CAPABILITY = "pesquisa-livre"
ROOT = Path(__file__).resolve().parents[2]
RESULTS_PER_QUERY = 2
FINAL = {"GROUNDED": State.RESPOSTA_FUNDAMENTADA, "PARTIAL": State.EXECUCAO_PARCIAL,
         "ABSTAIN": State.RESULTADO_DESCONHECIDO}


def reformulate(query: str, question: str) -> str | None:
    """Host rule (deterministic): keep only the question's content terms, longest first; None if no change."""
    terms = sorted(dict.fromkeys(content_terms(question)), key=len, reverse=True)[:4]
    alt = " ".join(terms)
    return alt if alt and alt.lower() != query.lower() else None


class FreeResearchMission:
    capability = CAPABILITY
    accepts_params = True

    def __init__(self, policy: EgressPolicy | None = None, *, model: str = "qwen3.5:2b", model_call=None,
                 fetcher_factory=None, runtime: Path | None = None, clock=time.monotonic):
        self.policy = policy or EgressPolicy.load()
        public = self.policy.mode == "public"
        self.provider = PV.for_policy(self.policy)
        if fetcher_factory is None:                      # public: refused here unless the policy is W3-authorised
            build_fetcher(self.policy, allow_public=public)
            fetcher_factory = lambda stop: build_fetcher(self.policy, allow_public=public)  # noqa: E731
        self._fetcher_factory = fetcher_factory
        self.model = model
        self.call = model_call or local_model(model)
        self.runtime = runtime or ROOT / ".runtime" / "web01-missions"
        self.clock = clock
        self._cancel = threading.Event()
        self.description = (f"Pesquisa LIVRE de leitura — modo {MODE_LABEL[self.policy.mode]}. O JARVIS propõe um plano "
                            "(modelo local, validado pelo anfitrião); só executa depois do código do operador; responde "
                            "com citações validadas (integridade + relevância + correspondência). Afirmações NÃO são "
                            "verificadas semanticamente.")

    def plan(self, question: str) -> tuple[Plan, dict]:
        return make_plan(question, self.call, self.model)

    def cancel(self) -> bool:
        self._cancel.set()
        return True

    def run(self, cancelled: threading.Event, on_start=None, *, params: dict | None = None) -> TaskOutcome:
        started = self.clock()
        self._cancel.clear()
        stop = _Either(cancelled, self._cancel)
        if not params or not isinstance(params.get("plan"), Plan):
            raise PermissionError("pesquisa livre sem plano autorizado")
        plan: Plan = params["plan"]
        guard = EgressGuard(self.policy, self._fetcher_factory(stop), cancelled=stop, clock=self.clock)
        kit = ResearchToolkit(guard, self.provider)
        if on_start:
            on_start()
        steps, opened = [], set()
        for q in plan.queries:
            for attempt, query in enumerate((q, None)):
                if attempt == 1:
                    query = reformulate(q, plan.question)
                    if query is None:
                        break
                if stop.is_set() or guard.requests >= self.policy.max_requests_per_mission:
                    break
                r, results = kit.web_search_public(query)
                step = {"query": query, "reformulated": attempt == 1, "search_receipt": r["seq"],
                        "status": r["status"], "opened": []}
                for url in [u for u in results if u not in opened][:RESULTS_PER_QUERY]:
                    if stop.is_set() or guard.requests >= self.policy.max_requests_per_mission:
                        break
                    if not self.policy.host_allowed(urlsplit(url).hostname or ""):
                        continue
                    opened.add(url)
                    ro, page = kit.web_open_public(url)
                    rel = G.relevance(plan.question, page.text) if page is not None else 0.0
                    step["opened"].append({"receipt": ro["seq"], "url": url, "status": ro["status"],
                                           "relevance": round(rel, 2)})
                steps.append(step)
                if any(o["relevance"] >= G.MIN_RELEVANCE for o in step["opened"]):
                    break                                  # relevant evidence found: no reformulation
        ps = G.passages(plan.question, kit.receipts, kit.kept)
        synth = {"raw": "", "seconds": 0.0, "error": None}
        if stop.is_set():
            report = {"final": "CANCELLED", "claims": [], "dropped": [], "answer": "", "schema_valid": False}
        elif not ps:
            report = {"final": "ABSTAIN", "claims": [], "dropped": [], "answer": "", "schema_valid": None,
                      "model_status": None, "uncertainty": "Nenhuma passagem relevante nas fontes consultadas."}
        else:
            try:
                synth["raw"], synth["seconds"] = self.call(G.SYNTH_SYSTEM, G.synthesis_prompt(plan.question, ps))
            except ModelError as exc:
                synth["error"] = str(exc)
            report = G.validate(synth["raw"], plan.question, ps, kit.receipts, kit.kept, plan.subquestions)
        if stop.is_set():
            report["final"] = "CANCELLED"
        seconds = round(self.clock() - started, 2)
        state = State.TAREFA_CANCELADA if report["final"] == "CANCELLED" else FINAL[report["final"]]
        run_dir = self._evidence(plan, params, steps, ps, synth, report, kit, guard, seconds)
        sources = []
        for r in kit.receipts:
            if r["tool"] == "web_open_public" and r["status"] == "OK":
                sources.append({"seq": r["seq"], "url": r["final_url"], "fetched_at": r["fetched_at"],
                                "sha256": r["sha256"], "bytes": r["bytes"],
                                "supports": [f"C{i}" for i, c in enumerate(report["claims"], 1)
                                             if c["source"]["seq"] == r["seq"]]})
        lines = [f"Modo: {MODE_LABEL[self.policy.mode]}", f"Pergunta: {plan.question}",
                 f"Plano: {plan.source}; consultas: " + "; ".join(s["query"] + (" (reformulada)" if s["reformulated"]
                                                                                  else "") for s in steps)]
        for i, c in enumerate(report["claims"], 1):
            lines.append(f"C{i} [{c['status']}] {c['text']} — fonte #{c['source']['seq']}: «{c['quote']}» "
                         f"(relevância {c['checks']['B_relevance']}, suporte lexical {c['checks']['C_lexical_support']})")
        for dr in report.get("dropped", []):
            lines.append(f"REMOVIDA: {dr['claim'][:120]} — {dr['why']}")
        if report.get("conflicts"):
            lines.append("Conflitos indicados: " + "; ".join(report["conflicts"]))
        if report["final"] == "ABSTAIN":
            lines.append("O JARVIS abstém-se: evidência insuficiente nas fontes consultadas.")
        commentary = ""
        if report.get("answer"):
            commentary = (report["answer"] + ("\n\nIncerteza: " + report["uncertainty"] if report.get("uncertainty")
                                              else ""))
        return TaskOutcome(state=state, capability=CAPABILITY,
                           operational_state=f"FREE_RESEARCH_{report['final']}_{self.policy.mode.upper()}",
                           verified=False, changes=None,
                           objectives=tuple((f"C{i}", c["status"], c["source"]["seq"])
                                            for i, c in enumerate(report["claims"], 1)),
                           receipts_count=len(kit.receipts),
                           receipt_events=tuple((r["seq"], r["tool"], r["status"]) for r in kit.receipts),
                           halt_reason_code="CANCELLED" if state == State.TAREFA_CANCELADA else "NONE",
                           error_code="NONE" if not synth["error"] else "MODEL_UNAVAILABLE",
                           model_commentary_unverified=commentary, seconds=seconds, findings=tuple(lines),
                           sources=tuple(sources))

    def _evidence(self, plan, params, steps, ps, synth, report, kit, guard, seconds) -> Path | None:
        run = self.runtime / f"livre-{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"
        try:
            (run / "pages").mkdir(parents=True, exist_ok=False)
            (run / "receipts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kit.receipts))
            (run / "egress_audit.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in guard.audit))
            for seq, raw in kit.kept.items():
                (run / "pages" / f"{seq}.bin").write_bytes(raw)
            (run / "result.json").write_text(json.dumps({
                "question": plan.question, "plan": plan.as_dict(), "plan_meta": params.get("plan_meta"),
                "steps": steps, "passages": ps, "synthesis_raw": synth["raw"], "synthesis_seconds": synth["seconds"],
                "synthesis_error": synth["error"], "validation": report, "mode": self.policy.mode,
                "transport_guarantees": guarantees(self.policy), "model": self.model, "seconds": seconds,
                "requests": guard.requests,
                "refused": [a for a in guard.audit if a.get("decision") == "REFUSED"],
                "timing": {"plan_s": (params.get("plan_meta") or {}).get("seconds"),
                           "network_and_search_s": round(seconds - synth["seconds"], 2),
                           "synthesis_s": synth["seconds"], "mission_total_s": seconds}},
                ensure_ascii=False, indent=1))
        except OSError:
            return None
        self.last_run = run
        return run
